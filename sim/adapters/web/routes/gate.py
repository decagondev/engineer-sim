from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from sim.core.ports.identity import IdentityError, Principal


def register(app, ctx):
    """Routes and helpers for the gate area (moved verbatim from create_web_app)."""
    auth = ctx.auth
    _INSTR_SID = ctx._INSTR_SID
    _SESSION_API = ctx._SESSION_API
    auth = ctx.auth

    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        auth = app.state.auth
        if not getattr(app.state, "public_base_url_fixed", False):
            host = request.headers.get("host", "")
            if host:
                app.state.public_base_url = f"{request.url.scheme}://{host}"
        if not auth.gated:
            return await call_next(request)
        path = request.url.path
        if path.startswith("/static") or path.startswith("/onboarding"):
            # always revalidate scripts and pages so a deploy is picked up on
            # the next load (ETags keep the revalidation cheap)
            resp = await call_next(request)
            resp.headers.setdefault("Cache-Control", "no-cache")
            return resp
        if path in {"/health", "/api/auth/config", "/api/site/announcement", "/",
                    "/instructor", "/login", "/challenger", "/admin"}:
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        try:
            principal = auth.principal_from_headers(request.headers)
        except IdentityError as e:
            return JSONResponse({"error": e.detail}, status_code=e.status)
        request.state.principal = principal
        from sim.adapters.llm.request_context import current_uid
        uid_token = current_uid.set(principal.uid)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            ctx._after_mutation(path)
        audit_this = request.method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/admin")
        try:
            if path.startswith("/api/admin"):
                if not auth.allow_admin(principal):
                    return JSONResponse({"error": "forbidden"}, status_code=403)
                resp = await call_next(request)
                if audit_this:
                    ctx._audit_write(request, principal, path, resp.status_code)
                return resp
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
            if audit_this:
                resp = await call_next(request)
                ctx._audit_write(request, principal, path, resp.status_code)
                return resp
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
        finally:
            current_uid.reset(uid_token)


    # published for the modules registered after this one
    ctx.auth_gate = auth_gate
