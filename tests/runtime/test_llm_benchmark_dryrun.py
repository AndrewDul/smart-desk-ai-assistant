"""Tests for the LLM benchmark script in dry-run / offline mode.

Verifies that:
- dry-run mode produces results for all prompts without a server
- all results in dry-run have status='dry_run'
- first_token_ms, tokens_per_second, total_ms are None in dry-run (no server)
- the script returns exit code 0 in dry-run
- JSON output is valid and contains expected keys
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "llm_benchmark.py"


def _run_dry_run(*extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", *extra_args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_llm_benchmark_dry_run_exits_zero() -> None:
    result = _run_dry_run()
    assert result.returncode == 0, (
        f"dry-run exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_llm_benchmark_dry_run_json_is_valid() -> None:
    result = _run_dry_run("--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) > 0


def test_llm_benchmark_dry_run_all_results_are_dry_run() -> None:
    result = _run_dry_run("--json")
    data = json.loads(result.stdout)
    for item in data:
        assert item.get("status") == "dry_run", (
            f"Expected status=dry_run, got {item.get('status')!r} for prompt {item.get('prompt')!r}"
        )


def test_llm_benchmark_dry_run_latency_fields_are_none() -> None:
    result = _run_dry_run("--json")
    data = json.loads(result.stdout)
    for item in data:
        assert item.get("first_token_ms") is None, (
            f"dry-run should not populate first_token_ms, got {item.get('first_token_ms')!r}"
        )
        assert item.get("tokens_per_second") is None
        assert item.get("total_ms") is None


def test_llm_benchmark_dry_run_covers_both_languages() -> None:
    result = _run_dry_run("--json")
    data = json.loads(result.stdout)
    languages = {item.get("language") for item in data}
    assert "en" in languages, "Missing English prompts"
    assert "pl" in languages, "Missing Polish prompts"


def test_llm_benchmark_dry_run_covers_all_prompts() -> None:
    result = _run_dry_run("--json")
    data = json.loads(result.stdout)
    assert len(data) >= 8, f"Expected at least 8 prompts, got {len(data)}"


def test_llm_benchmark_dry_run_json_has_required_keys() -> None:
    result = _run_dry_run("--json")
    data = json.loads(result.stdout)
    required_keys = {"prompt", "language", "health_check_ms", "status"}
    for item in data:
        missing = required_keys - item.keys()
        assert not missing, (
            f"dry-run result missing keys {missing} for prompt {item.get('prompt')!r}"
        )


def test_llm_benchmark_server_url_flag_accepted() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--json", "--server-url", "http://127.0.0.1:8000"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"--server-url flag rejected: returncode={result.returncode}\nstderr: {result.stderr}"
    )
    data = json.loads(result.stdout)
    assert len(data) >= 8


def test_llm_benchmark_default_server_url_reads_settings() -> None:
    """_default_server_url() must read from config/settings.json, not hardcode port 8080."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("llm_benchmark", str(SCRIPT))
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    url = mod._default_server_url()
    assert "8080" not in url, (
        f"_default_server_url() returned {url!r} — port 8080 is wrong; "
        "the product runtime uses 8000 (from config/settings.json)"
    )
    assert url.startswith("http"), f"Expected HTTP URL, got {url!r}"
