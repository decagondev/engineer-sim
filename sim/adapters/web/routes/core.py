from __future__ import annotations

from fastapi import Request


def register(app, ctx):
    """Routes and helpers for the core area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    workspace_reader = ctx.workspace_reader
    auth = ctx.auth
    public_base_url = ctx.public_base_url
    hosted = ctx.hosted
    repo_files = ctx.repo_files

    def _site() -> "InstructorSettings":
        try:
            return app.state.settings.get_instructor()
        except Exception:
            from sim.core.ports.settings import InstructorSettings
            return InstructorSettings()
    auth.allow_new_users = lambda: bool(_site().allow_signup)

    def _calibrated() -> bool:
        """Admin override wins over the GRADER_CALIBRATED env var."""
        v = _site().grader_calibrated
        return bool(app.state.grader_calibrated) if v is None else bool(v)
    app.state.public_base_url_fixed = bool(public_base_url)
    app.state.hosted = bool(hosted)

    from sim.core.workflow import resolve_workflow
    from sim.core.workspace.service import WorkspaceService, WorkspaceWriteError
    app.state.workspace = (WorkspaceService(files=workspace_reader,
                                            store=manager.session_files)
                           if workspace_reader is not None else None)
    # read-only browsing of a linked GitHub repo (set by the composition root)
    app.state.repo_workspace = (WorkspaceService(files=repo_files, store=None)
                                if repo_files is not None else None)

    def b(session_id):
        return manager.for_session(session_id)

    def _scenario_config() -> dict:
        """Starter URLs and enabled flags for every scenario, one store read."""
        s = app.state.settings
        fn = getattr(s, "all_scenario_config", None) if s is not None else None
        if fn is None:
            return {}
        try:
            return fn() or {}
        except Exception:
            return {}

    def _workflow(session_id):
        return resolve_workflow(b(session_id).scenario.track, app.state.hosted)

    def _repo_writable(url: str = "") -> bool:
        """May the current request commit to the linked repo at `url`? (A
        connected GitHub / GitLab account with a write scope, decided by the
        host router behind the files adapter. No URL: any host will do.)"""
        files = getattr(app.state.repo_workspace, "files", None) or app.state.repo_files
        fn = getattr(files, "can_write", None)
        try:
            return bool(fn(url)) if fn else False
        except Exception:
            return False

    def _session_repo_url(session_id: str) -> str:
        try:
            return (app.state.settings.get_session_repo_url(session_id) or "") if app.state.settings else ""
        except Exception:
            return ""

    def _workflow_payload(session_id) -> dict:
        wf = _workflow(session_id).as_dict()
        if wf["kind"] == "repo" and _repo_writable(_session_repo_url(session_id)):
            wf["editable"] = True
            wf["writes_to_repo"] = True
        return wf

    def _session_level(session_id: str) -> str:
        from sim.core.levels import DEFAULT_LEVEL
        s = app.state.settings
        if s is None:
            return DEFAULT_LEVEL
        return s.get_session_level(session_id) or s.get_instructor().default_level

    import re as _re
    from sim.core.ports.identity import IdentityError, Principal
    from sim.adapters.auth.services import LOCAL_INSTRUCTOR_EMAIL, LOCAL_INSTRUCTOR_UID

    _SESSION_API = _re.compile(r"^/api/session/([^/]+)")
    _INSTR_SID = _re.compile(r"^/api/instructor/session/([^/]+)")

    def _local_instructor() -> Principal:
        return Principal(LOCAL_INSTRUCTOR_UID, LOCAL_INSTRUCTOR_EMAIL, "instructor")

    def _actor(request: Request | None) -> Principal:
        if not app.state.auth.gated:
            return _local_instructor()
        p = getattr(getattr(request, "state", None), "principal", None)
        return p or _local_instructor()

    def _login_url() -> str:
        base = getattr(app.state, "public_base_url", "") or ""
        return f"{base}/login" if base else ""


    # published for the modules registered after this one
    ctx._INSTR_SID = _INSTR_SID
    ctx._SESSION_API = _SESSION_API
    ctx._actor = _actor
    ctx._calibrated = _calibrated
    ctx._local_instructor = _local_instructor
    ctx._login_url = _login_url
    ctx._repo_writable = _repo_writable
    ctx._scenario_config = _scenario_config
    ctx._session_level = _session_level
    ctx._session_repo_url = _session_repo_url
    ctx._site = _site
    ctx._workflow = _workflow
    ctx._workflow_payload = _workflow_payload
    ctx.b = b
