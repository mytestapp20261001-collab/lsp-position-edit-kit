import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import kit


def edit(start_line, start_col, end_line, end_col, text):
    return {"range": {"start": {"line": start_line, "character": start_col},
                      "end": {"line": end_line, "character": end_col}}, "text": text}


class KitTests(unittest.TestCase):
    def test_correct_all_cases(self):
        report = kit.audit(kit.Adapter("correct"))
        self.assertEqual(report["counts"], {"passed": 13, "failed": 0, "skipped": 0})

    def test_wrong_units_detected(self):
        report = kit.audit(kit.Adapter("wrong", convert=kit._wrong_units))
        self.assertEqual(report["counts"]["failed"], 7)
        self.assertIn("coordinate_mismatch", next(c for c in report["cases"] if c["id"] == "astral-utf-16")["errors"])

    def test_stale_coordinates_detected(self):
        report = kit.audit(kit.Adapter("stale", sequential=kit._stale_changes))
        self.assertEqual([c["id"] for c in report["cases"] if c["status"] == "failed"], ["sequential-shifting-snapshot"])

    def test_sequential_batch_detected(self):
        report = kit.audit(kit.Adapter("serial", simultaneous=kit.apply_sequential))
        self.assertEqual([c["id"] for c in report["cases"] if c["status"] == "failed"], ["simultaneous-original-snapshot"])

    def test_literal_oracle_consistency_using_byte_splices(self):
        # Independent of all kit conversion/application routines: splice UTF-8
        # bytes directly, and check manually stored snapshots and final strings.
        for case in kit.fixture_cases():
            with self.subTest(case=case["id"]):
                data = case["initial"].encode("utf-8")
                if case["kind"] == "didChange":
                    for change in case["edits"]:
                        self.assertEqual(data.decode("utf-8"), change["source"])
                        start, end = change["byte_span"]
                        data = data[:start] + change["replacement"].encode("utf-8") + data[end:]
                else:
                    for change in sorted(case["edits"], key=lambda e: e["byte_span"][0], reverse=True):
                        self.assertEqual(case["initial"], change["source"])
                        start, end = change["byte_span"]
                        data = data[:start] + change["replacement"].encode("utf-8") + data[end:]
                self.assertEqual(data.decode("utf-8"), case["expected_text"])

    def test_negotiation_default_and_implicit_utf16(self):
        self.assertEqual(kit.encoding_for(), "utf-16")
        self.assertEqual(kit.encoding_for(["utf-8"]), "utf-16")
        self.assertEqual(kit.encoding_for(["utf-8"], "utf-16"), "utf-16")
        self.assertEqual(kit.encoding_for([], None), "utf-16")

    def test_negotiation_explicit(self):
        for encoding in kit.ENCODINGS:
            self.assertEqual(kit.encoding_for([encoding], encoding), encoding)

    def test_negotiation_rejects_unoffered_or_unknown_selection(self):
        for offered, selected in [(None, "utf-8"), (["utf-8"], "utf-32"), (["future"], "future"), ([], ""), ([1], None), ("utf-8", None)]:
            with self.subTest(offered=offered, selected=selected), self.assertRaises(kit.Unsupported):
                kit.encoding_for(offered, selected)

    def test_optional_encodings_skip_honestly(self):
        report = kit.audit(kit.Adapter("utf16-only", supported_encodings=("utf-16",)))
        self.assertEqual(report["counts"], {"passed": 10, "failed": 0, "skipped": 3})
        self.assertEqual(report["status"], "passed_with_skips")

    def test_utf16_missing_is_not_silent_skip(self):
        with self.assertRaises(kit.Unsupported):
            kit.audit(kit.Adapter("invalid", supported_encodings=("utf-8",)))

    def test_byte_boundaries(self):
        for offset in [-1, 1, 2, 3, 6, True, 1.0]:
            with self.subTest(offset=offset), self.assertRaises(kit.Unsupported):
                kit.byte_position("😀a", offset, "utf-16")
        self.assertEqual(kit.byte_position("😀a", 4, "utf-16"), {"line": 0, "character": 2})

    def test_crlf_midpoint_rejected(self):
        with self.assertRaises(kit.Unsupported):
            kit.byte_position("a\r\nb", 2, "utf-16")
        self.assertEqual(kit.byte_position("a\r\nb", 3, "utf-16"), {"line": 1, "character": 0})

    def test_line_endings_and_non_eol_unicode(self):
        self.assertEqual(kit.byte_position("a\rb", 2, "utf-16"), {"line": 1, "character": 0})
        self.assertEqual(kit.byte_position("a\nb", 2, "utf-16"), {"line": 1, "character": 0})
        self.assertEqual(kit.byte_position("a\u2028b", 4, "utf-16"), {"line": 0, "character": 2})

    def test_empty_document(self):
        self.assertEqual(kit.byte_position("", 0, "utf-16"), {"line": 0, "character": 0})
        self.assertEqual(kit.apply_sequential("", [edit(0, 0, 0, 0, "😀")], "utf-16"), "😀")

    def test_character_overflow_clamps_before_eol(self):
        for encoding in kit.ENCODINGS:
            self.assertEqual(kit.position_index("😀\r\nx", {"line": 0, "character": 999}, encoding), 1)

    def test_invalid_positions(self):
        for pos in [{"line": -1, "character": 0}, {"line": 2, "character": 0}, {"line": 0, "character": -1},
                    {"line": True, "character": 0}, {"line": 0, "character": 0.5}, {}, None]:
            with self.subTest(pos=pos), self.assertRaises(kit.Unsupported):
                kit.position_index("😀", pos, "utf-16")
        with self.assertRaises(kit.Unsupported):
            kit.position_index("😀", {"line": 0, "character": 1}, "utf-16")
        with self.assertRaises(kit.Unsupported):
            kit.position_index("中", {"line": 0, "character": 1}, "utf-8")

    def test_reversed_range_rejected(self):
        with self.assertRaises(kit.Unsupported):
            kit.apply_sequential("ab", [edit(0, 2, 0, 0, "x")], "utf-16")

    def test_batch_uses_original_even_if_input_reversed(self):
        batch = [edit(0, 3, 0, 5, "longer"), edit(0, 6, 0, 8, "B")]
        self.assertEqual(kit.apply_simultaneous("😀 aa bb\n", list(reversed(batch)), "utf-16"), "😀 longer B\n")

    def test_batch_overlap_and_equal_start_policy(self):
        for batch in [[edit(0, 0, 0, 2, "x"), edit(0, 1, 0, 3, "y")],
                      [edit(0, 0, 0, 0, "x"), edit(0, 0, 0, 0, "y")]]:
            with self.assertRaises(kit.Unsupported):
                kit.apply_simultaneous("abcd", batch, "utf-16")

    def test_full_change_resets_snapshot(self):
        self.assertEqual(kit.apply_sequential("old", [{"text": "😀 x"}, edit(0, 3, 0, 4, "Y")], "utf-16"), "😀 Y")

    def test_adapter_exception_is_bounded_report(self):
        def broken(*args):
            raise RuntimeError("do not echo arbitrary messages")
        report = kit.audit(kit.Adapter("broken", convert=broken))
        self.assertEqual(report["counts"]["failed"], 13)
        self.assertNotIn("do not echo", json.dumps(report))

    def test_input_span_mutation_does_not_change_oracle(self):
        def mutating(text, span, encoding):
            span[0] = 0
            return kit.byte_range(text, span, encoding)
        self.assertGreater(kit.audit(kit.Adapter("mutating", convert=mutating))["counts"]["failed"], 0)
        self.assertEqual(kit.audit(kit.Adapter("correct"))["counts"]["failed"], 0)

    def test_cli_json_and_exit_codes(self):
        script = str(Path(kit.__file__).resolve())
        for adapter in ["correct", "wrong-units", "stale-changes", "serial-batch"]:
            result = subprocess.run([sys.executable, "-B", script, "--adapter", adapter], capture_output=True, text=True, timeout=5)
            report = json.loads(result.stdout)
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.returncode, 0 if adapter == "correct" else 1)
            self.assertEqual(report["schema_version"], 1)

    def test_audit_has_no_stdout_side_effects(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            kit.audit(kit.Adapter("correct"))
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
