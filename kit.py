"""Synthetic LSP boundary acceptance kit; no network, dynamic imports or user-file edits."""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import platform
from typing import Callable

ENCODINGS = ("utf-8", "utf-16", "utf-32")


class Unsupported(ValueError):
    """Outside this kit's declared input/encoding policy, not a protocol verdict."""


def encoding_for(client_encodings=None, server_encoding=None):
    """Validate the actual initialization result; do not invent negotiation."""
    if client_encodings is not None and (
        not isinstance(client_encodings, list)
        or any(not isinstance(x, str) for x in client_encodings)
    ):
        raise Unsupported("Invalid client positionEncodings")
    offered = set(client_encodings or ()) | {"utf-16"}
    selected = "utf-16" if server_encoding is None else server_encoding
    if not isinstance(selected, str) or selected not in ENCODINGS or selected not in offered:
        raise Unsupported("Unimplemented or unoffered selected encoding")
    return selected


def _units(text, encoding):
    if encoding == "utf-8":
        return len(text.encode("utf-8"))
    if encoding == "utf-16":
        return len(text.encode("utf-16-le")) // 2
    if encoding == "utf-32":
        return len(text)
    raise Unsupported("Unimplemented encoding")


def _lines(text):
    # Python splitlines also recognizes separators which LSP does not call EOL.
    text.encode("utf-8")  # This kit accepts Unicode scalar text, not lone surrogates.
    result, start, i = [], 0, 0
    while i < len(text):
        if text[i] in "\r\n":
            result.append((start, i))
            i += 2 if text[i:i + 2] == "\r\n" else 1
            start = i
        else:
            i += 1
    result.append((start, len(text)))
    return result


