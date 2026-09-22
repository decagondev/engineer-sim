from __future__ import annotations

from fastapi import Header
from fastapi import Request
from fastapi.responses import JSONResponse
from sim.adapters.web.app_base import log


def register(app, ctx):
    """Routes and helpers for the dashboards area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    auth = ctx.auth
    _actor = ctx._actor
    _build_record_for = ctx._build_record_for
    _flatten_tickets = ctx._flatten_tickets
    _grade_body = ctx._grade_body
    _grade_payload = ctx._grade_payload
    _instr_ok = ctx._instr_ok
    _review_for = ctx._review_for
    _session_level = ctx._session_level
    auth = ctx.auth
    b = ctx.b
    grade = ctx.grade

    def _merge_known_sessions(*, all_registered: bool, owner_uid: str = "",
                              assignee_uid: str = ""):
        """Message-store runs (legacy classroom) plus assignment-registry rows.
        On Firestore an owner/assignee scope is pushed into the query so an
        instructor never streams the whole server."""
        by_id = {}
        repo = app.state.repo
        msg_sessions = []
        if hasattr(repo, "list_sessions"):
            try:
                # Firestore: every session doc (index fields included) in one stream
                if all_registered:
                    msg_sessions = repo.list_sessions(include_empty=True)
                else:
                    msg_sessions = repo.list_sessions(include_empty=True, owner_uid=owner_uid,
                                                      assignee_uid=assignee_uid)
            except TypeError:
                msg_sessions = repo.list_sessions()
        complete = bool(msg_sessions) and all(s.get("complete") for s in msg_sessions)
        for s in msg_sessions:
            row = dict(s)
            row.pop("complete", None)
            row.setdefault("owner_uid", "")
            row.setdefault("assignee_uid", "")
            row.setdefault("status", "")
            if not row.get("first_ts"):
                row["first_ts"] = row.get("created_at") or ""
            if not row.get("last_ts"):
                row["last_ts"] = row.get("first_ts") or ""
            by_id[s["session_id"]] = row
        auth = app.state.auth
        if auth.sessions is not None and not complete:
            recs = (list(auth.sessions.list_all()) if all_registered
                    else list(auth.sessions.list_by_assignee(assignee_uid)) if assignee_uid
                    else list(auth.sessions.list_by_owner(owner_uid)))
            for rec in recs:
                row = by_id.get(rec.id, {"session_id": rec.id, "count": 0,
                                         "first_ts": rec.created_at, "last_ts": rec.created_at})
                if not row.get("first_ts"):
                    row["first_ts"] = rec.created_at
                if not row.get("last_ts"):
                    row["last_ts"] = rec.created_at
                row["assignee_uid"] = rec.assignee_uid
                row["owner_uid"] = rec.owner_uid
                row["status"] = rec.status
                if rec.scenario_key and not row.get("scenario_key"):
                    row["scenario_key"] = rec.scenario_key
                if rec.level and not row.get("level"):
                    row["level"] = rec.level
                by_id[rec.id] = row
        sessions = list(by_id.values())
        sessions.sort(key=lambda s: s.get("last_ts") or s.get("first_ts") or "", reverse=True)
        from sim.core.levels import LEVEL_ORDER
        default_level = None

        def fill(s):
            nonlocal default_level
            sid = s["session_id"]
            key = s.get("scenario_key") or ""
            s["scenario"] = key if key in manager.registry else manager.resolve_scenario_key(sid)
            lvl = s.get("level") or ""
            if lvl not in LEVEL_ORDER:
                lvl = _session_level(sid)
            s["level"] = lvl
        _parallel(fill, sessions)
        return sessions

    def _parallel(fn, items, workers: int = 8) -> None:
        """Run fn over items concurrently (Firestore reads are network-bound)."""
        items = list(items)
        if len(items) < 2:
            for it in items:
                fn(it)
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
            list(ex.map(fn, items))

    def _parse_ts(ts: str):
        from datetime import datetime, timezone
        if not ts:
            return None
        try:
            d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    def _user_labels() -> dict:
        """uid -> email, from one listing instead of a read per row."""
        users = app.state.auth.users
        if users is None:
            return {}
        try:
            return {u.uid: u.email for u in users.list()}
        except Exception:
            return {}

    def _enrich_sessions(rows: list) -> list:
        """Add what a dashboard row needs: scenario title/track, assignee label,
        whether anything was submitted, the stored grade, and a one-word state.
        Rows that already carry the index fields (Firestore session docs) need
        no further reads; the rest are looked up in parallel and, where the
        store supports it, written back so the next listing is one stream."""
        subs = app.state.submissions
        grades = app.state.grades
        labels = _user_labels() if rows else {}
        indexer = getattr(app.state.repo, "index_session", None)

        def fill(s):
            sid = s["session_id"]
            sc = manager.registry.get(s.get("scenario") or "")
            s["title"] = sc.title if sc else (s.get("scenario") or "")
            s["track"] = sc.track if sc else "product"
            s["assignee"] = labels.get(s.get("assignee_uid") or "", s.get("assignee_uid") or "")
            s["owner"] = labels.get(s.get("owner_uid") or "", s.get("owner_uid") or "")
            patch = {}
            if "submitted_ts" not in s:
                sub = None
                try:
                    sub = subs.latest(sid) if subs is not None else None
                except Exception:
                    sub = None
                s["submitted_ts"] = sub.ts if sub else ""
                patch["submitted_ts"] = s["submitted_ts"]
            if "graded_ts" not in s:
                g = None
                try:
                    g = grades.get(sid) if grades is not None else None
                except Exception:
                    g = None
                s["graded_ts"] = g.ts if g else ""
                s["grade_total"] = g.total if g else None
                s["graded_by"] = g.graded_by if g else ""
                patch.update({"graded_ts": s["graded_ts"], "grade_total": s["grade_total"],
                              "graded_by": s["graded_by"]})
            if "reviewed_ts" not in s:
                r = _review_for(sid)
                s["reviewed_ts"] = r.ts if r else ""
                patch["reviewed_ts"] = s["reviewed_ts"]
                if r and "review_total" not in s:
                    s["review_total"] = None
            if patch and indexer is not None:
                try:
                    indexer(sid, **patch)
                except Exception:
                    pass
            _apply_state(s)
        _parallel(fill, rows)
        return rows

    def _apply_state(s: dict) -> dict:
        """The one place a session's state is decided from its index fields."""
        s["submitted"] = bool(s.get("submitted_ts"))
        s["graded"] = bool(s.get("graded_ts"))
        s["reviewed"] = bool(s.get("reviewed_ts"))
        s.setdefault("grade_total", None)
        s.setdefault("review_total", None)
        s.setdefault("graded_by", "")
        # a submission newer than the grade needs another look
        current = s["graded"] and (not s["submitted"] or s["graded_ts"] >= s["submitted_ts"])
        s["state"] = ("reviewed" if current and s["reviewed"] else
                      "graded" if current else
                      "submitted" if s["submitted"] else
                      "active" if (s.get("count") or 0) > 0 else "not_started")
        return s

    _overview_cache: dict = {}
    _overview_refreshing: set = set()
    OVERVIEW_TTL = 60.0

    def _cached(key: str, build, fresh: bool = False):
        """Stale-while-revalidate: a cached overview is returned at once, and if
        it is older than OVERVIEW_TTL a background thread rebuilds it for the
        next visitor. Only the very first load (or fresh=1 from the Refresh
        button) waits for the stores."""
        import threading
        import time
        hit = _overview_cache.get(key)
        if hit and not fresh:
            if (time.monotonic() - hit[0]) >= OVERVIEW_TTL and key not in _overview_refreshing:
                _overview_refreshing.add(key)

                def refresh():
                    try:
                        _overview_cache[key] = (time.monotonic(), build())
                    except Exception as e:
                        log.warning("overview refresh failed for %s: %s", key, e)
                    finally:
                        _overview_refreshing.discard(key)
                threading.Thread(target=refresh, name=f"overview-{key}", daemon=True).start()
            data = dict(hit[1])
            data["cached_at"] = hit[2] if len(hit) > 2 else ""
            return data
        from datetime import datetime, timezone
        data = build()
        stamp = datetime.now(timezone.utc).isoformat()
        _overview_cache[key] = (time.monotonic(), data, stamp)
        out = dict(data)
        out["cached_at"] = stamp
        return out

    def _audit_write(request: Request, principal, path: str, status: int) -> None:
        """Record an admin write. Routes may set request.state.audit = (target, summary)."""
        log_store = app.state.audit
        if log_store is None:
            return
        from datetime import datetime, timezone
        from sim.core.ports.audit import AuditEntry
        extra = getattr(request.state, "audit", None) or ("", "")
        target, summary = (extra + ("", ""))[:2] if isinstance(extra, tuple) else ("", str(extra))
        if not target:
            parts = path.split("/")
            target = parts[4] if len(parts) > 4 else ""
        try:
            log_store.append(AuditEntry(
                ts=datetime.now(timezone.utc).isoformat(),
                actor=getattr(principal, "email", "") or getattr(principal, "uid", "") or "?",
                action=f"{request.method} {path}", target=target, summary=summary,
                status=int(status)))
        except Exception as e:
            log.warning("audit append failed: %s", e)

    def _after_mutation(path: str) -> None:
        """A write happened: the sessions list must not serve a stale copy, and
        the overviews should recount on their next read (served stale meanwhile)."""
        _overview_cache.pop("admin:sessions", None)
        for k, v in list(_overview_cache.items()):
            _overview_cache[k] = (0.0,) + tuple(v[1:])

    def _warm_overviews() -> None:
        """Build the admin overview shortly after boot so the first visit is
        served from cache (Firestore makes the cold build slow)."""
        import threading
        import time

        def run():
            time.sleep(3)
            for key, build in (("admin", ctx._admin_overview), ("admin:sessions", ctx._admin_sessions_payload)):
                try:
                    _cached(key, build, fresh=True)
                except Exception as e:
                    log.debug("warm-up of %s skipped: %s", key, e)
        threading.Thread(target=run, name="overview-warm", daemon=True).start()

    def _session_stats(rows: list) -> dict:
        """Aggregates for the overview pages. Cheap: one pass over the rows."""
        from datetime import datetime, timedelta, timezone
        from sim.core.levels import LEVEL_ORDER
        now = datetime.now(timezone.utc)
        days = [(now - timedelta(days=i)).date() for i in range(13, -1, -1)]
        active = {d.isoformat(): 0 for d in days}
        created = {d.isoformat(): 0 for d in days}
        by_sc: dict = {}
        by_level = {lvl: 0 for lvl in LEVEL_ORDER}
        by_track = {"interview": 0, "systems": 0, "product": 0}
        states = {"not_started": 0, "active": 0, "submitted": 0, "graded": 0, "reviewed": 0}
        active_24h = 0
        for s in rows:
            key = s.get("scenario") or ""
            b = by_sc.setdefault(key, {"key": key, "title": s.get("title") or key,
                                       "track": s.get("track") or "product",
                                       "total": 0, "active": 0, "submitted": 0,
                                       "not_started": 0, "graded": 0, "reviewed": 0})
            b["total"] += 1
            b[s.get("state") or "not_started"] += 1
            states[s.get("state") or "not_started"] += 1
            by_track[s.get("track") or "product"] = by_track.get(s.get("track") or "product", 0) + 1
            lvl = s.get("level") or ""
            if lvl in by_level:
                by_level[lvl] += 1
            last = _parse_ts(s.get("last_ts") or "")
            first = _parse_ts(s.get("first_ts") or "")
            if last and (s.get("count") or 0) > 0:
                if (now - last) <= timedelta(hours=24):
                    active_24h += 1
                k = last.date().isoformat()
                if k in active:
                    active[k] += 1
            if first:
                k = first.date().isoformat()
                if k in created:
                    created[k] += 1
        scen = sorted(by_sc.values(), key=lambda b: (-b["total"], b["title"]))
        return {
            "totals": {"sessions": len(rows), "active_24h": active_24h, **states},
            "by_scenario": scen,
            "by_level": [{"level": k, "count": v} for k, v in by_level.items()],
            "by_track": by_track,
            "activity": [{"day": d.isoformat(), "active": active[d.isoformat()],
                          "created": created[d.isoformat()]} for d in days],
        }

    def _instructor_rows(request: Request) -> list:
        auth = app.state.auth
        p = _actor(request)
        all_reg = (not auth.gated) or p.role == "admin"
        sessions = _merge_known_sessions(all_registered=all_reg, owner_uid=p.uid)
        if auth.gated and p.role == "instructor":
            sessions = [s for s in sessions
                        if s.get("owner_uid", p.uid) in ("", p.uid)]
        return _enrich_sessions(sessions)

    @app.get("/api/instructor/sessions")
    def instructor_sessions(request: Request,
                            x_instructor_token: str = Header(default="")):
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return {"sessions": _instructor_rows(request)}

    @app.get("/api/instructor/overview")
    def instructor_overview(request: Request, fresh: bool = False,
                            x_instructor_token: str = Header(default="")):
        """Numbers and charts for the instructor's landing page."""
        if not _instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        def build():
            rows = _instructor_rows(request)
            return {"stats": _session_stats(rows), "recent": rows[:8]}
        return _cached("instructor:" + _actor(request).uid, build, fresh)

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
        md = _audit_markdown(sid, include_tickets)
        return Response(
            content=md, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{sid}-audit.md"'})

    def _audit_markdown(sid: str, include_tickets: bool = False, regrade: bool = True) -> str:
        """The session's markdown audit; used by Export and by archiving."""
        from sim.core.levels import profile
        from sim.core.session.audit_export import build_audit_markdown
        bundle = b(sid)
        svc = bundle.session_service
        stored = app.state.grades.get(sid) if app.state.grades is not None else None
        if stored is not None:
            grade = _grade_payload(stored)      # the grade the instructor saw
        elif regrade:
            build_record = _build_record_for(sid)
            try:
                grade = _grade_body(sid, {"include_tickets": include_tickets}, build_record)
            except Exception:
                grade = None
        else:
            grade = None
        lvl = _session_level(sid)
        return build_audit_markdown(
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
            mermaid=svc.diagram_text(sid),
            tickets=_flatten_tickets(sid),
            submissions=app.state.submissions.list(sid) if app.state.submissions else [],
        )


    # published for the modules registered after this one
    ctx.OVERVIEW_TTL = OVERVIEW_TTL
    ctx._after_mutation = _after_mutation
    ctx._apply_state = _apply_state
    ctx._audit_markdown = _audit_markdown
    ctx._audit_write = _audit_write
    ctx._cached = _cached
    ctx._enrich_sessions = _enrich_sessions
    ctx._instructor_rows = _instructor_rows
    ctx._merge_known_sessions = _merge_known_sessions
    ctx._overview_cache = _overview_cache
    ctx._overview_refreshing = _overview_refreshing
    ctx._parallel = _parallel
    ctx._parse_ts = _parse_ts
    ctx._session_stats = _session_stats
    ctx._user_labels = _user_labels
    ctx._warm_overviews = _warm_overviews
    ctx.instructor_export_md = instructor_export_md
    ctx.instructor_overview = instructor_overview
    ctx.instructor_session = instructor_session
    ctx.instructor_sessions = instructor_sessions
