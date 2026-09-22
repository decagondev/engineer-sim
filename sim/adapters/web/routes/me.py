from __future__ import annotations

from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from sim.adapters.web.app_base import _STATIC


def register(app, ctx):
    """Routes and helpers for the me area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    auth = ctx.auth
    _actor = ctx._actor
    _local_instructor = ctx._local_instructor
    _site = ctx._site
    auth = ctx.auth
    b = ctx.b

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

    @app.get("/api/site/announcement")
    def site_announcement():
        return {"announcement": _site().announcement or ""}

    @app.get("/api/auth/me")
    def auth_me(request: Request):
        if not app.state.auth.gated:
            p = _local_instructor()
            return {"uid": p.uid, "email": p.email, "role": p.role, "disabled": False,
                    "name": "", "has_groq_key": False, "has_github_token": False,
                    "has_gitlab_token": False, **_gitlab_site()}
        p = getattr(request.state, "principal", None)
        if p is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from sim.adapters.llm.request_context import current_user
        rec = current_user(app.state.auth.users)
        return {"uid": p.uid, "email": p.email, "role": p.role, "disabled": False,
                "name": rec.name if rec else "",
                "has_groq_key": bool(rec.groq_key_enc) if rec else False,
                "has_github_token": bool(rec.github_token_enc) if rec else False,
                "github_connected": bool(rec and rec.github_token_enc and rec.github_scope),
                "github_oauth": bool(getattr(app.state.github_oauth, "configured", False)),
                "has_gitlab_token": bool(getattr(rec, "gitlab_token_enc", "")) if rec else False,
                "gitlab_connected": bool(rec and getattr(rec, "gitlab_token_enc", "")
                                         and getattr(rec, "gitlab_scope", "")),
                **_gitlab_site()}

    def _gitlab_site() -> dict:
        """Which GitLab instance this server knows, if any (for Settings and
        the Workspace app)."""
        cfg = manager._config
        url = getattr(cfg, "gitlab_url", "") or ""
        from urllib.parse import urlparse
        return {"gitlab_url": url, "gitlab_host": urlparse(url).netloc if url else "",
                "gitlab_oauth": bool(getattr(app.state.gitlab_oauth, "configured", False))}

    @app.patch("/api/me")
    def patch_me(request: Request, payload: dict):
        from sim.core.ports.users import UserRecord
        from sim.adapters.llm.request_context import current_user, prime_user
        auth = app.state.auth
        if not auth.gated:
            return JSONResponse({"error": "sign-in required"}, status_code=400)
        p = getattr(request.state, "principal", None)
        if p is None or auth.users is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        rec = current_user(auth.users)
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        name = rec.name
        if "name" in (payload or {}):
            name = str(payload.get("name") or "").strip()
        enc = rec.groq_key_enc
        if (payload or {}).get("clear_groq_key"):
            enc = ""
        elif "groq_key" in (payload or {}):
            raw = str(payload.get("groq_key") or "").strip()
            if not raw:
                return JSONResponse({"error": "Paste a Groq API key."}, status_code=400)
            try:
                from sim.adapters.llm.groq_client import validate_groq_key
                validate_groq_key(raw)
            except RuntimeError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
            enc = encrypt_secret(secret_from_config(manager._config), raw)
        gh = rec.github_token_enc
        if (payload or {}).get("clear_github_token"):
            gh = ""
        elif "github_token" in (payload or {}):
            raw = str(payload.get("github_token") or "").strip()
            if not raw:
                return JSONResponse({"error": "Paste a GitHub token."}, status_code=400)
            try:
                from sim.adapters.build.github_api import validate_token
                validate_token(raw)
            except RuntimeError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
            gh = encrypt_secret(secret_from_config(manager._config), raw)
        scope = rec.github_scope if gh == rec.github_token_enc else ""   # a pasted token is read-only
        gl = rec.gitlab_token_enc
        if (payload or {}).get("clear_gitlab_token"):
            gl = ""
        elif "gitlab_token" in (payload or {}):
            raw = str(payload.get("gitlab_token") or "").strip()
            site = _gitlab_site()["gitlab_url"]
            if not site:
                return JSONResponse({"error": "This server has no GitLab instance configured."}, status_code=400)
            if not raw:
                return JSONResponse({"error": "Paste a GitLab token."}, status_code=400)
            try:
                from sim.adapters.build.gitlab_api import validate_token as validate_gitlab_token
                validate_gitlab_token(site, raw)
            except RuntimeError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
            gl = encrypt_secret(secret_from_config(manager._config), raw)
        gl_scope = rec.gitlab_scope if gl == rec.gitlab_token_enc else ""
        rec = auth.users.upsert(UserRecord(
            uid=rec.uid, email=rec.email, role=rec.role, disabled=rec.disabled,
            created_at=rec.created_at, last_login=rec.last_login,
            name=name, groq_key_enc=enc, github_token_enc=gh, github_scope=scope,
            gitlab_token_enc=gl, gitlab_scope=gl_scope,
        ))
        prime_user(rec)
        return {"ok": True, "name": rec.name,
                "has_groq_key": bool(rec.groq_key_enc),
                "has_github_token": bool(rec.github_token_enc),
                "github_connected": bool(rec.github_token_enc and rec.github_scope),
                "has_gitlab_token": bool(rec.gitlab_token_enc),
                "gitlab_connected": bool(rec.gitlab_token_enc and rec.gitlab_scope)}

    # ---- GitHub connect (device flow) -------------------------------------
    def _me_record(request: Request):
        from sim.adapters.llm.request_context import current_user
        auth = app.state.auth
        p = getattr(request.state, "principal", None) if auth.gated else None
        if p is None or auth.users is None:
            return None, JSONResponse({"error": "sign-in required"}, status_code=400)
        rec = current_user(auth.users)
        if rec is None:
            return None, JSONResponse({"error": "not found"}, status_code=404)
        return rec, None

    def _connect_routes(forge: str, broker_attr: str, pending_attr: str, token_field: str,
                        scope_field: str, scope: str, not_configured: str, pack=None):
        """Device-flow connect for one forge: POST starts (the user types the
        code at the forge), GET polls until the token arrives, DELETE forgets it.
        `pack(token)` turns the OAuthToken into the plaintext to encrypt (GitLab
        keeps the refresh token too)."""
        import dataclasses
        import time
        from sim.core.ports.oauth import OAuthError
        from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
        from sim.adapters.llm.request_context import prime_user
        pack = pack or (lambda t: t.access_token)

        def broker():
            return getattr(app.state, broker_attr, None)

        def pending():
            return getattr(app.state, pending_attr)

        def connected(rec) -> bool:
            return bool(getattr(rec, token_field, "") and getattr(rec, scope_field, ""))

        @app.post(f"/api/me/{forge}/connect", name=f"{forge}_connect_start")
        def connect_start(request: Request):
            b = broker()
            if b is None or not getattr(b, "configured", False):
                return JSONResponse({"error": not_configured}, status_code=501)
            rec, err = _me_record(request)
            if err:
                return err
            try:
                code = b.start(scope)
            except OAuthError as e:
                return JSONResponse({"error": str(e)}, status_code=502)
            pending()[rec.uid] = {"device_code": code.device_code, "interval": code.interval,
                                  "started": time.monotonic(), "expires_in": code.expires_in}
            return {"user_code": code.user_code, "verification_uri": code.verification_uri,
                    "interval": code.interval, "expires_in": code.expires_in}

        @app.get(f"/api/me/{forge}/connect", name=f"{forge}_connect_poll")
        def connect_poll(request: Request):
            rec, err = _me_record(request)
            if err:
                return err
            p = pending().get(rec.uid)
            if not p:
                return {"status": "idle", "connected": connected(rec)}
            if time.monotonic() - p["started"] > p.get("expires_in", 900):
                pending().pop(rec.uid, None)
                return {"status": "expired"}
            try:
                token = broker().poll(p["device_code"])
            except OAuthError as e:
                pending().pop(rec.uid, None)
                return {"status": "failed", "error": str(e)}
            if token is None:
                return {"status": "pending", "interval": p["interval"]}
            pending().pop(rec.uid, None)
            enc = encrypt_secret(secret_from_config(manager._config), pack(token))
            got = token.scope or scope
            prime_user(app.state.auth.users.upsert(
                dataclasses.replace(rec, **{token_field: enc, scope_field: got})))
            return {"status": "connected", "scope": got}

        @app.delete(f"/api/me/{forge}/connect", name=f"{forge}_disconnect")
        def disconnect(request: Request):
            rec, err = _me_record(request)
            if err:
                return err
            pending().pop(rec.uid, None)
            prime_user(app.state.auth.users.upsert(
                dataclasses.replace(rec, **{token_field: "", scope_field: ""})))
            return {"ok": True}

    _connect_routes("github", "github_oauth", "github_pending", "github_token_enc", "github_scope",
                    "public_repo", "GitHub sign-in is not configured on this server (GITHUB_OAUTH_CLIENT_ID)")
    from sim.adapters.auth.gitlab_tokens import pack_token as _pack_gitlab
    _connect_routes("gitlab", "gitlab_oauth", "gitlab_pending", "gitlab_token_enc", "gitlab_scope",
                    "api", "GitLab sign-in is not configured on this server (GITLAB_URL + GITLAB_OAUTH_CLIENT_ID)",
                    pack=_pack_gitlab)

    @app.get("/api/me/sessions")
    def my_sessions(request: Request):
        """The caller's sessions with state and grade, from the session index
        (one scoped stream; never a read per session)."""
        auth = app.state.auth
        p = _actor(request)
        if auth.sessions is None:
            return {"sessions": []}
        if p.role == "admin":
            rows = ctx._merge_known_sessions(all_registered=True)
        elif p.role == "instructor":
            rows = ctx._merge_known_sessions(all_registered=False, owner_uid=p.uid)
        else:
            rows = ctx._merge_known_sessions(all_registered=False, assignee_uid=p.uid)
            rows = [r for r in rows if r.get("assignee_uid") == p.uid]
        out = []
        for s in rows:
            sc = manager.registry.get(s.get("scenario") or "")
            s = ctx._apply_state(dict(s))
            out.append({
                "session_id": s["session_id"], "scenario": s.get("scenario") or "",
                "title": sc.title if sc else (s.get("scenario") or ""),
                "track": sc.track if sc else "product",
                "level": s.get("level") or "", "status": s.get("status") or "",
                "owner_uid": s.get("owner_uid") or "", "assignee_uid": s.get("assignee_uid") or "",
                "created_at": s.get("first_ts") or "", "last_ts": s.get("last_ts") or "",
                "count": s.get("count") or 0, "state": s["state"],
                "grade_total": s.get("review_total") if s.get("review_total") is not None else s.get("grade_total"),
                "reviewed": s["reviewed"],
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


    # published for the modules registered after this one
    ctx._connect_routes = _connect_routes
    ctx._gitlab_site = _gitlab_site
    ctx._me_record = _me_record
    ctx.admin_page = admin_page
    ctx.auth_config = auth_config
    ctx.auth_me = auth_me
    ctx.challenger_page = challenger_page
    ctx.claim_session = claim_session
    ctx.instructor_page = instructor_page
    ctx.login_page = login_page
    ctx.my_sessions = my_sessions
    ctx.patch_me = patch_me
    ctx.site_announcement = site_announcement
