from __future__ import annotations

from fastapi import Header
from fastapi import Request
from fastapi.responses import JSONResponse
from pathlib import Path
from sim.adapters.web.app_base import log
from starlette.concurrency import run_in_threadpool


def register(app, ctx):
    """Routes and helpers for the session area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    auth = ctx.auth
    _actor = ctx._actor
    _calibrated = ctx._calibrated
    _session_level = ctx._session_level
    _workflow = ctx._workflow
    auth = ctx.auth
    b = ctx.b

    @app.post("/api/session/{session_id}/start")
    def start(session_id: str):
        svc = b(session_id).session_service
        svc.start(session_id)
        return {"session_id": session_id, "started": True,
                "started_at": svc.started_at(session_id)}

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
        if b(session_id).scenario.track == "interview":
            summary = svc.assessment_summary(session_id)
            if summary:
                extra.append("ASSESSMENT: " + summary)
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
        body["weights"] = {c.key: round(c.weight, 4) for c in adj}
        body["expectation"] = expectation
        body["build_record"] = build_record[:60_000]
        # each evidence string points back at the transcript message it quotes
        from sim.core.grading.evidence import annotate
        body = annotate(body, app.state.repo.list_for_session(session_id))
        body["calibrated"] = _calibrated()
        if not body["calibrated"]:
            body["caveat"] = ("Grader is not yet calibrated against human scores — "
                              "treat this as directional, not a grade.")
        return body

    def _linked_repo(session_id: str) -> str:
        """The repo the grader reads: the linked one, else the last repo submission."""
        url = app.state.settings.get_session_repo_url(session_id) if app.state.settings else None
        if url:
            return url
        sub = app.state.submissions.latest(session_id) if app.state.submissions else None
        return sub.content if sub and sub.kind == "repo" else ""

    def _sandbox_record(session_id: str) -> str:
        env = b(session_id).environment
        if env is None or app.state.build_observer is None:
            return ""
        h = env.handle(session_id)
        return app.state.build_observer.summary(h.workdir) if h else ""

    def _build_record_for(session_id: str) -> str:
        """How the engineer built, resolved per workflow (docs/WORKSPACE-PLAN.md section 3).
        The design text, diagram and tickets are appended separately by
        _enrich_build_record so they are never duplicated here."""
        wf = _workflow(session_id)
        if wf.kind == "repo":
            url = _linked_repo(session_id)
            if not url:
                return "(no repository linked or submitted)"
            if app.state.github_observer is None:
                return f"(repo {url} submitted; GitHub reading not configured)"
            try:
                return app.state.github_observer.summary(url)
            except Exception as e:
                return f"(could not read submitted repo {url}: {e})"
        sub = app.state.submissions.latest(session_id) if app.state.submissions else None
        if wf.kind == "sandbox":
            if sub and sub.kind == "repo" and app.state.github_observer is not None:
                try:
                    return app.state.github_observer.summary(sub.content)
                except Exception as e:
                    return f"(could not read submitted repo {sub.content}: {e})"
            if sub and sub.kind == "patch":
                return f"SUBMITTED PATCH ({sub.filename}):\n{sub.content}"
        # doc (and sandbox without a submission): the workspace's own git history
        return _sandbox_record(session_id)

    def _review_for(session_id: str):
        store = app.state.reviews
        try:
            return store.get(session_id) if store is not None else None
        except Exception:
            return None

    def _grade_payload(g, review=None) -> dict:
        """The stored model grade with the instructor's review merged over it."""
        from sim.core.grading.review import merge_review
        body = dict(g.body or {})
        body.update({"graded_at": g.ts, "graded_by": g.graded_by, "stored": True,
                     "total": g.total, "level": g.level,
                     "include_tickets": g.include_tickets, "calibrated": g.calibrated})
        if review is None:
            review = _review_for(g.session_id)
        return merge_review(body, review, b(g.session_id).scenario.rubric)

    def _store_grade(session_id: str, body: dict, request: Request | None) -> dict:
        """Persist the grade so dashboards and exports show it without
        re-running the grader; a regrade replaces the previous one."""
        from datetime import datetime, timezone
        from sim.core.ports.grades import StoredGrade
        store = app.state.grades
        if store is None or body.get("error"):
            return body
        actor = _actor(request)
        ts = datetime.now(timezone.utc).isoformat()
        g = StoredGrade(session_id=session_id, total=float(body.get("total") or 0),
                        level=body.get("level") or "", ts=ts,
                        graded_by=actor.email or actor.uid,
                        include_tickets=bool(body.get("include_tickets")),
                        calibrated=bool(body.get("calibrated")), body=body)
        try:
            store.save(g)
        except Exception as e:
            log.warning("could not store grade for %s: %s", session_id, e)
            return body
        return _grade_payload(g)

    @app.post("/api/session/{session_id}/grade")
    async def grade(session_id: str, request: Request, payload: dict | None = None):
        build_record = (payload or {}).get("build_record", "")
        if not build_record:
            build_record = await run_in_threadpool(_build_record_for, session_id)
        body = await run_in_threadpool(
            _grade_body, session_id, payload, build_record)
        body = await run_in_threadpool(_store_grade, session_id, body, request)
        app.state.bus.notify(session_id, "grade")
        return JSONResponse(body)

    @app.get("/api/session/{session_id}/grade")
    def stored_grade(session_id: str):
        """The last stored grade for this session, with the instructor's review
        merged over it, or 404 when never graded."""
        store = app.state.grades
        g = store.get(session_id) if store is not None else None
        if g is None:
            return JSONResponse({"error": "not graded yet"}, status_code=404)
        return JSONResponse(_grade_payload(g))

    def _may_review(request: Request, session_id: str) -> bool:
        auth = app.state.auth
        if not auth.gated:
            return True
        return auth.allow_session(_actor(request), session_id, grade=True)

    @app.put("/api/instructor/session/{session_id}/review")
    def instructor_review(session_id: str, payload: dict, request: Request,
                          x_instructor_token: str = Header(default="")):
        """Save the instructor's per-criterion overrides and comment. The model
        grade is untouched; readers see the merge."""
        from datetime import datetime, timezone
        from sim.core.grading.review import HumanReview, ReviewError, validate_review
        if not ctx._instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not _may_review(request, session_id):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if app.state.reviews is None:
            return JSONResponse({"error": "reviews not configured"}, status_code=501)
        rubric = b(session_id).scenario.rubric
        try:
            scores = validate_review((payload or {}).get("scores") or {}, rubric)
        except ReviewError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        comment = str((payload or {}).get("comment") or "").strip()[:4000]
        if not scores and not comment:
            return JSONResponse({"error": "nothing to save: adjust a score or write a comment"},
                                status_code=400)
        actor = _actor(request)
        review = HumanReview(session_id=session_id, scores=scores, comment=comment,
                             reviewer=actor.email or actor.uid,
                             ts=datetime.now(timezone.utc).isoformat())
        app.state.reviews.save(review)
        g = app.state.grades.get(session_id) if app.state.grades is not None else None
        if g is not None:
            merged = _grade_payload(g, review)
            _index_review_total(session_id, merged.get("total"))
            return {"ok": True, "grade": merged}
        return {"ok": True, "grade": None, "review": {
            "scores": scores, "comment": comment, "reviewer": review.reviewer, "ts": review.ts}}

    @app.delete("/api/instructor/session/{session_id}/review")
    def instructor_clear_review(session_id: str, request: Request,
                                x_instructor_token: str = Header(default="")):
        if not ctx._instr_ok(x_instructor_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not _may_review(request, session_id):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if app.state.reviews is not None:
            app.state.reviews.delete_for_session(session_id)
        return {"ok": True}

    def _index_review_total(session_id: str, total) -> None:
        indexer = getattr(app.state.repo, "index_session", None)
        if indexer is not None:
            try:
                indexer(session_id, review_total=total)
            except Exception:
                pass

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
        if app.state.hosted:
            return JSONResponse({"error": "starter downloads are only available on a local "
                                          "server; fork the starter repo instead"},
                                status_code=404)
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
        if app.state.hosted and _workflow(session_id).kind == "repo":
            return JSONResponse({"error": "this server only accepts a linked GitHub repo "
                                          "for this scenario"}, status_code=405)
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
        bundle = b(session_id)
        svc = bundle.session_service
        if bundle.scenario.track != "product" or filename.lower().endswith(".md"):
            # design-doc tracks paste the document itself; a product patch is
            # already the build record and must not be echoed as a "design"
            svc.remember_design(session_id, content)
            _maybe_diagram(session_id, content)
        svc.after_submission(session_id)
        app.state.bus.notify(session_id, "submission")
        return {"ok": True, "seq": sub.seq, "filename": filename, "lines": sub.lines}

    @app.get("/api/session/{session_id}/workspace/repo")
    def get_linked_repo(session_id: str):
        url = app.state.settings.get_session_repo_url(session_id) if app.state.settings else None
        return {"url": url or "", "workflow": _workflow(session_id).as_dict()}

    @app.post("/api/session/{session_id}/workspace/repo")
    def link_repo(session_id: str, payload: dict):
        """Remember the learner's public repo so Files can browse it and the
        grader can read it. Validated against the forge; recorded in the transcript."""
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        if not _workflow(session_id).needs_repo_url:
            return JSONResponse({"error": "this scenario is worked in the workspace, "
                                          "not a linked repo"}, status_code=405)
        url = (payload or {}).get("url", "").strip()
        if app.state.github_observer is None:
            return JSONResponse({"error": "repo submission not configured"}, status_code=501)
        ok, msg = app.state.github_observer.validate(url)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        previous = app.state.settings.get_session_repo_url(session_id) or ""
        app.state.settings.set_session_repo_url(session_id, url)
        if previous != url:
            app.state.repo.append(StoredMessage(
                session_id=session_id, sender="tester", channel="general",
                content=f"[reveal] Linked repo: {url}",
                ts=datetime.now(timezone.utc).isoformat(), kind="event"))
        return {"ok": True, "url": url, "message": msg}

    @app.post("/api/session/{session_id}/submit-repo")
    def submit_repo(session_id: str, payload: dict):
        from datetime import datetime, timezone
        from sim.core.ports.repository import StoredMessage
        url = (payload or {}).get("url", "").strip()
        if not url and app.state.settings is not None:
            url = app.state.settings.get_session_repo_url(session_id) or ""
        if not url:
            return JSONResponse({"error": "link your repo first"}, status_code=400)
        if app.state.github_observer is None:
            return JSONResponse({"error": "repo submission not configured"}, status_code=501)
        ok, msg = app.state.github_observer.validate(url)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        if app.state.settings is not None and _workflow(session_id).needs_repo_url:
            app.state.settings.set_session_repo_url(session_id, url)
        ts = datetime.now(timezone.utc).isoformat()
        app.state.submissions.save(session_id, "github-repo", url, ts, kind="repo")
        app.state.repo.append(StoredMessage(
            session_id=session_id, sender="tester", channel="general",
            content=f"[reveal] Submitted repo: {url}", ts=ts, kind="event"))
        svc = b(session_id).session_service
        reader = getattr(app.state.github_observer, "read_file", None)
        design = reader(url, "DESIGN.md") if reader else None
        if design and design.strip():
            # a pushed DESIGN.md is the design: the assessor and grader read it
            svc.remember_design(session_id, design)
            _maybe_diagram(session_id, design)
        svc.after_submission(session_id)
        app.state.bus.notify(session_id, "submission")
        return {"ok": True, "message": msg}

    @app.get("/api/session/{session_id}/submissions")
    def list_submissions(session_id: str):
        subs = app.state.submissions.list(session_id)
        return {"submissions": [
            {"seq": s.seq, "filename": s.filename, "lines": s.lines,
             "ts": s.ts, "kind": s.kind, "content": s.content}
            for s in subs]}


    # published for the modules registered after this one
    ctx._build_record_for = _build_record_for
    ctx._enrich_build_record = _enrich_build_record
    ctx._flatten_tickets = _flatten_tickets
    ctx._grade_body = _grade_body
    ctx._grade_payload = _grade_payload
    ctx._index_review_total = _index_review_total
    ctx._linked_repo = _linked_repo
    ctx._may_review = _may_review
    ctx._maybe_diagram = _maybe_diagram
    ctx._review_for = _review_for
    ctx._sandbox_record = _sandbox_record
    ctx._store_grade = _store_grade
    ctx._ticket_record = _ticket_record
    ctx.end = end
    ctx.get_diagram = get_diagram
    ctx.get_linked_repo = get_linked_repo
    ctx.grade = grade
    ctx.instructor_clear_review = instructor_clear_review
    ctx.instructor_review = instructor_review
    ctx.link_repo = link_repo
    ctx.list_submissions = list_submissions
    ctx.start = start
    ctx.starter_zip = starter_zip
    ctx.stored_grade = stored_grade
    ctx.submit_repo = submit_repo
    ctx.submit_work = submit_work
    ctx.transcript = transcript
