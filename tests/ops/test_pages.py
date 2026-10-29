"""Workflow de GitHub Pages: app real y demo sintético (Task OPS-06)."""

import re
from pathlib import Path

import yaml

WF = Path(".github/workflows")
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")


def load(n):
    return yaml.safe_load((WF / n).read_text())


def on(wf):
    return wf.get("on", wf.get(True))  # PyYAML lee `on:` como True


def steps(wf):
    return [s for j in wf["jobs"].values() for s in j["steps"]]


def step(wf, name):
    return next(s for s in steps(wf) if s.get("name") == name)


def test_pages_shape():
    wf, text = load("pages.yml"), (WF / "pages.yml").read_text()
    assert on(wf)["push"]["branches"] == ["main"] and "workflow_dispatch" in on(wf)
    assert wf["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    assert wf["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    assert "secrets." not in text and set(re.findall(r"vars\.(\w+)", text)) == {"FRANCES_DATA_URL"}
    assert all(PINNED.fullmatch(s["uses"]) for s in steps(wf) if "uses" in s)
    job = wf["jobs"]["pages"]
    assert job["environment"]["name"] == "github-pages"
    assert step(wf, "Build demo")["env"]["VITE_BASE"] == "/${{ github.event.repository.name }}/demo/"
    names = [s.get("name") for s in job["steps"]]
    assert (
        names.index("Build app")
        < names.index("Build demo")
        < names.index("Demo bundle")
        < names.index("Deploy pages")
    )
    assert step(wf, "Demo bundle")["run"] == "uv run frances demo-bundle --out web/dist/demo/data"
