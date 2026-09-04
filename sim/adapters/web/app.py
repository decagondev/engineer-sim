from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def create_web_app(manager, grader, grader_calibrated: bool = False,
                   build_observer=None, workspace_reader=None,
                   instructor_password: str = "", github_observer=None) -> FastAPI:
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

    def b(session_id):
        return manager.for_session(session_id)

    def _session_level(session_id: str) -> str:
        from sim.core.levels import DEFAULT_LEVEL
        s = app.state.settings
        if s is None:
            return DEFAULT_LEVEL
        return s.get_session_level(session_id) or s.get_instructor().default_level

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
                "starter_url": starter_url,
                "personas": [{"key": p.key, "name": p.name, "role": p.role}
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

    @app.post("/api/session/{session_id}/grade")
    async def grade(session_id: str, payload: dict | None = None):
        import dataclasses as _dc
        from sim.core.grading.rubric import Rubric
        from sim.core.levels import profile
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
        prof = profile(_session_level(session_id))
        adj = tuple(_dc.replace(c, weight=c.weight * prof.weight_shift.get(c.key, 1.0))
                    for c in bundle.scenario.rubric.criteria)
        result = await run_in_threadpool(
            app.state.grader.grade, session_id, app.state.repo,
            Rubric(criteria=adj), build_record, prof.expectation)
        body = result.as_dict()
        body["level"] = prof.key
        body["calibrated"] = app.state.grader_calibrated
        if not app.state.grader_calibrated:
            body["caveat"] = ("Grader is not yet calibrated against human scores — "
                              "treat this as directional, not a grade.")
        return JSONResponse(body)

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

    def _instr_ok(token: str) -> bool:
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
    def instructor_set_level(session_id: str, payload: dict,
                             x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from sim.core.levels import LEVEL_ORDER
        lvl = payload.get("level", "")
        if lvl not in LEVEL_ORDER:
            return JSONResponse({"error": "bad level"}, status_code=400)
        app.state.settings.set_session_level(session_id, lvl)
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
    def instructor_set_scenario(session_id: str, payload: dict,
                                x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        key = payload.get("scenario", "")
        if key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        app.state.settings.set_session_scenario(session_id, key)
        return {"ok": True, "scenario": key}

    @app.get("/api/instructor/sessions")
    def instructor_sessions(x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        repo = app.state.repo
        sessions = repo.list_sessions() if hasattr(repo, "list_sessions") else []
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
                         "difficulty": bundle.scenario.difficulty},
            "level": _session_level(sid),
            "personas": [{"key": p.key, "name": p.name, "role": p.role}
                         for p in bundle.scenario.personas],
            "transcript": bundle.session_service.export(sid),
            "mail": mail_meta,
            "submissions": [
                {"seq": s.seq, "filename": s.filename, "lines": s.lines,
                 "ts": s.ts, "content": s.content}
                for s in app.state.submissions.list(sid)
            ],
        }

    # ---- websocket ------------------------------------------------------
    @app.websocket("/ws/{session_id}")
    async def ws(websocket: WebSocket, session_id: str):
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
                        {"sender": m.sender, "content": m.content,
                         "channel": m.channel, "ts": m.ts})
        except WebSocketDisconnect:
            return

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    return app
