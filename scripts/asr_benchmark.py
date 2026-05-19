"""
ASR benchmark: run recorded WAV samples through available ASR backends.
Measures transcription quality without touching production settings.

Usage:
    .venv/bin/python scripts/asr_benchmark.py [options]

Backends:
    faster_whisper  (default)
    vosk
    whisper_cpp

Options:
    --model-size tiny|base|small|medium|large|<path>
    --compute-type int8|int8_float16|float16|float32
    --beam-size N
    --language auto|sample|en|pl
        auto   = let FasterWhisper detect language
        sample = use language field from index.json per WAV
        en/pl  = force all samples to that language
    --condition-on-previous-text true|false
    --vad-filter true|false
    --sweep     run multiple built-in config combinations
    --json-print  print full JSON results to stdout
    --json-out PATH
    --csv-out PATH
    --dry-run
    --input-dir DIR   (default: var/data/asr_test_samples)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INPUT_DIR = ROOT / "var" / "data" / "asr_test_samples"

SWEEP_CONFIGS: list[dict[str, Any]] = [
    {"model_size": "tiny",  "compute_type": "int8", "beam_size": 1, "language_mode": "auto",
     "condition_on_previous_text": False, "vad_filter": False},
    {"model_size": "tiny",  "compute_type": "int8", "beam_size": 3, "language_mode": "sample",
     "condition_on_previous_text": False, "vad_filter": False},
    {"model_size": "base",  "compute_type": "int8", "beam_size": 1, "language_mode": "sample",
     "condition_on_previous_text": False, "vad_filter": False},
    {"model_size": "base",  "compute_type": "int8", "beam_size": 3, "language_mode": "sample",
     "condition_on_previous_text": False, "vad_filter": False},
    {"model_size": "small", "compute_type": "int8", "beam_size": 1, "language_mode": "sample",
     "condition_on_previous_text": False, "vad_filter": False},
]

_TRANSCRIPTION_TIMEOUT_S = 60.0


def _load_settings() -> dict:
    try:
        with open(ROOT / "config" / "settings.json") as f:
            return json.load(f)
    except Exception:
        return {}


def _word_error_rough(expected: str, recognized: str) -> float:
    """Rough WER: (substitutions + length diff) / ref_len. Capped at 1.0."""
    ref = expected.lower().split()
    hyp = recognized.lower().split()
    if not ref:
        return 0.0 if not hyp else 1.0
    subs = sum(1 for r, h in zip(ref, hyp) if r != h)
    return min(1.0, (subs + abs(len(ref) - len(hyp))) / len(ref))


def _bool_arg(value: str) -> bool:
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


# ---------------------------------------------------------------------------
# FasterWhisper backend
# ---------------------------------------------------------------------------

def _load_faster_whisper_model(
    model_size: str,
    compute_type: str,
) -> tuple[Any, dict | None]:
    """Return (model, None) on success or (None, error_dict)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, {"status": "backend_unavailable", "error": "faster_whisper not installed"}
    try:
        model = WhisperModel(model_size, compute_type=compute_type, num_workers=1)
        return model, None
    except Exception as err:
        msg = str(err)
        if "no such file" in msg.lower() or "not found" in msg.lower() or "404" in msg.lower():
            return None, {"status": "model_unavailable", "error": f"model '{model_size}' not found: {err}"}
        return None, {"status": "error", "error": str(err)}


