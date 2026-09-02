"""Unit tests for SoS report CLI helpers."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOS_SCRIPTS = PROJECT_ROOT / "skills" / "release" / "rhdh-release-sos" / "scripts"

if str(_SOS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SOS_SCRIPTS))

import sos_report as report_mod  # noqa: E402


class TestTeamJql:
    def test_appends_team_filter(self):
        base = 'fixVersion = "2.1.0" AND sprint is EMPTY'
        assert report_mod._team_jql(base, "abc-123") == (
            'fixVersion = "2.1.0" AND sprint is EMPTY AND "Team[Team]" = "abc-123"'
        )


class TestWriteReportHtml:
    def test_writes_self_contained_file(self, tmp_path):
        report = {
            "version": "2.1.0",
            "as_of": "2026-09-02",
            "report_html": "<!DOCTYPE html><html><body>ok</body></html>",
        }
        path = report_mod.write_report_html(report, tmp_path / "sos.html")
        assert path.read_text(encoding="utf-8") == report["report_html"]
        assert path.name == "sos.html"
        assert path.is_file()

    def test_default_html_path_uses_skill_reports_dir(self):
        path = report_mod.default_html_path("2.1.0", "2026-09-02")
        assert path.parent == report_mod.reports_dir()
        assert path.name == "rhdh-2.1.0-sos-2026-09-02.html"

    def test_attach_html_artifact_sets_path(self, tmp_path):
        report = {
            "version": "2.1.0",
            "as_of": "2026-09-02",
            "report_html": "<!DOCTYPE html><html><body>ok</body></html>",
        }
        report_mod.attach_html_artifact(report, tmp_path / "sos.html")
        assert report["report_html_path"] == str((tmp_path / "sos.html").resolve())
