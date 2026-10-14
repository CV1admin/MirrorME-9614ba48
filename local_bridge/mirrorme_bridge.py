#!/usr/bin/env python3
"""Local MirrorME bridge.

This process runs only on the operator's machine. It gives the MirrorME browser UI
one stable local endpoint and proxies chat requests to a local Ollama runtime.

Default route:
    MirrorME UI -> http://localhost:8765/api/chat -> http://localhost:11434/api/chat

No API keys are required. No request is sent to a cloud model by this bridge.

Handshake route:
    GET  /api/handshake/challenge
    POST /api/handshake/verify
    GET  /api/handshake/status?session_id=...

Intelligence pipeline stub (hard rules #1–#5):
    POST /api/intelligence/route
    Body: { request, session, mk_decision?, publication_request? }

VIREAX multi-model chat:
    GET  /api/vireax/models
    POST /api/vireax/converse
    Body: { task, models?: [name, ...], max_rounds?: 1-3, allow_cloud?: true }
    Cloud models (Anthropic, OpenAI, Gemini) come only from --cloud-model and keys
    in this process's environment; cloud calls require allow_cloud: true.

The handshake is local session confirmation. It is not cryptographic proof of legal
identity and must not be represented as consciousness, biometric verification, or
external account authentication.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_BRIDGE_DIR = Path(__file__).resolve().parent
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

try:
    from intelligence_pipeline.api import handle_scientific_route
except ImportError:  # pragma: no cover - package always shipped with bridge
    handle_scientific_route = None  # type: ignore[assignment,misc]

try:
    from vireax_chat import (
        VireaxModelError,
        VireaxRequestError,
        build_cloud_catalog,
        describe_cloud_catalog,
        list_ollama_models,
        ollama_model_details,
        run_vireax_chat,
    )
except ImportError:  # pragma: no cover - qviraex ships with the repository
    run_vireax_chat = None  # type: ignore[assignment]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "mirrorme:latest"
DEFAULT_OPERATOR = "Marek K"
HANDSHAKE_TTL_SECONDS = 300
HANDSHAKE_CONFIRMATION_PHRASE = "CONFIRM_LOCAL_MIRRORME"
HANDSHAKE_PROTOCOL_VERSION = "MirrorME-Local-Handshake/v0.2"
MAX_REQUEST_BYTES = 1_048_576
DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    if length > MAX_REQUEST_BYTES:
        raise ValueError("request_body_too_large")
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _is_local_address(value: str) -> bool:
    normalized = value.lower()
    return (
        normalized.startswith("127.")
        or normalized == "localhost"
        or normalized.startswith("http://127.")
        or normalized.startswith("http://localhost")
        or normalized.startswith("https://localhost")
    )


def _now_seconds() -> int:
    return int(time.time())


class MirrorMeBridgeHandler(BaseHTTPRequestHandler):
    server_version = "MirrorMeLocalBridge/0.2"

    def _request_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.server.allowed_origins  # type: ignore[attr-defined]

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in self.server.allowed_origins:  # type: ignore[attr-defined]
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome's Private Network Access preflight: lets an allowed HTTPS origin
        # (e.g. the deployed site) reach this loopback-only bridge.
        if origin and origin in self.server.allowed_origins and self.headers.get(  # type: ignore[attr-defined]
            "Access-Control-Request-Private-Network"
        ) == "true":
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "mirrorme-local-bridge",
                    "version": self.server_version,
                    "default_model": self.server.default_model,  # type: ignore[attr-defined]
                    "ollama_url": self.server.ollama_url,  # type: ignore[attr-defined]
                    "operator": self.server.operator,  # type: ignore[attr-defined]
                    "handshake_protocol": HANDSHAKE_PROTOCOL_VERSION,
                    "intelligence_pipeline_stub": handle_scientific_route is not None,
                    "intelligence_route": "/api/intelligence/route",
                    "vireax_chat": run_vireax_chat is not None,
                    "vireax_default_models": list(getattr(self.server, "vireax_models", [])),
                },
            )
            return

        if path == "/api/vireax/models":
            self._handle_vireax_models()
            return

        if path == "/api/handshake/challenge":
            self._handle_handshake_challenge()
            return

        if path == "/api/handshake/status":
            query = urllib.parse.parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._handle_handshake_status(session_id)
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            if path == "/api/chat":
                payload = _read_json(self)
                self._proxy_ollama_chat(payload)
                return

            if path == "/api/handshake/verify":
                payload = _read_json(self)
                self._handle_handshake_verify(payload)
                return

            if path == "/api/vireax/converse":
                payload = _read_json(self)
                self._handle_vireax_converse(payload)
                return

            if path == "/api/intelligence/route":
                if handle_scientific_route is None:
                    self._send_json(
                        503,
                        {
                            "ok": False,
                            "error": "intelligence_pipeline_unavailable",
                            "hint": "local_bridge/intelligence_pipeline package missing",
                        },
                    )
                    return
                payload = _read_json(self)
                result = handle_scientific_route(payload)
                status = 200 if result.get("ok") else 403
                # awaiting_mk_review is an expected success stop
                if result.get("stage") == "awaiting_mk_review":
                    status = 200
                self._send_json(status, result)
                return

            self._send_json(404, {"ok": False, "error": "not_found"})
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
        except ValueError as exc:
            self._send_json(413, {"ok": False, "error": str(exc)})
        except urllib.error.URLError as exc:
            self._send_json(
                502,
                {
                    "ok": False,
                    "error": "ollama_unreachable",
                    "detail": str(exc.reason),
                    "hint": "Start Ollama with `ollama serve` and pull the selected model.",
                },
            )
        except Exception as exc:  # defensive boundary for local operator visibility
            self._send_json(500, {"ok": False, "error": "bridge_error", "detail": str(exc)})

    def _handle_handshake_challenge(self) -> None:
        self._remove_expired_handshakes()

        session_id = str(uuid.uuid4())
        nonce = secrets.token_urlsafe(24)
        issued_at = _now_seconds()
        expires_at = issued_at + HANDSHAKE_TTL_SECONDS

        self.server.handshake_sessions[session_id] = {  # type: ignore[attr-defined]
            "session_id": session_id,
            "nonce": nonce,
            "issued_at_unix": issued_at,
            "expires_at_unix": expires_at,
            "state": "CHALLENGE_ISSUED",
            "operator": None,
            "readiness_score": 0.0,
        }

        self._send_json(
            200,
            {
                "ok": True,
                "protocol": HANDSHAKE_PROTOCOL_VERSION,
                "state": "CHALLENGE_ISSUED",
                "session_id": session_id,
                "nonce": nonce,
                "issued_at_unix": issued_at,
                "expires_at_unix": expires_at,
                "operator_expected": self.server.operator,  # type: ignore[attr-defined]
                "required_confirmation_phrase": HANDSHAKE_CONFIRMATION_PHRASE,
                "required_verify_fields": [
                    "session_id",
                    "nonce",
                    "operator",
                    "confirmation_phrase",
                ],
                "truth_boundary": "Local operator confirmation only; not cryptographic identity proof.",
            },
        )

    def _handle_handshake_verify(self, payload: dict[str, Any]) -> None:
        self._remove_expired_handshakes()

        session_id = str(payload.get("session_id", ""))
        nonce = str(payload.get("nonce", ""))
        operator = str(payload.get("operator", ""))
        confirmation_phrase = str(payload.get("confirmation_phrase", ""))
        client_capabilities = payload.get("client_capabilities", {})

        session = self.server.handshake_sessions.get(session_id)  # type: ignore[attr-defined]
        if not session:
            self._send_json(404, {"ok": False, "error": "handshake_session_not_found_or_expired"})
            return

        if session.get("nonce") != nonce:
            self._send_json(403, {"ok": False, "error": "nonce_mismatch"})
            return

        if confirmation_phrase != HANDSHAKE_CONFIRMATION_PHRASE:
            self._send_json(
                403,
                {
                    "ok": False,
                    "error": "confirmation_phrase_mismatch",
                    "required_confirmation_phrase": HANDSHAKE_CONFIRMATION_PHRASE,
                },
            )
            return

        operator_expected = self.server.operator  # type: ignore[attr-defined]
        operator_match = operator.strip().lower() == str(operator_expected).strip().lower()
        bridge_local = _is_local_address(self.server.server_address[0])  # type: ignore[attr-defined]
        ollama_local = _is_local_address(self.server.ollama_url)  # type: ignore[attr-defined]

        readiness_score = 0.40
        readiness_score += 0.20 if operator_match else 0.0
        readiness_score += 0.20 if bridge_local else 0.0
        readiness_score += 0.20 if ollama_local else 0.0
        readiness_score = round(min(readiness_score, 1.0), 3)

        warnings: list[str] = []
        if not operator_match:
            warnings.append("operator_name_does_not_match_expected_local_operator")
        if not bridge_local:
            warnings.append("bridge_not_bound_to_loopback_address")
        if not ollama_local:
            warnings.append("ollama_url_not_loopback")

        session.update(
            {
                "state": "VERIFIED_LOCAL_SESSION",
                "operator": operator,
                "verified_at_unix": _now_seconds(),
                "readiness_score": readiness_score,
                "client_capabilities": client_capabilities,
                "warnings": warnings,
            }
        )

        self._send_json(
            200,
            {
                "ok": True,
                "protocol": HANDSHAKE_PROTOCOL_VERSION,
                "state": "VERIFIED_LOCAL_SESSION",
                "session_id": session_id,
                "operator": operator,
                "readiness_score": readiness_score,
                "readiness_mode": "local_runtime_confirmation_not_authentication",
                "checks": {
                    "nonce_valid": True,
                    "confirmation_phrase_valid": True,
                    "operator_match": operator_match,
                    "bridge_loopback": bridge_local,
                    "ollama_loopback": ollama_local,
                },
                "warnings": warnings,
                "truth_boundary": "This verifies a local session handshake only. It does not prove legal identity, biological identity, consciousness, or external account ownership.",
            },
        )

    def _handle_handshake_status(self, session_id: str) -> None:
        self._remove_expired_handshakes()

        if not session_id:
            self._send_json(400, {"ok": False, "error": "session_id_required"})
            return

        session = self.server.handshake_sessions.get(session_id)  # type: ignore[attr-defined]
        if not session:
            self._send_json(404, {"ok": False, "error": "handshake_session_not_found_or_expired"})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "protocol": HANDSHAKE_PROTOCOL_VERSION,
                "session": {
                    key: value
                    for key, value in session.items()
                    if key not in {"nonce"}
                },
                "truth_boundary": "Local session state only; nonce is not returned after challenge.",
            },
        )

    def _remove_expired_handshakes(self) -> None:
        now = _now_seconds()
        expired = [
            session_id
            for session_id, session in self.server.handshake_sessions.items()  # type: ignore[attr-defined]
            if int(session.get("expires_at_unix", 0)) < now
        ]
        for session_id in expired:
            del self.server.handshake_sessions[session_id]  # type: ignore[attr-defined]

    def _handle_vireax_models(self) -> None:
        if run_vireax_chat is None:
            self._send_json(503, {"ok": False, "error": "vireax_unavailable"})
            return
        ollama_error = None
        try:
            models = list_ollama_models(self.server.ollama_url)  # type: ignore[attr-defined]
        except (urllib.error.URLError, OSError, ValueError) as exc:
            models = []
            ollama_error = str(getattr(exc, "reason", exc))
        details = ollama_model_details(self.server.ollama_url, models) if models else {}  # type: ignore[attr-defined]
        self._send_json(
            200,
            {
                "ok": True,
                "models": models,
                "model_details": details,
                "ollama_error": ollama_error,
                "cloud_models": describe_cloud_catalog(getattr(self.server, "vireax_cloud_catalog", {})),
                "default_models": list(getattr(self.server, "vireax_models", [])),
            },
        )

    def _handle_vireax_converse(self, payload: dict[str, Any]) -> None:
        if run_vireax_chat is None:
            self._send_json(503, {"ok": False, "error": "vireax_unavailable"})
            return
        try:
            result = run_vireax_chat(
                payload,
                ollama_url=self.server.ollama_url,  # type: ignore[attr-defined]
                default_models=getattr(self.server, "vireax_models", []),
                cloud_catalog=getattr(self.server, "vireax_cloud_catalog", {}),
            )
        except VireaxRequestError as exc:
            self._send_json(400, {"ok": False, "error": "invalid_request", "detail": str(exc)})
            return
        except VireaxModelError as exc:
            self._send_json(
                502,
                {
                    "ok": False,
                    "error": "model_call_failed",
                    "detail": str(exc),
                    "hint": "Check that Ollama is running, local models are pulled, and cloud model IDs are valid.",
                },
            )
            return
        self._send_json(200, result)

    def _proxy_ollama_chat(self, payload: dict[str, Any]) -> None:
        ollama_url = self.server.ollama_url.rstrip("/")  # type: ignore[attr-defined]
        default_model = self.server.default_model  # type: ignore[attr-defined]

        payload.setdefault("model", default_model)
        payload.setdefault("stream", True)

        request = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=_json_bytes(payload),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            self.send_response(response.status)
            self._cors_headers()
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[MirrorMeBridge] " + fmt % args + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local MirrorME bridge.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--operator", default=DEFAULT_OPERATOR)
    parser.add_argument(
        "--allowed-origin",
        action="append",
        dest="allowed_origins",
        help="Browser origin allowed to call the bridge; repeat for multiple origins.",
    )
    parser.add_argument(
        "--vireax-model",
        action="append",
        dest="vireax_models",
        help="Default model for VIREAX chat (Ollama name or provider/model); repeat for each.",
    )
    parser.add_argument(
        "--cloud-model",
        action="append",
        dest="cloud_models",
        help=(
            "Offer a cloud model in VIREAX chat as provider/model, provider one of "
            "anthropic, openai, gemini. Keys come from ANTHROPIC_API_KEY, OPENAI_API_KEY, "
            "GEMINI_API_KEY. Repeatable."
        ),
    )
    args = parser.parse_args()
    cloud_catalog = {}
    if run_vireax_chat is not None:
        try:
            cloud_catalog = build_cloud_catalog(args.cloud_models or [])
        except ValueError as exc:
            parser.error(str(exc))

    server = ThreadingHTTPServer((args.host, args.port), MirrorMeBridgeHandler)
    server.ollama_url = args.ollama_url  # type: ignore[attr-defined]
    server.default_model = args.model  # type: ignore[attr-defined]
    server.operator = args.operator  # type: ignore[attr-defined]
    server.allowed_origins = set(args.allowed_origins or DEFAULT_ALLOWED_ORIGINS)  # type: ignore[attr-defined]
    server.handshake_sessions = {}  # type: ignore[attr-defined]
    server.vireax_models = list(args.vireax_models or [])  # type: ignore[attr-defined]
    server.vireax_cloud_catalog = cloud_catalog  # type: ignore[attr-defined]

    print(f"MirrorME local bridge running at http://{args.host}:{args.port}")
    print(f"Proxy target: {args.ollama_url}/api/chat")
    print(f"Default model: {args.model}")
    print(f"Operator: {args.operator}")
    print(f"Handshake protocol: {HANDSHAKE_PROTOCOL_VERSION}")
    print(f"Allowed browser origins: {', '.join(sorted(server.allowed_origins))}")
    if cloud_catalog:
        for entry in describe_cloud_catalog(cloud_catalog):
            state = "ready" if entry["available"] else f"needs {entry['key_env']}"
            print(f"Cloud model: {entry['id']} ({state})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("MirrorME local bridge stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