def _transcribe_single_fw(
    model: Any,
    wav_path: Path,
    language: str | None,
    *,
    beam_size: int,
    condition_on_previous_text: bool,
    vad_filter: bool,
    timeout_seconds: float = _TRANSCRIPTION_TIMEOUT_S,
) -> dict:
    """Transcribe one WAV file using a loaded WhisperModel. Runs in a thread with timeout."""
    result_holder: list[dict] = []
    error_holder: list[Exception] = []

    def _run() -> None:
        try:
            t0 = time.monotonic()
            kwargs: dict[str, Any] = {
                "beam_size": beam_size,
                "condition_on_previous_text": condition_on_previous_text,
                "vad_filter": vad_filter,
            }
            if language is not None:
                kwargs["language"] = language

            segments_iter, info = model.transcribe(str(wav_path), **kwargs)
            text = " ".join(s.text.strip() for s in segments_iter).strip()
            duration_ms = (time.monotonic() - t0) * 1000.0
            result_holder.append({
                "status": "ok",
                "recognized_text": text,
                "detected_language": getattr(info, "language", "?"),
                "duration_ms": round(duration_ms, 1),
            })
        except Exception as err:
            error_holder.append(err)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if t.is_alive():
        return {"status": "timeout", "error": f"transcription exceeded {timeout_seconds:.0f}s"}
    if error_holder:
        return {"status": "error", "error": str(error_holder[0])}
    return result_holder[0] if result_holder else {"status": "error", "error": "no result"}


def _run_config_faster_whisper(
    entries: list[dict],
    input_dir: Path,
    *,
    model_size: str,
    compute_type: str,
    beam_size: int,
    language_mode: str,
    condition_on_previous_text: bool,
    vad_filter: bool,
) -> list[dict]:
    """Load model once, run all entries, return rows."""
    print(
        f"  [fw] loading model_size={model_size!r} compute_type={compute_type!r} "
        f"beam_size={beam_size} language={language_mode!r} ...",
        end="",
        flush=True,
    )
    t_load = time.monotonic()
    model, load_err = _load_faster_whisper_model(model_size, compute_type)
    load_ms = (time.monotonic() - t_load) * 1000.0
    print(f" {load_ms:.0f}ms")

    if load_err is not None:
        return [
            {
                "file": entry["file"],
                "expected_text": entry["expected_text"],
                "language": entry["language"],
                "backend": "faster_whisper",
                "model_size": model_size,
                "compute_type": compute_type,
                "beam_size": beam_size,
                "language_mode": language_mode,
                "recognized_text": "",
                "duration_ms": None,
                "word_error_rough": None,
                **load_err,
            }
            for entry in entries
        ]

    results = []
    for entry in entries:
        wav_path = input_dir / entry["file"]
        if not wav_path.exists():
            results.append(_missing_row(entry, model_size, compute_type, beam_size, language_mode))
            continue

        sample_lang = entry["language"]
        if language_mode == "auto":
            fw_lang = None
        elif language_mode == "sample":
            fw_lang = sample_lang if sample_lang in {"pl", "en"} else None
        elif language_mode in {"pl", "en"}:
            fw_lang = language_mode
        else:
            fw_lang = None

        raw = _transcribe_single_fw(
            model,
            wav_path,
            fw_lang,
            beam_size=beam_size,
            condition_on_previous_text=condition_on_previous_text,
            vad_filter=vad_filter,
        )

        recognized = raw.get("recognized_text", "")
        expected = entry["expected_text"]
        wer = _word_error_rough(expected, recognized) if raw.get("status") == "ok" else None

        row: dict[str, Any] = {
            "file": entry["file"],
            "expected_text": expected,
            "language": sample_lang,
            "backend": "faster_whisper",
            "model_size": model_size,
            "compute_type": compute_type,
            "beam_size": beam_size,
            "language_mode": language_mode,
            "recognized_text": recognized,
            "detected_language": raw.get("detected_language"),
            "duration_ms": raw.get("duration_ms"),
            "word_error_rough": wer,
            "status": raw.get("status", "ok"),
        }
        if "error" in raw:
            row["error"] = raw["error"]
        results.append(row)

    return results


def _missing_row(entry: dict, model_size: str, compute_type: str, beam_size: int, language_mode: str) -> dict:
    return {
        "file": entry["file"],
        "expected_text": entry["expected_text"],
        "language": entry["language"],
        "backend": "faster_whisper",
        "model_size": model_size,
        "compute_type": compute_type,
        "beam_size": beam_size,
        "language_mode": language_mode,
        "recognized_text": "",
        "duration_ms": None,
        "word_error_rough": None,
        "status": "file_missing",
    }


