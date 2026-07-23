"""Host-side client for a long-lived (persistent) Blender ambassador. — B0.

Instead of spawning a fresh ``blender --background --python-expr <script>`` per
tool call (which loses scene continuity — objects from call N vanish for call
N+1), this backend starts ONE long-lived Blender running the MCP server *inside*
Blender (``blender --background --python mcp_servers/blender_mcp_server.py``) and
talks to it over a line-delimited JSON pipe (stdin → request, stdout → response),
exactly as docs/blender.md describes.

Charter note (Article 4.2 embassy isolation): the conductor reaches Blender
ONLY through this pipe. It gains no host-filesystem rights beyond launching the
process. The Article 4.3 sandbox stays inside the ambassador and is enforced
server-side.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import Optional


_SERVER = str(Path(__file__).resolve().parent / "blender_mcp_server.py")

# Used only if the registry can't be imported to enumerate blender.* tools.
_FALLBACK_TOOLS = (
    "blender.get_scene_info", "blender.create_object", "blender.modify_object",
    "blender.set_material", "blender.render", "blender.get_viewport",
    "blender.execute_script", "blender.undo",
)


class _PipeClosed(Exception):
    """Raised when the Blender stdout pipe closes (process exited/crashed)."""


def _blender_tool_names() -> list:
    try:
        from tools.registry import TOOL_DEFINITIONS
        names = [n for n in TOOL_DEFINITIONS if n.startswith("blender.")]
        if names:
            return names
    except Exception:
        pass
    return list(_FALLBACK_TOOLS)


def _default_command() -> list:
    override = os.environ.get("BLENDER_MCP_CMD")
    if override:
        return shlex.split(override)
    blender = os.environ.get("BLENDER_PATH", "blender")
    return [blender, "--background", "--python", _SERVER]


class PersistentBlenderBackend:
    """One long-lived Blender process reached over a JSON stdio pipe.

    Exposes a ``tools`` dict (name → async callable) so it drops straight into
    ``ToolExecutor.register_mcp_server`` / ``register_blender`` exactly like an
    in-process ``BlenderMCPServer`` would.
    """

    def __init__(self, command: Optional[list] = None, *,
                 call_timeout: float = 60.0):
        self.command = list(command) if command else _default_command()
        self.call_timeout = call_timeout
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._id = 0
        self.tools = {name: self._make_tool(name) for name in _blender_tool_names()}

    # ── lifecycle ─────────────────────────────────────────────────────────
    def health(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.health():
            return
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # stderr inherits: Blender logs + the ambassador's Article 4.3
            # witness log stay visible to the operator.
        )

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        try:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()

    async def _ensure(self) -> None:
        if not self.health():
            await self.start()

    # ── request / response (one request → one response, serialised) ────────
    async def call(self, name: str, arguments: Optional[dict] = None,
                   timeout: Optional[float] = None) -> dict:
        """Send one tool request, return its result dict.

        On a dead/broken pipe the process is restarted once and the call is
        retried; a second failure returns a structured error (never raises).
        """
        timeout = timeout or self.call_timeout
        args = arguments or {}
        async with self._lock:
            for attempt in (1, 2):
                try:
                    return await self._call_once(name, args, timeout)
                except FileNotFoundError as e:
                    # Missing Blender binary — retrying won't help.
                    return {"success": False,
                            "error": f"Blender not found: {e}. Set BLENDER_PATH "
                                     f"or install Blender."}
                except (_PipeClosed, BrokenPipeError, ConnectionResetError) as e:
                    await self.stop()
                    if attempt == 2:
                        return {"success": False,
                                "error": f"Blender pipe unavailable: {e}"}
                    # else: loop; _ensure() restarts Blender on retry

    async def _call_once(self, name: str, arguments: dict, timeout: float) -> dict:
        await self._ensure()
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise _PipeClosed("Blender process not started")
        self._id += 1
        rid = str(self._id)
        payload = json.dumps({"id": rid, "name": name, "arguments": arguments}) + "\n"
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()
        try:
            return await asyncio.wait_for(self._read_response(proc, rid), timeout=timeout)
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Blender pipe timeout after {timeout:.0f}s"}

    async def _read_response(self, proc, rid: str) -> dict:
        # Skip Blender's startup banner and any non-JSON stdout noise until the
        # matching JSON response arrives.
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                raise _PipeClosed("Blender stdout closed (process exited)")
            text = raw.decode(errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue  # banner / log line — not our response
            if not isinstance(msg, dict):
                continue
            if "id" in msg and msg["id"] != rid:
                continue  # stale/mismatched response
            if msg.get("success"):
                return msg.get("result", {}) or {}
            return {"success": False, "error": msg.get("error", "unknown error")}

    def _make_tool(self, name: str):
        async def _tool(**kwargs):
            return await self.call(name, kwargs)
        _tool.__name__ = name.replace(".", "_")
        _tool.__doc__ = f"Persistent Blender tool: {name}"
        return _tool


# ── factory / mode switch ───────────────────────────────────────────────────
_SINGLETON = None


def create_blender_ambassador(force: bool = False):
    """Return the Blender ambassador for the current ``BLENDER_MCP_MODE``.

    * ``persistent`` (default) — a shared :class:`PersistentBlenderBackend`
      (one long-lived Blender for the whole process, so tool calls and scene
      snapshots share continuity).
    * ``oneshot`` — the legacy in-host ``BlenderMCPServer`` that spawns a fresh
      Blender per call (rollback path).

    Cached as a process singleton so the conductor and the Blender agent share
    the same instance/process. Pass ``force=True`` to rebuild (mainly tests).
    """
    global _SINGLETON
    if _SINGLETON is not None and not force:
        return _SINGLETON
    mode = os.environ.get("BLENDER_MCP_MODE", "persistent").strip().lower()
    if mode == "oneshot":
        from mcp_servers.blender_mcp_server import BlenderMCPServer
        _SINGLETON = BlenderMCPServer()
    else:
        _SINGLETON = PersistentBlenderBackend()
    return _SINGLETON
