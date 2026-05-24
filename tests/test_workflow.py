"""Structural assertions for `.github/workflows/refresh.yml`.

The workflow is a deploy gate + daily refresh. These tests assert the
contracts (cron time, no-third-party-action allowlist, pytest-blocks-deploy,
gh-pages-only push, no hardcoded secrets) rather than executing the workflow.

YAML quirk handled here: in YAML 1.1 (PyYAML default), the bare key `on:`
parses as the boolean `True`. We read either `wf['on']` or `wf[True]` via a
small accessor.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "refresh.yml"

ALLOWED_ACTIONS = {"actions/checkout", "actions/setup-python", "actions/cache"}


def _on(wf: dict):
    """YAML 1.1 turns the `on:` key into Python True. Return whichever side holds it."""
    return wf.get("on") if "on" in wf else wf.get(True)


@pytest.fixture(scope="module")
def wf() -> dict:
    with WORKFLOW_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def wf_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def steps(wf: dict) -> list[dict]:
    jobs = wf["jobs"]
    assert len(jobs) >= 1, "workflow must define at least one job"
    job = next(iter(jobs.values()))
    return job["steps"]


def test_workflow_yaml_parses():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    assert isinstance(loaded, dict)


def test_cron_is_0500_utc(wf):
    on = _on(wf)
    assert on is not None, "workflow has no `on:` trigger block"
    schedule = on["schedule"]
    assert isinstance(schedule, list) and len(schedule) >= 1
    assert schedule[0]["cron"] == "0 5 * * *"


def test_workflow_dispatch_present(wf):
    on = _on(wf)
    assert "workflow_dispatch" in on, "manual trigger must be available"


def test_permissions_contents_write(wf):
    assert wf["permissions"]["contents"] == "write"


def test_pytest_step_runs_before_refresh_and_generate(steps):
    pytest_idx = None
    refresh_idx = None
    generate_idx = None
    for i, step in enumerate(steps):
        run = step.get("run", "") or ""
        if "pytest" in run and pytest_idx is None:
            pytest_idx = i
        if "scripts/refresh.py" in run and refresh_idx is None:
            refresh_idx = i
        if "scripts/generate.py" in run and generate_idx is None:
            generate_idx = i
    assert pytest_idx is not None, "no pytest step found"
    assert refresh_idx is not None, "no refresh.py step found"
    assert generate_idx is not None, "no generate.py step found"
    assert pytest_idx < refresh_idx, "pytest must run before refresh.py"
    assert pytest_idx < generate_idx, "pytest must run before generate.py"


def test_pytest_step_does_not_continue_on_error(steps):
    for step in steps:
        run = step.get("run", "") or ""
        if "pytest" in run:
            assert step.get("continue-on-error", False) is False, (
                "pytest step must NOT continue-on-error — failure must block deploy"
            )
            return
    pytest.fail("no pytest step found")


def test_no_third_party_actions_outside_allowlist(steps):
    for step in steps:
        uses = step.get("uses")
        if not uses:
            continue
        # `org/repo@ref` or `org/repo/subpath@ref`
        repo = uses.split("@", 1)[0]
        # only check top-level org/repo
        parts = repo.split("/")
        assert len(parts) >= 2, f"malformed uses: {uses!r}"
        top = f"{parts[0]}/{parts[1]}"
        assert top in ALLOWED_ACTIONS, (
            f"action {uses!r} is not on the allowlist {sorted(ALLOWED_ACTIONS)}"
        )


def test_push_targets_gh_pages_only(steps):
    push_line_re = re.compile(r"^.*\bgit\s+push\b.*$", re.MULTILINE)
    found_push = False
    for step in steps:
        run = step.get("run", "") or ""
        for line in push_line_re.findall(run):
            found_push = True
            assert "gh-pages" in line, f"push line missing gh-pages target: {line!r}"
            # Forbid pushing to main as a destination ref. We allow incidental
            # textual occurrences only if not used as a refspec — but the
            # safest rule is to disallow `main` anywhere on a push line.
            assert not re.search(r"\bmain\b", line), (
                f"push line must not reference main: {line!r}"
            )
    assert found_push, "no `git push` line found in any run block"


def test_no_hardcoded_tokens(wf_text):
    # Allow the GITHUB_TOKEN secret substitution itself.
    sanitized = wf_text.replace("${{ secrets.GITHUB_TOKEN }}", "<<GHA_TOKEN_REF>>")
    forbidden_patterns = [
        r"ghp_[A-Za-z0-9]{20,}",
        r"gho_[A-Za-z0-9]{20,}",
        r"ghs_[A-Za-z0-9]{20,}",
        r"ghu_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r'(?i)\btoken\s*:\s*"[^"$][^"]*"',
        r"(?i)\bpassword\s*:",
    ]
    for pat in forbidden_patterns:
        m = re.search(pat, sanitized)
        assert m is None, f"forbidden token-like pattern {pat!r} matched: {m.group(0)!r}"


def test_concurrency_group_set(wf):
    assert wf["concurrency"]["group"] == "refresh"
    assert wf["concurrency"].get("cancel-in-progress", False) is False


def test_timeout_minutes_set(wf):
    job = next(iter(wf["jobs"].values()))
    tm = job.get("timeout-minutes")
    assert tm is not None, "job must declare timeout-minutes"
    assert tm <= 10, f"timeout-minutes must be <= 10 (got {tm})"


def test_site_includes_index_and_calendar_html(steps):
    stage_step = None
    for step in steps:
        if step.get("name") == "Stage site":
            stage_step = step
            break
    assert stage_step is not None, "no `Stage site` step found"
    run = stage_step["run"]
    assert "_site/index.html" in run, "root URL must serve calendar.html as index.html"
    assert "_site/calendar.html" in run, "named URL calendar.html must also be staged"


def test_workflow_uses_token_from_secrets_only(steps):
    publish_step = None
    for step in steps:
        run = step.get("run", "") or ""
        if "git push" in run:
            publish_step = step
            break
    assert publish_step is not None, "no publish step found"
    env = publish_step.get("env", {}) or {}
    assert env.get("GITHUB_TOKEN") == "${{ secrets.GITHUB_TOKEN }}", (
        "publish step must expose GITHUB_TOKEN via the secrets context"
    )
    # No other env entry may look like a secret value (i.e. not be a `${{ secrets.* }}` ref).
    suspicious_keys = re.compile(r"(?i)(token|secret|password|api[_-]?key|pat)")
    for k, v in env.items():
        if k == "GITHUB_TOKEN":
            continue
        if suspicious_keys.search(k):
            assert isinstance(v, str) and v.startswith("${{ secrets."), (
                f"env var {k} looks secret-like but is not sourced from secrets context: {v!r}"
            )