# ---------------------------------------------------------------------------
# Vosk backend (unchanged, settings-based)
# ---------------------------------------------------------------------------

def _run_vosk_backend(entries: list[dict], input_dir: Path, settings: dict) -> list[dict]:
    try:
        import vosk
    except ImportError:
        return [{"status": "backend_unavailable", "error": "vosk not installed"}]

    asr_settings = settings.get("asr", {})
    model_paths = asr_settings.get("vosk_model_paths", {})

    import wave
    results = []
    for entry in entries:
        wav_path = input_dir / entry["file"]
        language = entry["language"]
        model_path = model_paths.get(language)
        if not model_path or not Path(model_path).exists():
            results.append({
                "file": entry["file"], "expected_text": entry["expected_text"],
                "language": language, "backend": "vosk",
                "status": "model_unavailable", "error": f"no vosk model for language={language}",
            })
            continue
        try:
            t0 = time.monotonic()
            model = vosk.Model(str(model_path))
            with wave.open(str(wav_path)) as wf:
                rec = vosk.KaldiRecognizer(model, wf.getframerate())
                rec.SetWords(True)
                frames = wf.readframes(wf.getnframes())
                rec.AcceptWaveform(frames)
                result = json.loads(rec.FinalResult())
            text = result.get("text", "").strip()
            duration_ms = (time.monotonic() - t0) * 1000.0
            wer = _word_error_rough(entry["expected_text"], text)
            results.append({
                "file": entry["file"], "expected_text": entry["expected_text"],
                "language": language, "backend": "vosk",
                "recognized_text": text, "duration_ms": round(duration_ms, 1),
                "word_error_rough": wer, "status": "ok",
            })
        except Exception as err:
            results.append({
                "file": entry["file"], "expected_text": entry["expected_text"],
                "language": language, "backend": "vosk",
                "status": "error", "error": str(err),
            })
    return results


# ---------------------------------------------------------------------------
# whisper.cpp backend (settings-based)
# ---------------------------------------------------------------------------

def _run_whisper_cpp_backend(entries: list[dict], input_dir: Path, settings: dict) -> list[dict]:
    import subprocess

    vi = settings.get("voice_input", {})
    cli_path = vi.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli")
    model_path = vi.get("model_path", "models/ggml-base.bin")
    full_cli = ROOT / cli_path
    full_model = ROOT / model_path

    if not full_cli.exists():
        return [{"status": "backend_unavailable", "error": f"whisper-cli not found: {full_cli}"}]
    if not full_model.exists():
        return [{"status": "model_unavailable", "error": f"model not found: {full_model}"}]

    results = []
    for entry in entries:
        wav_path = input_dir / entry["file"]
        if not wav_path.exists():
            results.append({"file": entry["file"], "status": "file_missing"}); continue

        lang_flag = entry["language"] if entry["language"] in {"pl", "en"} else "auto"
        cmd = [str(full_cli), "-m", str(full_model), "-f", str(wav_path), "-l", lang_flag, "--no-timestamps", "-np"]
        try:
            t0 = time.monotonic()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            duration_ms = (time.monotonic() - t0) * 1000.0
            if proc.returncode != 0:
                results.append({
                    "file": entry["file"], "expected_text": entry["expected_text"],
                    "language": entry["language"], "backend": "whisper_cpp",
                    "status": "error", "error": proc.stderr.strip()[:200],
                })
                continue
            text = proc.stdout.strip()
            wer = _word_error_rough(entry["expected_text"], text)
            results.append({
                "file": entry["file"], "expected_text": entry["expected_text"],
                "language": entry["language"], "backend": "whisper_cpp",
                "recognized_text": text, "duration_ms": round(duration_ms, 1),
                "word_error_rough": wer, "status": "ok",
            })
        except Exception as err:
            results.append({
                "file": entry["file"], "expected_text": entry["expected_text"],
                "language": entry["language"], "backend": "whisper_cpp",
                "status": "error", "error": str(err),
            })
    return results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_table(results: list[dict]) -> None:
    def _tr(s: str, n: int) -> str:
        return s if len(s) <= n else s[:n - 1] + "…"

    header = f"{'[LNG]':5} {'EXPECTED':<35} {'RECOGNIZED':<35} {'WER':>5} {'MS':>6} STATUS"
    print(header)
    print("-" * len(header))
    for row in results:
        lng = f"[{row.get('language', '?')}]"
        exp = _tr(row.get("expected_text", ""), 34)
        rec = _tr(row.get("recognized_text", ""), 34)
        wer = f"{row['word_error_rough']:.2f}" if row.get("word_error_rough") is not None else "  -  "
        ms = f"{row.get('duration_ms', 0):.0f}" if row.get("duration_ms") else "    -"
        status = row.get("status", "?")
        print(f"{lng:5} {exp:<35} {rec:<35} {wer:>5} {ms:>6} {status}")


