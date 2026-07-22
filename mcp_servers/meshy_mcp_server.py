"""Meshy MCP ambassador — text/image-to-3D embassy.

Calls Meshy OpenAPI (`https://api.meshy.ai/openapi/`) directly. Tool surface
covers the core async task workflow used by gamedev-mcp-hub / official MCP:

  create → poll/get → (optional) wait until SUCCEEDED

Without ``MESHY_API_KEY`` the ambassador runs in stub mode so tests and local
conductor boots stay offline-friendly. Live calls spend credits — agents must
prefer ``mode=preview`` first.

Charter: declarative only (4.2), cost/sandbox policy logged at startup (4.3),
downloads confined under ``assets/meshy/`` (4.4).
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx

from mcp_servers.base_mcp_server import BaseMCPServer

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ASSETS_ROOT = Path("assets/meshy")
ALLOWED_MODES = ("preview", "refine")
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED"}


class MeshyMCPServer(BaseMCPServer):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__("meshy")
        self.api_key = (api_key or os.getenv("MESHY_API_KEY") or "").strip()
        self.base_url = (
            base_url or os.getenv("MESHY_BASE_URL") or "https://api.meshy.ai/openapi"
        ).rstrip("/")
        self._http = http_client
        self.stub_mode = not bool(self.api_key)
        self._stub_tasks: dict[str, dict] = {}
        self._setup_tools()
        self._log_sandbox_policy()

    def _log_sandbox_policy(self) -> None:
        mode = "stub (no API key)" if self.stub_mode else "live HTTP"
        self.logger.info(
            "Meshy ambassador online — mode=%s base=%s (Article 4.2)",
            mode, self.base_url,
        )
        self.logger.info(
            "Cost fence: prefer mode=preview before refine; "
            "wait_* polls with explicit timeout (Article 4.3 spirit)."
        )
        self.logger.info(
            "Article 4.4 — downloads confined under %s/", ASSETS_ROOT
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

    async def _request(self, method: str, path: str, json_body: Optional[dict] = None) -> dict:
        client = await self._client()
        owns = self._http is None
        try:
            resp = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json_body,
            )
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }
            # Some create endpoints return plain JSON {"result": "task_id"}
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            return {"success": True, "data": data}
        finally:
            if owns:
                await client.aclose()

    def _safe_filename(self, name: str, ext: str = ".glb") -> Optional[Path]:
        stem = Path(name).stem
        if not SAFE_ID_RE.match(stem):
            return None
        ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
        return ASSETS_ROOT / f"{stem}{ext}"

    def _setup_tools(self) -> None:
        @self.register("meshy.create_text_to_3d")
        async def create_text_to_3d(
            prompt: str,
            mode: str = "preview",
            preview_task_id: Optional[str] = None,
            should_remesh: bool = True,
            enable_pbr: bool = False,
            ai_model: str = "latest",
        ):
            """Create a text-to-3D task (preview or refine). Returns task_id."""
            if not prompt and mode == "preview":
                return {"success": False, "error": "prompt required for preview"}
            if mode not in ALLOWED_MODES:
                return {"success": False, "error": f"mode must be one of {ALLOWED_MODES}"}
            if mode == "refine" and not preview_task_id:
                return {"success": False, "error": "preview_task_id required for refine"}
            if self.stub_mode:
                tid = f"stub-{uuid4().hex[:12]}"
                self._stub_tasks[tid] = {
                    "id": tid,
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "prompt": prompt,
                    "mode": mode,
                    "model_urls": {
                        "glb": f"stub://assets/meshy/{tid}.glb",
                    },
                }
                return {"success": True, "stub": True, "task_id": tid, "mode": mode}
            body: dict = {"mode": mode, "ai_model": ai_model}
            if mode == "preview":
                body.update({"prompt": prompt, "should_remesh": should_remesh})
            else:
                body.update({
                    "preview_task_id": preview_task_id,
                    "enable_pbr": enable_pbr,
                })
                if prompt:
                    body["prompt"] = prompt
            result = await self._request("POST", "/v2/text-to-3d", body)
            if not result.get("success"):
                return result
            task_id = result["data"].get("result") or result["data"].get("id")
            return {"success": True, "task_id": task_id, "mode": mode, "raw": result["data"]}

        @self.register("meshy.get_text_to_3d")
        async def get_text_to_3d(task_id: str):
            """Get status / result of a text-to-3D task."""
            if not task_id:
                return {"success": False, "error": "task_id required"}
            if self.stub_mode:
                task = self._stub_tasks.get(task_id) or {
                    "id": task_id, "status": "FAILED",
                    "task_error": {"message": "unknown stub task"},
                }
                return {"success": True, "stub": True, "task": task}
            result = await self._request("GET", f"/v2/text-to-3d/{task_id}")
            if not result.get("success"):
                return result
            return {"success": True, "task": result["data"]}

        @self.register("meshy.wait_text_to_3d")
        async def wait_text_to_3d(
            task_id: str,
            timeout_s: float = 300.0,
            poll_interval_s: float = 5.0,
        ):
            """Poll a text-to-3D task until terminal or timeout."""
            if timeout_s > 900:
                return {"success": False, "error": "timeout_s max 900"}
            elapsed = 0.0
            while elapsed <= timeout_s:
                status = await get_text_to_3d(task_id)
                if not status.get("success"):
                    return status
                task = status.get("task") or {}
                st = task.get("status")
                if st in TERMINAL:
                    return {"success": True, "task": task, "waited_s": elapsed}
                await asyncio.sleep(poll_interval_s)
                elapsed += poll_interval_s
            return {
                "success": False,
                "error": "timeout waiting for task",
                "task_id": task_id,
                "waited_s": elapsed,
            }

        @self.register("meshy.create_image_to_3d")
        async def create_image_to_3d(
            image_url: str,
            ai_model: str = "latest",
            should_remesh: bool = True,
        ):
            """Create an image-to-3D task from a public URL or data URI."""
            if not image_url:
                return {"success": False, "error": "image_url required"}
            if self.stub_mode:
                tid = f"stub-img-{uuid4().hex[:12]}"
                self._stub_tasks[tid] = {
                    "id": tid,
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "image_url": image_url[:120],
                    "model_urls": {"glb": f"stub://assets/meshy/{tid}.glb"},
                }
                return {"success": True, "stub": True, "task_id": tid}
            body = {
                "image_url": image_url,
                "ai_model": ai_model,
                "should_remesh": should_remesh,
            }
            result = await self._request("POST", "/v1/image-to-3d", body)
            if not result.get("success"):
                return result
            task_id = result["data"].get("result") or result["data"].get("id")
            return {"success": True, "task_id": task_id, "raw": result["data"]}

        @self.register("meshy.get_image_to_3d")
        async def get_image_to_3d(task_id: str):
            """Get status / result of an image-to-3D task."""
            if not task_id:
                return {"success": False, "error": "task_id required"}
            if self.stub_mode:
                task = self._stub_tasks.get(task_id) or {
                    "id": task_id, "status": "FAILED",
                    "task_error": {"message": "unknown stub task"},
                }
                return {"success": True, "stub": True, "task": task}
            result = await self._request("GET", f"/v1/image-to-3d/{task_id}")
            if not result.get("success"):
                return result
            return {"success": True, "task": result["data"]}

        @self.register("meshy.get_balance")
        async def get_balance():
            """Check remaining Meshy credits."""
            if self.stub_mode:
                return {"success": True, "stub": True, "balance": 0}
            result = await self._request("GET", "/v1/balance")
            if not result.get("success"):
                return result
            data = result["data"]
            return {"success": True, "balance": data.get("balance", data)}

        @self.register("meshy.download_model")
        async def download_model(
            url: str,
            filename: str = "model.glb",
        ):
            """Download a model URL into assets/meshy/ (Article 4.4)."""
            if not url or not isinstance(url, str):
                return {"success": False, "error": "url required"}
            if url.startswith("stub://"):
                path = self._safe_filename(filename)
                if not path:
                    return {"success": False, "error": "invalid filename"}
                path.write_text(f"stub model from {url}\n", encoding="utf-8")
                return {"success": True, "stub": True, "saved_to": str(path)}
            if not (url.startswith("https://") or url.startswith("http://")):
                return {"success": False, "error": "url must be http(s)"}
            path = self._safe_filename(filename)
            if not path:
                return {"success": False, "error": "invalid filename"}
            client = await self._client()
            owns = self._http is None
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code >= 400:
                    return {"success": False, "error": f"HTTP {resp.status_code}"}
                path.write_bytes(resp.content)
                return {
                    "success": True,
                    "saved_to": str(path),
                    "bytes": len(resp.content),
                }
            finally:
                if owns:
                    await client.aclose()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = MeshyMCPServer()
    asyncio.run(server.run_stdio())
