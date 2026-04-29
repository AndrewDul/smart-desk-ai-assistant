from __future__ import annotations

from types import SimpleNamespace

from modules.core.assistant_impl.response_mixin import CoreAssistantResponseMixin


def test_text_only_stream_report_is_not_treated_as_audio_delivery() -> None:
    report = SimpleNamespace(
        chunks_spoken=0,
        full_text="My name is NeXa.",
    )

    assert CoreAssistantResponseMixin._stream_report_delivered(report) is False


def test_spoken_stream_report_is_treated_as_delivered() -> None:
    report = SimpleNamespace(
        chunks_spoken=1,
        full_text="My name is NeXa.",
    )

    assert CoreAssistantResponseMixin._stream_report_delivered(report) is True


def test_finalize_response_report_does_not_invent_spoken_chunks_from_text() -> None:
    mixin = CoreAssistantResponseMixin.__new__(CoreAssistantResponseMixin)

    report = SimpleNamespace(
        chunks_spoken=0,
        full_text="My name is NeXa.",
        display_title="",
        display_lines=[],
        chunk_kinds=[],
        live_streaming=False,
        started_at_monotonic=10.0,
        finished_at_monotonic=11.0,
        first_audio_started_at_monotonic=0.0,
        first_audio_latency_ms=0.0,
        first_chunk_started_at_monotonic=0.0,
        first_chunk_latency_ms=0.0,
        first_sentence_started_at_monotonic=0.0,
        first_sentence_latency_ms=0.0,
        total_elapsed_ms=1000.0,
    )

    finalized = mixin._finalize_response_stream_report(
        stream_report=report,
        started_at=10.0,
        finished_at=11.0,
        full_text="My name is NeXa.",
        display_title="",
        display_lines=[],
        default_chunk_kinds=["content"],
    )

    assert finalized.full_text == "My name is NeXa."
    assert finalized.chunks_spoken == 0
