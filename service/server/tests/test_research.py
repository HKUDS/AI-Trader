"""Tests for the last30days research adapter.

Exercises parsing, timeout, missing-binary, and JSON-shape tolerance. We
don't run the actual last30days CLI here (slow + network-dependent) —
instead we point the adapter at a fake script via the LAST30DAYS_SCRIPT
env hook and inject controllable behaviour.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from research import last30days_client as l30


def _write_fake_script(directory: Path, body: str) -> Path:
    """Create an executable Python script that emulates the CLI."""
    script = directory / "fake_last30days.py"
    script.write_text("#!/usr/bin/env python3\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


class ResolveTests(unittest.TestCase):
    def test_env_override_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            script = _write_fake_script(tdp, 'print("{}")\n')
            with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(script)}):
                resolved = l30._resolve_skill_entrypoint()
                self.assertEqual(resolved, script)

    def test_env_override_missing_returns_none(self) -> None:
        with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": "/nonexistent/path.py"}):
            self.assertIsNone(l30._resolve_skill_entrypoint())


class ResearchSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        body = (
            "import json, sys\n"
            "print(json.dumps({\n"
            '    "synthesis": "Investors are bullish on 2330 ahead of earnings.",\n'
            '    "sources": [\n'
            '        {"title": "Reddit thread", "url": "https://r/x", "platform": "reddit"},\n'
            '        {"title": "HN comment", "url": "https://hn/y", "platform": "hn"}\n'
            "    ]\n"
            "}))\n"
        )
        self.script = _write_fake_script(Path(self.tmp.name), body)
        self.env = patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(self.script)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_research_returns_ok_with_synthesis(self) -> None:
        result = l30.research("2330", timeout_seconds=10)
        self.assertEqual(result.status, "ok")
        self.assertIn("bullish", result.synthesis)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(result.topic, "2330")

    def test_to_cache_payload_drops_raw(self) -> None:
        result = l30.research("2330", timeout_seconds=10)
        payload = result.to_cache_payload()
        self.assertNotIn("raw", payload)
        self.assertEqual(payload["status"], "ok")

    def test_backend_available_true_when_script_present(self) -> None:
        self.assertTrue(l30.is_backend_available())


class ResearchFailureModeTests(unittest.TestCase):
    def test_unavailable_when_no_script(self) -> None:
        with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": "/does/not/exist.py"}):
            result = l30.research("2330", timeout_seconds=5)
            self.assertEqual(result.status, "unavailable")
            self.assertIn("not installed", (result.error or ""))

    def test_backend_available_false_when_missing(self) -> None:
        with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": "/does/not/exist.py"}):
            self.assertFalse(l30.is_backend_available())

    def test_nonzero_exit_returns_error_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            body = "import sys\nsys.stderr.write('boom')\nsys.exit(2)\n"
            script = _write_fake_script(Path(td), body)
            with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(script)}):
                result = l30.research("2330", timeout_seconds=10)
                self.assertEqual(result.status, "error")
                self.assertIn("boom", (result.error or ""))

    def test_invalid_json_falls_back_to_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            body = "print('not valid json{')\n"
            script = _write_fake_script(Path(td), body)
            with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(script)}):
                result = l30.research("2330", timeout_seconds=10)
                self.assertEqual(result.status, "error")
                self.assertIn("invalid JSON", (result.error or ""))

    def test_timeout_returns_timeout_status(self) -> None:
        # The skill exec on this fake takes 5s; we cap the call at 0.5s.
        with tempfile.TemporaryDirectory() as td:
            body = "import time\ntime.sleep(5)\n"
            script = _write_fake_script(Path(td), body)
            with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(script)}):
                result = l30.research("2330", timeout_seconds=0.5)
                self.assertEqual(result.status, "timeout")


class TolerantParserTests(unittest.TestCase):
    """Different last30days versions may rename fields; the parser shouldn't
    crash, it should fall back to whichever synthesis-shaped field is present."""

    def _run_with_payload(self, payload: dict) -> l30.ResearchResult:
        with tempfile.TemporaryDirectory() as td:
            body = f"import json\nprint(json.dumps({json.dumps(payload)}))\n"
            script = _write_fake_script(Path(td), body)
            with patch.dict(os.environ, {"LAST30DAYS_SCRIPT": str(script)}):
                return l30.research("topic", timeout_seconds=10)

    def test_summary_field_used_when_synthesis_absent(self) -> None:
        result = self._run_with_payload({"summary": "fallback summary"})
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.synthesis, "fallback summary")

    def test_citations_field_used_when_sources_absent(self) -> None:
        result = self._run_with_payload({
            "synthesis": "x",
            "citations": [{"title": "a", "url": "https://b"}],
        })
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.sources), 1)

    def test_empty_payload_returns_ok_with_empty_synthesis(self) -> None:
        result = self._run_with_payload({})
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.synthesis, "")
        self.assertEqual(result.sources, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
