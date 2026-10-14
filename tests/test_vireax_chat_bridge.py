from __future__ import annotations

import http.client
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from local_bridge.mirrorme_bridge import DEFAULT_ALLOWED_ORIGINS, DEFAULT_MODEL, MirrorMeBridgeHandler
from local_bridge.vireax_chat import (
    CLOUD_PROVIDERS,
    CloudModel,
    CloudProvider,
    build_cloud_catalog,
)

INSTALLED = ["alpha:1", "beta:2", "gamma:3"]
CLOUD_CALLS: list[dict] = []
LOCAL_SYSTEM_PROMPTS: list[str] = []
# alpha and beta mimic two Modelfiles built on one base model; gamma differs.
SHOW_DETAILS = {
    "alpha:1": {"family": "qwen3", "parameter_size": "8.2B", "quantization_level": "Q4_K_M"},
    "beta:2": {"family": "qwen3", "parameter_size": "8.2B", "quantization_level": "Q4_K_M"},
    "gamma:3": {"family": "llama", "parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
}


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
        if self.path == "/api/show":
            if model in SHOW_DETAILS:
                self._json(200, {"details": SHOW_DETAILS[model]})
            else:
                self._json(404, {"error": "not found"})
            return
        if self.path == "/v1/messages":  # fake Anthropic
            CLOUD_CALLS.append({"path": self.path, "key": self.headers.get("x-api-key"), "body": body})
            peers = "Prior contributions" in body["messages"][0]["content"]
            self._json(200, {"id": "msg", "content": [{"type": "text", "text": f"{model} cloud (saw peers: {peers})"}]})
            return
        if self.path == "/openai/chat/completions":  # fake OpenAI-compatible cloud
            CLOUD_CALLS.append({"path": self.path, "key": self.headers.get("Authorization"), "body": body})
            self._json(200, {"choices": [{"message": {"content": f"{model} cloud"}}]})
            return
        if self.path != "/v1/chat/completions" or model not in INSTALLED:
            self._json(404, {"error": "model not found"})
            return
        LOCAL_SYSTEM_PROMPTS.append(body["messages"][0]["content"])
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
        fake = f"http://127.0.0.1:{cls.ollama.server_address[1]}"
        claude = CloudProvider("anthropic", "Anthropic", "anthropic", f"{fake}/v1/messages", "TEST_ANTHROPIC_KEY")
        gpt = CloudProvider("openai", "OpenAI", "openai", f"{fake}/openai/chat/completions", "TEST_OPENAI_KEY",
                            max_tokens_field="max_completion_tokens")
        cls.bridge.vireax_cloud_catalog = {
            "anthropic/claude-test": CloudModel("anthropic/claude-test", claude, "claude-test"),
            "openai/gpt-test": CloudModel("openai/gpt-test", gpt, "gpt-test"),
        }
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

    def test_cloud_models_listed_without_keys_or_endpoints(self) -> None:
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-secret"}):
            status, _, data = self.request("GET", "/api/vireax/models")
        self.assertEqual(status, 200)
        listed = {m["id"]: m for m in data["cloud_models"]}
        self.assertTrue(listed["anthropic/claude-test"]["available"])
        self.assertFalse(listed["openai/gpt-test"]["available"])
        serialized = json.dumps(data)
        self.assertNotIn("sk-secret", serialized)
        self.assertNotIn("/v1/messages", serialized)

    def test_cloud_requires_explicit_consent_before_any_call(self) -> None:
        CLOUD_CALLS.clear()
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-secret"}):
            status, _, data = self.request(
                "POST", "/api/vireax/converse",
                {"task": "private", "models": ["alpha:1", "anthropic/claude-test"], "max_rounds": 1},
            )
        self.assertEqual(status, 400)
        self.assertIn("cloud_consent_required", data["detail"])
        self.assertIn("Anthropic", data["detail"])
        self.assertEqual(CLOUD_CALLS, [])

    def test_cloud_key_missing_is_reported_before_any_call(self) -> None:
        CLOUD_CALLS.clear()
        with mock.patch.dict(os.environ, {}, clear=True):
            status, _, data = self.request(
                "POST", "/api/vireax/converse",
                {"task": "x", "models": ["alpha:1", "openai/gpt-test"], "max_rounds": 1, "allow_cloud": True},
            )
        self.assertEqual(status, 400)
        self.assertIn("TEST_OPENAI_KEY", data["detail"])
        self.assertEqual(CLOUD_CALLS, [])

    def test_mixed_local_and_cloud_conversation(self) -> None:
        CLOUD_CALLS.clear()
        env = {"TEST_ANTHROPIC_KEY": "sk-ant", "TEST_OPENAI_KEY": "sk-oai"}
        with mock.patch.dict(os.environ, env):
            status, _, data = self.request(
                "POST", "/api/vireax/converse",
                {
                    "task": "Is the claim sound?",
                    "models": ["alpha:1", "anthropic/claude-test", "openai/gpt-test"],
                    "max_rounds": 2,
                    "allow_cloud": True,
                },
            )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["sent_to_cloud"], ["Anthropic", "OpenAI"])
        self.assertEqual(
            data["providers"],
            {"alpha:1": "ollama", "anthropic/claude-test": "anthropic", "openai/gpt-test": "openai"},
        )
        self.assertEqual(len(data["turns"]), 6)
        self.assertEqual([t["provider"] for t in data["turns"][:3]], ["ollama", "anthropic", "openai"])
        self.assertIn("saw peers: False", data["turns"][1]["output"])
        self.assertIn("saw peers: True", data["turns"][4]["output"])
        anthropic_calls = [c for c in CLOUD_CALLS if c["path"] == "/v1/messages"]
        openai_calls = [c for c in CLOUD_CALLS if c["path"] == "/openai/chat/completions"]
        self.assertEqual(len(anthropic_calls), 2)
        self.assertEqual(anthropic_calls[0]["key"], "sk-ant")
        self.assertEqual(anthropic_calls[0]["body"]["model"], "claude-test")
        self.assertEqual(openai_calls[0]["key"], "Bearer sk-oai")
        self.assertEqual(openai_calls[0]["body"]["max_completion_tokens"], 2048)
        self.assertNotIn("sk-ant", json.dumps(data))

    def test_models_listing_includes_base_model_details(self) -> None:
        status, _, data = self.request("GET", "/api/vireax/models")
        self.assertEqual(status, 200)
        self.assertEqual(data["model_details"]["alpha:1"]["family"], "qwen3")
        self.assertEqual(data["model_details"]["gamma:3"]["family"], "llama")

    def test_same_base_local_models_are_disclosed(self) -> None:
        status, _, data = self.request(
            "POST", "/api/vireax/converse", {"task": "x", "models": ["alpha:1", "beta:2"], "max_rounds": 1},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["independence"]["same_base_groups"], [["alpha:1", "beta:2"]])
        self.assertIn("same base model", data["independence"]["notes"][0])

    def test_distinct_local_models_still_note_single_provider(self) -> None:
        status, _, data = self.request(
            "POST", "/api/vireax/converse", {"task": "x", "models": ["alpha:1", "gamma:3"], "max_rounds": 1},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["independence"]["same_base_groups"], [])
        self.assertEqual(len(data["independence"]["notes"]), 1)
        self.assertIn("one provider", data["independence"]["notes"][0])

    def test_vireax_system_prompt_reaches_every_model_and_is_reported(self) -> None:
        CLOUD_CALLS.clear()
        LOCAL_SYSTEM_PROMPTS.clear()
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-ant"}):
            status, _, data = self.request(
                "POST", "/api/vireax/converse",
                {"task": "x", "models": ["alpha:1", "anthropic/claude-test"], "max_rounds": 1, "allow_cloud": True},
            )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["system_prompt"]["version"], "vireax-mirror-agent/1.0")
        self.assertTrue(data["system_prompt"]["sha256"].startswith("sha256:"))
        self.assertTrue(LOCAL_SYSTEM_PROMPTS[-1].startswith("You are VIREÁX"))
        self.assertTrue(CLOUD_CALLS[-1]["body"]["system"].startswith("You are VIREÁX"))
        self.assertNotIn("You are VIREÁX", json.dumps(data))

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


