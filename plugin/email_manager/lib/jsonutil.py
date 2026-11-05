"""Tolerant JSON parsing, ported from Email Manager v3.0.0 core/ai.py.

Models (especially reasoning models) may return bare JSON, fenced JSON, JSONL,
or a truncated JSON array. The workflow must never throw a whole batch away just
because one of those shapes appeared.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional


def parse_json(text: str) -> Optional[Any]:
    """Parse JSON out of model output: whole text, fenced/embedded, or JSONL."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            continue

    values = _decode_stream(cleaned)
    if values:
        return values if len(values) > 1 else values[0]
    return None


def _decode_stream(text: str) -> Optional[list]:
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    decoder = json.JSONDecoder()
    out = []
    index = min(starts)
    while index < len(text):
        while index < len(text) and text[index] in " \t\r\n,":
            index += 1
        if index >= len(text):
            break
        try:
            value, index = decoder.raw_decode(text, index)
        except ValueError:
            break
        out.append(value)
    return out or None


def salvage_array(text: str) -> Optional[List[Any]]:
    """Recover complete elements from a truncated JSON array."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("[")
    if start == -1:
        return None
    decoder = json.JSONDecoder()
    out: List[Any] = []
    index = start + 1
    while index < len(cleaned):
        while index < len(cleaned) and cleaned[index] in " \t\r\n,":
            index += 1
        if index >= len(cleaned):
            break
        try:
            value, end = decoder.raw_decode(cleaned, index)
        except ValueError:
            break
        out.append(value)
        index = end
    return out or None


def looks_truncated(text: str) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"```(?:json)?", "", text)
    return cleaned.count("[") > cleaned.count("]") or cleaned.count("{") > cleaned.count("}")


def as_text_list(payload: Any) -> Optional[List[str]]:
    """Normalise a model payload into a list of strings (report one-liners)."""
    candidates = list(payload.values()) if isinstance(payload, dict) else [payload]
    for candidate in candidates:
        if isinstance(candidate, str):
            candidate = parse_json(candidate) or salvage_array(candidate)
        if isinstance(candidate, list) and candidate and all(isinstance(x, str) for x in candidate):
            return candidate
    return None
