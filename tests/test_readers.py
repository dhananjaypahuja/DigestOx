"""The Slack and GitHub readers parse exports without touching the database."""

import json
import os
import stat
import sys
from datetime import UTC, datetime

import pytest

from conftest import GITHUB_20, SLACK_A, THIN_CONFIG, pulse_json, zip_export
from customer_pulse.config import load_config
from customer_pulse.errors import PulseError
from customer_pulse.readers import github, slack


def test_slack_ts_is_parsed_exactly():
    assert slack.parse_ts("1789402320.000100") == datetime(2026, 9, 14, 16, 12, 0, 100, tzinfo=UTC)
    for bad in ("1789402320", "1789402320.1", 1789402320.0001, None):
        with pytest.raises(ValueError, match="not a Slack ts"):
            slack.parse_ts(bad)


@pytest.mark.parametrize(
    ("markup", "plain"),
    [
        ("thanks <@U1>", "thanks @Priya Raman"),
        ("see <#C1|general>", "see #general"),
        ("<!here> please", "@here please"),
        ("<https://x.example/a|the doc>", "the doc (https://x.example/a)"),
        ("<https://x.example/a>", "https://x.example/a"),
        ("<mailto:a@b.example|a@b.example>", "a@b.example"),
        ("&gt; quoted &amp; &lt;b&gt;", "> quoted & <b>"),
    ],
)
def test_slack_markup_is_rendered_for_people(markup, plain):
    assert slack.render_text(markup, {"U1": {"real_name": "Priya Raman"}}) == plain


def test_slack_folder_and_zip_read_the_same(tmp_path):
    folder = slack.read_export(SLACK_A)
    zipped = slack.read_export(zip_export(SLACK_A, tmp_path))
    nested = slack.read_export(zip_export(SLACK_A, tmp_path, root="export"))
    assert folder.signals == zipped.signals == nested.signals
    assert folder.content_sha256 != zipped.content_sha256 != nested.content_sha256
    assert len(folder.signals) == 12
    assert folder.skipped == 1
    assert {c.name for c in folder.channels} >= {"bivo-morrowvale", "bivo-community"}


def test_slack_reader_keeps_the_author_email_only_for_attribution():
    signal = next(s for s in slack.read_export(SLACK_A).signals if s.author_name == "Oren Blake")
    assert signal.author_email == "oren.blake@kettlewren.example"
    assert "@" not in signal.text


def test_slack_reader_refuses_a_broken_export(tmp_path):
    (tmp_path / "channels.json").write_text("[]")
    with pytest.raises(PulseError, match=r"users\.json is missing"):
        slack.read_export(tmp_path)
    (tmp_path / "users.json").write_text("{not json")
    with pytest.raises(PulseError, match="not valid JSON"):
        slack.read_export(tmp_path)


def test_github_reader_parses_issues_and_comments():
    export = github.read_export(GITHUB_20)
    assert [i.number for i in export.issues] == [18, 21, 23, 24]
    closed = next(i for i in export.issues if i.number == 23)
    assert (closed.state, closed.state_reason) == ("CLOSED", "not_planned")
    assert closed.closed_at == datetime(2026, 9, 19, 17, 5, tzinfo=UTC)
    assert closed.labels == ["P1", "area:sso", "bug"]
    assert [c.source_key for c in export.comments] == [
        "IC_kwDOBivo18a",
        "IC_kwDOBivo21a",
        "IC_kwDOBivo21b",
        "IC_kwDOBivo23a",
    ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"state": "MERGED"}, "unknown state"),
        ({"state": "CLOSED", "closedAt": None}, "its closedAt"),
        ({"createdAt": "yesterday"}, "not a timestamp"),
        ({"title": ""}, "missing title"),
    ],
)
def test_github_reader_refuses_inconsistent_issues(tmp_path, change, message):
    issues = json.loads(GITHUB_20.read_text())
    issues[0].update(change)
    path = tmp_path / "issues.json"
    path.write_text(json.dumps(issues))
    with pytest.raises(PulseError, match=message):
        github.read_export(path)


def test_vendor_config_is_validated(tmp_path):
    path = tmp_path / "pulse.toml"
    path.write_text(THIN_CONFIG)
    vendor = load_config(path, tmp_path).vendor
    assert vendor.email_domains == {"bivo.example"}
    assert vendor.slack_team_ids == {"T0BIVO0001"}
    for bad in (
        'email_domains = ["Bivo.example"]',
        'email_domains = "bivo.example"',
        "slack_team_ids = [1]",
        'colour = "red"',
    ):
        path.write_text(f"[vendor]\n{bad}\n")
        with pytest.raises(PulseError) as err:
            load_config(path, tmp_path)
        assert err.value.code == "invalid_config"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_log_is_private_and_an_exposed_log_is_refused(thin_project):
    log = thin_project / ".pulse" / "pulse.log"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    os.chmod(log, 0o644)
    code, status = pulse_json("status")
    assert code == 0
    assert any("pulse.log" in p for p in status["database"]["privacy_problems"])
    code, result = pulse_json("import", "slack", str(SLACK_A))
    assert code == 1
    assert result["error"]["code"] == "database_not_private"
    assert "chmod 600" in result["error"]["hint"]
    assert pulse_json("status")[1]["counts"]["imports"] == 0  # refused before importing


def test_a_log_symlink_is_never_followed(thin_project, tmp_path):
    log = thin_project / ".pulse" / "pulse.log"
    log.unlink()
    outside = tmp_path / "outside.log"
    log.symlink_to(outside)
    code, result = pulse_json("import", "slack", str(SLACK_A))
    assert code == 1
    assert result["error"]["code"] == "database_path_not_regular"
    assert not outside.exists()
    log.unlink()
    assert pulse_json("status")[1]["counts"]["imports"] == 0  # refused before importing
