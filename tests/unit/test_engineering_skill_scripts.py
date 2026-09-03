from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2]


def load_script(relative_path: str, module_name: str):
    script_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_pr_context_parses_supported_references_and_issue_links():
    fetch = load_script(
        "skills/plugins/rhdh-pr-review/scripts/fetch_pr_context.py",
        "rhdh_pr_review_fetch_context",
    )

    assert fetch.parse_pr_input("https://github.com/acme/widgets/pull/42") == (
        "acme/widgets",
        42,
    )
    assert fetch.parse_pr_input("acme/widgets#42") == ("acme/widgets", 42)
    assert fetch.parse_pr_input("42") == (None, 42)

    github_issues, jira_keys = fetch.extract_issue_refs(
        "Fixes #7, refs #8, and tracks RHIDP-123 plus RHIDP-123."
    )
    assert github_issues == [7, 8]
    assert jira_keys == ["RHIDP-123"]


def test_overlay_analyzers_preserve_workspace_and_priority_classification():
    analyze = load_script(
        "skills/plugins/rhdh-overlay/scripts/analyze-pr.py",
        "rhdh_overlay_analyze_pr",
    )
    triage = load_script(
        "skills/plugins/rhdh-overlay/scripts/triage-prs.py",
        "rhdh_overlay_triage_prs",
    )

    files = [
        {"path": "workspaces/catalog/source.json"},
        {"path": "workspaces/catalog/plugins-list.yaml"},
        {"path": "CODEOWNERS"},
    ]
    assert analyze.extract_workspaces(files) == ["catalog"]
    assert analyze.check_codeowners_modified(files)

    labels = [{"name": "mandatory-workspace"}, {"name": "workspace-update"}]
    assert analyze.classify_priority(labels)[0] == "critical"
    assert triage.classify_priority(labels)[0] == "critical"
    assert triage.extract_workspace_from_title("Update catalog workspace to 1.2.3") == "catalog"


def test_shared_adf_parser_keeps_the_current_milestone_date():
    from datetime import datetime

    milestones = load_script(
        "skills/reference/rhdh-jira-api/scripts/adf_milestones.py",
        "rhdh_shared_adf_natural_dates",
    )
    description = {
        "type": "tableRow",
        "content": [
            {"type": "tableCell", "content": [{"type": "text", "text": "Code Freeze"}]},
            {
                "type": "tableCell",
                "content": [
                    {"type": "text", "text": "August "},
                    {"type": "text", "text": "27", "marks": [{"type": "strike"}]},
                    {"type": "text", "text": "31 (done)"},
                ],
            },
        ],
    }
    dates = milestones.extract_milestone_dates(description)
    assert dates["code_freeze"] == f"{datetime.now().year}-08-31"
    assert dates["feature_freeze"] == "TBD"
    assert milestones.parse_natural_date("Sep 2, 2025") == "2025-09-02"
    assert milestones.parse_natural_date("TBD") is None
