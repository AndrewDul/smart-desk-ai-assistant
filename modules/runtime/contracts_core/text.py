from __future__ import annotations

import re
import uuid

from .enums import StreamMode


def create_turn_id(prefix: str = "turn") -> str:
    """Return a short trace-friendly ID."""

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_text(text: str) -> str:
    """Normalize free-form user or assistant text for comparisons."""

    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def clean_response_text(text: str) -> str:
    """Prepare assistant text before it becomes a stream chunk."""

    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned


def chunk_text_for_streaming(
    text: str,
    language: str,
    mode: StreamMode = StreamMode.SENTENCE,
    *,
    min_chunk_chars: int = 24,
) -> list["AssistantChunk"]:
    """
    Convert assistant text into chunks suitable for premium low-latency TTS.
    """

    from .response import AssistantChunk

    cleaned = clean_response_text(text)
    if not cleaned:
        return []

    if mode == StreamMode.WHOLE_RESPONSE:
        return [AssistantChunk(text=cleaned, language=language, sequence_index=0)]

    if mode == StreamMode.PARAGRAPH:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
        return [
            AssistantChunk(text=paragraph, language=language, sequence_index=index)
            for index, paragraph in enumerate(paragraphs)
        ]

    sentences = _split_into_sentences(cleaned)
    merged_sentences = _merge_short_sentences(sentences, min_chunk_chars=min_chunk_chars)

    return [
        AssistantChunk(text=sentence, language=language, sequence_index=index)
        for index, sentence in enumerate(merged_sentences)
    ]


def _split_into_sentences(text: str) -> list[str]:
    """
    Split text into clean sentence-like units.

    The regex is intentionally conservative.
    It protects common abbreviations and decimal numbers.
    """

    protected = text
    protected = re.sub(
        r"\b(e\.g|i\.e|mr|mrs|ms|dr|prof)\.",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected,
        flags=re.IGNORECASE,
    )
    protected = re.sub(
        r"\b(np|itd|itp|dr|prof)\.",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected,
        flags=re.IGNORECASE,
    )
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", protected)

    parts = re.split(r"(?<=[.!?])\s+", protected)
    sentences = [part.replace("<DOT>", ".").strip() for part in parts if part and part.strip()]

    if sentences:
        return sentences

    fallback = clean_response_text(text)
    return [fallback] if fallback else []


def _merge_short_sentences(sentences: list[str], *, min_chunk_chars: int) -> list[str]:
    if not sentences:
        return []

    merged: list[str] = []
    buffer = ""

    for sentence in sentences:
        current = sentence.strip()
        if not current:
            continue

        if not buffer:
            buffer = current
            continue

        if len(buffer) < min_chunk_chars:
            buffer = f"{buffer} {current}".strip()
            continue

        merged.append(buffer)
        buffer = current

    if buffer:
        if merged and len(buffer) < max(12, min_chunk_chars // 2):
            merged[-1] = f"{merged[-1]} {buffer}".strip()
        else:
            merged.append(buffer)

    return merged


__all__ = [
    "chunk_text_for_streaming",
    "clean_response_text",
    "create_turn_id",
    "normalize_text",
]