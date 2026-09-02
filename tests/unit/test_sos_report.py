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