def _summarize(results: list[dict], config_label: str = "") -> dict:
    ok_rows = [r for r in results if r.get("status") == "ok" and r.get("word_error_rough") is not None]
    en_rows = [r for r in ok_rows if r.get("language") == "en"]
    pl_rows = [r for r in ok_rows if r.get("language") == "pl"]

    def _avg_wer(rows: list[dict]) -> float | None:
        return sum(r["word_error_rough"] for r in rows) / len(rows) if rows else None

    def _avg_ms(rows: list[dict]) -> float | None:
        ms_rows = [r for r in rows if r.get("duration_ms") is not None]
        return sum(r["duration_ms"] for r in ms_rows) / len(ms_rows) if ms_rows else None

    worst = sorted(ok_rows, key=lambda r: r.get("word_error_rough", 0), reverse=True)[:3]

    return {
        "config": config_label,
        "n_ok": len(ok_rows),
        "n_total": len(results),
        "avg_wer": round(_avg_wer(ok_rows), 3) if _avg_wer(ok_rows) is not None else None,
        "en_avg_wer": round(_avg_wer(en_rows), 3) if _avg_wer(en_rows) is not None else None,
        "pl_avg_wer": round(_avg_wer(pl_rows), 3) if _avg_wer(pl_rows) is not None else None,
        "avg_duration_ms": round(_avg_ms(ok_rows), 1) if _avg_ms(ok_rows) is not None else None,
        "worst_samples": [
            {"file": r["file"], "expected": r["expected_text"],
             "recognized": r.get("recognized_text", ""), "wer": r["word_error_rough"]}
            for r in worst
        ],
    }


def _recommend(summaries: list[dict]) -> str:
    ok_summaries = [s for s in summaries if s.get("avg_wer") is not None]
    if not ok_summaries:
        return "No valid results — cannot recommend."

    best = min(ok_summaries, key=lambda s: s["avg_wer"])
    worst_ok = max(ok_summaries, key=lambda s: s["avg_wer"])

    lines = []
    lines.append(f"Best config:  {best['config']}  avg_wer={best['avg_wer']:.3f}  pl_wer={best.get('pl_avg_wer', '?')}")
    lines.append(f"Worst config: {worst_ok['config']}  avg_wer={worst_ok['avg_wer']:.3f}")

    best_wer = best.get("avg_wer", 1.0)
    best_pl = best.get("pl_avg_wer", 1.0) or 1.0
    best_ms = best.get("avg_duration_ms", 0) or 0

    if best_wer < 0.25:
        lines.append(f"Verdict: GOOD — avg WER {best_wer:.2f} < 0.25. Consider using {best['config']} in production.")
    elif best_wer < 0.45:
        lines.append(f"Verdict: ACCEPTABLE — avg WER {best_wer:.2f}. Acceptable for general questions.")
    else:
        lines.append(f"Verdict: WEAK — avg WER {best_wer:.2f} >= 0.45. Transcripts likely corrupted for Polish open questions.")

    if best_pl > 0.5:
        lines.append("Polish WER is still high (>0.50). Consider larger model or whisper.cpp for open PL questions.")
    elif best_pl > 0.25:
        lines.append("Polish WER improved but still above 0.25. Language=sample helps; beam_size=3 may help further.")

    if best_ms > 3000:
        lines.append(f"Warning: avg transcription time {best_ms:.0f}ms — may exceed real-time budget on RPi5.")
    elif best_ms > 0:
        lines.append(f"Speed: avg {best_ms:.0f}ms per sample — within acceptable range.")

    return "\n".join(lines)


