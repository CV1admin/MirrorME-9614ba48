#!/usr/bin/env python3
"""Start VIREAX chat with one command: the web app and the local bridge.

Examples
  python scripts/start_vireax.py                      # this computer only
  python scripts/start_vireax.py --tailscale          # also reachable from your phone over Tailscale
  python scripts/start_vireax.py --tailscale --vireax-model llama3.1:8b --vireax-model anthropic/claude-sonnet-5-5

Cloud models need their key in this terminal first, e.g. ANTHROPIC_API_KEY.
Press Ctrl+C to stop everything.

The bridge has no login. Only bind it to Tailscale or this computer, never to
0.0.0.0 on shared Wi-Fi: anyone who can reach it can use your models and keys.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UI_PORT = 3000
BRIDGE_PORT = 8765
HOSTED_SITE = "https://cv1admin.github.io"


def tailscale_ip() -> str:
    exe = shutil.which("tailscale")
    if not exe:
        sys.exit("Tailscale isn't installed or isn't on PATH. Install it, sign in, and try again.")
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10, check=True).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        sys.exit(f"Couldn't read the Tailscale address ({exc}). Is Tailscale running and signed in?")
    ip = out.strip().splitlines()[0] if out.strip() else ""
    if not ip.startswith("100."):
        sys.exit(f"Unexpected Tailscale address {ip!r}. Run `tailscale status` to check the connection.")
    return ip


def ollama_models(url: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as response:
            return [m["name"] for m in json.load(response).get("models", [])]
    except (OSError, ValueError, KeyError):
        return None


def _stop_on_signal(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def _spawn(cmd: list[str]) -> subprocess.Popen:
    """Start a child in its own process group so stopping it also stops anything it launched."""
    if os.name == "nt":
        return subprocess.Popen(cmd, cwd=REPO, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(cmd, cwd=REPO, start_new_session=True)


def _stop(process: subprocess.Popen, force: bool = False) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # taskkill /T stops the whole tree (npx.cmd -> node).
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T"] + (["/F"] if force else []),
                       capture_output=True, check=False)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGINT)
    except ProcessLookupError:
        pass


def main() -> None:
    signal.signal(signal.SIGTERM, _stop_on_signal)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tailscale", action="store_true", help="bind to this computer's Tailscale address")
    parser.add_argument("--host", help="bind address (default 127.0.0.1, or the Tailscale address)")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--vireax-model", action="append", default=[], help="default model; repeatable")
    parser.add_argument("--cloud-model", action="append", default=[], help="provider/model; repeatable")
    parser.add_argument("--no-ui", action="store_true", help=f"start only the bridge and use {HOSTED_SITE}")
    args = parser.parse_args()

    if args.tailscale and args.host:
        parser.error("use either --tailscale or --host, not both")
    host = tailscale_ip() if args.tailscale else (args.host or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        parser.error("refusing to bind to every network interface; use --tailscale or a specific address")

    models = ollama_models(args.ollama_url)
    if models is None:
        print(f"! Ollama isn't answering at {args.ollama_url}. Local models won't work until you run `ollama serve`.")
    elif len(models) < 2:
        print(f"! Ollama has {len(models)} model(s). Pull at least two, or add a cloud model.")

    ui_origin = f"http://{host}:{UI_PORT}"
    bridge_cmd = [
        sys.executable, str(REPO / "local_bridge" / "mirrorme_bridge.py"),
        "--host", host, "--port", str(BRIDGE_PORT), "--ollama-url", args.ollama_url,
    ]
    origins = [HOSTED_SITE] if args.no_ui else [ui_origin]
    if host == "127.0.0.1" and not args.no_ui:
        origins.append(f"http://localhost:{UI_PORT}")
    for origin in origins:
        bridge_cmd += ["--allowed-origin", origin]
    for model in args.vireax_model:
        bridge_cmd += ["--vireax-model", model]
    for model in args.cloud_model:
        bridge_cmd += ["--cloud-model", model]

    processes: list[subprocess.Popen] = []
    try:
        processes.append(_spawn(bridge_cmd))
        if not args.no_ui:
            npx = shutil.which("npx")
            if not npx:
                sys.exit("Node.js (npx) isn't installed. Install it, or use --no-ui with the hosted site.")
            if not (REPO / "node_modules").exists():
                print("Installing web app dependencies (first run only)…")
                subprocess.run([shutil.which("npm") or "npm", "ci", "--no-audit", "--no-fund"], cwd=REPO, check=True)
            processes.append(_spawn([npx, "vite", "--host", host, "--port", str(UI_PORT), "--strictPort"]))
        time.sleep(3)
        if any(p.poll() is not None for p in processes):
            sys.exit("Something stopped during start-up; see the messages above.")

        page = f"{HOSTED_SITE}/MirrorME/#/vireax" if args.no_ui else f"{ui_origin}/#/vireax"
        print("\nVIREAX chat is running.")
        print(f"  Open: {page}")
        if args.tailscale:
            print("  On your phone: switch Tailscale on and open the same link.")
        print("  Stop: Ctrl+C\n")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        print("A process exited; stopping the rest.")
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        for p in processes:
            _stop(p)
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _stop(p, force=True)


if __name__ == "__main__":
    main()
