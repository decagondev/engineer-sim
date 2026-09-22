from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
import os
from sim.core.ports.identity import IdentityError, Principal
import re as _re


def register(app, ctx):
    """Routes and helpers for the admin area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    grader = ctx.grader
    auth = ctx.auth
    _actor = ctx._actor
    _audit_markdown = ctx._audit_markdown
    _build_record_for = ctx._build_record_for
    _cached = ctx._cached
    _calibrated = ctx._calibrated
    _enrich_sessions = ctx._enrich_sessions
    _grade_payload = ctx._grade_payload
    _login_url = ctx._login_url
    _merge_known_sessions = ctx._merge_known_sessions
    _overview_cache = ctx._overview_cache
    _parse_ts = ctx._parse_ts
    _scenario_config = ctx._scenario_config
    _session_stats = ctx._session_stats
    _site = ctx._site
    auth = ctx.auth
    b = ctx.b
    transcript = ctx.transcript

    @app.get("/api/admin/audit")
    def admin_audit(limit: int = 200, before: str = ""):
        store = app.state.audit
        if store is None:
            return {"entries": []}
        rows = store.list(limit=max(1, min(int(limit), 1000)), before=before)
        return {"entries": [e.as_dict() for e in rows]}

    # ---- archive: export, then cascade-delete, old finished sessions ----
    def _archive_candidates(older_than_days: int, states: list) -> list:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, int(older_than_days)))
        rows = _enrich_sessions(_merge_known_sessions(all_registered=True))
        out = []
        for s in rows:
            if states and s.get("state") not in states:
                continue
            last = _parse_ts(s.get("last_ts") or s.get("first_ts") or "")
            if last is None or last > cutoff:
                continue
            out.append(s)
        return out

    def _archive_one(s: dict) -> None:
        from datetime import datetime, timezone
        from sim.core.ports.archive import ArchiveRecord
        sid = s["session_id"]
        md = _audit_markdown(sid, regrade=False)
        app.state.archive.put(ArchiveRecord(
            session_id=sid, ts=datetime.now(timezone.utc).isoformat(),
            title=s.get("title") or "", scenario=s.get("scenario") or "",
            assignee=s.get("assignee") or "", state=s.get("state") or "",
            size=len(md.encode("utf-8")), markdown=md))
        _cascade_delete_session(sid)

    @app.post("/api/admin/sessions/archive")
    def admin_archive_sessions(request: Request, payload: dict):
        """Archive finished sessions older than N days: keep the markdown audit,
        delete everything else. dry_run reports what would go."""
        import threading
        if app.state.archive is None:
            return JSONResponse({"error": "archive store not configured"}, status_code=501)
        days = int((payload or {}).get("older_than_days", 30))
        states = list((payload or {}).get("states") or ["graded", "reviewed"])
        dry = bool((payload or {}).get("dry_run", True))
        job = getattr(app.state, "archive_job", None)
        if job and job.get("status") == "running":
            return JSONResponse({"error": "an archive job is already running"}, status_code=409)
        cands = _archive_candidates(days, states)
        preview = [{"session_id": s["session_id"], "title": s.get("title"), "assignee": s.get("assignee"),
                    "state": s.get("state"), "last_ts": s.get("last_ts")} for s in cands]
        request.state.audit = ("", f"{'previewed' if dry else 'started'} archive of {len(cands)} "
                                   f"session(s) older than {days} d in {','.join(states)}")
        if dry:
            return {"dry_run": True, "count": len(cands), "sessions": preview}
        job = {"status": "running", "total": len(cands), "done": 0, "failed": [], "started": ""}
        app.state.archive_job = job

        def run():
            for s in cands:
                try:
                    _archive_one(s)
                except Exception as e:
                    job["failed"].append({"session_id": s["session_id"], "error": str(e)[:200]})
                job["done"] += 1
            job["status"] = "done"
            _overview_cache.clear()
        threading.Thread(target=run, name="archive", daemon=True).start()
        return {"dry_run": False, "count": len(cands), "job": job}

    @app.get("/api/admin/sessions/archive")
    def admin_archive_status():
        return {"job": getattr(app.state, "archive_job", None)}

    @app.get("/api/admin/archives")
    def admin_archives():
        store = app.state.archive
        return {"archives": [a.meta() for a in store.list()] if store is not None else []}

    @app.get("/api/admin/archives/{sid}.md")
    def admin_archive_md(sid: str):
        from fastapi.responses import Response
        store = app.state.archive
        rec = store.get(sid) if store is not None else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return Response(content=rec.markdown, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{sid}-audit.md"'})

    def _cascade_delete_session(sid: str) -> None:
        auth = app.state.auth
        for store in (app.state.repo, manager.unlock, manager.mailstore,
                      manager.ticketstore, manager.submissions, app.state.settings,
                      getattr(manager, "grades", None), getattr(manager, "reviews", None)):
            if store is None:
                continue
            fn = getattr(store, "delete_for_session", None) or getattr(
                store, "delete_session_settings", None)
            if callable(fn):
                try:
                    fn(sid)
                except TypeError:
                    if hasattr(store, "delete_session_settings"):
                        store.delete_session_settings(sid)
        if manager.session_files is not None:
            try:
                manager.session_files.delete_session(sid)
            except Exception:
                pass
        env = b(sid).environment
        if env is not None:
            try:
                h = env.handle(sid)
                env.teardown(sid)
                if h is not None and app.state.workspace is not None:
                    app.state.workspace.forget(h.workdir, sid)
            except Exception:
                pass
        if auth.sessions:
            auth.sessions.delete(sid)

    def _cohorts():
        return getattr(manager, "cohorts", None)

    def _membership_map(store):
        by_uid = {}
        if store is None:
            return by_uid
        for c in store.list():
            for uid in store.members(c.id):
                by_uid.setdefault(uid, []).append(c.id)
        return by_uid

    def _user_payload(u, cohort_ids=None):
        return {"uid": u.uid, "email": u.email, "name": u.name or "",
                "role": u.role, "disabled": u.disabled,
                "created_at": u.created_at, "last_login": u.last_login,
                "has_groq_key": bool(getattr(u, "groq_key_enc", "")),
                "has_github_token": bool(getattr(u, "github_token_enc", "")),
                "has_gitlab_token": bool(getattr(u, "gitlab_token_enc", "")),
                "cohort_ids": list(cohort_ids or [])}

    def _sort_dicts(rows, sort: str, direction: str, allowed: dict):
        key = allowed.get(sort) or next(iter(allowed.values()))
        rev = (direction or "asc").lower() == "desc"
        def val(row):
            v = key(row)
            if isinstance(v, (int, float)):
                return v
            return str(v or "").lower()
        return sorted(rows, key=val, reverse=rev)

    def _create_directory_user(payload: dict):
        import secrets
        from datetime import datetime, timezone
        from sim.core.ports.identity import ROLES
        from sim.core.ports.users import UserRecord
        email = (payload or {}).get("email", "").strip()
        role = (payload or {}).get("role", "challenger")
        name = (payload or {}).get("name", "").strip()
        if not email or role not in ROLES:
            return None, JSONResponse({"error": "email and valid role required"},
                                      status_code=400)
        auth = app.state.auth
        uid = ""
        chosen = str((payload or {}).get("password") or "").strip()
        if chosen and len(chosen) < 6:
            return None, JSONResponse(
                {"error": "Password must be at least 6 characters."}, status_code=400)
        if auth.firebase is not None:
            password = chosen or secrets.token_urlsafe(16)
            send_reset = (payload or {}).get("send_reset")
            if send_reset is None:
                send_reset = not bool(chosen)
            try:
                uid = auth.firebase.create_email_user(email, password)
                if send_reset:
                    auth.firebase.send_password_reset(email, continue_url=_login_url())
            except IdentityError as e:
                return None, JSONResponse({"error": e.detail}, status_code=e.status)
        uid = uid or ("u-" + secrets.token_hex(8))
        rec = auth.users.upsert(UserRecord(
            uid=uid, email=email, role=role, name=name, disabled=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        return rec, None

    @app.get("/api/admin/users")
    def admin_list_users(sort: str = "name", direction: str = "asc"):
        users = app.state.auth.users
        if users is None:
            return {"users": []}
        by_uid = _membership_map(_cohorts())
        rows = []
        for u in users.list():
            rows.append(_user_payload(u, by_uid.get(u.uid, [])))
        rows = _sort_dicts(rows, sort, direction, {
            "name": lambda r: r["name"] or r["email"],
            "email": lambda r: r["email"],
            "role": lambda r: r["role"],
            "created_at": lambda r: r["created_at"],
        })
        return {"users": rows}

    @app.post("/api/admin/users")
    def admin_create_user(payload: dict):
        rec, err = _create_directory_user(payload or {})
        if err:
            return err
        cid = (payload or {}).get("cohort_id") or ""
        if cid and _cohorts() and _cohorts().get(cid):
            _cohorts().add_member(cid, rec.uid)
        return {"ok": True, "uid": rec.uid, "email": rec.email, "role": rec.role,
                "name": rec.name}

    _EMAIL_RE = _re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

    def _parse_people(text: str) -> tuple[list, list]:
        """Turn pasted text into [(name, email)], plus the lines with no email.

        Accepts one entry per line in any of: email · Name <email> ·
        "Name, email" · "email, Name" · spreadsheet rows with tabs. Several
        entries on one line separated by ; or , also work when they are bare
        emails. Duplicates (case-insensitive) collapse to the first mention."""
        people, bad, seen = [], [], set()
        for raw in (text or "").splitlines():
            line = raw.strip().strip(",;")
            if not line:
                continue
            emails = _EMAIL_RE.findall(line)
            if not emails:
                bad.append(line)
                continue
            if len(emails) > 1:
                # several bare emails on one line; no names to recover
                for em in emails:
                    if em.lower() not in seen:
                        seen.add(em.lower()); people.append(("", em))
                continue
            em = emails[0]
            name = line.replace(em, " ")
            for ch in "<>,;	\"'":
                name = name.replace(ch, " ")
            name = " ".join(name.split())
            if em.lower() in seen:
                continue
            seen.add(em.lower()); people.append((name, em))
        return people, bad

    @app.post("/api/admin/users/bulk")
    def admin_bulk_users(payload: dict):
        """Create many accounts from pasted text and optionally drop them all
        into a cohort. Existing accounts are not recreated but are still added
        to the cohort. Never aborts the batch on one bad row."""
        from sim.core.ports.identity import ROLES
        payload = payload or {}
        role = payload.get("role") or "challenger"
        if role not in ROLES:
            return JSONResponse({"error": "invalid role"}, status_code=400)
        people, invalid = _parse_people(str(payload.get("text") or ""))
        cid = str(payload.get("cohort_id") or "").strip()
        store = _cohorts()
        cohort = store.get(cid) if (cid and store) else None
        if cid and cohort is None:
            return JSONResponse({"error": "cohort not found"}, status_code=404)
        new_name = str(payload.get("cohort_name") or "").strip()
        if new_name and cohort is None:
            if store is None:
                return JSONResponse({"error": "cohorts unavailable"}, status_code=503)
            import secrets
            from datetime import datetime, timezone
            from sim.core.ports.cohorts import CohortRecord
            cohort = store.upsert(CohortRecord(
                id="co-" + secrets.token_hex(5), name=new_name,
                notes=str(payload.get("cohort_notes") or "").strip(),
                created_at=datetime.now(timezone.utc).isoformat()))
            cid = cohort.id
        send_reset = payload.get("send_reset", True)
        users = app.state.auth.users
        created, existing, failed = [], [], []
        for name, email in people:
            rec = users.get_by_email(email) if users else None
            if rec is not None:
                if cohort is not None:
                    store.add_member(cid, rec.uid)
                existing.append({"uid": rec.uid, "email": rec.email,
                                 "name": rec.name or "", "role": rec.role})
                continue
            rec, err = _create_directory_user({
                "email": email, "name": name, "role": role,
                "send_reset": bool(send_reset)})
            if err:
                try:
                    reason = (err.body or b"").decode("utf-8")
                    import json as _json
                    reason = _json.loads(reason).get("error") or reason
                except Exception:
                    reason = "could not create"
                failed.append({"email": email, "name": name, "reason": reason})
                continue
            if cohort is not None:
                store.add_member(cid, rec.uid)
            created.append({"uid": rec.uid, "email": rec.email,
                            "name": rec.name or "", "role": rec.role})
        return {"ok": True, "role": role,
                "cohort": ({"id": cohort.id, "name": cohort.name} if cohort else None),
                "created": created, "existing": existing, "failed": failed,
                "invalid": invalid}

    def _sync_user_cohorts(uid: str, cohort_ids):
        store = _cohorts()
        if store is None:
            return []
        wanted = []
        for raw in list(cohort_ids or []):
            cid = str(raw or "").strip()
            if cid and store.get(cid) and cid not in wanted:
                wanted.append(cid)
        current = list(store.cohorts_for(uid))
        for cid in wanted:
            if cid not in current:
                store.add_member(cid, uid)
        for cid in current:
            if cid not in wanted:
                store.remove_member(cid, uid)
        return wanted

    @app.patch("/api/admin/users/{uid}")
    def admin_patch_user(uid: str, payload: dict):
        from sim.core.ports.identity import ROLES
        from sim.core.ports.users import UserRecord
        auth = app.state.auth
        rec = auth.users.get(uid) if auth.users else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = payload or {}
        role = body.get("role", rec.role)
        disabled = rec.disabled
        if "disabled" in body:
            disabled = bool(body["disabled"])
        name = rec.name
        if "name" in body:
            name = str(body.get("name") or "").strip()
        email = rec.email
        if "email" in body:
            email = str(body.get("email") or "").strip()
            if not email:
                return JSONResponse({"error": "email required"}, status_code=400)
            other = auth.users.get_by_email(email)
            if other and other.uid != rec.uid:
                return JSONResponse({"error": "email already in use"}, status_code=400)
        if role not in ROLES:
            return JSONResponse({"error": "bad role"}, status_code=400)
        if rec.role == "admin" and (role != "admin" or disabled) and auth.users.count_role("admin") <= 1:
            return JSONResponse({"error": "cannot remove the last admin"}, status_code=400)
        fb = auth.firebase
        try:
            if fb is not None and email != rec.email:
                fb.update_email(rec.uid, email)
            if fb is not None and disabled != rec.disabled:
                fb.set_disabled(rec.uid, disabled)
            if body.get("password"):
                if fb is None:
                    pass
                else:
                    fb.set_password(rec.uid, str(body.get("password") or ""))
            if body.get("send_reset"):
                if fb is None:
                    pass
                else:
                    fb.send_password_reset(email, continue_url=_login_url())
        except IdentityError as e:
            return JSONResponse({"error": e.detail}, status_code=e.status)
        rec = auth.users.upsert(UserRecord(
            uid=rec.uid, email=email, role=role, disabled=disabled,
            created_at=rec.created_at, last_login=rec.last_login, name=name,
            groq_key_enc=rec.groq_key_enc, github_token_enc=rec.github_token_enc,
            github_scope=rec.github_scope, gitlab_token_enc=rec.gitlab_token_enc,
            gitlab_scope=rec.gitlab_scope))
        if "cohort_ids" in body:
            cids = _sync_user_cohorts(rec.uid, body.get("cohort_ids"))
        else:
            store = _cohorts()
            cids = list(store.cohorts_for(rec.uid)) if store else []
        return {"ok": True, "uid": rec.uid, "role": rec.role,
                "disabled": rec.disabled, "name": rec.name,
                "email": rec.email, "cohort_ids": cids,
                "password_set": bool(body.get("password")),
                "reset_sent": bool(body.get("send_reset"))}

    @app.delete("/api/admin/users/{uid}")
    def admin_delete_user(uid: str):
        auth = app.state.auth
        rec = auth.users.get(uid) if auth.users else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if rec.role == "admin" and auth.users.count_role("admin") <= 1:
            return JSONResponse({"error": "cannot delete the last admin"}, status_code=400)
        if auth.firebase is not None:
            try:
                auth.firebase.delete_account(uid)
            except IdentityError as e:
                return JSONResponse({"error": e.detail}, status_code=e.status)
        if _cohorts():
            _cohorts().remove_user(uid)
        auth.users.delete(uid)
        return {"ok": True}

    @app.get("/api/admin/cohorts")
    def admin_list_cohorts(sort: str = "name", direction: str = "asc"):
        store = _cohorts()
        if store is None:
            return {"cohorts": []}
        rows = []
        for c in store.list():
            members = list(store.members(c.id))
            rows.append({"id": c.id, "name": c.name, "notes": c.notes,
                         "created_at": c.created_at, "member_count": len(members)})
        rows = _sort_dicts(rows, sort, direction, {
            "name": lambda r: r["name"],
            "created_at": lambda r: r["created_at"],
            "members": lambda r: r["member_count"],
        })
        return {"cohorts": rows}

    @app.post("/api/admin/cohorts")
    def admin_create_cohort(payload: dict):
        import secrets
        from datetime import datetime, timezone
        from sim.core.ports.cohorts import CohortRecord
        store = _cohorts()
        if store is None:
            return JSONResponse({"error": "cohorts unavailable"}, status_code=503)
        name = (payload or {}).get("name", "").strip()
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        rec = store.upsert(CohortRecord(
            id="co-" + secrets.token_hex(5),
            name=name,
            notes=(payload or {}).get("notes", "").strip(),
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        return {"ok": True, "id": rec.id, "name": rec.name, "notes": rec.notes}

    @app.get("/api/admin/cohorts/{cid}")
    def admin_get_cohort(cid: str):
        store = _cohorts()
        rec = store.get(cid) if store else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        users = app.state.auth.users
        members = []
        for uid in store.members(cid):
            u = users.get(uid) if users else None
            if u:
                members.append(_user_payload(u, [cid]))
            else:
                members.append({"uid": uid, "email": "", "name": "", "role": "",
                                "disabled": False, "created_at": "",
                                "last_login": "", "cohort_ids": [cid]})
        members.sort(key=lambda m: (m.get("name") or m.get("email") or "").lower())
        return {"id": rec.id, "name": rec.name, "notes": rec.notes,
                "created_at": rec.created_at, "members": members}

    @app.patch("/api/admin/cohorts/{cid}")
    def admin_patch_cohort(cid: str, payload: dict):
        from sim.core.ports.cohorts import CohortRecord
        store = _cohorts()
        rec = store.get(cid) if store else None
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        name = (payload or {}).get("name", rec.name).strip()
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        notes = rec.notes
        if "notes" in (payload or {}):
            notes = str(payload.get("notes") or "").strip()
        rec = store.upsert(CohortRecord(
            id=rec.id, name=name, notes=notes, created_at=rec.created_at))
        return {"ok": True, "id": rec.id, "name": rec.name, "notes": rec.notes}

    @app.delete("/api/admin/cohorts/{cid}")
    def admin_delete_cohort(cid: str):
        store = _cohorts()
        if store is None or not store.delete(cid):
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"ok": True}

    @app.post("/api/admin/cohorts/{cid}/members")
    def admin_add_cohort_member(cid: str, payload: dict):
        store = _cohorts()
        if store is None or store.get(cid) is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        uid = (payload or {}).get("uid") or ""
        email = (payload or {}).get("email") or ""
        users = app.state.auth.users
        rec = users.get(uid) if uid and users else None
        if rec is None and email and users:
            rec = users.get_by_email(email)
        if rec is None:
            return JSONResponse({"error": "user not found"}, status_code=404)
        store.add_member(cid, rec.uid)
        return {"ok": True, "uid": rec.uid}

    @app.delete("/api/admin/cohorts/{cid}/members/{uid}")
    def admin_remove_cohort_member(cid: str, uid: str):
        store = _cohorts()
        if store is None or store.get(cid) is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        store.remove_member(cid, uid)
        return {"ok": True}

    @app.post("/api/admin/cohorts/{cid}/onboard")
    def admin_onboard_cohort_member(cid: str, payload: dict):
        store = _cohorts()
        if store is None or store.get(cid) is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        rec, err = _create_directory_user(payload or {})
        if err:
            return err
        store.add_member(cid, rec.uid)
        return {"ok": True, "uid": rec.uid, "email": rec.email, "name": rec.name,
                "role": rec.role, "cohort_id": cid}

    def _uid_label(uid: str) -> str:
        if not uid:
            return ""
        users = app.state.auth.users
        rec = users.get(uid) if users else None
        return rec.email if rec else uid

    @app.get("/api/admin/overview")
    def admin_overview(fresh: bool = False):
        """Deployment-wide numbers: people, keys, cohorts, scenarios, sessions."""
        return _cached("admin", _admin_overview, fresh)

    def _admin_overview():
        auth = app.state.auth
        users = list(auth.users.list()) if auth.users else []
        by_role = {"admin": 0, "instructor": 0, "challenger": 0}
        disabled = 0
        chall = [u for u in users if u.role == "challenger"]
        for u in users:
            by_role[u.role] = by_role.get(u.role, 0) + 1
            if u.disabled:
                disabled += 1
        groq = sum(1 for u in chall if getattr(u, "groq_key_enc", ""))
        gh = sum(1 for u in chall if getattr(u, "github_token_enc", ""))
        both = sum(1 for u in chall if getattr(u, "groq_key_enc", "") and getattr(u, "github_token_enc", ""))
        store = _cohorts()
        cohorts = list(store.list()) if store else []
        members = sum(len(list(store.members(c.id))) for c in cohorts) if store else 0
        reg = manager.registry
        cfg = _scenario_config()
        enabled = sum(1 for k in reg if (cfg.get(k) or {}).get("enabled", True))
        tracks = {"interview": 0, "systems": 0, "product": 0}
        for sc in reg.values():
            tracks[sc.track] = tracks.get(sc.track, 0) + 1
        rows = _enrich_sessions(_merge_known_sessions(all_registered=True))
        status = {"auth_mode": auth.mode, "firebase_project_id": auth.firebase_project_id,
                  "users_count": len(users),
                  "bootstrap_configured": bool(auth.bootstrap_admin_email),
                  "persistence": getattr(manager._config, "persistence", "sqlite")}
        return {
            "users": {"total": len(users), "by_role": by_role, "disabled": disabled,
                      "challengers": len(chall), "with_groq": groq, "with_github": gh,
                      "with_both": both},
            "cohorts": {"count": len(cohorts), "members": members,
                        "list": [{"id": c.id, "name": c.name,
                                  "members": len(list(store.members(c.id)))}
                                 for c in cohorts]},
            "scenarios": {"total": len(reg), "enabled": enabled, "by_track": tracks},
            "sessions": _session_stats(rows),
            "recent": rows[:8],
            "auth": status,
        }

    def _admin_sessions_payload() -> dict:
        # one listing + one users listing; labels and states come from the
        # session index, never a read per row
        rows = _enrich_sessions(_merge_known_sessions(all_registered=True))
        return {"sessions": _session_rows(rows)}

    @app.get("/api/admin/sessions")
    def admin_list_sessions(fresh: bool = False):
        return _cached("admin:sessions", _admin_sessions_payload, fresh)

    def _session_rows(rows: list) -> list:
        return [
            {"session_id": s["session_id"],
             "owner_uid": s.get("owner_uid") or "",
             "assignee_uid": s.get("assignee_uid") or "",
             "owner": s.get("owner") or "",
             "assignee": s.get("assignee") or "",
             "scenario": s.get("scenario") or "",
             "title": s.get("title") or "",
             "level": s.get("level") or "",
             "status": s.get("status") or "",
             "state": s.get("state") or "not_started",
             "grade_total": s.get("grade_total"),
             "created_at": s.get("first_ts") or "",
             "count": s.get("count") or 0,
             "last_ts": s.get("last_ts") or ""}
            for s in rows
        ]

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
    def admin_delete_session(sid: str, request: Request):
        request.state.audit = (sid, f"deleted session {sid} and everything attached to it")
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

    def _settings_payload() -> dict:
        s = _site()
        cfg = manager._config
        return {
            "onboarded": s.onboarded, "default_level": s.default_level,
            "allow_signup": s.allow_signup,
            "grader_calibrated": s.grader_calibrated,
            "grader_calibrated_env": bool(app.state.grader_calibrated),
            "grader_calibrated_effective": _calibrated(),
            "announcement": s.announcement,
            "levels": [{"key": k, "label": v} for k, v in
                       ((l["key"], l["label"]) for l in __import__("sim.core.levels", fromlist=["levels_meta"]).levels_meta())],
            "deployment": {
                "llm_provider": cfg.llm_provider,
                "model": {"groq": cfg.groq_model, "anthropic": cfg.anthropic_model,
                          "ollama": cfg.ollama_model}.get(cfg.llm_provider, ""),
                "model_from_env": bool(os.environ.get({"groq": "GROQ_MODEL", "anthropic": "ANTHROPIC_MODEL",
                                                       "ollama": "OLLAMA_MODEL"}.get(cfg.llm_provider, ""))),
                "commit": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("GIT_COMMIT") or "")[:12],
                "hosted": app.state.hosted, "work_mode": cfg.work_mode,
                "env_provider": cfg.env_provider,
                "persistence": cfg.persistence, "auth_mode": cfg.auth_mode,
                "firebase_project_id": cfg.firebase_project_id,
                "public_base_url": app.state.public_base_url,
                "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
                "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "github_token_set": bool(cfg.github_token),
                "byok_secret_set": bool(cfg.byok_secret),
                "bootstrap_admin_email": cfg.bootstrap_admin_email,
                "github_oauth_set": bool(cfg.github_oauth_client_id),
                "gitlab_url": cfg.gitlab_url,
                "gitlab_token_set": bool(cfg.gitlab_token),
                "gitlab_oauth_set": bool(cfg.gitlab_url and cfg.gitlab_oauth_client_id),
                "llm_fallback_providers": cfg.llm_fallback_providers,
                "llm_failover": _failover_status(),
            },
        }

    def _failover_status():
        chain = getattr(manager, "llm", None)
        inner = getattr(chain, "_fallback", chain)          # ScopedLLMClient wraps the chain
        fn = getattr(inner, "status", None)
        try:
            return fn() if fn else None
        except Exception:
            return None

    @app.get("/api/admin/settings")
    def admin_get_settings():
        return _settings_payload()

    @app.put("/api/admin/settings")
    def admin_put_settings(payload: dict):
        import dataclasses
        from sim.core.levels import LEVEL_ORDER
        cur = _site()
        changes = {}
        if "default_level" in payload:
            lvl = str(payload.get("default_level") or "")
            if lvl not in LEVEL_ORDER:
                return JSONResponse({"error": "unknown level"}, status_code=400)
            changes["default_level"] = lvl
        if "onboarded" in payload:
            changes["onboarded"] = bool(payload.get("onboarded"))
        if "allow_signup" in payload:
            changes["allow_signup"] = bool(payload.get("allow_signup"))
        if "grader_calibrated" in payload:
            v = payload.get("grader_calibrated")
            changes["grader_calibrated"] = None if v is None or v == "" else bool(v)
        if "announcement" in payload:
            changes["announcement"] = str(payload.get("announcement") or "").strip()[:280]
        app.state.settings.set_instructor(dataclasses.replace(cur, **changes))
        return {"ok": True, **_settings_payload()}

    # ---- calibration from reviewed sessions -----------------------------
    def _rubric_for(scenario_key: str):
        sc = manager.registry.get(scenario_key or "")
        return sc.rubric if sc else None

    def _reviewed_fixtures() -> list:
        """Every session that has both a stored grade and an instructor review
        becomes a calibration fixture; the human scores are the merged verdict."""
        from sim.core.grading.fixtures import fixture_from_review
        out = []
        rows = _enrich_sessions(_merge_known_sessions(all_registered=True))
        for s in rows:
            if not (s.get("reviewed") and s.get("graded")):
                continue
            sid = s["session_id"]
            g = app.state.grades.get(sid) if app.state.grades is not None else None
            if g is None:
                continue
            merged = _grade_payload(g)
            rubric = _rubric_for(s.get("scenario") or "")
            if rubric is None:
                continue
            body = g.body or {}
            fx = fixture_from_review(
                sid, app.state.repo.list_for_session(sid), merged, rubric,
                scenario_key=s.get("scenario") or "", level=g.level,
                build_record=body.get("build_record") or _build_record_for(sid),
                expectation=body.get("expectation") or "")
            if fx:
                out.append(fx)
        return out

    def _calibration_runner():
        from sim.app.calibration_runner import CalibrationRunner
        from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
        from sim.core.ports.repository import StoredMessage
        runner = getattr(app.state, "calibration_runner", None)
        if runner is not None:
            return runner
        store = getattr(manager, "calibration_runs", None)
        if store is None:
            return None

        def reader_from(transcript):
            repo = InMemoryMessageRepository()
            for i, m in enumerate(transcript):
                repo.append(StoredMessage(session_id="fx", sender=m["sender"],
                                          channel=m.get("channel", "general"),
                                          content=m["content"], ts=f"t{i:03d}",
                                          kind=m.get("kind", "message")))
            return repo

        def grader():
            override = getattr(app.state, "calibration_grader", None)
            if override is not None:
                return override
            if manager._config.llm_provider == "fake":
                raise ValueError("calibration needs a real model provider (LLM_PROVIDER is fake)")
            return app.state.grader

        cfg = manager._config
        model = {"groq": cfg.groq_model, "anthropic": cfg.anthropic_model,
                 "ollama": cfg.ollama_model}.get(cfg.llm_provider, "")
        runner = CalibrationRunner(store, fixtures=_reviewed_fixtures, grader=grader,
                                   rubric_for=_rubric_for, reader_from=reader_from,
                                   provider=cfg.llm_provider, model=model)
        app.state.calibration_runner = runner
        return runner

    def _calibration_payload() -> dict:
        runner = _calibration_runner()
        latest = runner.latest() if runner else None
        cfg = manager._config
        return {
            "latest": latest.as_dict() if latest else None,
            "running": bool(runner and runner.running()),
            "fixtures_available": sum(1 for s in _enrich_sessions(_merge_known_sessions(all_registered=True))
                                      if s.get("reviewed") and s.get("graded")),
            "provider": cfg.llm_provider,
            "can_run": cfg.llm_provider != "fake" or getattr(app.state, "calibration_grader", None) is not None,
            "calibrated": _calibrated(),
            "thresholds": {"max_total_mae": 0.15, "min_within_tolerance": 0.8,
                           "min_rank_correlation": 0.7, "tolerance": 0.15},
        }

    @app.get("/api/admin/calibration")
    def admin_calibration():
        return _calibration_payload()

    @app.get("/api/admin/calibration/fixtures.json")
    def admin_calibration_fixtures():
        """The reviewed sessions as fixtures, for the CLI harness or safekeeping."""
        return {"fixtures": _reviewed_fixtures()}

    @app.post("/api/admin/calibration/run")
    def admin_calibration_run(request: Request, sync: bool = False):
        from sim.app.calibration_runner import CalibrationBusy
        runner = _calibration_runner()
        if runner is None:
            return JSONResponse({"error": "calibration store not configured"}, status_code=501)
        payload = _calibration_payload()
        if not payload["can_run"]:
            return JSONResponse({"error": "calibration needs a real model provider; this server "
                                          "runs LLM_PROVIDER=fake"}, status_code=400)
        if payload["fixtures_available"] == 0:
            return JSONResponse({"error": "no reviewed sessions yet: review at least one graded "
                                          "session in the instructor replay first"}, status_code=400)
        try:
            run = runner.start(started_by=_actor(request).email or _actor(request).uid, sync=sync)
        except CalibrationBusy as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        return {"ok": True, "run": run.as_dict()}

    @app.post("/api/admin/calibration/apply")
    def admin_calibration_apply():
        """Flip grader_calibrated only on the strength of a passing run."""
        import dataclasses
        runner = _calibration_runner()
        latest = runner.latest() if runner else None
        if latest is None or latest.status != "done" or not latest.passed:
            return JSONResponse({"error": "the latest calibration run did not pass"}, status_code=409)
        app.state.settings.set_instructor(dataclasses.replace(_site(), grader_calibrated=True))
        return {"ok": True, "calibrated": _calibrated(), "run": latest.id}

    @app.post("/api/admin/cache/clear")
    def admin_clear_cache():
        """Recount the overviews and session list on their next read."""
        _overview_cache.clear()
        return {"ok": True}

    @app.get("/api/admin/scenarios")
    def admin_scenarios():
        out = []
        cfg = _scenario_config()
        overrides = manager.override_meta()
        for m in manager.scenarios_meta():
            m = dict(m)
            m["starter_url"] = (cfg.get(m["key"]) or {}).get("starter_url")
            m["enabled"] = (cfg.get(m["key"]) or {}).get("enabled", True)
            o = overrides.get(m["key"])
            m["customised"] = o is not None
            m["store_only"] = bool(o) and not o.get("on_disk", True)
            m["based_on"] = (o or {}).get("based_on", "")
            out.append(m)
        return {"scenarios": out}

    def _scenario_yaml_text(key: str) -> tuple[str, str]:
        """(yaml text, source) where source is 'override' or 'disk'."""
        store = getattr(manager, "scenarios_store", None)
        o = store.get(key) if store is not None else None
        if o is not None:
            return o.yaml_text, "override"
        from sim.adapters.persistence.scenario_files import SCENARIOS_DIR
        p = SCENARIOS_DIR / key / "scenario.yaml"
        if p.is_file():
            return p.read_text(encoding="utf-8"), "disk"
        return "", ""

    def _validate_scenario_yaml(key: str, text: str, based_on: str = ""):
        """Parse and check the YAML; returns (scenario, error message)."""
        import yaml as _yaml
        from sim.adapters.persistence.scenario_files import load_scenario_text, starter_dir_for
        from sim.core.scenario.scenario import ScenarioError
        try:
            data = _yaml.safe_load(text or "")
        except _yaml.YAMLError as e:
            return None, f"YAML error: {str(e).splitlines()[0]}"
        if not isinstance(data, dict):
            return None, "the document must be a mapping with key, title, personas, rubric"
        if data.get("key") != key:
            return None, f"the YAML 'key' must be {key!r}"
        base = starter_dir_for(based_on or key) or starter_dir_for(key)
        try:
            sc = load_scenario_text(text, base.parent if base else None)
        except (ScenarioError, ValueError, KeyError, TypeError) as e:
            return None, f"invalid scenario: {e}"
        if not sc.rubric.criteria:
            return None, "a scenario needs at least one rubric criterion"
        return sc, ""

    @app.get("/api/admin/scenarios/{key}/yaml")
    def admin_scenario_yaml(key: str):
        text, source = _scenario_yaml_text(key)
        if not source:
            return JSONResponse({"error": "no such scenario"}, status_code=404)
        meta = manager.override_meta().get(key) or {}
        from sim.adapters.persistence.scenario_files import SCENARIOS_DIR
        return {"key": key, "yaml": text, "source": source,
                "on_disk": (SCENARIOS_DIR / key / "scenario.yaml").is_file(),
                "based_on": meta.get("based_on", ""), "ts": meta.get("ts", ""), "author": meta.get("author", "")}

    @app.put("/api/admin/scenarios/{key}/yaml")
    def admin_put_scenario_yaml(key: str, payload: dict, request: Request, validate: bool = False):
        """Save (or just validate) a scenario's YAML as an override; the registry
        reloads and the next session uses it."""
        from datetime import datetime, timezone
        from sim.core.ports.scenarios import ScenarioOverride
        store = getattr(manager, "scenarios_store", None)
        if store is None:
            return JSONResponse({"error": "scenario store not configured"}, status_code=501)
        text = str((payload or {}).get("yaml") or "")
        existing = store.get(key)
        based_on = (payload or {}).get("based_on") or (existing.based_on if existing else "")
        sc, err = _validate_scenario_yaml(key, text, based_on)
        if err:
            return JSONResponse({"error": err}, status_code=400)
        if validate:
            return {"ok": True, "valid": True, "title": sc.title, "track": sc.track,
                    "personas": [p.name for p in sc.personas], "criteria": [c.key for c in sc.rubric.criteria]}
        actor = _actor(request)
        store.put(ScenarioOverride(key=key, yaml_text=text, ts=datetime.now(timezone.utc).isoformat(),
                                   author=actor.email or actor.uid, based_on=based_on))
        manager.reload_registry()
        request.state.audit = (key, f"saved scenario {key} ({sc.title})")
        return {"ok": True, "key": key, "title": sc.title, "track": sc.track, "source": "override"}

    @app.delete("/api/admin/scenarios/{key}/yaml")
    def admin_delete_scenario_override(key: str, request: Request):
        """Drop the override: a file-backed scenario reverts to disk, a
        dashboard-only one disappears."""
        store = getattr(manager, "scenarios_store", None)
        if store is None or not store.delete(key):
            return JSONResponse({"error": "no override for that scenario"}, status_code=404)
        manager.reload_registry()
        on_disk = key in manager.registry
        request.state.audit = (key, f"{'reverted' if on_disk else 'deleted'} scenario {key}")
        return {"ok": True, "reverted_to_disk": on_disk, "removed": not on_disk}

    @app.post("/api/admin/scenarios")
    def admin_new_scenario(payload: dict, request: Request):
        """A new scenario from a template: copy its YAML with a new key and title;
        the starter folder is borrowed from the template."""
        import re as _re
        import yaml as _yaml
        from datetime import datetime, timezone
        from sim.core.ports.scenarios import ScenarioOverride
        store = getattr(manager, "scenarios_store", None)
        if store is None:
            return JSONResponse({"error": "scenario store not configured"}, status_code=501)
        key = str((payload or {}).get("key") or "").strip().lower()
        title = str((payload or {}).get("title") or "").strip()
        based_on = str((payload or {}).get("based_on") or "").strip()
        if not _re.fullmatch(r"[a-z][a-z0-9_]{2,40}", key):
            return JSONResponse({"error": "key must be 3-40 chars: lowercase letters, digits, underscores"},
                                status_code=400)
        if key in manager.registry:
            return JSONResponse({"error": "that key already exists"}, status_code=409)
        if not title:
            return JSONResponse({"error": "a title is required"}, status_code=400)
        text, source = _scenario_yaml_text(based_on)
        if not source:
            return JSONResponse({"error": "no such template scenario"}, status_code=400)
        data = _yaml.safe_load(text) or {}
        data["key"], data["title"] = key, title
        new_text = _yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
        root_base = (store.get(based_on).based_on if store.get(based_on) else "") or based_on
        sc, err = _validate_scenario_yaml(key, new_text, root_base)
        if err:
            return JSONResponse({"error": err}, status_code=400)
        actor = _actor(request)
        store.put(ScenarioOverride(key=key, yaml_text=new_text, ts=datetime.now(timezone.utc).isoformat(),
                                   author=actor.email or actor.uid, based_on=root_base))
        manager.reload_registry()
        request.state.audit = (key, f"created scenario {key} from {based_on}")
        return {"ok": True, "key": key, "title": sc.title, "based_on": root_base}

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
                "bootstrap_configured": bool(auth.bootstrap_admin_email),
                "persistence": getattr(manager._config, "persistence", "sqlite")}


    # published for the modules registered after this one
    ctx._EMAIL_RE = _EMAIL_RE
    ctx._admin_overview = _admin_overview
    ctx._admin_sessions_payload = _admin_sessions_payload
    ctx._archive_candidates = _archive_candidates
    ctx._archive_one = _archive_one
    ctx._calibration_payload = _calibration_payload
    ctx._calibration_runner = _calibration_runner
    ctx._cascade_delete_session = _cascade_delete_session
    ctx._cohorts = _cohorts
    ctx._create_directory_user = _create_directory_user
    ctx._failover_status = _failover_status
    ctx._membership_map = _membership_map
    ctx._parse_people = _parse_people
    ctx._reviewed_fixtures = _reviewed_fixtures
    ctx._rubric_for = _rubric_for
    ctx._scenario_yaml_text = _scenario_yaml_text
    ctx._session_rows = _session_rows
    ctx._settings_payload = _settings_payload
    ctx._sort_dicts = _sort_dicts
    ctx._sync_user_cohorts = _sync_user_cohorts
    ctx._uid_label = _uid_label
    ctx._user_payload = _user_payload
    ctx._validate_scenario_yaml = _validate_scenario_yaml
    ctx.admin_add_cohort_member = admin_add_cohort_member
    ctx.admin_archive_md = admin_archive_md
    ctx.admin_archive_sessions = admin_archive_sessions
    ctx.admin_archive_status = admin_archive_status
    ctx.admin_archives = admin_archives
    ctx.admin_audit = admin_audit
    ctx.admin_auth_status = admin_auth_status
    ctx.admin_bulk_users = admin_bulk_users
    ctx.admin_calibration = admin_calibration
    ctx.admin_calibration_apply = admin_calibration_apply
    ctx.admin_calibration_fixtures = admin_calibration_fixtures
    ctx.admin_calibration_run = admin_calibration_run
    ctx.admin_clear_cache = admin_clear_cache
    ctx.admin_create_cohort = admin_create_cohort
    ctx.admin_create_user = admin_create_user
    ctx.admin_delete_cohort = admin_delete_cohort
    ctx.admin_delete_messages = admin_delete_messages
    ctx.admin_delete_scenario_override = admin_delete_scenario_override
    ctx.admin_delete_session = admin_delete_session
    ctx.admin_delete_submissions = admin_delete_submissions
    ctx.admin_delete_ticket = admin_delete_ticket
    ctx.admin_delete_user = admin_delete_user
    ctx.admin_get_cohort = admin_get_cohort
    ctx.admin_get_settings = admin_get_settings
    ctx.admin_list_cohorts = admin_list_cohorts
    ctx.admin_list_sessions = admin_list_sessions
    ctx.admin_list_users = admin_list_users
    ctx.admin_messages = admin_messages
    ctx.admin_new_scenario = admin_new_scenario
    ctx.admin_onboard_cohort_member = admin_onboard_cohort_member
    ctx.admin_overview = admin_overview
    ctx.admin_patch_cohort = admin_patch_cohort
    ctx.admin_patch_session = admin_patch_session
    ctx.admin_patch_user = admin_patch_user
    ctx.admin_put_scenario = admin_put_scenario
    ctx.admin_put_scenario_yaml = admin_put_scenario_yaml
    ctx.admin_put_settings = admin_put_settings
    ctx.admin_remove_cohort_member = admin_remove_cohort_member
    ctx.admin_scenario_yaml = admin_scenario_yaml
    ctx.admin_scenarios = admin_scenarios
    ctx.admin_submissions = admin_submissions
    ctx.admin_tickets = admin_tickets
    ctx.admin_unlock_reset = admin_unlock_reset