class SystemPromptTests(unittest.TestCase):
    def test_prompt_is_the_spec_text_without_provenance_header(self) -> None:
        from qviraex.vireax.system_prompt import load_vireax_system_prompt

        prompt = load_vireax_system_prompt()
        self.assertEqual(prompt.version, "vireax-mirror-agent/1.0")
        self.assertTrue(prompt.text.startswith("You are VIREÁX, a personal reflective AI agent."))
        self.assertNotIn("Source: Civilisation-one/DOCUMENTS", prompt.text)
        for required in ("Mirror:", "Critic:", "Never claim that a test passed", "NOT_TESTED", "no persistent memory"):
            self.assertIn(required, prompt.text)


class CloudCatalogTests(unittest.TestCase):
    def test_anthropic_defaults_offered_only_with_key(self) -> None:
        self.assertEqual(build_cloud_catalog([], environ={}), {})
        catalog = build_cloud_catalog([], environ={"ANTHROPIC_API_KEY": "k"})
        self.assertEqual(sorted(catalog), ["anthropic/claude-haiku-5-5", "anthropic/claude-sonnet-5-5"])
        self.assertIs(catalog["anthropic/claude-sonnet-5-5"].provider, CLOUD_PROVIDERS["anthropic"])

    def test_listed_models_replace_defaults_for_that_provider(self) -> None:
        catalog = build_cloud_catalog(
            ["anthropic/claude-opus-5-5", "openai/gpt-x", "gemini/gemini-x"],
            environ={"ANTHROPIC_API_KEY": "k"},
        )
        self.assertEqual(sorted(catalog), ["anthropic/claude-opus-5-5", "gemini/gemini-x", "openai/gpt-x"])
        self.assertEqual(catalog["openai/gpt-x"].api_model, "gpt-x")

    def test_invalid_entries_rejected(self) -> None:
        for entry in ("gpt-x", "azure/gpt-x", "openai/", "openai/bad name"):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    build_cloud_catalog([entry], environ={})


if __name__ == "__main__":
    unittest.main()
