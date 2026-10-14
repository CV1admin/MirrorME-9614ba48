"""Versioned VIREAX system prompt used by the bridge chat.

The prompt text lives in ``prompts/vireax_mirror_agent_v1.txt``. Its first lines,
up to a ``---`` line, are a provenance header and are not sent to models.
A prompt is guidance only: tool permissions and memory rules are enforced in code.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "vireax_mirror_agent_v1.txt"
PROMPT_VERSION = "vireax-mirror-agent/1.0"


@dataclass(frozen=True)
class SystemPrompt:
    version: str
    text: str
    sha256: str


@lru_cache(maxsize=1)
def load_vireax_system_prompt() -> SystemPrompt:
    raw = PROMPT_FILE.read_text(encoding="utf-8")
    _header, sep, body = raw.partition("\n---\n")
    text = (body if sep else raw).strip()
    if not text:
        raise RuntimeError("VIREAX system prompt file is empty")
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SystemPrompt(PROMPT_VERSION, text, digest)
