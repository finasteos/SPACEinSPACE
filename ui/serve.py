#!/usr/bin/env python3
"""Server for Agent Ecosystem Dashboard + API.
Reads Supabase config from .env and serves UI and vector API."""

import os
import json
import http.server
import socketserver
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_ANON_KEY)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY (or SUPABASE_SERVICE_KEY) must be set in .env")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def pca_2d(points, n_components=2):
    """Simple PCA via SVD. points: list of lists (n_samples x n_features)."""
    import numpy as np
    X = np.array(points, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] < 2 or X.shape[1] < 2:
        return None
    # Center
    mean = X.mean(axis=0)
    X_centered = X - mean
    # SVD
    U, S, Vt = np.linalg.svd(X_centered, full_matrices=False)
    return (X_centered @ Vt[:n_components].T).tolist()


def random_projection_2d(points):
    """Fallback: random normal projection."""
    import numpy as np
    X = np.array(points, dtype=np.float64)
    n_features = X.shape[1]
    rng = np.random.RandomState(42)
    proj = rng.randn(n_features, 2)
    proj /= np.linalg.norm(proj, axis=0)
    return (X @ proj).tolist()


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def _inject_config(self, html_path):
        with open(html_path) as f:
            html = f.read()
        return html.replace("__SUPABASE_URL__", SUPABASE_URL).replace("__SUPABASE_ANON_KEY__", SUPABASE_ANON_KEY)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/dashboard"):
            self._send_html(self._inject_config(os.path.join(os.path.dirname(__file__), "index.html")))

        elif path == "/graph":
            self._send_html(self._inject_config(os.path.join(os.path.dirname(__file__), "graph.html")))

        elif path == "/vectors":
            self._send_html(self._inject_config(os.path.join(os.path.dirname(__file__), "vectors.html")))

        elif path == "/world":
            self._send_html(self._inject_config(os.path.join(os.path.dirname(__file__), "human_view.html")))

        elif path == "/tools":
            self._send_html(self._inject_config(os.path.join(os.path.dirname(__file__), "tools.html")))

        elif path == "/neo_minimal.css":
            css_path = os.path.join(os.path.dirname(__file__), "neo_minimal.css")
            if os.path.exists(css_path):
                with open(css_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        elif path == "/api/toolstats":
            self._handle_tool_stats_api()

        elif path == "/api/vectors":
            self._handle_vector_api()

        else:
            super().do_GET()

    def _handle_vector_api(self):
        try:
            import numpy as np
        except ImportError:
            self._send_json({"error": "numpy required: pip install numpy"}, 500)
            return

        # Fetch memories with embeddings
        result = supabase.table("agent_memories") \
            .select("id, memory_type, content, source, confidence, created_at, embedding") \
            .not_.is_("embedding", "null") \
            .order("created_at", desc=True) \
            .limit(200) \
            .execute()

        records = result.data
        if not records:
            self._send_json({"points": [], "error": "No embeddings found"})
            return

        embeddings = [r["embedding"] for r in records]
        try:
            reduced = pca_2d(embeddings)
        except Exception:
            reduced = random_projection_2d(embeddings)

        if reduced is None:
            self._send_json({"points": [], "error": "Not enough data for PCA"}, 200)
            return

        points = []
        for i, r in enumerate(records):
            points.append({
                "id": r["id"],
                "x": reduced[i][0],
                "y": reduced[i][1],
                "type": r["memory_type"],
                "content": r["content"][:120],
                "source": r.get("source", ""),
                "confidence": r.get("confidence", 1.0),
                "created_at": r.get("created_at", ""),
            })

        by_type = {}
        for p in points:
            by_type.setdefault(p["type"], 0)
            by_type[p["type"]] += 1

        self._send_json({
            "points": points,
            "count": len(points),
            "by_type": by_type,
        })

    def _handle_tool_stats_api(self):
        from tools.stats import ToolTuning
        tuning = ToolTuning(None)  # sync from DB directly
        since = self._get_param("hours", "24")
        try:
            result = supabase.table("tool_calls") \
                .select("tool_name, success, latency_ms, error_message, input_params") \
                .gte("created_at", (datetime.now() - timedelta(hours=int(since))).isoformat()) \
                .execute()
            for row in result.data or []:
                tuning.record(
                    tool_name=row["tool_name"],
                    success=row.get("success", True),
                    latency_ms=row.get("latency_ms", 0) or 0,
                    error=row.get("error_message"),
                    params=row.get("input_params"),
                )
            self._send_json(tuning.report())
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_param(self, name, default=None):
        from urllib.parse import parse_qs
        qs = parse_qs(urllib.parse.urlparse(self.path).query)
        vals = qs.get(name, [])
        return vals[0] if vals else default

    def log_message(self, fmt, *args):
        print(f"[Dashboard] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"🚀 Dashboard: http://localhost:{PORT}")
        print(f"   Graph:     http://localhost:{PORT}/graph")
        print(f"   Vectors:   http://localhost:{PORT}/vectors")
        print(f"   API:       http://localhost:{PORT}/api/vectors")
        httpd.serve_forever()
