from __future__ import annotations

import http.client
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from local_bridge.mirrorme_bridge import DEFAULT_ALLOWED_ORIGINS, DEFAULT_MODEL, MirrorMeBridgeHandler

INSTALLED = ["alpha:1", "beta:2", "gamma:3"]


class FakeOllamaHandler(BaseHTTPRequestHandler):
    """Minimal stand-in for Ollama's /api/tags and OpenAI-compatible chat route."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/tags":
            self._json(200, {"models": [{"name": name} for name in INSTALLED]})
        else:
            self._json(404, {})

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        model = body["model"]
        if self.path != "/v1/chat/completions" or model not in INSTALLED:
            self._json(404, {"error": "model not found"})
            return
        prompt = body["messages"][-1]["content"]
        seen_peers = "Prior contributions" in prompt
        self._json(200, {
            "id": "fake",
            "choices": [{"message": {"content": f"{model} answer (saw peers: {seen_peers})"}}],
        })

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def _start(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class VireaxChatBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ollama = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        _start(cls.ollama)
        cls.bridge = ThreadingHTTPServer(("127.0.0.1", 0), MirrorMeBridgeHandler)
        cls.bridge.ollama_url = f"http://127.0.0.1:{cls.ollama.server_address[1]}"
        cls.bridge.default_model = DEFAULT_MODEL
        cls.bridge.operator = "test"
        cls.bridge.allowed_origins = set(DEFAULT_ALLOWED_ORIGINS) | {"https://cv1admin.github.io"}
        cls.bridge.handshake_sessions = {}
        cls.bridge.vireax_models = ["alpha:1", "beta:2"]
        _start(cls.bridge)

    @classmethod
    def tearDownClass(cls) -> None:
        for server in (cls.bridge, cls.ollama):
            server.shutdown()
            server.server_close()

    def request(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.bridge.server_address[1], timeout=10)
        body = json.dumps(payload).encode() if payload is not None else None
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        conn.request(method, path, body=body, headers=all_headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, dict(response.getheaders()), (json.loads(raw) if raw else None)

    def test_lists_installed_models_and_defaults(self) -> None:
        status, _, data = self.request("GET", "/api/vireax/models")
        self.assertEqual(status, 200)
        self.assertEqual(data["models"], INSTALLED)
        self.assertEqual(data["default_models"], ["alpha:1", "beta:2"])

    def test_converse_runs_independent_first_round_then_review(self) -> None:
        status, _, data = self.request(
            "POST", "/api/vireax/converse",
            {"task": "Is the claim sound?", "models": ["alpha:1", "gamma:3"], "max_rounds": 2},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["status"], "completed_unverified")
        self.assertEqual(len(data["turns"]), 4)
        first, second = data["turns"][:2], data["turns"][2:]
        for turn in first:
            self.assertEqual(turn["round"], 1)
            self.assertEqual(turn["role"], "independent_analyst")
            self.assertIn("saw peers: False", turn["output"])
        for turn in second:
            self.assertEqual(turn["role"], "critical_reviewer")
            self.assertIn("saw peers: True", turn["output"])
        self.assertTrue(data["audit_head_hash"].startswith("sha256:"))

    def test_server_default_models_used_when_none_given(self) -> None:
        status, _, data = self.request("POST", "/api/vireax/converse", {"task": "x", "max_rounds": 1})
        self.assertEqual(status, 200, data)
        self.assertEqual([t["model"] for t in data["turns"]], ["alpha:1", "beta:2"])

    def test_invalid_requests_are_rejected_before_any_model_call(self) -> None:
        cases = [
            {"task": "", "models": ["alpha:1", "beta:2"]},
            {"task": "x", "models": ["alpha:1"]},
            {"task": "x", "models": ["alpha:1", "alpha:1"]},
            {"task": "x", "models": ["alpha:1", "bad name!"]},
            {"task": "x", "models": ["alpha:1", "beta:2"], "max_rounds": 4},
            {"task": "x" * 20_001, "models": ["alpha:1", "beta:2"]},
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:60]):
                status, _, data = self.request("POST", "/api/vireax/converse", payload)
                self.assertEqual(status, 400)
                self.assertEqual(data["error"], "invalid_request")

    def test_missing_model_reports_model_failure(self) -> None:
        status, _, data = self.request(
            "POST", "/api/vireax/converse", {"task": "x", "models": ["alpha:1", "missing:9"], "max_rounds": 1},
        )
        self.assertEqual(status, 502)
        self.assertEqual(data["error"], "model_call_failed")

    def test_disallowed_origin_is_blocked(self) -> None:
        status, _, _ = self.request(
            "POST", "/api/vireax/converse", {"task": "x"}, headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)

    def test_private_network_preflight_for_allowed_origin(self) -> None:
        status, headers, _ = self.request(
            "OPTIONS", "/api/vireax/converse",
            headers={"Origin": "https://cv1admin.github.io", "Access-Control-Request-Private-Network": "true"},
        )
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "https://cv1admin.github.io")


if __name__ == "__main__":
    unittest.main()
