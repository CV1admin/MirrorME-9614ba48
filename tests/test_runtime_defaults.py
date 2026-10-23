from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_defaults_unify_on_mirrorme_latest() -> None:
    bridge_text = (REPO_ROOT / "local_bridge" / "mirrorme_bridge.py").read_text(encoding="utf-8")
    start_script_text = (REPO_ROOT / "scripts" / "start-mirrorme.ps1").read_text(encoding="utf-8")
    run_script_text = (REPO_ROOT / "scripts" / "run-mirrorme.ps1").read_text(encoding="utf-8")
    settings_text = (REPO_ROOT / "pages" / "Settings.tsx").read_text(encoding="utf-8")

    assert 'DEFAULT_MODEL = "mirrorme:latest"' in bridge_text
    assert '"mirrorme:latest"' in start_script_text
    assert '"mirrorme:latest"' in run_script_text
    assert "const DEFAULT_OLLAMA_MODEL = 'mirrorme:latest';" in settings_text
    assert "ollamaModel: DEFAULT_OLLAMA_MODEL" in settings_text
