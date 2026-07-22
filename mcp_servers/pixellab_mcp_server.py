"""PixelLab MCP ambassador — pixel-art generation embassy.

Calls PixelLab REST (`https://api.pixellab.ai/v1`) directly so agents do not
depend on spawning the Node MCP package. Tool names mirror pixellab-mcp.

Without ``PIXELLAB_API_KEY`` / ``PIXELLAB_SECRET`` the ambassador runs in
stub mode (deterministic fake images) so the conductor stays testable offline.

Charter: declarative only (4.2), sandbox policy logged at startup (4.3),
asset writes confined under ``assets/pixellab/`` (4.4).
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
from pathlib import Path
from typing import Optional

import httpx

from mcp_servers.base_mcp_server import BaseMCPServer

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ASSETS_ROOT = Path("assets/pixellab")
# 1x1 transparent PNG
_STUB_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class PixelLabMCPServer(BaseMCPServer):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__("pixellab")
        self.api_key = (
            api_key
            or os.getenv("PIXELLAB_API_KEY")
            or os.getenv("PIXELLAB_SECRET")
            or ""
        ).strip()
        self.base_url = (
            base_url or os.getenv("PIXELLAB_BASE_URL") or "https://api.pixellab.ai/v1"
        ).rstrip("/")
        self._http = http_client
        self.stub_mode = not bool(self.api_key)
        self._setup_tools()
        self._log_sandbox_policy()

    def _log_sandbox_policy(self) -> None:
        mode = "stub (no API key)" if self.stub_mode else "live HTTP"
        self.logger.info(
            "PixelLab ambassador online — mode=%s base=%s (Article 4.2)",
            mode, self.base_url,
        )
        self.logger.info(
            "Article 4.4 — optional save_to confined under %s/", ASSETS_ROOT
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        return httpx.AsyncClient(timeout=120.0)

    def _safe_save_path(self, save_to: Optional[str]) -> Optional[Path]:
        if not save_to or not isinstance(save_to, str):
            return None
        ref = save_to.strip()
        if not ref or ref.startswith(("/", "~")) or ".." in ref or "\\" in ref:
            return None
        # Only the basename is used — always under assets/pixellab
        name = Path(ref).name
        if not name or Path(name).suffix.lower() not in (
            ".png", ".webp", ".gif", ".jpg", ".jpeg",
        ):
            return None
        ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
        return ASSETS_ROOT / name

    async def _post(self, path: str, body: dict) -> dict:
        client = await self._client()
        owns = self._http is None
        try:
            resp = await client.post(
                f"{self.base_url}{path}", headers=self._headers(), json=body
            )
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }
            return {"success": True, "data": resp.json()}
        finally:
            if owns:
                await client.aclose()

    async def _get(self, path: str) -> dict:
        client = await self._client()
        owns = self._http is None
        try:
            resp = await client.get(
                f"{self.base_url}{path}", headers=self._headers()
            )
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }
            return {"success": True, "data": resp.json()}
        finally:
            if owns:
                await client.aclose()

    def _maybe_save(self, image_b64: Optional[str], save_to: Optional[str]) -> Optional[str]:
        if not image_b64 or not save_to:
            return None
        path = self._safe_save_path(save_to)
        if path is None:
            return None
        raw = image_b64
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        path.write_bytes(base64.b64decode(raw))
        return str(path)

    def _setup_tools(self) -> None:
        @self.register("pixellab.generate_pixflux")
        async def generate_pixflux(
            description: str,
            width: int = 64,
            height: int = 64,
            negative_description: str = "",
            text_guidance_scale: float = 8.0,
            no_background: bool = False,
            outline: Optional[str] = None,
            shading: Optional[str] = None,
            detail: Optional[str] = None,
            save_to: Optional[str] = None,
        ):
            """Generate pixel art from text (Pixflux)."""
            if not description or not isinstance(description, str):
                return {"success": False, "error": "description required"}
            if width * height > 256 * 256:
                return {"success": False, "error": "max resolution 256x256"}
            if self.stub_mode:
                saved = None
                if save_to:
                    path = self._safe_save_path(save_to)
                    if path:
                        path.write_bytes(_STUB_PNG)
                        saved = str(path)
                return {
                    "success": True,
                    "stub": True,
                    "description": description,
                    "width": width,
                    "height": height,
                    "image_base64": base64.b64encode(_STUB_PNG).decode(),
                    "saved_to": saved,
                }
            body = {
                "description": description,
                "image_size": {"width": width, "height": height},
                "negative_description": negative_description or None,
                "text_guidance_scale": text_guidance_scale,
                "no_background": no_background,
                "outline": outline,
                "shading": shading,
                "detail": detail,
            }
            result = await self._post("/generate-image-pixflux", body)
            if not result.get("success"):
                return result
            data = result["data"]
            image = data.get("image") or {}
            b64 = image.get("base64") if isinstance(image, dict) else None
            if b64 is None and isinstance(image, str):
                b64 = image
            saved = self._maybe_save(b64, save_to)
            return {
                "success": True,
                "usage": data.get("usage"),
                "image_base64": b64,
                "saved_to": saved,
            }

        @self.register("pixellab.get_balance")
        async def get_balance():
            """Check PixelLab credit balance."""
            if self.stub_mode:
                return {"success": True, "stub": True, "type": "usd", "usd": 0.0}
            result = await self._get("/balance")
            if not result.get("success"):
                return result
            data = result["data"]
            return {"success": True, **data}

        @self.register("pixellab.rotate")
        async def rotate(
            image_base64: str,
            to_direction: str,
            from_direction: Optional[str] = None,
            width: int = 64,
            height: int = 64,
            save_to: Optional[str] = None,
        ):
            """Rotate a character sprite to another cardinal direction."""
            if not image_base64:
                return {"success": False, "error": "image_base64 required"}
            allowed = {"south", "east", "north", "west",
                       "south-east", "south-west", "north-east", "north-west"}
            if to_direction not in allowed:
                return {"success": False, "error": f"to_direction must be one of {sorted(allowed)}"}
            if self.stub_mode:
                saved = None
                if save_to:
                    path = self._safe_save_path(save_to)
                    if path:
                        path.write_bytes(_STUB_PNG)
                        saved = str(path)
                return {
                    "success": True,
                    "stub": True,
                    "to_direction": to_direction,
                    "image_base64": base64.b64encode(_STUB_PNG).decode(),
                    "saved_to": saved,
                }
            body = {
                "image": {"type": "base64", "base64": image_base64},
                "to_direction": to_direction,
                "from_direction": from_direction,
                "image_size": {"width": width, "height": height},
            }
            result = await self._post("/rotate", body)
            if not result.get("success"):
                return result
            data = result["data"]
            image = data.get("image") or {}
            b64 = image.get("base64") if isinstance(image, dict) else image
            saved = self._maybe_save(b64 if isinstance(b64, str) else None, save_to)
            return {"success": True, "image_base64": b64, "saved_to": saved, "usage": data.get("usage")}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = PixelLabMCPServer()
    asyncio.run(server.run_stdio())
