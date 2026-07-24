"""Tool execution engine.

Why this matters: agent responses from the LLM contain fenced JSON blocks
like

    ```tool
    {"name": "web.search", "arguments": {"query": "Blender 4.2 Python"}}
    ```

This module extracts those blocks, validates arguments against the
``tools/registry.py`` ToolDef schemas (if available), and runs each call
asynchronously with telemetry + DB logging.

Built-in handlers (always registered):
  * ``web.search``  — DuckDuckGo instant-answer (no API key)
  * ``file.read``   — read text files inside project root
  * ``file.write``  — write text files inside project root
  * ``math.eval``   — safe arithmetic evaluation of an expression string
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable, Dict, List, Optional, Any, Tuple

import httpx

from shared.a2a_protocol import A2AMessage, A2ABus
from shared.telemetry import telemetry, AgentSpan


ToolHandler = Callable[..., Awaitable[Dict[str, Any]]]


# ─── Default project sandbox ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─── ToolExecutor ────────────────────────────────────────────────
class ToolExecutor:
    """Dispatch ```tool``` blocks from LLM output to async handlers."""

    def __init__(self, db=None, bus: Optional[A2ABus] = None,
                 agent_capabilities: Optional[Callable[[str], Tuple[str, ...]]] = None) -> None:
        self.db = db
        self.bus = bus
        # Charter Article 4 enforcement: callable wired by the
        # conductor that maps agent_id → declared capability tuple.
        # ToolExecutor uses it to gate every tool call whose ToolDef
        # declares `requires_capability`. If None, capability-gated
        # tools are rejected fail-closed at execution time.
        self._agent_capabilities = agent_capabilities
        # Charter Article 4 — fail-loud sentinel. Probe the resolver
        # once at startup. If it returns a non-tuple-of-strings for
        # an agent it knows, the conductor is mis-wired and we want
        # this to surface NOW, not on the first tool call. A known
        # resolver may raise KeyError for the sentinel — that's
        # accepted (some resolvers don't accept arbitrary ids).
        if agent_capabilities is not None:
            try:
                _probe = agent_capabilities("__charter_4_sentinel__")
            except Exception:
                _probe = None
            if _probe is not None and (
                not isinstance(_probe, tuple)
                or not all(isinstance(c, str) for c in _probe)
            ):
                raise ValueError(
                    f"Charter Article 4 Violation: agent_capabilities "
                    f"resolver returned a non-tuple-of-strings shape "
                    f"({type(_probe).__name__}={_probe!r}). "
                    f"Wire as `lambda aid: tuple_of_strings`."
                )
        self._handlers: Dict[str, ToolHandler] = {}
        self._tool_defs: Dict[str, Any] = {}
        self._register_builtins()
        # Pull schema definitions from the registry if importable
        try:
            from tools.registry import TOOL_DEFINITIONS
            self._tool_defs = TOOL_DEFINITIONS
        except Exception:
            pass

    # ─── Registration ────────────────────────────────────────
    def register(self, name: str):
        """Decorator — register an async function as a tool handler."""
        def dec(fn: ToolHandler):
            self._handlers[name] = fn
            return fn
        return dec

    def register_handler(self, name: str, fn: ToolHandler) -> None:
        self._handlers[name] = fn

    def register_blender(self, blender_server) -> None:
        """Wire all ``blender.*`` handlers from a BlenderMCPServer instance."""
        for name in getattr(blender_server, "tools", {}).keys():
            handler = blender_server.tools[name]
            self.register_handler(name, handler)

    def register_mcp_server(self, server) -> None:
        """Wire all tools from any BaseMCPServer-style ambassador."""
        for name in getattr(server, "tools", {}).keys():
            self.register_handler(name, server.tools[name])

    # ─── Built-ins ───────────────────────────────────────────
    def _register_builtins(self) -> None:
        @self.register("web.search")
        async def web_search(query: str) -> Dict[str, Any]:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1"},
                )
            data = resp.json()
            return {
                "query": query,
                "abstract": data.get("AbstractText", "")[:500],
                "related": [t.get("Text", "") for t in data.get("RelatedTopics", [])[:5]],
            }

        @self.register("file.read")
        async def file_read(path: str) -> Dict[str, Any]:
            safe = _resolve_within_project(path)
            with open(safe, "r", encoding="utf-8") as f:
                content = f.read()
            return {"path": str(safe), "bytes": len(content), "content": content}

        @self.register("file.write")
        async def file_write(path: str, content: str) -> Dict[str, Any]:
            safe = _resolve_within_project(path)
            safe.parent.mkdir(parents=True, exist_ok=True)
            with open(safe, "w", encoding="utf-8") as f:
                f.write(content)
            return {"path": str(safe), "bytes": len(content)}

        @self.register("math.eval")
        async def math_eval(expression: str) -> Dict[str, Any]:
            # Very restricted: digits + math symbols only
            if not re.fullmatch(r"[\d\s\.\+\-\*\/\(\)eE]+", expression or ""):
                raise ValueError(f"Unsafe expression: {expression!r}")
            return {"expression": expression, "result": eval(expression, {"__builtins__": {}}, {})}

        # ── Artifact handoffs (Waggle-inspired) ─────────────
        @self.register("artifact.resolve")
        async def artifact_resolve(token: str) -> Dict[str, Any]:
            from shared.artifacts import get_artifact_store
            return get_artifact_store().resolve(token)

        @self.register("artifact.read")
        async def artifact_read(
            token: str,
            agent_id: str = "anonymous",
            offset: int = 0,
            limit: int = 4096,
        ) -> Dict[str, Any]:
            from shared.artifacts import get_artifact_store
            return get_artifact_store().read(
                token, agent_id=agent_id, offset=offset, limit=limit
            )

        @self.register("artifact.mint")
        async def artifact_mint(
            content: str,
            minted_by: str = "anonymous",
            summary: str = "",
            thread_id: str = "",
            kind: str = "text",
        ) -> Dict[str, Any]:
            from shared.artifacts import get_artifact_store
            store = get_artifact_store()
            if kind == "json":
                try:
                    obj = json.loads(content)
                except json.JSONDecodeError:
                    obj = content
                m = store.mint_json(
                    obj, minted_by=minted_by, summary=summary,
                    thread_id=thread_id or None,
                )
            else:
                m = store.mint_text(
                    content, minted_by=minted_by, summary=summary,
                    thread_id=thread_id or None, kind=kind,
                )
            return {
                "success": True,
                "token": m.token,
                "byte_size": m.byte_size,
                "summary": m.summary,
                "kind": m.kind,
            }

        @self.register("artifact.revoke")
        async def artifact_revoke(
            token: str, by_agent: str = "anonymous"
        ) -> Dict[str, Any]:
            from shared.artifacts import get_artifact_store
            return get_artifact_store().revoke(token, by_agent=by_agent)

    # ─── Validation ─────────────────────────────────────────
    # ─── Capability gate (Charter Article 4) ──────────────────────────────────
    async def _check_capability_gate(
        self,
        *,
        name: str,
        agent_id: str,
        args: Dict[str, Any],
        thread_id: str,
        span,
        tool_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Enforce Charter Article 4 before schema dispatch.

        Returns a result dict (already span-finished and witness-logged)
        if the call should be rejected; returns None if the gate passes.
        Backwards-compatible: tools without a ToolDef, or with empty
        `requires_capability`, are not gated here. Membership is exact
        set-semantics — a resolver returning anything other than a tuple
        of strings is UB by the type annotation.
        """
        tool_def = self._tool_defs.get(name)
        if tool_def is None:
            return None
        required = list(getattr(tool_def, "requires_capability", []) or [])
        if not required:
            return None

        if self._agent_capabilities is None:
            err = (
                f"Charter Article 4 Violation: tool '{name}' requires "
                f"capabilities {required!r} but ToolExecutor has no "
                f"agent_capabilities resolver wired."
            )
            span.finish(success=False, error=err)
            telemetry.record_span(span)
            if self.db is not None:
                try:
                    await self.db.log_tool_call(
                        thread_id=thread_id, agent_id=agent_id,
                        tool_name=name, input_params=args,
                        success=False, error_message=err, latency_ms=0,
                    )
                except Exception:
                    pass
            return {"id": tool_id, "name": name, "success": False,
                    "error": err, "latency_ms": 0}

        try:
            declared = set(self._agent_capabilities(agent_id) or ())
        except Exception as e:
            err = (
                f"Charter Article 4 Violation: agent_capabilities resolver "
                f"raised: {type(e).__name__}: {e}"
            )
            span.finish(success=False, error=err)
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": False,
                    "error": err}

        missing = [c for c in required if c not in declared]
        if missing:
            err = (
                f"Charter Article 4 Violation: agent '{agent_id}' lacks "
                f"required capability {missing!r} for tool '{name}' "
                f"(requires: {required!r}, declared: {sorted(declared)!r})."
            )
            span.finish(success=False, error=err)
            telemetry.record_span(span)
            if self.db is not None:
                try:
                    await self.db.log_tool_call(
                        thread_id=thread_id, agent_id=agent_id,
                        tool_name=name, input_params=args,
                        success=False, error_message=err, latency_ms=0,
                    )
                except Exception:
                    pass
            return {"id": tool_id, "name": name, "success": False,
                    "error": err, "latency_ms": 0}

        return None

    def validate_arguments(self, name: str, arguments: Dict[str, Any]) -> List[str]:
        """Return list of validation errors (empty list = OK)."""
        tool_def = self._tool_defs.get(name)
        if not tool_def:
            return []  # unknown tool: not our job to fail
        schema = getattr(tool_def, "parameters_schema", {})
        errors: List[str] = []

        for field in schema.get("required", []):
            if field not in arguments:
                errors.append(f"Missing required field: {field}")
        props = schema.get("properties", {})
        for key, val in arguments.items():
            prop = props.get(key)
            if not prop:
                continue
            if "enum" in prop and val not in prop["enum"]:
                errors.append(f"Invalid {key}: {val!r} (allowed: {prop['enum']})")
        return errors

    # ─── Parsing ────────────────────────────────────────────
    @staticmethod
    def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
        """Extract fenced tool-call blocks.

        Accepts both `````tool`` and `````json`` fences containing a JSON
        object with ``name`` and ``arguments`` (or ``parameters``).
        """
        pattern = re.compile(
            r"```(?:tool|json)?\s*\n(\{.*?\})\s*```",
            re.DOTALL,
        )
        calls: List[Dict[str, Any]] = []
        for m in pattern.finditer(text):
            raw = m.group(1).strip()
            # Tolerate single quotes
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    obj = json.loads(raw.replace("'", '"'))
                except json.JSONDecodeError:
                    continue
            if not isinstance(obj, dict) or "name" not in obj:
                continue
            args = obj.get("arguments") or obj.get("parameters") or obj.get("params") or {}
            calls.append({
                "id": obj.get("id", str(hash(raw) & 0xFFFFFFFF)),
                "name": obj["name"],
                "arguments": args,
            })
        return calls

    # ─── Execution ──────────────────────────────────────────
    async def execute(
        self,
        tool_call: Dict[str, Any],
        thread_id: str,
        agent_id: str,
    ) -> Dict[str, Any]:
        name = tool_call.get("name", "")
        args = tool_call.get("arguments") or {}
        tool_id = str(tool_call.get("id", ""))

        span: AgentSpan = telemetry.start_span(agent_id, f"tool:{name}")

        # Charter Article 4 — capability gate (empirically enforced).
        # Fail closed: if the tool declares required capabilities and
        # either no resolver is wired or the caller lacks them, we
        # refuse the call and log a witness entry before returning.
        capability_error = await self._check_capability_gate(
            name=name, agent_id=agent_id, args=args,
            thread_id=thread_id, span=span, tool_id=tool_id,
        )
        if capability_error is not None:
            return capability_error

        handler = self._handlers.get(name)
        if handler is None:
            span.finish(success=False, error=f"Unknown tool: {name}")
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": False,
                    "error": f"Unknown tool: {name}"}

        # Inject caller identity into artifact tools when omitted.
        if name == "artifact.read" and not args.get("agent_id"):
            args = {**args, "agent_id": agent_id}
        elif name == "artifact.mint" and (
            not args.get("minted_by") or args.get("minted_by") == "anonymous"
        ):
            args = {**args, "minted_by": agent_id, "thread_id": args.get("thread_id") or thread_id}
        elif name == "artifact.revoke" and (
            not args.get("by_agent") or args.get("by_agent") == "anonymous"
        ):
            args = {**args, "by_agent": agent_id}

        # Schema-driven validation (best-effort)
        validation_errors = self.validate_arguments(name, args)
        if validation_errors:
            msg = "; ".join(validation_errors)
            # Also include failure pattern hints if available
            tool_def = self._tool_defs.get(name)
            if tool_def and getattr(tool_def, "failure_patterns", None):
                msg += "\nHints:\n" + "\n".join(
                    f"  • {k}: {v}" for k, v in tool_def.failure_patterns.items()
                )
            span.finish(success=False, error=msg)
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": False, "error": msg}

        start = datetime.now()
        try:
            result = await asyncio.wait_for(handler(**args), timeout=30)
            latency_ms = int((datetime.now() - start).total_seconds() * 1000)
            # Compact bulky results into artifact:// tokens so handoffs stay small.
            # Never compact the artifact tools themselves.
            if not name.startswith("artifact."):
                try:
                    from shared.artifacts import get_artifact_store
                    result = get_artifact_store().compact_tool_result(
                        result,
                        agent_id=agent_id,
                        thread_id=thread_id,
                        tool_name=name,
                    )
                except Exception:
                    pass
            span.finish(success=True)
            telemetry.record_span(span)
            if self.db is not None:
                try:
                    await self.db.log_tool_call(
                        thread_id=thread_id,
                        agent_id=agent_id,
                        tool_name=name,
                        input_params=args,
                        output_result=result if isinstance(result, dict) else {"result": result},
                        success=True,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass
            return {"id": tool_id, "name": name, "success": True,
                    "result": result, "latency_ms": latency_ms}
        except asyncio.TimeoutError:
            latency_ms = int((datetime.now() - start).total_seconds() * 1000)
            err = f"Timeout after 30s"
            span.finish(success=False, error=err)
            telemetry.record_span(span)
            if self.db is not None:
                try:
                    await self.db.log_tool_call(
                        thread_id=thread_id, agent_id=agent_id, tool_name=name,
                        input_params=args, success=False, error_message=err,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass
            return {"id": tool_id, "name": name, "success": False, "error": err, "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((datetime.now() - start).total_seconds() * 1000)
            err = f"{type(e).__name__}: {e}"
            span.finish(success=False, error=err)
            telemetry.record_span(span)
            if self.db is not None:
                try:
                    await self.db.log_tool_call(
                        thread_id=thread_id, agent_id=agent_id, tool_name=name,
                        input_params=args, success=False, error_message=err,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass
            return {"id": tool_id, "name": name, "success": False, "error": err, "latency_ms": latency_ms}

    async def execute_all(
        self,
        text: str,
        thread_id: str,
        agent_id: str,
    ) -> List[Dict[str, Any]]:
        """Run every tool call found in ``text`` and return raw results."""
        results = []
        for call in self.parse_tool_calls(text):
            results.append(await self.execute(call, thread_id, agent_id))
        return results


# ─── Helpers ─────────────────────────────────────────────────────
def _resolve_within_project(path: str) -> Path:
    """Resolve ``path`` to an absolute Path, refusing path traversal
    outside the project root."""
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = p.resolve()
    try:
        p.relative_to(PROJECT_ROOT)
    except ValueError as e:
        raise PermissionError(
            f"Path escapes project root: {p} not under {PROJECT_ROOT}"
        ) from e
    return p
