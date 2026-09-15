"""Which way a session is worked and submitted. Pure: a function of the
scenario track and whether the server is hosted. See docs/WORKSPACE-PLAN.md.

    track                local run   hosted
    interview / systems  doc         doc
    product              sandbox     repo

doc      the learner edits DESIGN.md in the browser on a server-side workspace
sandbox  the learner builds in a per-session dev box on the server (local runs)
repo     the learner pushes to a public GitHub repo and links it; read-only here
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

DOC = "doc"
SANDBOX = "sandbox"
REPO = "repo"

_DOC_TRACKS = ("interview", "systems")


@dataclass(frozen=True)
class Workflow:
    kind: str                 # doc | sandbox | repo
    editable: bool            # the Files app may write
    needs_repo_url: bool      # the Workspace app asks for a GitHub URL
    submit_label: str         # copy for the single Submit button
    submit_hint: str          # one sentence under the button

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_workflow(track: str, hosted: bool) -> Workflow:
    if (track or "product") in _DOC_TRACKS:
        return Workflow(
            kind=DOC, editable=True, needs_repo_url=False,
            submit_label="Submit DESIGN.md",
            submit_hint="Submits the DESIGN.md in your workspace as it is now.",
        )
    if hosted:
        return Workflow(
            kind=REPO, editable=False, needs_repo_url=True,
            submit_label="Submit for grading",
            submit_hint="Grades what you have pushed to your linked repo.",
        )
    return Workflow(
        kind=SANDBOX, editable=True, needs_repo_url=False,
        submit_label="Submit from workspace",
        submit_hint="Grades the commits in your workspace.",
    )
