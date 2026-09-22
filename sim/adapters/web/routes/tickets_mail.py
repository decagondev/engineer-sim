from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def register(app, ctx):
    """Routes and helpers for the tickets_mail area (moved verbatim from create_web_app)."""
    b = ctx.b

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


    # published for the modules registered after this one
    ctx.mail_compose = mail_compose
    ctx.mail_open = mail_open
    ctx.mail_reply = mail_reply
    ctx.mail_threads = mail_threads
    ctx.mail_unread = mail_unread
    ctx.tickets_board = tickets_board
    ctx.tickets_create = tickets_create
    ctx.tickets_move = tickets_move
