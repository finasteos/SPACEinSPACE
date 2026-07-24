"""Artifact handoffs — Waggle-inspired refs for the A2A bus.

Problem: agents paste whole tool payloads (base64 images, Meshy task JSON,
scene dumps) into the next agent's context. That burns tokens and loses
attribution.

Solution (SPACE-shaped, not a waggle fork):
  * Mint a short token ``artifact://space/<id>`` (~28 bytes).
  * The token travels on the bus; the bytes stay in ``assets/artifacts/``.
  * ``resolve`` returns attribution + summary (never the payload).
  * ``read`` returns a budgeted slice and appends a read receipt.
  * ``revoke`` / ``supersede`` keep lineage honest.

Charter notes:
  * Witnessed (Article 3): every mint/read/revoke is logged on the manifest.
  * Bounded (Article 4): read has a hard byte budget; paths stay under
    ``assets/artifacts/`` (Article 4.4 spirit).
  * The token never auto-expands into message content.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


TOKEN_RE = re.compile(r"artifact://space/([a-f0-9]{12})")
TOKEN_PREFIX = "artifact://space/"
DEFAULT_READ_BUDGET = 4096
MAX_READ_BUDGET = 65536
COMPACT_THRESHOLD_BYTES = 2048
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_ROOT = PROJECT_ROOT / "assets" / "artifacts"


def make_token(artifact_id: str) -> str:
    return f"{TOKEN_PREFIX}{artifact_id}"


def parse_token(token: str) -> Optional[str]:
    if not isinstance(token, str):
        return None
    token = token.strip()
    m = TOKEN_RE.fullmatch(token) or TOKEN_RE.search(token)
    if not m:
        # also accept bare id
        if re.fullmatch(r"[a-f0-9]{12}", token):
            return token
        return None
    return m.group(1)


def extract_tokens(text: str) -> List[str]:
    if not text:
        return []
    seen = set()
    out: List[str] = []
    for i in TOKEN_RE.findall(text):
        tok = make_token(i)
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


@dataclass
class ReadReceipt:
    agent_id: str
    at: str
    offset: int
    bytes_returned: int


@dataclass
class ArtifactManifest:
    id: str
    token: str
    kind: str  # text | json | image | model | blob
    media_type: str
    minted_by: str
    thread_id: Optional[str]
    parent_id: Optional[str]
    created_at: str
    byte_size: int
    sha256: str
    summary: str
    path: str  # relative to project root
    revoked: bool = False
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    source_tool: Optional[str] = None
    reads: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArtifactStore:
    """Filesystem-backed artifact store (one process / conductor instance)."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else STORE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _paths(self, artifact_id: str) -> Tuple[Path, Path]:
        return (
            self.root / f"{artifact_id}.bin",
            self.root / f"{artifact_id}.json",
        )

    def _write_manifest(self, manifest: ArtifactManifest) -> None:
        _, meta_path = self._paths(manifest.id)
        meta_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_manifest(self, artifact_id: str) -> Optional[ArtifactManifest]:
        _, meta_path = self._paths(artifact_id)
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return ArtifactManifest(**data)

    def mint(
        self,
        *,
        payload: bytes,
        kind: str,
        media_type: str,
        minted_by: str,
        summary: str,
        thread_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        source_tool: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        supersedes: Optional[str] = None,
    ) -> ArtifactManifest:
        if kind not in ("text", "json", "image", "model", "blob"):
            raise ValueError(f"invalid kind: {kind}")
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")
        artifact_id = uuid4().hex[:12]
        token = make_token(artifact_id)
        digest = hashlib.sha256(payload).hexdigest()
        bin_path, _ = self._paths(artifact_id)
        try:
            rel = str(bin_path.relative_to(PROJECT_ROOT))
        except ValueError:
            # Tests / alternate roots may live outside the project tree.
            rel = str(bin_path)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            bin_path.write_bytes(bytes(payload))
            manifest = ArtifactManifest(
                id=artifact_id,
                token=token,
                kind=kind,
                media_type=media_type,
                minted_by=minted_by,
                thread_id=thread_id,
                parent_id=parent_id,
                created_at=now,
                byte_size=len(payload),
                sha256=digest,
                summary=(summary or "")[:500],
                path=rel,
                source_tool=source_tool,
                supersedes=supersedes,
                metadata=metadata or {},
            )
            self._write_manifest(manifest)
            if supersedes:
                parent = self._load_manifest(parse_token(supersedes) or supersedes)
                if parent and not parent.revoked:
                    parent.superseded_by = token
                    self._write_manifest(parent)
        return manifest

    def mint_text(
        self,
        text: str,
        *,
        minted_by: str,
        summary: str = "",
        kind: str = "text",
        media_type: str = "text/plain",
        **kwargs,
    ) -> ArtifactManifest:
        return self.mint(
            payload=text.encode("utf-8"),
            kind=kind,
            media_type=media_type,
            minted_by=minted_by,
            summary=summary or text[:200],
            **kwargs,
        )

    def mint_json(
        self,
        obj: Any,
        *,
        minted_by: str,
        summary: str = "",
        **kwargs,
    ) -> ArtifactManifest:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
        return self.mint(
            payload=raw.encode("utf-8"),
            kind="json",
            media_type="application/json",
            minted_by=minted_by,
            summary=summary or raw[:200],
            **kwargs,
        )

    def mint_file(
        self,
        path: Path,
        *,
        minted_by: str,
        kind: str = "blob",
        media_type: str = "application/octet-stream",
        summary: str = "",
        **kwargs,
    ) -> ArtifactManifest:
        path = Path(path)
        payload = path.read_bytes()
        return self.mint(
            payload=payload,
            kind=kind,
            media_type=media_type,
            minted_by=minted_by,
            summary=summary or f"file:{path.name} ({len(payload)} bytes)",
            metadata={"source_path": str(path)},
            **kwargs,
        )

    def resolve(self, token: str) -> Dict[str, Any]:
        """Attribution + summary only — never the payload."""
        artifact_id = parse_token(token)
        if not artifact_id:
            return {"success": False, "error": f"invalid token: {token!r}"}
        manifest = self._load_manifest(artifact_id)
        if manifest is None:
            return {"success": False, "error": f"unknown artifact: {token}"}
        return {
            "success": True,
            "token": manifest.token,
            "kind": manifest.kind,
            "media_type": manifest.media_type,
            "minted_by": manifest.minted_by,
            "thread_id": manifest.thread_id,
            "parent_id": manifest.parent_id,
            "created_at": manifest.created_at,
            "byte_size": manifest.byte_size,
            "sha256": manifest.sha256,
            "summary": manifest.summary,
            "revoked": manifest.revoked,
            "supersedes": manifest.supersedes,
            "superseded_by": manifest.superseded_by,
            "source_tool": manifest.source_tool,
            "read_count": len(manifest.reads),
            "metadata": manifest.metadata,
        }

    def read(
        self,
        token: str,
        *,
        agent_id: str,
        offset: int = 0,
        limit: int = DEFAULT_READ_BUDGET,
    ) -> Dict[str, Any]:
        """Budgeted payload slice + read receipt."""
        artifact_id = parse_token(token)
        if not artifact_id:
            return {"success": False, "error": f"invalid token: {token!r}"}
        if offset < 0:
            return {"success": False, "error": "offset must be >= 0"}
        limit = min(max(1, int(limit)), MAX_READ_BUDGET)

        with self._lock:
            manifest = self._load_manifest(artifact_id)
            if manifest is None:
                return {"success": False, "error": f"unknown artifact: {token}"}
            if manifest.revoked:
                return {"success": False, "error": "artifact revoked", "token": token}
            bin_path, _ = self._paths(artifact_id)
            if not bin_path.exists():
                return {"success": False, "error": "payload missing"}
            data = bin_path.read_bytes()
            chunk = data[offset: offset + limit]
            receipt = ReadReceipt(
                agent_id=agent_id,
                at=datetime.now(timezone.utc).isoformat(),
                offset=offset,
                bytes_returned=len(chunk),
            )
            manifest.reads.append(asdict(receipt))
            self._write_manifest(manifest)

        # Prefer utf-8 text when kind is text/json
        text_out: Optional[str] = None
        if manifest.kind in ("text", "json"):
            try:
                text_out = chunk.decode("utf-8")
            except UnicodeDecodeError:
                text_out = None

        return {
            "success": True,
            "token": manifest.token,
            "offset": offset,
            "limit": limit,
            "bytes_returned": len(chunk),
            "byte_size": manifest.byte_size,
            "eof": offset + len(chunk) >= manifest.byte_size,
            "text": text_out,
            "base64": None if text_out is not None else
                __import__("base64").b64encode(chunk).decode("ascii"),
            "kind": manifest.kind,
            "media_type": manifest.media_type,
        }

    def revoke(self, token: str, *, by_agent: str) -> Dict[str, Any]:
        artifact_id = parse_token(token)
        if not artifact_id:
            return {"success": False, "error": f"invalid token: {token!r}"}
        with self._lock:
            manifest = self._load_manifest(artifact_id)
            if manifest is None:
                return {"success": False, "error": f"unknown artifact: {token}"}
            manifest.revoked = True
            manifest.metadata["revoked_by"] = by_agent
            manifest.metadata["revoked_at"] = datetime.now(timezone.utc).isoformat()
            self._write_manifest(manifest)
        return {"success": True, "token": manifest.token, "revoked": True}

    def compact_tool_result(
        self,
        result: Any,
        *,
        agent_id: str,
        thread_id: str,
        tool_name: str,
    ) -> Any:
        """Replace large / bulky tool payloads with artifact tokens.

        Rules:
          * ``image_base64`` → image artifact; field becomes token
          * dict/list whose JSON exceeds COMPACT_THRESHOLD → json artifact
          * ``saved_to`` file path is recorded on metadata (file already on disk)
        """
        if not isinstance(result, dict):
            raw = json.dumps(result, default=str)
            if len(raw.encode("utf-8")) < COMPACT_THRESHOLD_BYTES:
                return result
            m = self.mint_json(
                result,
                minted_by=agent_id,
                thread_id=thread_id,
                source_tool=tool_name,
                summary=f"tool:{tool_name} compact",
            )
            return {
                "artifact": m.token,
                "summary": m.summary,
                "kind": m.kind,
                "byte_size": m.byte_size,
                "compacted": True,
            }

        out = dict(result)
        # PixelLab / vision-style base64
        if isinstance(out.get("image_base64"), str) and len(out["image_base64"]) > 200:
            import base64
            try:
                raw = base64.b64decode(out["image_base64"])
            except Exception:
                raw = out["image_base64"].encode("utf-8")
            m = self.mint(
                payload=raw,
                kind="image",
                media_type="image/png",
                minted_by=agent_id,
                thread_id=thread_id,
                source_tool=tool_name,
                summary=out.get("description") or f"image from {tool_name}",
                metadata={"saved_to": out.get("saved_to")},
            )
            out.pop("image_base64", None)
            out["artifact"] = m.token
            out["artifact_kind"] = "image"
            out["compacted"] = True

        # Meshy / large nested task blobs
        encoded = json.dumps(out, default=str).encode("utf-8")
        if len(encoded) >= COMPACT_THRESHOLD_BYTES and "artifact" not in out:
            m = self.mint_json(
                out,
                minted_by=agent_id,
                thread_id=thread_id,
                source_tool=tool_name,
                summary=f"tool:{tool_name} ({len(encoded)} bytes)",
            )
            return {
                "artifact": m.token,
                "summary": m.summary,
                "kind": "json",
                "byte_size": m.byte_size,
                "compacted": True,
                # keep tiny success/task_id hints if present
                "success": out.get("success"),
                "task_id": out.get("task_id"),
                "saved_to": out.get("saved_to"),
            }
        return out


# Process-wide default store (conductor / tools share one root).
_default_store: Optional[ArtifactStore] = None


def get_artifact_store() -> ArtifactStore:
    global _default_store
    if _default_store is None:
        _default_store = ArtifactStore()
    return _default_store


def handoff_line(token: str, hint: str = "") -> str:
    """One-line bus content: token travels; payload does not."""
    hint = (hint or "").strip()
    if hint:
        return f"{token}  # {hint[:120]}"
    return token
