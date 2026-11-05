"""Tests of the report boundary, especially non-disclosure of raw secrets."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from normalize_scan import normalize


class NormalizeTests(unittest.TestCase):
    def test_gitleaks_strips_sensitive_fields(self):
        fake = [{"RuleID": "generic-api-key", "File": "app.py", "StartLine": 12,
                 "Commit": "abc", "Fingerprint": "abc:app.py:12",
                 "Secret": "SUPER-SENSITIVE", "Match": "password=SUPER-SENSITIVE",
                 "Author": "someone", "Email": "private@example.com"}]
        result = normalize("gitleaks", fake)
        exported = json.dumps(result)
        self.assertEqual(result["finding_count"], 1)
        for forbidden in ("SUPER-SENSITIVE", "password=", "private@example.com"):
            self.assertNotIn(forbidden, exported)

    def test_bandit_counts_severity(self):
        result = normalize("bandit", {"results": [{"test_id": "B105", "filename": "app.py",
            "line_number": 5, "issue_severity": "LOW", "issue_confidence": "MEDIUM",
            "code": "password='SECRET'"}]})
        self.assertEqual(result["by_severity"], {"LOW": 1})
        self.assertNotIn("SECRET", json.dumps(result))

    def test_pip_audit_keeps_only_id_and_fix(self):
        result = normalize("pip-audit", {"dependencies": [{"name": "abc", "version": "1.0",
            "vulns": [{"id": "PYSEC-0", "fix_versions": ["2.0"], "description": "secret"}]}]})
        self.assertEqual(result["finding_count"], 1)
        self.assertNotIn("secret", json.dumps(result))

    def test_npm_missing_vulnerabilities_is_operational_error(self):
        with self.assertRaises(ValueError):
            normalize("npm-audit", {"error": {"code": "EAUDIT"}})

    def test_cli_observation_and_new_secret_gate(self):
        script = Path(__file__).with_name("normalize_scan.py")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            for gated in (False, True):
                raw = path / "raw.json"
                safe = path / "safe.json"
                raw.write_text('[{"RuleID":"test","Secret":"SECRET"}]', encoding="utf-8")
                command = [sys.executable, str(script), "--tool", "gitleaks", "--input", str(raw),
                           "--output", str(safe), "--exit-code", "1"]
                if gated:
                    command.append("--fail-findings")
                outcome = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(outcome.returncode, 1 if gated else 0)
                self.assertFalse(raw.exists())
                self.assertNotIn("SECRET", safe.read_text(encoding="utf-8"))

    def test_bandit_high_gate_allows_justified_low_but_blocks_high(self):
        script = Path(__file__).with_name("normalize_scan.py")
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            for severity, expected in (("LOW", 0), ("HIGH", 1)):
                raw = directory / "raw.json"
                out = directory / "safe.json"
                raw.write_text(json.dumps({"results": [{"test_id": "B000",
                    "filename": "app.py", "line_number": 10,
                    "issue_severity": severity, "issue_confidence": "HIGH"}]}))
                result = subprocess.run([sys.executable, str(script),
                    "--tool", "bandit", "--input", str(raw),
                    "--output", str(out), "--exit-code", "1",
                    "--fail-severity", "HIGH"], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected)
                self.assertTrue(out.is_file())
                self.assertFalse(raw.exists())

    def test_operational_error_must_fail(self):
        script = Path(__file__).with_name("normalize_scan.py")
        with tempfile.TemporaryDirectory() as d:
            outcome = subprocess.run([sys.executable, str(script), "--tool", "gitleaks",
                "--input", str(Path(d)/"raw.json"), "--output", str(Path(d)/"safe.json"),
                "--exit-code", "2"], capture_output=True, text=True)
            self.assertEqual(outcome.returncode, 2)


if __name__ == "__main__":
    unittest.main()