def _write_csv(results: list[dict], csv_path: Path) -> None:
    if not results:
        return
    fieldnames = list(dict.fromkeys(k for r in results for k in r))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_single_config(
    entries: list[dict],
    input_dir: Path,
    *,
    backend: str,
    model_size: str,
    compute_type: str,
    beam_size: int,
    language_mode: str,
    condition_on_previous_text: bool,
    vad_filter: bool,
    settings: dict,
) -> list[dict]:
    if backend == "faster_whisper":
        return _run_config_faster_whisper(
            entries, input_dir,
            model_size=model_size,
            compute_type=compute_type,
            beam_size=beam_size,
            language_mode=language_mode,
            condition_on_previous_text=condition_on_previous_text,
            vad_filter=vad_filter,
        )
    if backend == "vosk":
        return _run_vosk_backend(entries, input_dir, settings)
    if backend == "whisper_cpp":
        return _run_whisper_cpp_backend(entries, input_dir, settings)
    return [{"status": "error", "error": f"unknown backend {backend!r}"}]


def run_sweep(entries: list[dict], input_dir: Path) -> tuple[list[list[dict]], list[dict]]:
    """Run all SWEEP_CONFIGS. Returns (all_results, all_summaries)."""
    all_results: list[list[dict]] = []
    all_summaries: list[dict] = []

    for cfg in SWEEP_CONFIGS:
        label = (
            f"{cfg['model_size']}/{cfg['compute_type']}/beam{cfg['beam_size']}"
            f"/lang={cfg['language_mode']}"
        )
        print(f"\n{'='*60}")
        print(f"Config: {label}")
        print(f"{'='*60}")

        rows = _run_config_faster_whisper(
            entries, input_dir,
            model_size=cfg["model_size"],
            compute_type=cfg["compute_type"],
            beam_size=cfg["beam_size"],
            language_mode=cfg["language_mode"],
            condition_on_previous_text=cfg["condition_on_previous_text"],
            vad_filter=cfg["vad_filter"],
        )
        _print_table(rows)
        summary = _summarize(rows, config_label=label)
        all_results.append(rows)
        all_summaries.append(summary)

    return all_results, all_summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR quality benchmark for NeXa (no settings changes)")
    parser.add_argument("--backend", choices=["faster_whisper", "vosk", "whisper_cpp"],
                        default="faster_whisper")
    parser.add_argument("--input-dir", type=str, default=str(INPUT_DIR))
    parser.add_argument("--model-size", type=str, default=None,
                        help="Model size or path (tiny/base/small/medium/large)")
    parser.add_argument("--compute-type", type=str, default=None,
                        help="Compute type (int8/int8_float16/float16/float32)")
    parser.add_argument("--beam-size", type=int, default=None)
    parser.add_argument("--language", type=str, default=None,
                        help="auto|sample|en|pl  (sample=use language from index.json)")
    parser.add_argument("--condition-on-previous-text", type=str, default="false",
                        dest="condition_on_previous_text")
    parser.add_argument("--vad-filter", type=str, default="false", dest="vad_filter")
    parser.add_argument("--sweep", action="store_true",
                        help="Run all built-in sweep configurations")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-print", action="store_true",
                        help="Print full JSON results to stdout (replaces table)")
    parser.add_argument("--json-out", type=str, default=None)
    parser.add_argument("--csv-out", type=str, default=None)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    index_path = input_dir / "index.json"

    if not index_path.exists():
        print(f"No index.json at {index_path}")
        print("Run scripts/record_asr_test_samples.py first.")
        sys.exit(1)

    with open(index_path) as f:
        entries = json.load(f)

    settings = _load_settings()
    vi = settings.get("voice_input", {})

    # Resolve defaults from settings.json (read-only)
    model_size = args.model_size or vi.get("model_size_or_path", "tiny")
    compute_type = args.compute_type or vi.get("compute_type", "int8")
    beam_size = args.beam_size if args.beam_size is not None else vi.get("beam_size", 1)
    language_mode = args.language or "auto"
    copt = _bool_arg(args.condition_on_previous_text)
    vad = _bool_arg(args.vad_filter)

    print(
        f"[asr_benchmark] samples={len(entries)} dir={input_dir} "
        f"backend={args.backend}"
    )

    if args.dry_run:
        print("Dry run — samples:")
        for e in entries:
            print(f"  [{e['language']}] {e['expected_text']} -> {e['file']}")
        return

    if args.sweep:
        all_results, all_summaries = run_sweep(entries, input_dir)

        print(f"\n{'='*60}")
        print("SWEEP SUMMARY")
        print(f"{'='*60}")
        for s in all_summaries:
            wer = f"{s['avg_wer']:.3f}" if s.get("avg_wer") is not None else "  N/A"
            en_wer = f"{s['en_avg_wer']:.3f}" if s.get("en_avg_wer") is not None else "  N/A"
            pl_wer = f"{s['pl_avg_wer']:.3f}" if s.get("pl_avg_wer") is not None else "  N/A"
            ms = f"{s['avg_duration_ms']:.0f}" if s.get("avg_duration_ms") else "  N/A"
            print(f"  {s['config']:<45} avg={wer}  en={en_wer}  pl={pl_wer}  ms={ms}")

        print(f"\n{'='*60}")
        print("RECOMMENDATION")
        print(f"{'='*60}")
        print(_recommend(all_summaries))

        all_rows_flat = [row for config_rows in all_results for row in config_rows]
        if args.json_print:
            print(json.dumps({"summaries": all_summaries, "results": all_rows_flat}, indent=2, ensure_ascii=False))
        if args.json_out:
            _write_json_out(args.json_out, {"summaries": all_summaries, "results": all_rows_flat})
        if args.csv_out:
            _write_csv(all_rows_flat, Path(args.csv_out))
        return

    # Single config run
    print(
        f"  model_size={model_size!r} compute_type={compute_type!r} beam_size={beam_size} "
        f"language={language_mode!r} condition_on_prev={copt} vad_filter={vad}"
    )
    print()

    results = run_single_config(
        entries, input_dir,
        backend=args.backend,
        model_size=model_size,
        compute_type=compute_type,
        beam_size=beam_size,
        language_mode=language_mode,
        condition_on_previous_text=copt,
        vad_filter=vad,
        settings=settings,
    )

    if args.json_print:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        _print_table(results)

    summary = _summarize(results, config_label=f"{model_size}/{compute_type}/beam{beam_size}/lang={language_mode}")
    print()
    print(f"  ok={summary['n_ok']}/{summary['n_total']}  avg_wer={summary.get('avg_wer', 'N/A')}  "
          f"en_wer={summary.get('en_avg_wer', 'N/A')}  pl_wer={summary.get('pl_avg_wer', 'N/A')}  "
          f"avg_ms={summary.get('avg_duration_ms', 'N/A')}")

    if args.json_out:
        _write_json_out(args.json_out, results)
    if args.csv_out:
        _write_csv(results, Path(args.csv_out))


def _write_json_out(path: str, data: Any) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[asr_benchmark] JSON written to {out_path}")


if __name__ == "__main__":
    main()