def byte_position(text, byte_offset, encoding):
    if type(byte_offset) is not int or not 0 <= byte_offset <= len(text.encode("utf-8")):
        raise Unsupported("Byte offset out of bounds")
    try:
        index = len(text.encode("utf-8")[:byte_offset].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise Unsupported("Byte offset is inside a scalar") from exc
    for line, (start, end) in enumerate(_lines(text)):
        if start <= index <= end:
            return {"line": line, "character": _units(text[start:index], encoding)}
    raise Unsupported("Byte offset is inside CRLF")


def byte_range(text, span, encoding):
    if not isinstance(span, (list, tuple)) or len(span) != 2 or span[0] > span[1]:
        raise Unsupported("Invalid byte span")
    return {"start": byte_position(text, span[0], encoding),
            "end": byte_position(text, span[1], encoding)}


def position_index(text, position, encoding):
    if not isinstance(position, dict) or any(type(position.get(k)) is not int for k in ("line", "character")):
        raise Unsupported("Position must contain integer line and character")
    line, character = position["line"], position["character"]
    rows = _lines(text)
    if not 0 <= line < len(rows) or character < 0:
        raise Unsupported("Position outside supported line/column policy")
    start, end = rows[line]
    if character >= _units(text[start:end], encoding):
        return end  # LSP character overflow clamps to line end.
    used = 0
    for index in range(start, end):
        if used == character:
            return index
        used += _units(text[index], encoding)
        if used > character:
            raise Unsupported("Position splits an encoded scalar")
    return end


def _indices(text, edit, encoding):
    start = position_index(text, edit["range"]["start"], encoding)
    end = position_index(text, edit["range"]["end"], encoding)
    if start > end or not isinstance(edit.get("text"), str):
        raise Unsupported("Reversed range or non-text replacement")
    edit["text"].encode("utf-8")
    return start, end, edit["text"]


def apply_sequential(text, changes, encoding):
    """didChange contentChanges: each range belongs to the preceding result."""
    for change in changes:
        if "range" not in change:
            text = change["text"]
            _lines(text)
        else:
            start, end, replacement = _indices(text, change, encoding)
            text = text[:start] + replacement + text[end:]
    return text


def apply_simultaneous(text, edits, encoding):
    """Non-overlapping TextEdit batch: all ranges belong to the original text.

    This example excludes equal-start edits, even though LSP permits certain ones.
    """
    spans = sorted(_indices(text, edit, encoding) for edit in edits)
    for previous, current in zip(spans, spans[1:]):
        if previous[0] == current[0] or previous[1] > current[0]:
            raise Unsupported("Overlapping or equal-start batch edits")
    for start, end, replacement in reversed(spans):
        text = text[:start] + replacement + text[end:]
    return text


def _wrong_units(text, span, encoding):
    return byte_range(text, span, "utf-32")


def _stale_changes(text, changes, encoding):
    spans = [_indices(text, edit, encoding) for edit in changes]
    for start, end, replacement in spans:
        text = text[:start] + replacement + text[end:]
    return text


@dataclass(frozen=True)
class Adapter:
    """Explicit trusted callables. The CLI never loads arbitrary code."""
    name: str
    convert: Callable = byte_range
    sequential: Callable = apply_sequential
    simultaneous: Callable = apply_simultaneous
    supported_encodings: tuple = ENCODINGS


def fixture_cases():
    return json.loads(Path(__file__).with_name("fixtures.json").read_text(encoding="utf-8"))["cases"]


def audit(adapter):
    """Pass only original synthetic fixture inputs to the adapter.

    Manual source snapshots are inputs for conversion. Expected coordinates and
    final text are separate literal assertions, never calculated by this adapter.
    """
    if "utf-16" not in adapter.supported_encodings:
        raise Unsupported("An LSP adapter must support the UTF-16 default")
    results = []
    for case in fixture_cases():
        encoding = encoding_for(case.get("client_position_encodings"), case.get("server_position_encoding"))
        if encoding not in adapter.supported_encodings:
            results.append({"id": case["id"], "encoding": encoding, "status": "skipped",
                            "reason": "optional encoding not implemented by adapter"})
            continue
        actual_ranges, errors, changes = [], [], []
        try:
            for edit in case["edits"]:
                converted = adapter.convert(edit["source"], copy.deepcopy(edit["byte_span"]), encoding)
                actual_ranges.append(copy.deepcopy(converted))
                changes.append({"range": converted, "text": edit["replacement"]})
            expected_ranges = [edit["expected_range"] for edit in case["edits"]]
            if actual_ranges != expected_ranges:
                errors.append("coordinate_mismatch")
            apply = adapter.sequential if case["kind"] == "didChange" else adapter.simultaneous
            actual_text = apply(case["initial"], changes, encoding)
            if actual_text != case["expected_text"]:
                errors.append("final_text_mismatch")
            detail = {"actual_ranges": actual_ranges, "actual_text": actual_text}
        except Exception as exc:
            # No traceback, arbitrary exception text, user files or environment values.
            errors.append("adapter_error:" + type(exc).__name__)
            detail = {"actual_ranges": actual_ranges}
        results.append({"id": case["id"], "encoding": encoding,
                        "status": "failed" if errors else "passed", "errors": errors, **detail})
    counts = {status: sum(r["status"] == status for r in results) for status in ("passed", "failed", "skipped")}
    return {"schema_version": 1, "adapter": adapter.name, "python": platform.python_version(),
            "fixture_scope": "synthetic-only", "counts": counts,
            "status": "failed" if counts["failed"] else "passed_with_skips" if counts["skipped"] else "passed",
            "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=("correct", "wrong-units", "stale-changes", "serial-batch"), default="correct")
    args = parser.parse_args()
    adapters = {"correct": Adapter("correct"),
                "wrong-units": Adapter("wrong-units", convert=_wrong_units),
                "stale-changes": Adapter("stale-changes", sequential=_stale_changes),
                "serial-batch": Adapter("serial-batch", simultaneous=apply_sequential)}
    report = audit(adapters[args.adapter])
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return int(report["counts"]["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
