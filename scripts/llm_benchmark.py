"""LLM runtime performance benchmark for NeXa.

Measures: health check latency, first token latency, tokens/sec, total response.
Supports --dry-run mode for CI/offline testing.

Usage:
  python scripts/llm_benchmark.py                        # real benchmark
  python scripts/llm_benchmark.py --dry-run              # mock mode (no server needed)
  python scripts/llm_benchmark.py --dry-run --json       # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _default_server_url() -> str:
    """Read server_url from config/settings.json; fall back to http://127.0.0.1:8000."""
    try:
        settings_path = REPO_ROOT / "config" / "settings.json"
        if not settings_path.exists():
            settings_path = REPO_ROOT / "config" / "settings.example.json"
        if settings_path.exists():
            import json as _json
            settings = _json.loads(settings_path.read_text(encoding="utf-8"))
            url = str((settings.get("llm") or {}).get("server_url") or "").strip()
            if url:
                return url
    except Exception:
        pass
    return "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# Mock results (used in --dry-run mode)
# ---------------------------------------------------------------------------

_MOCK_RESULTS: list[dict[str, Any]] = [
    {
        "prompt": "Who are you?",
        "language": "en",
        "health_check_ms": 2.1,
        "first_token_ms": None,
        "tokens_per_second": None,
        "total_ms": None,
        "status": "dry_run",
        "note": "dry-run: server not contacted",
    },
    {
        "prompt": "Kim jesteś?",
        "language": "pl",
        "health_check_ms": 2.0,
        "first_token_ms": None,
        "tokens_per_second": None,
        "total_ms": None,
        "status": "dry_run",
        "note": "dry-run: server not contacted",
    },
]


# ---------------------------------------------------------------------------
# Real benchmark
# ---------------------------------------------------------------------------

def _check_health(server_url: str, *, timeout: float = 2.0) -> tuple[bool, float]:
    try:
        import urllib.request
        t0 = time.perf_counter()
        with urllib.request.urlopen(f"{server_url}/health", timeout=timeout) as resp:
            elapsed = (time.perf_counter() - t0) * 1000
            ok = resp.status == 200
            return ok, elapsed
    except Exception:
        return False, (time.perf_counter() - t0) * 1000 if "t0" in dir() else -1.0


def _stream_prompt(server_url: str, prompt: str, *, timeout: float = 30.0) -> dict[str, Any]:
    try:
        import json as _json
        import urllib.request

        payload = _json.dumps({
            "prompt": f"[INST]{prompt}[/INST]",
            "n_predict": 200,
            "stream": True,
            "temperature": 0.2,
            "top_p": 0.9,
            "stop": ["\n\n", "[INST]", "[/INST]"],
        }).encode()

        req = urllib.request.Request(
            f"{server_url}/completion",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        t_start = time.perf_counter()
        first_token_ms: float | None = None
        token_count = 0
        full_text = ""

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                chunk_json = line[6:]
                if chunk_json == "[DONE]":
                    break
                try:
                    chunk = _json.loads(chunk_json)
                except Exception:
                    continue
                token = chunk.get("content", "")
                if token:
                    if first_token_ms is None:
                        first_token_ms = (time.perf_counter() - t_start) * 1000
                    token_count += 1
                    full_text += token
                if chunk.get("stop", False):
                    break

        total_ms = (time.perf_counter() - t_start) * 1000
        tokens_per_sec = (token_count / (total_ms / 1000.0)) if total_ms > 0 else None

        return {
            "first_token_ms": first_token_ms,
            "tokens_per_second": tokens_per_sec,
            "total_ms": total_ms,
            "token_count": token_count,
            "response_preview": full_text[:120].replace("\n", " "),
            "status": "ok",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

PROMPTS = [
    ("Who are you?", "en"),
    ("Explain what a black hole is in two short sentences.", "en"),
    ("Give me three steps to clean my desk.", "en"),
    ("Tell me what you can help me with.", "en"),
    ("Kim jesteś?", "pl"),
    ("Wyjaśnij w dwóch krótkich zdaniach czym jest czarna dziura.", "pl"),
    ("Podaj trzy kroki jak uporządkować biurko.", "pl"),
    ("Powiedz, w czym możesz mi pomóc.", "pl"),
]


def run_dry_run() -> list[dict[str, Any]]:
    results = []
    for prompt, language in PROMPTS:
        results.append({
            "prompt": prompt,
            "language": language,
            "health_check_ms": 1.5,
            "first_token_ms": None,
            "tokens_per_second": None,
            "total_ms": None,
            "token_count": 0,
            "status": "dry_run",
            "note": "dry-run mode: server not contacted, all latency fields are None",
        })
    return results


def run_real_benchmark(server_url: str) -> list[dict[str, Any]]:
    health_ok, health_ms = _check_health(server_url)

    if not health_ok:
        print(f"[llm-benchmark] health check failed for {server_url} — is llama-server running?")
        return [{
            "status": "health_failed",
            "server_url": server_url,
            "health_check_ms": health_ms,
            "note": "Server unreachable. Run with --dry-run for offline testing.",
        }]

    print(f"[llm-benchmark] health ok, health_check_ms={health_ms:.1f}")

    results = []
    for prompt, language in PROMPTS:
        print(f"[llm-benchmark] prompting ({language}): {prompt[:60]!r}...")
        stream_result = _stream_prompt(server_url, prompt)
        result = {
            "prompt": prompt,
            "language": language,
            "health_check_ms": health_ms,
            **stream_result,
        }
        results.append(result)
        if stream_result.get("status") == "ok":
            print(
                f"  first_token_ms={stream_result.get('first_token_ms', 'n/a'):.0f}  "
                f"tokens/sec={stream_result.get('tokens_per_second', 0):.1f}  "
                f"total_ms={stream_result.get('total_ms', 0):.0f}"
                if stream_result.get("first_token_ms") is not None else "  (no tokens)"
            )
        else:
            print(f"  error: {stream_result.get('error', 'unknown')}")
    return results


def _print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== LLM Benchmark Summary ===")
    for r in results:
        status = r.get("status", "?")
        prompt = r.get("prompt", "?")[:50]
        if status == "dry_run":
            print(f"  [{r.get('language', '?')}] {prompt!r} — dry-run (no server)")
        elif status == "ok":
            print(
                f"  [{r.get('language', '?')}] {prompt!r}: "
                f"first_token={r.get('first_token_ms', 'n/a'):.0f}ms  "
                f"tps={r.get('tokens_per_second', 0):.1f}  "
                f"total={r.get('total_ms', 0):.0f}ms"
                if r.get("first_token_ms") is not None else
                f"  [{r.get('language', '?')}] {prompt!r} — no tokens produced"
            )
        else:
            print(f"  [{r.get('language', '?')}] {prompt!r} — {status}: {r.get('error', r.get('note', ''))}")


def main() -> int:
    parser = argparse.ArgumentParser(description="NeXa LLM runtime benchmark")
    parser.add_argument("--dry-run", action="store_true", help="Mock mode — no server needed")
    parser.add_argument(
        "--server-url",
        default=None,
        help="llama-server URL (default: from config/settings.json or http://127.0.0.1:8000)",
    )
    parser.add_argument("--json", dest="json_output", action="store_true", help="JSON output to stdout")
    args = parser.parse_args()

    server_url = args.server_url or _default_server_url()

    if args.dry_run:
        results = run_dry_run()
    else:
        results = run_real_benchmark(server_url)

    if args.json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_summary(results)

    failed = sum(1 for r in results if r.get("status") not in {"ok", "dry_run"})
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
