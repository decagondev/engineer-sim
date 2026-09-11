from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def create_web_app(manager, grader, grader_calibrated: bool = False,
                   build_observer=None, workspace_reader=None,
                   instructor_password: str = "", github_observer=None,
                   auth=None) -> FastAPI:
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
    app.state.github_observer = github_observer
    if auth is None:
        from sim.adapters.auth.services import AuthServices
        auth = AuthServices("password", password=instructor_password)
    app.state.auth = auth

    def b(session_id):
        return manager.for_session(session_id)

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

    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        auth = app.state.auth
        if not auth.gated:
            return await call_next(request)
        path = request.url.path
        if (path.startswith("/static") or path in {
            "/health", "/api/auth/config", "/", "/instructor", "/login",
            "/challenger", "/admin",
        }):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        try:
            principal = auth.principal_from_headers(request.headers)
        except IdentityError as e:
            return JSONResponse({"error": e.detail}, status_code=e.status)
        request.state.principal = principal
        if path.startswith("/api/admin"):
            if not auth.allow_admin(principal):
                return JSONResponse({"error": "forbidden"}, status_code=403)
            return await call_next(request)
        if path.startswith("/api/instructor"):
            if not auth.allow_instructor(principal):
                return JSONResponse({"error": "forbidden"}, status_code=403)
            m = _INSTR_SID.match(path)
            if m and request.method == "GET":
                if not auth.allow_session(principal, m.group(1)):
                    return JSONResponse({"error": "forbidden"}, status_code=403)
            return await call_next(request)
        if path == "/api/scenarios" and principal.role == "challenger":
            return JSONResponse({"error": "forbidden"}, status_code=403)
        m = _SESSION_API.match(path)
        if m:
            sid = m.group(1)
            if path.endswith("/claim") and request.method == "POST":
                from sim.core.access.policy import can_claim_session
                rec = auth.session(sid)
                if not can_claim_session(principal, rec):
                    return JSONResponse({"error": "forbidden"}, status_code=403)
                return await call_next(request)
            grade = "/grade" in path
            mutate = request.method not in ("GET", "HEAD")
            if grade:
                if not auth.allow_session(principal, sid, grade=True):
                    return JSONResponse({"error": "forbidden"}, status_code=403)
            elif not auth.allow_session(principal, sid, mutate=mutate):
                return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)

    # ---- static / shell -------------------------------------------------
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/scenarios")
    def scenarios():
        out = []
        for m in manager.scenarios_meta():
            m = dict(m)
            m["starter_url"] = (app.state.settings.get_scenario_starter_url(m["key"])
                                if app.state.settings else None)
            out.append(m)
        return {"scenarios": out, "default": manager.default_scenario_key()}

    def _scenario_info(sc):
        starter_url = (app.state.settings.get_scenario_starter_url(sc.key)
                       if app.state.settings else None)
        return {"key": sc.key, "title": sc.title, "difficulty": sc.difficulty,
                "track": sc.track, "role_label": sc.role_label,
                "starter_url": starter_url,
                "personas": [{"key": p.key, "name": p.name, "role": p.role,
                              "lane": getattr(p, "lane", "")}
                             for p in sc.personas]}

    @app.get("/api/session/{session_id}/scenario")
    def session_scenario(session_id: str):
        return _scenario_info(b(session_id).scenario)

    @app.get("/api/levels")
    def levels():
        from sim.core.levels import levels_meta
        return {"levels": levels_meta()}

    @app.get("/api/session/{session_id}/level")
    def get_level(session_id: str):
        from sim.core.levels import profile
        lvl = _session_level(session_id)
        return {"level": lvl, "label": profile(lvl).label,
                "difficulty": b(session_id).scenario.difficulty}

    # ---- session lifecycle ---------------------------------------------
    @app.post("/api/session/{session_id}/start")
    def start(session_id: str):
        b(session_id).session_service.start(session_id)
        return {"session_id": session_id, "started": True}

    @app.post("/api/session/{session_id}/end")
    def end(session_id: str):
        b(session_id).session_service.end(session_id)
        return {"session_id": session_id, "ended": True}

    @app.get("/api/session/{session_id}/transcript")
    def transcript(session_id: str):
        return JSONResponse(b(session_id).session_service.export(session_id))

    def _flatten_tickets(session_id: str) -> list[dict]:
        board = b(session_id).ticket_service.board(session_id)
        out = []
        for col in board.get("columns", []):
            out.extend(col.get("tickets", []))
        return out

    def _ticket_record(session_id: str) -> str:
        lines = []
        for t in _flatten_tickets(session_id):
            lines.append(f"### {t.get('key')} {t.get('title')} ({t.get('status')})")
            lines.append(t.get("description") or "")
        return "\n".join(lines)

    def _enrich_build_record(session_id: str, build_record: str,
                             include_tickets: bool) -> str:
        svc = b(session_id).session_service
        extra = []
        design = svc.design_text(session_id)
        mermaid = svc.diagram_text(session_id)
        if design:
            extra.append("DESIGN DOCUMENT:\n" + design)
        if mermaid:
            extra.append("DESIGN DIAGRAM (mermaid):\n" + mermaid)
        if include_tickets:
            extra.append("TICKETS:\n" + _ticket_record(session_id))
        if not extra:
            return build_record
        return ((build_record + "\n\n") if build_record else "") + "\n\n".join(extra)

    def _maybe_diagram(session_id: str, design: str) -> None:
        bundle = b(session_id)
        if bundle.scenario.track != "interview" or not (design or "").strip():
            return
        from pathlib import Path
        from sim.core.design.diagram import render_design_diagram
        mermaid = render_design_diagram(manager.llm, design)
        bundle.session_service.remember_diagram(session_id, mermaid)
        env = bundle.environment
        h = env.handle(session_id) if env is not None else None
        if h is None and env is not None:
            try:
                h = env.provision(session_id)
            except Exception:
                h = None
        if h is not None:
            try:
                Path(h.workdir, "DESIGN.mmd").write_text(mermaid, encoding="utf-8")
            except OSError:
                pass

    def _grade_body(session_id: str, payload: dict | None, build_record: str):
        import dataclasses as _dc
        from sim.core.grading.rubric import Criterion, Rubric
        from sim.core.levels import (
            interview_expectation, profile, systems_expectation)
        bundle = b(session_id)
        include_tickets = bool((payload or {}).get("include_tickets"))
        interview = bundle.scenario.track == "interview"
        if interview:
            include_tickets = include_tickets  # toggle only applies here
        else:
            include_tickets = False
        build_record = _enrich_build_record(
            session_id, build_record, include_tickets)
        prof = profile(_session_level(session_id))
        adj = tuple(_dc.replace(c, weight=c.weight * prof.weight_shift.get(c.key, 1.0))
                    for c in bundle.scenario.rubric.criteria)
        grade_criteria = adj
        if include_tickets:
            grade_criteria = adj + (Criterion(
                key="tickets",
                description=(
                    "EXTRA CREDIT: implementation tickets are specific enough "
                    "that an engineer who had only the tickets (not the design "
                    "doc) could implement the system. Score 0 if there are no "
                    "useful tickets."
                ),
                weight=0.5,
            ),)
        if interview:
            expectation = interview_expectation(prof.key)
        elif bundle.scenario.track == "systems":
            expectation = systems_expectation(prof.key)
        else:
            expectation = prof.expectation
        result = app.state.grader.grade(
            session_id, app.state.repo, Rubric(criteria=grade_criteria),
            build_record, expectation)
        body = result.as_dict()
        if include_tickets:
            tickets_s = next((s for s in result.scores if s.key == "tickets"), None)
            by_key = {s.key: s.score for s in result.scores}
            weighted = sum(by_key.get(c.key, 0.0) * c.weight for c in adj)
            total_w = sum(c.weight for c in adj)
            base = weighted / total_w if total_w else 0.0
            bonus = 0.15 * (tickets_s.score if tickets_s else 0.0)
            body["total_base"] = round(base, 3)
            body["total"] = round(min(1.0, base + bonus), 3)
            body["include_tickets"] = True
            body["scores"] = [s for s in body["scores"] if s["key"] != "tickets"]
            if tickets_s:
                body["tickets_extra"] = {
                    "key": "tickets", "score": round(tickets_s.score, 3),
                    "evidence": tickets_s.evidence,
                }
        else:
            body["include_tickets"] = False
        body["level"] = prof.key
        body["calibrated"] = app.state.grader_calibrated
        if not app.state.grader_calibrated:
            body["caveat"] = ("Grader is not yet calibrated against human scores — "
                              "treat this as directional, not a grade.")
        return body

    @app.post("/api/session/{session_id}/grade")
    async def grade(session_id: str, payload: dict | None = None):
        bundle = b(session_id)
        build_record = (payload or {}).get("build_record", "")
        if not build_record and app.state.submissions is not None:
            sub = app.state.submissions.latest(session_id)
            if sub and sub.kind == "repo" and app.state.github_observer is not None:
                try:
                    build_record = await run_in_threadpool(
                        app.state.github_observer.summary, sub.content)
                except Exception as e:
                    build_record = f"(could not read submitted repo {sub.content}: {e})"
            elif sub:
                build_record = f"SUBMITTED PATCH ({sub.filename}):\n{sub.content}"
        if not build_record and bundle.environment and app.state.build_observer:
            h = bundle.environment.handle(session_id)
            if h:
                build_record = app.state.build_observer.summary(h.workdir)
        body = await run_in_threadpool(
            _grade_body, session_id, payload, build_record)
        return JSONResponse(body)

    @app.get("/api/session/{session_id}/diagram")
    def get_diagram(session_id: str):
        svc = b(session_id).session_service
        mermaid = svc.diagram_text(session_id)
        if not mermaid:
            from pathlib import Path
            env = b(session_id).environment
            h = env.handle(session_id) if env is not None else None
            if h is not None:
                p = Path(h.workdir) / "DESIGN.mmd"
                if p.is_file():
                    mermaid = p.read_text(encoding="utf-8")
                    svc.remember_diagram(session_id, mermaid)
        return {"mermaid": mermaid}

    # ---- learner submission (Version A: code lives on the learner's machine) ----
    @app.get("/api/session/{session_id}/starter.zip")
    def starter_zip(session_id: str):
        import io, zipfile
        from pathlib import Path as _P
        from fastapi.responses import Response
        sc = b(session_id).scenario
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            base = _P(sc.starter_template) if sc.starter_template else None
            if base and base.exists():
                for f in base.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(base).as_posix())
            else:
                z.writestr("README.md", f"# {sc.title}\n\nNo starter files for this scenario — begin from scratch.\n")
        return Response(content=buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{session_id}-starter.zip"'})

    @app.post("/api/session/{session_id}/submit")
    def submit_work(session_id: str, payload: dict):
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        content = (payload or {}).get("content", "")
        filename = (payload or {}).get("filename", "work.patch")
        if not content.strip():
            return JSONResponse({"error": "nothing submitted"}, status_code=400)
        ts = datetime.now(timezone.utc).isoformat()
        sub = app.state.submissions.save(session_id, filename, content, ts)
        # a short marker in the transcript so the instructor replay shows the moment
        app.state.repo.append(StoredMessage(
            session_id=session_id, sender="tester", channel="general",
            content=f"[reveal] Submitted work: {filename} ({sub.lines} lines).",
            ts=ts, kind="event"))
        svc = b(session_id).session_service
        svc.remember_design(session_id, content)
        _maybe_diagram(session_id, content)
        svc.after_submission(session_id)
        return {"ok": True, "seq": sub.seq, "filename": filename, "lines": sub.lines}

    @app.post("/api/session/{session_id}/submit-repo")
    def submit_repo(session_id: str, payload: dict):
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        url = (payload or {}).get("url", "").strip()
        if app.state.github_observer is None:
            return JSONResponse({"error": "github submission not configured"}, status_code=501)
        ok, msg = app.state.github_observer.validate(url)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        ts = datetime.now(timezone.utc).isoformat()
        app.state.submissions.save(session_id, "github-repo", url, ts, kind="repo")
        app.state.repo.append(StoredMessage(
            session_id=session_id, sender="tester", channel="general",
            content=f"[reveal] Submitted repo: {url}", ts=ts, kind="event"))
        b(session_id).session_service.after_submission(session_id)
        return {"ok": True, "message": msg}

    @app.get("/api/session/{session_id}/submissions")
    def list_submissions(session_id: str):
        subs = app.state.submissions.list(session_id)
        return {"submissions": [
            {"seq": s.seq, "filename": s.filename, "lines": s.lines,
             "ts": s.ts, "kind": s.kind, "content": s.content}
            for s in subs]}

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
            env.teardown(session_id)
        return {"torn_down": True}

    # ---- files ----------------------------------------------------------
    @app.get("/api/session/{session_id}/files/list")
    def files_list(session_id: str, path: str = ""):
        if app.state.files is None:
            return JSONResponse({"error": "no file browser"}, status_code=501)
        wd = _workdir(session_id)
        if not wd:
            return JSONResponse({"error": "no workspace — open the Workspace app first"}, status_code=409)
        try:
            entries = app.state.files.list_dir(wd, path)
        except (ValueError, NotADirectoryError, FileNotFoundError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"path": path, "entries": [
            {"name": e.name, "is_dir": e.is_dir, "size": e.size} for e in entries]}

    @app.get("/api/session/{session_id}/files/read")
    def files_read(session_id: str, path: str = ""):
        if app.state.files is None:
            return JSONResponse({"error": "no file browser"}, status_code=501)
        wd = _workdir(session_id)
        if not wd:
            return JSONResponse({"error": "no workspace — open the Workspace app first"}, status_code=409)
        try:
            c = app.state.files.read_file(wd, path)
        except (ValueError, IsADirectoryError, FileNotFoundError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"path": c.path, "text": c.text, "note": c.note}

    # ---- tickets --------------------------------------------------------
    @app.get("/api/session/{session_id}/tickets")
    def tickets_board(session_id: str):
        return b(session_id).ticket_service.board(session_id)

    @app.post("/api/session/{session_id}/tickets")
    def tickets_create(session_id: str, payload: dict):
        ts = b(session_id).ticket_service
        ts.create(session_id, payload.get("title", "").strip() or "(untitled)",
                  payload.get("description", ""),
                  issue_type=payload.get("issue_type", "task"),
                  priority=payload.get("priority", "medium"),
                  labels=payload.get("labels", ""))
        return ts.board(session_id)

    @app.post("/api/session/{session_id}/tickets/{ticket_id}/move")
    def tickets_move(session_id: str, ticket_id: str, payload: dict):
        ts = b(session_id).ticket_service
        try:
            ts.move(session_id, ticket_id, payload.get("status", ""))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return ts.board(session_id)

    # ---- mail -----------------------------------------------------------
    @app.get("/api/session/{session_id}/mail/threads")
    def mail_threads(session_id: str):
        m = b(session_id).mail_service
        return {"threads": m.list_threads(session_id), "unread": m.unread(session_id)}

    @app.get("/api/session/{session_id}/mail/unread")
    def mail_unread(session_id: str):
        return {"count": b(session_id).mail_service.unread(session_id)}

    @app.get("/api/session/{session_id}/mail/thread/{thread_id}")
    def mail_open(session_id: str, thread_id: str):
        try:
            return b(session_id).mail_service.open_thread(session_id, thread_id)
        except KeyError:
            return JSONResponse({"error": "no such thread"}, status_code=404)

    @app.post("/api/session/{session_id}/mail/compose")
    async def mail_compose(session_id: str, payload: dict):
        return await run_in_threadpool(
            b(session_id).mail_service.compose, session_id,
            payload.get("to", ""), payload.get("subject", ""), payload.get("body", ""))

    @app.post("/api/session/{session_id}/mail/thread/{thread_id}/reply")
    async def mail_reply(session_id: str, thread_id: str, payload: dict):
        try:
            return await run_in_threadpool(
                b(session_id).mail_service.reply, session_id, thread_id,
                payload.get("body", ""))
        except KeyError:
            return JSONResponse({"error": "no such thread"}, status_code=404)

    # ---- instructor (light password gate; NOT real auth) ---------------
    @app.get("/instructor")
    def instructor_page():
        return FileResponse(_STATIC / "instructor.html")

    @app.get("/login")
    def login_page():
        return FileResponse(_STATIC / "login.html")

    @app.get("/challenger")
    def challenger_page():
        return FileResponse(_STATIC / "challenger.html")

    @app.get("/admin")
    def admin_page():
        return FileResponse(_STATIC / "admin.html")

    @app.get("/api/auth/config")
    def auth_config():
        return app.state.auth.public_config()

    @app.get("/api/auth/me")
    def auth_me(request: Request):
        if not app.state.auth.gated:
            p = _local_instructor()
            return {"uid": p.uid, "email": p.email, "role": p.role, "disabled": False}
        p = getattr(request.state, "principal", None)
        if p is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return {"uid": p.uid, "email": p.email, "role": p.role, "disabled": False}

    @app.get("/api/me/sessions")
    def my_sessions(request: Request):
        auth = app.state.auth
        p = _actor(request)
        if auth.sessions is None:
            return {"sessions": []}
        rows = list(auth.sessions.list_by_assignee(p.uid))
        if p.role in ("instructor", "admin"):
            rows = list(auth.sessions.list_by_owner(p.uid)) if p.role == "instructor" else list(auth.sessions.list_all())
        out = []
        for rec in rows:
            title = rec.scenario_key
            if rec.scenario_key in manager.registry:
                title = manager.registry[rec.scenario_key].title
            out.append({
                "session_id": rec.id, "scenario": rec.scenario_key, "title": title,
                "level": rec.level, "status": rec.status,
                "owner_uid": rec.owner_uid, "assignee_uid": rec.assignee_uid,
                "created_at": rec.created_at,
            })
        return {"sessions": out}

    @app.post("/api/session/{session_id}/claim")
    def claim_session(session_id: str, request: Request):
        from sim.core.access.policy import can_claim_session
        auth = app.state.auth
        p = _actor(request)
        rec = auth.session(session_id) if auth.sessions else None
        if not can_claim_session(p, rec):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        auth.touch_session(session_id, assignee_uid=p.uid, status="active")
        return {"ok": True, "session_id": session_id}

    @app.post("/api/instructor/sessions")
    def instructor_create_session(payload: dict, request: Request,
                                  x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        import uuid
        from sim.core.levels import LEVEL_ORDER
        key = (payload or {}).get("scenario", "")
        if key and key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        lvl = (payload or {}).get("level") or app.state.settings.get_instructor().default_level
        if lvl not in LEVEL_ORDER:
            return JSONResponse({"error": "bad level"}, status_code=400)
        sid = (payload or {}).get("session_id") or ("s-" + uuid.uuid4().hex[:10])
        assignee = (payload or {}).get("assignee_uid") or ""
        email = (payload or {}).get("assignee_email") or ""
        auth = app.state.auth
        if email and auth.users:
            u = auth.users.get_by_email(email)
            if u:
                assignee = u.uid
        owner = _actor(request).uid
        if key:
            app.state.settings.set_session_scenario(sid, key)
        app.state.settings.set_session_level(sid, lvl)
        if auth.sessions:
            auth.touch_session(sid, owner_uid=owner, assignee_uid=assignee,
                               scenario_key=key, level=lvl, status="assigned")
        return {"ok": True, "session_id": sid, "url": f"/#{sid}"}

    def _instr_ok(token: str) -> bool:
        if app.state.auth.gated:
            return True
        return bool(app.state.instructor_password) and token == app.state.instructor_password

    @app.post("/api/instructor/auth")
    def instructor_auth(payload: dict):
        return {"ok": payload.get("password", "") == app.state.instructor_password}

    @app.get("/api/instructor/settings")
    def instructor_get_settings(x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from sim.core.levels import levels_meta
        s = app.state.settings.get_instructor()
        scs = []
        for m in manager.scenarios_meta():
            m = dict(m); m["starter_url"] = app.state.settings.get_scenario_starter_url(m["key"])
            scs.append(m)
        return {"onboarded": s.onboarded, "default_level": s.default_level,
                "levels": levels_meta(), "scenarios": scs}

    @app.post("/api/instructor/settings")
    def instructor_set_settings(payload: dict, x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from sim.core.ports.settings import InstructorSettings
        app.state.settings.set_instructor(InstructorSettings(
            onboarded=bool(payload.get("onboarded", True)),
            default_level=payload.get("default_level", "senior")))
        return {"ok": True}

    @app.post("/api/instructor/session/{session_id}/level")
    def instructor_set_level(session_id: str, payload: dict, request: Request,
                             x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from sim.core.levels import LEVEL_ORDER
        lvl = payload.get("level", "")
        if lvl not in LEVEL_ORDER:
            return JSONResponse({"error": "bad level"}, status_code=400)
        app.state.settings.set_session_level(session_id, lvl)
        app.state.auth.touch_session(
            session_id, owner_uid=_actor(request).uid, level=lvl)
        return {"ok": True, "level": lvl}

    @app.post("/api/instructor/scenario/{scenario_key}/starter-url")
    def instructor_set_starter_url(scenario_key: str, payload: dict,
                                   x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if scenario_key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        app.state.settings.set_scenario_starter_url(scenario_key,
                                                    payload.get("url", "").strip())
        return {"ok": True}

    @app.post("/api/instructor/session/{session_id}/scenario")
    def instructor_set_scenario(session_id: str, payload: dict, request: Request,
                                x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        key = payload.get("scenario", "")
        if key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        app.state.settings.set_session_scenario(session_id, key)
        app.state.auth.touch_session(
            session_id, owner_uid=_actor(request).uid, scenario_key=key)
        return {"ok": True, "scenario": key}

    @app.get("/api/instructor/sessions")
    def instructor_sessions(request: Request,
                            x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        auth = app.state.auth
        p = _actor(request)
        by_id = {}
        repo = app.state.repo
        msg_sessions = repo.list_sessions() if hasattr(repo, "list_sessions") else []
        for s in msg_sessions:
            by_id[s["session_id"]] = dict(s)
        if auth.sessions is not None:
            recs = (list(auth.sessions.list_all()) if (auth.gated and p.role == "admin")
                    else list(auth.sessions.list_by_owner(p.uid)) if auth.gated
                    else list(auth.sessions.list_all()))
            for rec in recs:
                row = by_id.get(rec.id, {"session_id": rec.id, "count": 0,
                                         "first_ts": rec.created_at, "last_ts": rec.created_at})
                row["assignee_uid"] = rec.assignee_uid
                row["owner_uid"] = rec.owner_uid
                row["status"] = rec.status
                by_id[rec.id] = row
        sessions = list(by_id.values())
        if auth.gated and p.role == "instructor":
            sessions = [s for s in sessions
                        if s.get("owner_uid", p.uid) in ("", p.uid)]
        sessions.sort(key=lambda s: s.get("last_ts") or "", reverse=True)
        for s in sessions:
            sid = s["session_id"]
            s["scenario"] = manager.resolve_scenario_key(sid)
            s["level"] = _session_level(sid)
        return {"sessions": sessions}

    @app.get("/api/instructor/session/{sid}")
    def instructor_session(sid: str, x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        bundle = b(sid)
        mail_meta = {}
        for th in bundle.mail_service.list_threads(sid):
            mail_meta["mail:" + th["id"]] = {"subject": th["subject"],
                                             "with_name": th["with_name"]}
        return {
            "scenario": {"title": bundle.scenario.title,
                         "difficulty": bundle.scenario.difficulty,
                         "track": bundle.scenario.track},
            "level": _session_level(sid),
            "personas": [{"key": p.key, "name": p.name, "role": p.role,
                          "lane": getattr(p, "lane", "")}
                         for p in bundle.scenario.personas],
            "transcript": bundle.session_service.export(sid),
            "mail": mail_meta,
            "submissions": [
                {"seq": s.seq, "filename": s.filename, "lines": s.lines,
                 "ts": s.ts, "content": s.content}
                for s in app.state.submissions.list(sid)
            ],
        }

    @app.get("/api/instructor/session/{sid}/export.md")
    def instructor_export_md(sid: str, include_tickets: bool = False,
                             x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from fastapi.responses import Response
        from sim.core.levels import profile
        from sim.core.session.audit_export import build_audit_markdown
        bundle = b(sid)
        svc = bundle.session_service
        build_record = ""
        if app.state.submissions is not None:
            sub = app.state.submissions.latest(sid)
            if sub:
                build_record = f"SUBMITTED PATCH ({sub.filename}):\n{sub.content}"
        if not svc.design_text(sid) and build_record:
            svc.remember_design(sid, build_record)
        try:
            grade = _grade_body(sid, {"include_tickets": include_tickets}, build_record)
        except Exception:
            grade = None
        lvl = _session_level(sid)
        mermaid = svc.diagram_text(sid)
        md = build_audit_markdown(
            session_id=sid,
            title=bundle.scenario.title,
            track=bundle.scenario.track,
            difficulty=bundle.scenario.difficulty,
            level=lvl,
            level_label=profile(lvl).label,
            personas=bundle.scenario.personas,
            rows=app.state.repo.list_for_session(sid),
            grade=grade,
            design=svc.design_text(sid),
            mermaid=mermaid,
            tickets=_flatten_tickets(sid),
            submissions=app.state.submissions.list(sid) if app.state.submissions else [],
        )
        return Response(
            content=md, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{sid}-audit.md"'})

    def _cascade_delete_session(sid: str) -> None:
        auth = app.state.auth
        for store in (app.state.repo, manager.unlock, manager.mailstore,
                      manager.ticketstore, manager.submissions, app.state.settings):
            fn = getattr(store, "delete_for_session", None) or getattr(
                store, "delete_session_settings", None)
            if callable(fn):
                try:
                    fn(sid)
                except TypeError:
                    if hasattr(store, "delete_session_settings"):
                        store.delete_session_settings(sid)
        env = b(sid).environment
        if env is not None:
            try:
                env.teardown(sid)
            except Exception:
                pass
        if auth.sessions:
            auth.sessions.delete(sid)

    @app.get("/api/admin/users")
    def admin_list_users():
        users = app.state.auth.users
        if users is None:
            return {"users": []}
        return {"users": [
            {"uid": u.uid, "email": u.email, "role": u.role,
             "disabled": u.disabled, "created_at": u.created_at,
             "last_login": u.last_login}
            for u in users.list()
        ]}

    @app.post("/api/admin/users")
    def admin_create_user(payload: dict):
        import secrets
        from sim.core.ports.identity import ROLES
        from sim.core.ports.users import UserRecord
        from datetime import datetime, timezone
        email = (payload or {}).get("email", "").strip()
        role = (payload or {}).get("role", "challenger")
        if not email or role not in ROLES:
            return JSONResponse({"error": "email and valid role required"}, status_code=400)
        auth = app.state.auth
        uid = ""
        if auth.firebase is not None:
            password = secrets.token_urlsafe(16)
            try:
                uid = auth.firebase.create_email_user(email, password)
                if (payload or {}).get("send_reset", True):
                    auth.firebase.send_password_reset(email)
            except IdentityError as e:
                return JSONResponse({"error": e.detail}, status_code=e.status)
        uid = uid or ("u-" + secrets.token_hex(8))
        rec = auth.users.upsert(UserRecord(
            uid=uid, email=email, role=role, disabled=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        return {"ok": True, "uid": rec.uid, "email": rec.email, "role": rec.role}

    @app.patch("/api/admin/users/{uid}")
    def admin_patch_user(uid: str, payload: dict):
        from sim.core.ports.identity import ROLES
        from sim.core.ports.users import UserRecord
        auth = app.state.auth
        rec = auth.users.get(uid) if auth.users else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        role = (payload or {}).get("role", rec.role)
        disabled = rec.disabled
        if "disabled" in (payload or {}):
            disabled = bool(payload["disabled"])
        if role not in ROLES:
            return JSONResponse({"error": "bad role"}, status_code=400)
        if rec.role == "admin" and (role != "admin" or disabled) and auth.users.count_role("admin") <= 1:
            return JSONResponse({"error": "cannot remove the last admin"}, status_code=400)
        rec = auth.users.upsert(UserRecord(
            uid=rec.uid, email=rec.email, role=role, disabled=disabled,
            created_at=rec.created_at, last_login=rec.last_login))
        return {"ok": True, "uid": rec.uid, "role": rec.role, "disabled": rec.disabled}

    @app.delete("/api/admin/users/{uid}")
    def admin_delete_user(uid: str):
        auth = app.state.auth
        rec = auth.users.get(uid) if auth.users else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if rec.role == "admin" and auth.users.count_role("admin") <= 1:
            return JSONResponse({"error": "cannot delete the last admin"}, status_code=400)
        auth.users.delete(uid)
        return {"ok": True}

    @app.get("/api/admin/sessions")
    def admin_list_sessions():
        auth = app.state.auth
        rows = list(auth.sessions.list_all()) if auth.sessions else []
        return {"sessions": [
            {"session_id": r.id, "owner_uid": r.owner_uid,
             "assignee_uid": r.assignee_uid, "scenario": r.scenario_key,
             "level": r.level, "status": r.status, "created_at": r.created_at}
            for r in rows
        ]}

    @app.patch("/api/admin/sessions/{sid}")
    def admin_patch_session(sid: str, payload: dict):
        auth = app.state.auth
        rec = auth.session(sid)
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        owner = (payload or {}).get("owner_uid", rec.owner_uid)
        assignee = (payload or {}).get("assignee_uid", rec.assignee_uid)
        scenario = (payload or {}).get("scenario", rec.scenario_key)
        level = (payload or {}).get("level", rec.level)
        status = (payload or {}).get("status", rec.status)
        if scenario:
            app.state.settings.set_session_scenario(sid, scenario)
        if level:
            app.state.settings.set_session_level(sid, level)
        auth.touch_session(sid, owner_uid=owner, assignee_uid=assignee,
                           scenario_key=scenario, level=level, status=status)
        return {"ok": True}

    @app.delete("/api/admin/sessions/{sid}")
    def admin_delete_session(sid: str):
        _cascade_delete_session(sid)
        return {"ok": True}

    @app.get("/api/admin/sessions/{sid}/messages")
    def admin_messages(sid: str):
        return {"messages": b(sid).session_service.export(sid)}

    @app.delete("/api/admin/sessions/{sid}/messages")
    def admin_delete_messages(sid: str):
        app.state.repo.delete_for_session(sid)
        return {"ok": True}

    @app.get("/api/admin/sessions/{sid}/tickets")
    def admin_tickets(sid: str):
        return b(sid).ticket_service.board(sid)

    @app.delete("/api/admin/sessions/{sid}/tickets/{tid}")
    def admin_delete_ticket(sid: str, tid: str):
        ok = manager.ticketstore.delete_one(sid, tid)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"ok": True}

    @app.get("/api/admin/sessions/{sid}/submissions")
    def admin_submissions(sid: str):
        subs = app.state.submissions.list(sid)
        return {"submissions": [
            {"seq": s.seq, "filename": s.filename, "lines": s.lines,
             "ts": s.ts, "kind": s.kind, "content": s.content}
            for s in subs]}

    @app.delete("/api/admin/sessions/{sid}/submissions")
    def admin_delete_submissions(sid: str):
        app.state.submissions.delete_for_session(sid)
        return {"ok": True}

    @app.post("/api/admin/sessions/{sid}/unlock/reset")
    def admin_unlock_reset(sid: str):
        manager.unlock.delete_for_session(sid)
        return {"ok": True}

    @app.get("/api/admin/settings")
    def admin_get_settings():
        s = app.state.settings.get_instructor()
        return {"onboarded": s.onboarded, "default_level": s.default_level}

    @app.put("/api/admin/settings")
    def admin_put_settings(payload: dict):
        from sim.core.ports.settings import InstructorSettings
        app.state.settings.set_instructor(InstructorSettings(
            onboarded=bool(payload.get("onboarded", True)),
            default_level=payload.get("default_level", "senior")))
        return {"ok": True}

    @app.get("/api/admin/scenarios")
    def admin_scenarios():
        out = []
        for m in manager.scenarios_meta():
            m = dict(m)
            m["starter_url"] = app.state.settings.get_scenario_starter_url(m["key"])
            m["enabled"] = app.state.settings.get_scenario_enabled(m["key"])
            out.append(m)
        return {"scenarios": out}

    @app.put("/api/admin/scenarios/{key}")
    def admin_put_scenario(key: str, payload: dict):
        if key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        if "url" in payload or "starter_url" in payload:
            app.state.settings.set_scenario_starter_url(
                key, (payload.get("starter_url") or payload.get("url") or "").strip())
        if "enabled" in payload:
            app.state.settings.set_scenario_enabled(key, bool(payload["enabled"]))
        return {"ok": True}

    @app.get("/api/admin/auth/status")
    def admin_auth_status():
        auth = app.state.auth
        n = len(list(auth.users.list())) if auth.users else 0
        return {"auth_mode": auth.mode, "firebase_project_id": auth.firebase_project_id,
                "users_count": n,
                "bootstrap_configured": bool(auth.bootstrap_admin_email)}

    # ---- websocket ------------------------------------------------------
    @app.websocket("/ws/{session_id}")
    async def ws(websocket: WebSocket, session_id: str):
        auth = app.state.auth
        if auth.gated:
            token = websocket.query_params.get("token") or ""
            try:
                principal = auth.principal_from_token(token)
            except IdentityError as e:
                await websocket.close(code=4401)
                return
            if not auth.allow_session(principal, session_id, mutate=True):
                await websocket.close(code=4403)
                return
        await websocket.accept()
        svc = b(session_id).session_service
        try:
            while True:
                data = await websocket.receive_json()
                content = (data or {}).get("content", "").strip()
                target = (data or {}).get("target")
                if not content:
                    continue
                try:
                    msgs = await run_in_threadpool(
                        svc.post_tester_message, session_id, content, target)
                except Exception as exc:
                    log.exception("chat turn failed for session %s", session_id)
                    await websocket.send_json({
                        "kind": "error",
                        "error": str(exc) or exc.__class__.__name__,
                    })
                    continue
                for m in msgs:
                    await websocket.send_json(
                        {"id": m.id, "sender": m.sender, "content": m.content,
                         "channel": m.channel, "ts": m.ts, "kind": m.kind})
        except WebSocketDisconnect:
            return

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    return app
