from __future__ import annotations

from fastapi.responses import JSONResponse
from sim.core.workspace.service import WorkspaceService, WorkspaceWriteError


def register(app, ctx):
    """Routes and helpers for the workspace area (moved verbatim from create_web_app)."""
    _maybe_diagram = ctx._maybe_diagram
    _sandbox_record = ctx._sandbox_record
    _workflow = ctx._workflow
    _workflow_payload = ctx._workflow_payload
    b = ctx.b

    # ---- environment (sandbox) -----------------------------------------
    from sim.core.ports.environment import SandboxError, SandboxUnavailable

    def _workdir(session_id):
        env = b(session_id).environment
        if env is None:
            return None
        h = env.handle(session_id)
        return h.workdir if h else None

    @app.post("/api/session/{session_id}/environment/provision")
    def provision_env(session_id: str):
        env = b(session_id).environment
        if env is None:
            return JSONResponse({"error": "no environment configured"}, status_code=501)
        try:
            h = env.provision(session_id)
        except SandboxUnavailable as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        except SandboxError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return {"workdir": h.workdir, "created": h.created,
                "container": h.container, "connect_hint": h.connect_hint}

    @app.get("/api/session/{session_id}/environment")
    def get_env(session_id: str):
        env = b(session_id).environment
        if env is None:
            return JSONResponse({"error": "no environment configured"}, status_code=501)
        h = env.handle(session_id)
        return {"provisioned": h is not None, "workdir": (h.workdir if h else None),
                "container": (h.container if h else None),
                "connect_hint": (h.connect_hint if h else None)}

    @app.post("/api/session/{session_id}/environment/teardown")
    def teardown_env(session_id: str):
        env = b(session_id).environment
        if env is not None:
            h = env.handle(session_id)
            env.teardown(session_id)
            if h is not None and app.state.workspace is not None:
                app.state.workspace.forget(h.workdir, session_id)
        return {"torn_down": True}

    # ---- files ----------------------------------------------------------
    class _NoWorkspace(Exception):
        def __init__(self, msg: str, status: int = 409) -> None:
            super().__init__(msg)
            self.status = status

    def _ws(session_id: str):
        """(WorkspaceService, root) for this session's workflow. `doc` auto-
        provisions the folder; `sandbox` needs the Workspace app; `repo`
        needs a linked GitHub URL (read-only)."""
        wf = _workflow(session_id)
        if wf.kind == "repo":
            svc = app.state.repo_workspace
            if svc is None:
                raise _NoWorkspace("repo browsing is not configured on this server", 501)
            url = app.state.settings.get_session_repo_url(session_id) if app.state.settings else None
            if not url:
                raise _NoWorkspace("link your GitHub repo in the Workspace app first")
            return svc, url
        svc = app.state.workspace
        if svc is None:
            raise _NoWorkspace("no file browser", 501)
        env = b(session_id).environment
        if env is None:
            raise _NoWorkspace("no environment configured", 501)
        h = env.handle(session_id)
        if h is None and wf.kind == "doc":
            try:
                h = env.provision(session_id)
            except (SandboxUnavailable, SandboxError) as e:
                raise _NoWorkspace(str(e), 503)
        if h is None:
            raise _NoWorkspace("no workspace — open the Workspace app first")
        return svc, h.workdir

    def _ws_error(e: Exception):
        if isinstance(e, _NoWorkspace):
            return JSONResponse({"error": str(e)}, status_code=e.status)
        return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/api/session/{session_id}/files/list")
    def files_list(session_id: str, path: str = ""):
        try:
            svc, root = _ws(session_id)
            entries = svc.list_dir(root, session_id, path)
        except (_NoWorkspace, ValueError, NotADirectoryError, FileNotFoundError) as e:
            return _ws_error(e)
        wf = _workflow_payload(session_id)
        return {"path": path, "editable": wf["editable"], "entries": [
            {"name": e.name, "is_dir": e.is_dir, "size": e.size} for e in entries]}

    @app.get("/api/session/{session_id}/files/read")
    def files_read(session_id: str, path: str = ""):
        try:
            svc, root = _ws(session_id)
            c = svc.read(root, session_id, path)
        except (_NoWorkspace, ValueError, IsADirectoryError, FileNotFoundError) as e:
            return _ws_error(e)
        return {"path": c.path, "text": c.text, "note": c.note}

    @app.put("/api/session/{session_id}/files/write")
    def files_write(session_id: str, payload: dict):
        from sim.core.ports.workspace import ReadOnlyWorkspace
        wf = _workflow_payload(session_id)
        if not wf["editable"]:
            return JSONResponse({"error": "this workspace is read-only: connect GitHub in the "
                                          "Workspace app to edit here, or push and press Refresh"},
                                status_code=405)
        path = (payload or {}).get("path", "")
        text = (payload or {}).get("text")
        if not isinstance(text, str):
            return JSONResponse({"error": "text must be a string"}, status_code=400)
        try:
            svc, root = _ws(session_id)
            svc.write(root, session_id, path, text)
        except ReadOnlyWorkspace as e:
            return JSONResponse({"error": str(e)}, status_code=405)
        except (_NoWorkspace, WorkspaceWriteError, ValueError,
                IsADirectoryError, FileNotFoundError) as e:
            return _ws_error(e)
        return {"ok": True, "path": path, "revision": _safe_refresh(svc, root)}

    def _safe_refresh(svc, root: str) -> str:
        fn = getattr(svc.files, "refresh", None)
        try:
            return fn(root) if fn else ""
        except Exception as e:
            return f"(refresh failed: {e})"

    @app.get("/api/session/{session_id}/files/diff")
    def files_diff(session_id: str):
        """What changed since the starter: a unified diff, read-only."""
        try:
            svc, root = _ws(session_id)
        except _NoWorkspace as e:
            return _ws_error(e)
        fn = getattr(svc.files, "diff", None)
        if fn is None:
            return {"diff": "", "note": "this workspace cannot be compared with its starter"}
        try:
            text = fn(root) or ""
        except Exception as e:
            return {"diff": "", "note": f"could not compute the diff: {e}"}
        if len(text) > 400_000:
            text = text[:400_000] + "\n... (truncated)"
        return {"diff": text, "note": "" if text else "no changes against the starter yet"}

    @app.post("/api/session/{session_id}/files/refresh")
    def files_refresh(session_id: str):
        try:
            svc, root = _ws(session_id)
        except _NoWorkspace as e:
            return _ws_error(e)
        return {"ok": True, "revision": _safe_refresh(svc, root)}

    @app.post("/api/session/{session_id}/submit-workspace")
    def submit_workspace(session_id: str):
        """Submit the sandbox as it is (sandbox workflow): commit the working
        tree so the build record shows browser edits, then run the director."""
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        wf = _workflow(session_id)
        if wf.kind != "sandbox":
            return JSONResponse({"error": "this scenario is not submitted from a workspace"},
                                status_code=405)
        try:
            svc, root = _ws(session_id)
        except _NoWorkspace as e:
            return _ws_error(e)
        snap = getattr(svc.files, "snapshot", None)
        rev = ""
        if snap:
            try:
                rev = snap(root, "submitted from workspace") or ""
            except Exception:
                rev = ""
        record = _sandbox_record(session_id) or "(workspace has no git history)"
        ts = datetime.now(timezone.utc).isoformat()
        sub = app.state.submissions.save(session_id, "workspace", record, ts, kind="workspace")
        app.state.repo.append(StoredMessage(
            session_id=session_id, sender="tester", channel="general",
            content=f"[reveal] Submitted work: workspace{(' @ ' + rev) if rev else ''}.",
            ts=ts, kind="event"))
        b(session_id).session_service.after_submission(session_id)
        app.state.bus.notify(session_id, "submission")
        return {"ok": True, "seq": sub.seq, "revision": rev}

    @app.post("/api/session/{session_id}/submit-doc")
    def submit_doc(session_id: str):
        """Submit DESIGN.md straight from the workspace (doc workflow)."""
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        wf = _workflow(session_id)
        if wf.kind != "doc":
            return JSONResponse({"error": "this scenario is not submitted as a design document"},
                                status_code=405)
        try:
            svc, root = _ws(session_id)
        except _NoWorkspace as e:
            return _ws_error(e)
        text = svc.design_text(root, session_id)
        if not text.strip():
            return JSONResponse({"error": "DESIGN.md is empty — write your design first"},
                                status_code=400)
        snap = getattr(svc.files, "snapshot", None)
        rev = ""
        if snap:
            try:
                rev = snap(root, "submitted design") or ""
            except Exception:
                rev = ""
        ts = datetime.now(timezone.utc).isoformat()
        sub = app.state.submissions.save(session_id, "DESIGN.md", text, ts, kind="doc")
        app.state.repo.append(StoredMessage(
            session_id=session_id, sender="tester", channel="general",
            content=f"[reveal] Submitted work: DESIGN.md ({sub.lines} lines).",
            ts=ts, kind="event"))
        bundle = b(session_id)
        bundle.session_service.remember_design(session_id, text)
        _maybe_diagram(session_id, text)
        bundle.session_service.after_submission(session_id)
        app.state.bus.notify(session_id, "submission")
        return {"ok": True, "seq": sub.seq, "lines": sub.lines, "revision": rev}


    # published for the modules registered after this one
    ctx._NoWorkspace = _NoWorkspace
    ctx._safe_refresh = _safe_refresh
    ctx._workdir = _workdir
    ctx._ws = _ws
    ctx._ws_error = _ws_error
    ctx.files_diff = files_diff
    ctx.files_list = files_list
    ctx.files_read = files_read
    ctx.files_refresh = files_refresh
    ctx.files_write = files_write
    ctx.get_env = get_env
    ctx.provision_env = provision_env
    ctx.submit_doc = submit_doc
    ctx.submit_workspace = submit_workspace
    ctx.teardown_env = teardown_env
