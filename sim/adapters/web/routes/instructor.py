from __future__ import annotations

from fastapi import Header
from fastapi import Request
from fastapi.responses import JSONResponse


def register(app, ctx):
    """Routes and helpers for the instructor area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    auth = ctx.auth
    _actor = ctx._actor
    _grade_payload = ctx._grade_payload
    _scenario_config = ctx._scenario_config
    _site = ctx._site
    auth = ctx.auth

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

    # ---- cohorts (instructor view: read cohorts, batch-create sessions) ----
    def _users_by_uid() -> dict:
        """One listing of the directory; a read per member is what made the
        cohort screens take minutes on Firestore."""
        users = app.state.auth.users
        if users is None:
            return {}
        try:
            return {u.uid: u for u in users.list()}
        except Exception:
            return {}

    def _cohort_members(store, cid: str, users_by_uid: dict | None = None) -> list:
        by_uid = _users_by_uid() if users_by_uid is None else users_by_uid
        out = []
        for uid in store.members(cid):
            u = by_uid.get(uid)
            if u is None:
                out.append({"uid": uid, "email": "", "name": "", "role": "",
                            "disabled": False})
            else:
                out.append({"uid": u.uid, "email": u.email, "name": u.name or "",
                            "role": u.role, "disabled": u.disabled,
                            "has_groq_key": bool(getattr(u, "groq_key_enc", "")),
                            "has_github_token": bool(getattr(u, "github_token_enc", "")),
                            "has_gitlab_token": bool(getattr(u, "gitlab_token_enc", ""))})
        out.sort(key=lambda m: (m["name"] or m["email"] or m["uid"]).lower())
        return out

    def _assignable(m: dict) -> str:
        """'' when a member can be handed a session, else the reason not."""
        if not m["role"]:
            return "no account"
        if m["role"] != "challenger":
            return f"role is {m['role']}"
        if m["disabled"]:
            return "account disabled"
        return ""

    @app.get("/api/instructor/cohorts")
    def instructor_cohorts(x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        store = ctx._cohorts()
        if store is None:
            return {"cohorts": []}
        rows = []
        by_uid = _users_by_uid()
        for c in store.list():
            members = _cohort_members(store, c.id, by_uid)
            rows.append({"id": c.id, "name": c.name, "notes": c.notes,
                         "member_count": len(members),
                         "challenger_count": sum(1 for m in members if not _assignable(m))})
        rows.sort(key=lambda r: r["name"].lower())
        return {"cohorts": rows}

    @app.get("/api/instructor/cohorts/{cid}")
    def instructor_cohort(cid: str, scenario: str = "",
                          x_instructor_token: str = Header(default="")):
        """Members plus, for each, the sessions they already hold (optionally
        only for one scenario) so the batch screen can show who is covered."""
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        store = ctx._cohorts()
        rec = store.get(cid) if store else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        sessions = app.state.auth.sessions
        by_assignee: dict = {}
        if sessions is not None:
            for r in sessions.list_all():           # one stream, not one per member
                if r.assignee_uid:
                    by_assignee.setdefault(r.assignee_uid, []).append(r)
        members = []
        for m in _cohort_members(store, cid):
            held = []
            for r in by_assignee.get(m["uid"], []):
                if scenario and r.scenario_key != scenario:
                    continue
                held.append({"session_id": r.id, "scenario": r.scenario_key,
                             "level": r.level, "status": r.status})
            members.append({**m, "blocked": _assignable(m), "sessions": held})
        return {"id": rec.id, "name": rec.name, "notes": rec.notes,
                "members": members}

    def _cohort_report(cid: str, scenario: str):
        from sim.core.reporting.cohort import cohort_results
        store = ctx._cohorts()
        rec = store.get(cid) if store else None
        if rec is None:
            return None, JSONResponse({"error": "not found"}, status_code=404)
        if scenario not in manager.registry:
            return None, JSONResponse({"error": "no such scenario"}, status_code=400)
        members = [m for m in _cohort_members(store, cid) if not _assignable(m)]
        uids = {m["uid"] for m in members}
        rows = [r for r in ctx._enrich_sessions(ctx._merge_known_sessions(all_registered=True))
                if r.get("scenario") == scenario and r.get("assignee_uid") in uids]
        grades = {}
        if app.state.grades is not None and rows:
            stored = app.state.grades.list_many([r["session_id"] for r in rows])
            grades = {sid: _grade_payload(g) for sid, g in stored.items()}
        report = cohort_results(scenario, members, rows, grades, manager.registry[scenario].rubric)
        return report, None

    @app.get("/api/instructor/cohorts/{cid}/results")
    def instructor_cohort_results(cid: str, scenario: str = "", fresh: bool = False,
                                  x_instructor_token: str = Header(default="")):
        """How the cohort did on one scenario: per-criterion distribution, who
        has not submitted, and every member's totals."""
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        def build():
            report, err = _cohort_report(cid, scenario)
            return {"error": err} if err is not None else {"report": report.as_dict(),
                                                            "title": manager.registry[scenario].title}
        data = ctx._cached(f"cohort:{cid}:{scenario}", build, fresh)
        if data.get("error") is not None:
            return data["error"]
        return data

    @app.get("/api/instructor/cohorts/{cid}/results.csv")
    def instructor_cohort_results_csv(cid: str, scenario: str = "",
                                      x_instructor_token: str = Header(default="")):
        from fastapi.responses import Response
        from sim.core.reporting.cohort import results_csv
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        report, err = _cohort_report(cid, scenario)
        if err is not None:
            return err
        return Response(content=results_csv(report), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{cid}-{scenario}-results.csv"'})

    @app.post("/api/instructor/cohorts/{cid}/sessions")
    def instructor_cohort_sessions(cid: str, payload: dict, request: Request,
                                   x_instructor_token: str = Header(default="")):
        """One session per assignable member, all on the same scenario + level.
        Members who already hold a session on that scenario are skipped unless
        skip_existing is false."""
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        import uuid
        from sim.core.levels import LEVEL_ORDER
        store = ctx._cohorts()
        rec = store.get(cid) if store else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        key = (payload or {}).get("scenario", "")
        if key not in manager.registry:
            return JSONResponse({"error": "no such scenario"}, status_code=400)
        lvl = (payload or {}).get("level") or app.state.settings.get_instructor().default_level
        if lvl not in LEVEL_ORDER:
            return JSONResponse({"error": "bad level"}, status_code=400)
        skip_existing = bool((payload or {}).get("skip_existing", True))
        only = (payload or {}).get("uids")
        only = {str(u) for u in only} if isinstance(only, list) else None
        auth = app.state.auth
        owner = _actor(request).uid
        created, skipped = [], []
        held: dict = {}
        if skip_existing and auth.sessions is not None:
            for r in auth.sessions.list_all():
                if r.assignee_uid and r.scenario_key == key:
                    held.setdefault(r.assignee_uid, []).append(r)
        for m in _cohort_members(store, cid):
            if only is not None and m["uid"] not in only:
                continue   # the client is creating in batches to show progress
            why = _assignable(m)
            if why:
                skipped.append({**m, "reason": why})
                continue
            if skip_existing and auth.sessions is not None:
                have = held.get(m["uid"], [])
                if have:
                    skipped.append({**m, "reason": "already has this scenario",
                                    "session_id": have[0].id})
                    continue
            sid = "s-" + uuid.uuid4().hex[:10]
            app.state.settings.set_session_scenario(sid, key)
            app.state.settings.set_session_level(sid, lvl)
            if auth.sessions:
                auth.touch_session(sid, owner_uid=owner, assignee_uid=m["uid"],
                                   scenario_key=key, level=lvl, status="assigned")
            created.append({**m, "session_id": sid, "url": f"/#{sid}"})
        return {"ok": True, "cohort": {"id": rec.id, "name": rec.name},
                "scenario": key, "level": lvl,
                "created": created, "skipped": skipped}

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
        cfg = _scenario_config()
        scs = []
        for m in manager.scenarios_meta():
            m = dict(m)
            m["starter_url"] = (cfg.get(m["key"]) or {}).get("starter_url")
            m["enabled"] = (cfg.get(m["key"]) or {}).get("enabled", True)
            scs.append(m)
        return {"onboarded": s.onboarded, "default_level": s.default_level,
                "levels": levels_meta(), "scenarios": scs}

    @app.post("/api/instructor/settings")
    def instructor_set_settings(payload: dict, x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        import dataclasses
        cur = _site()
        app.state.settings.set_instructor(dataclasses.replace(
            cur, onboarded=bool(payload.get("onboarded", True)),
            default_level=payload.get("default_level", cur.default_level or "senior")))
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


    # published for the modules registered after this one
    ctx._assignable = _assignable
    ctx._cohort_members = _cohort_members
    ctx._cohort_report = _cohort_report
    ctx._instr_ok = _instr_ok
    ctx._users_by_uid = _users_by_uid
    ctx.instructor_auth = instructor_auth
    ctx.instructor_cohort = instructor_cohort
    ctx.instructor_cohort_results = instructor_cohort_results
    ctx.instructor_cohort_results_csv = instructor_cohort_results_csv
    ctx.instructor_cohort_sessions = instructor_cohort_sessions
    ctx.instructor_cohorts = instructor_cohorts
    ctx.instructor_create_session = instructor_create_session
    ctx.instructor_get_settings = instructor_get_settings
    ctx.instructor_set_level = instructor_set_level
    ctx.instructor_set_scenario = instructor_set_scenario
    ctx.instructor_set_settings = instructor_set_settings
    ctx.instructor_set_starter_url = instructor_set_starter_url
