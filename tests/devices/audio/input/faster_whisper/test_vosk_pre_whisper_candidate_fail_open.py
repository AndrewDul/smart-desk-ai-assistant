from __future__ import annotations

import ast
from pathlib import Path


CORE_PATH = Path("modules/devices/audio/input/faster_whisper/backend/core.py")


def _parse_core() -> ast.Module:
    return ast.parse(CORE_PATH.read_text(encoding="utf-8"))


def _function_by_name(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function not found: {name}")


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def test_vosk_pre_whisper_transcript_converter_does_not_use_stale_local_name() -> None:
    tree = _parse_core()
    function = _function_by_name(
        tree,
        "_transcript_result_from_vosk_pre_whisper_candidate",
    )

    stale_names = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and node.id == "pre_whisper_candidate"
    ]

    assert stale_names == []


def test_vosk_pre_whisper_accepted_candidate_conversion_is_fail_open() -> None:
    tree = _parse_core()
    parents = _parent_map(tree)

    conversion_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "_transcript_result_from_vosk_pre_whisper_candidate"
        ):
            conversion_calls.append(node)

    assert conversion_calls, "Expected Vosk pre-Whisper transcript conversion call."

    guarded_calls = []
    for call in conversion_calls:
        current: ast.AST | None = call
        while current is not None:
            current = parents.get(current)
            if isinstance(current, ast.Try):
                guarded_calls.append(call)
                break

    assert guarded_calls == conversion_calls

    source = CORE_PATH.read_text(encoding="utf-8")
    assert "failed safely; falling back to FasterWhisper" in source
