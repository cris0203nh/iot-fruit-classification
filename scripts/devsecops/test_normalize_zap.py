"""Validaciones del perímetro del reporte DAST y del gate de severidad."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from normalize_zap import normalize

SCRIPT = Path(__file__).with_name("normalize_zap.py")


def example(risk="2", rule="10020", count="3"):
    return {"site": [{"@name": "http://localhost:8765/token?secret=EXPOSED",
                      "alerts": [{"pluginid": rule, "riskcode": risk,
                                  "count": count,
                                  "instances": [{"uri": "http://x/?token=EXPOSED",
                                                 "requestHeader": "Bearer EXPOSED"}],
                                  "evidence": "EXPOSED"}]}]}


class ZapNormalizerTests(unittest.TestCase):
    def run_cli(self, report, exit_code):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / "raw.json", Path(tmp) / "safe.json"
            source.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source),
                                     "--output", str(dest), "--exit-code", str(exit_code),
                                     "--fail-severity", "HIGH"],
                                    capture_output=True, text=True, check=False)
            return result.returncode, not source.exists(), dest.read_text() if dest.exists() else None

    def test_no_secret_or_urls_in_sanitized_report(self):
        safe = json.dumps(normalize(example()))
        self.assertNotIn("EXPOSED", safe)
        self.assertNotIn("Bearer", safe)
        self.assertNotIn("http", safe)
        self.assertEqual(normalize(example())["finding_count"], 1)
        self.assertEqual(normalize(example())["by_severity"]["MEDIUM"], 1)

    def test_low_and_medium_do_not_block(self):
        for risk in ("0", "1", "2"):
            code, removed, output = self.run_cli(example(risk=risk), 2)
            self.assertEqual(code, 0)
            self.assertTrue(removed)
            self.assertIsNotNone(output)

    def test_high_and_critical_block(self):
        for risk in ("3", "4"):
            code, removed, output = self.run_cli(example(risk=risk), 1)
            self.assertEqual(code, 1)
            self.assertTrue(removed)
            self.assertIsNotNone(output)

    def test_operational_error_fails_closed(self):
        code, removed, output = self.run_cli(example(), 3)
        self.assertEqual(code, 2)
        self.assertTrue(removed)
        self.assertIsNone(output)

    def test_invalid_and_empty_reports_fail_closed(self):
        for bad in ({}, {"site": []}, {"site": [{}]}, example(risk="5"),
                    example(rule="invalid"), example(count="-1")):
            with self.assertRaises(ValueError):
                normalize(bad)
        code, removed, output = self.run_cli({"site": []}, 0)
        self.assertEqual(code, 2)
        self.assertTrue(removed)
        self.assertIsNone(output)

    def test_valid_clean_report_passes(self):
        report = {"site": [{"@name": "http://localhost:8765", "alerts": []}]}
        code, removed, output = self.run_cli(report, 0)
        self.assertEqual(code, 0)
        self.assertTrue(removed)
        self.assertEqual(json.loads(output)["finding_count"], 0)

    def test_duplicate_rules_aggregate_instances(self):
        report = example()
        report["site"].append(example()["site"][0])
        normalized = normalize(report)
        self.assertEqual(normalized["finding_count"], 1)
        self.assertEqual(normalized["findings"][0]["occurrences"], 6)


if __name__ == "__main__":
    unittest.main()
