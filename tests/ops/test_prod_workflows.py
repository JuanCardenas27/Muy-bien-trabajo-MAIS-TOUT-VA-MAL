"""Contratos de los workflows de producción y la config de despliegue (OPS-05).

Los workflows solo corren en el repo de producción (``FRANCES_PROD``), nunca en
PRs ni en el PC del usuario: datos en R2, código en git (D1, R-30).
"""

from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

import yaml

from frances.audio.voices import load_voices
from frances.paths import DataPaths

WF = Path(".github/workflows")
R2 = {"R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"}
MASTER_SECRETS = {
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "AZURE_SPEECH_KEY",
    "AZURE_SPEECH_REGION",
    "AZURE_TRANSLATOR_KEY",
    "AZURE_TRANSLATOR_REGION",
    "FRANCES_PASSPHRASE",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "GITHUB_TOKEN",
} | R2
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")
NAMES = ("daily.yml", "reconcile.yml")


def load(n: str) -> dict[str, Any]:
    return yaml.safe_load((WF / n).read_text(encoding="utf-8"))


def on(wf: dict[str, Any]) -> dict[str, Any]:
    return wf.get("on", wf.get(True))  # PyYAML lee `on:` como True


def steps(wf: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for j in wf["jobs"].values() for s in j["steps"]]


def step(wf: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in steps(wf) if s.get("name") == name)


def test_crons_triggers_concurrency_and_pins():
    assert [on(load(n))["schedule"][0]["cron"] for n in NAMES] == ["17 10 * * *", "0 11 * * 0"]
    # R-30: nunca push/PR; solo schedule o workflow_dispatch.
    assert all(set(on(load(n))) == {"schedule", "workflow_dispatch"} for n in NAMES)
    assert all(
        load(n)["concurrency"] == {"group": "frances-prod", "cancel-in-progress": False}
        for n in NAMES
    )
    assert all(PINNED.fullmatch(s["uses"]) for n in NAMES for s in steps(load(n)) if "uses" in s)


def test_public_repo_hardening_in_every_workflow():  # R-30
    for p in WF.glob("*.yml"):
        text, wf = p.read_text(), yaml.safe_load(p.read_text())
        assert "pull_request_target" not in text and "self-hosted" not in text
        if "secrets." in text.replace("secrets.GITHUB_TOKEN", ""):
            assert set(on(wf)) <= {"schedule", "workflow_dispatch"}
            environments = [j.get("environment", {}).get("name") for j in wf["jobs"].values()]
            assert all(name == "production" for name in environments)


def test_secrets_vars_only_from_master_and_step_scoped():
    for n in NAMES:
        text, wf = (WF / n).read_text(), load(n)
        assert set(re.findall(r"secrets\.(\w+)", text)) <= MASTER_SECRETS
        assert set(re.findall(r"vars\.(\w+)", text)) <= {"FRANCES_PROD"}
        assert "secrets." not in yaml.safe_dump({k: v for k, v in wf.items() if k != "jobs"})
        assert all("secrets." not in str(j.get("env", {})) for j in wf["jobs"].values())


def test_daily_job_shape():
    job = load("daily.yml")["jobs"]["daily"]
    assert job["if"] == "vars.FRANCES_PROD == 'true'" and job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {"contents": "read", "issues": "write", "actions": "write"}
    assert job["timeout-minutes"] == 120 and job["environment"]["name"] == "production"


def test_reconcile_job_shape():
    wf = load("reconcile.yml")
    job = wf["jobs"]["reconcile"]
    assert job["if"] == "vars.FRANCES_PROD == 'true'" and job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    assert job["timeout-minutes"] == 60 and job["environment"]["name"] == "production"
    assert step(wf, "Reconcile")["id"] == "daily"
    push = step(wf, "Push")
    assert push["run"] == "uv run frances r2 push --label reconcile --data data"
    assert push["if"] == "always() && steps.daily.outputs.code != '3'"
    names = [s.get("name") for s in job["steps"]]
    assert (
        names.index("Lease")
        < names.index("Pull")
        < names.index("Reconcile")
        < names.index("Push")
        < names.index("Release lease")
    )
    text = yaml.safe_dump(job)
    assert "apt-get" not in text and "frances bundle" not in text


def test_publish_steps_skip_on_auth_failure():  # REVIEW FOCUS 1
    wf = load("daily.yml")
    for name in ("Bundle", "Publish"):
        cond = step(wf, name)["if"]
        assert "steps.daily.outputs.code != '3'" in cond
        assert "steps.decide.outputs.deploy == 'true'" in cond
    for name in ("Dump", "Push"):
        assert "steps.daily.outputs.code != '3'" in step(wf, name)["if"]
    s = [x.get("name") for x in steps(wf)]
    assert (
        s.index("Lease")
        < s.index("Pull")
        < s.index("Run daily")
        < s.index("Publish")
        < s.index("Push")
        < s.index("Release lease")
    )
    assert step(wf, "Release lease")["if"] == "always()"


def test_keepalive_reenables_scheduled_workflows():  # D11: GitHub apaga los cron tras 60 días
    run = step(load("daily.yml"), "Keepalive")["run"]
    assert "actions/workflows/daily.yml/enable" in run
    assert "actions/workflows/reconcile.yml/enable" in run


def test_readme_lists_every_secret():
    readme = Path("deploy/README.md").read_text()
    every = MASTER_SECRETS - {"GITHUB_TOKEN"} | {"CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"}
    assert all(f"`{s}`" in readme for s in every)
    assert "LIVE-02" in readme and "`FRANCES_PROD`" in readme


def test_deploy_config_and_voices_load(tmp_path: Path):
    shutil.copytree("deploy", tmp_path, dirs_exist_ok=True)
    assert set(tomllib.loads((tmp_path / "frances.toml").read_text())) == {
        "classroom",
        "cards",
        "audio",
        "translator",
        "bundle",
    }
    assert len(load_voices(DataPaths(tmp_path))) == 17
