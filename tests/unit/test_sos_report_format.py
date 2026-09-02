"""Unit tests for SoS report markdown rendering."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOS_SCRIPTS = PROJECT_ROOT / "skills" / "release" / "rhdh-release-sos" / "scripts"

if str(_SOS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SOS_SCRIPTS))

import sos_report_format as format_mod  # noqa: E402

SAMPLE_REPORT = {
    "version": "2.1.0",
    "as_of": "2026-09-02",
    "active_section": {"title": "Feature Freeze", "milestone_key": "feature_freeze"},
    "milestones": [
        {
            "milestone": "Feature Freeze",
            "key": "feature_freeze",
            "date": "2026-09-22",
            "days_until": 20,
        },
        {
            "milestone": "Code Freeze",
            "key": "code_freeze",
            "date": "2026-10-13",
            "days_until": 41,
        },
        {
            "milestone": "Go/No Go",
            "key": "go_no_go",
            "date": "2026-10-26",
            "days_until": 54,
        },
        {
            "milestone": "GA Announce",
            "key": "ga_announce",
            "date": "2026-10-28",
            "days_until": 56,
        },
    ],
    "checks_upcoming": [
        {
            "title": "FF scope outstanding",
            "when": "FF - 7d",
            "resolved_date": "2026-09-15",
        }
    ],
    "results": [
        {
            "title": "FF Epics, Stories, Tasks not in a sprint",
            "count": 157,
            "status": "ok",
            "jira_url": "https://redhat.atlassian.net/issues/?jql=sprint+is+EMPTY",
            "teams": [
                {
                    "team_name": "RHDH COPE",
                    "count": 12,
                    "status": "ok",
                    "jira_url": "https://redhat.atlassian.net/issues/?jql=sprint+team+cope",
                },
                {
                    "team_name": "RHDH Install Method",
                    "count": 0,
                    "status": "ok",
                    "jira_url": "https://redhat.atlassian.net/issues/?jql=sprint+team+install",
                },
            ],
        },
        {
            "title": "FF Epics, Stories, Tasks in New, To Do, or Backlog",
            "count": 0,
            "status": "ok",
            "jira_url": "https://redhat.atlassian.net/issues/?jql=status+in+New",
            "teams": [
                {
                    "team_name": "RHDH COPE",
                    "count": 0,
                    "status": "ok",
                    "jira_url": "https://redhat.atlassian.net/issues/?jql=status+team+cope",
                },
            ],
        },
    ],
}


class TestReportFormat:
    def test_check_summary_values(self):
        assert format_mod.check_summary(SAMPLE_REPORT["results"][0]) == "157 open"
        assert format_mod.check_summary(SAMPLE_REPORT["results"][1]) == "None open"

    def test_fixed_template_shape(self):
        markdown = format_mod.render_report_markdown(SAMPLE_REPORT)
        assert markdown.startswith("# RHDH 2.1.0 — SoS Release Check-in\n")
        assert "| Release phase | Feature Freeze |" in markdown
        assert "## Milestones" in markdown
        assert "## Checks" in markdown
        assert "| ↳ COPE | 12 open | [Open in Jira]" in markdown
        assert "| ↳ COPE | None open | [Open in Jira]" in markdown
        assert "Upcoming checks" not in markdown
        assert "Follow-up" not in markdown
        assert "executed" not in markdown.lower()

    def test_team_display_name_strips_rhdh_prefix(self):
        assert format_mod.team_display_name("RHDH COPE") == "COPE"
        assert format_mod.team_display_name("Install Method") == "Install Method"

    def test_enrich_report_adds_summary_and_markdown(self):
        enriched = format_mod.enrich_report(SAMPLE_REPORT)
        assert enriched["results"][0]["summary"] == "157 open"
        assert "executive_summary" not in enriched
        assert "[Open in Jira]" in enriched["report_markdown"]
        assert enriched["report_html"].startswith("<!DOCTYPE html>")
        assert "RHDH 2.1.0 — SoS Release Check-in" in enriched["report_html"]
        assert 'class="summary summary-open"' in enriched["report_html"]
        assert 'class="team-row"' in enriched["report_html"]
        assert "<style>" in enriched["report_html"]

    def test_summary_css_class(self):
        assert format_mod.summary_css_class({"status": "ok", "count": 0}) == "summary-none"
        assert format_mod.summary_css_class({"status": "ok", "count": 3}) == "summary-open"
        assert format_mod.summary_css_class({"status": "unverified"}) == "summary-unverified"
