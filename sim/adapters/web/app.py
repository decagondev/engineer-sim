"""Web adapter: builds the FastAPI app and registers the route modules under
sim/adapters/web/routes/ in dependency order. Each module is a closure over
one WebContext (see routes/context.py); helpers a module publishes are
available to the modules registered after it, and to earlier ones at call
time as ctx.<name>."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sim.adapters.web.app_base import _STATIC, log
from sim.adapters.web.routes import (admin, core, dashboards, gate, instructor, live, me,
                                     session, shell, tickets_mail, workspace)
from sim.adapters.web.routes.context import WebContext

# registration order: a module may use helpers published by the ones before it
ROUTE_MODULES = (core, gate, shell, session, workspace, tickets_mail, me, instructor,
                 dashboards, admin, live)


def create_web_app(manager, grader, grader_calibrated: bool = False,
                   build_observer=None, workspace_reader=None,
                   instructor_password: str = "", github_observer=None,
                   auth=None,
                   public_base_url: str = "", hosted: bool = False,
                   repo_files=None, github_oauth=None, gitlab_oauth=None) -> FastAPI:
    """Web adapter. Resolves each session to a per-scenario bundle via the manager;
    grader / build observer / file reader / settings are app-global.
    """
    app = FastAPI(title="Engineering Flight Simulator")
    app.state.manager = manager
    app.state.grader = grader
    app.state.grader_calibrated = grader_calibrated
    app.state.build_observer = build_observer
    app.state.files = workspace_reader
    app.state.instructor_password = instructor_password
    app.state.settings = manager.settings
    app.state.repo = manager.repo
    app.state.submissions = manager.submissions
    app.state.grades = getattr(manager, "grades", None)
    app.state.reviews = getattr(manager, "reviews", None)
    app.state.audit = getattr(manager, "audit", None)
    app.state.archive = getattr(manager, "archive", None)
    from sim.adapters.web.live import SessionBus
    app.state.bus = SessionBus()
    app.state.github_oauth = github_oauth
    app.state.gitlab_oauth = gitlab_oauth
    app.state.github_pending = {}          # uid -> {device_code, interval, started}
    app.state.gitlab_pending = {}
    app.state.repo_files = repo_files
    app.state.github_observer = github_observer
    if auth is None:
        from sim.adapters.auth.services import AuthServices
        auth = AuthServices("password", password=instructor_password)
    app.state.auth = auth
    app.state.public_base_url = public_base_url or ""

    ctx = WebContext(
        app=app, manager=manager, grader=grader, grader_calibrated=grader_calibrated,
        build_observer=build_observer, workspace_reader=workspace_reader,
        instructor_password=instructor_password, github_observer=github_observer,
        auth=auth, public_base_url=public_base_url, hosted=hosted, repo_files=repo_files,
        github_oauth=github_oauth, gitlab_oauth=gitlab_oauth)
    for mod in ROUTE_MODULES:
        mod.register(app, ctx)

    if getattr(manager, "_config", None) is not None and \
            getattr(manager._config, "persistence", "sqlite") in ("firestore", "firebase"):
        ctx._warm_overviews()
    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    onboarding = Path(__file__).resolve().parents[3] / "docs" / "onboarding"
    if onboarding.exists():
        # role onboarding guides (docs/onboarding/<role>/), public like /login
        app.mount("/onboarding", StaticFiles(directory=str(onboarding), html=True),
                  name="onboarding")
    else:
        log.warning("onboarding guides not found at %s; /onboarding will 404 "
                    "(check .dockerignore keeps docs/onboarding)", onboarding)
    return app
