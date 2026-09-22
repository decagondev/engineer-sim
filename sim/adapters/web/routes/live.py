from __future__ import annotations

from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from sim.adapters.web.app_base import log
from starlette.concurrency import run_in_threadpool
from sim.core.ports.identity import IdentityError, Principal


def register(app, ctx):
    """Routes and helpers for the live area (moved verbatim from create_web_app)."""
    auth = ctx.auth
    _instr_ok = ctx._instr_ok
    auth = ctx.auth
    b = ctx.b

    @app.websocket("/ws/{session_id}")
    async def ws(websocket: WebSocket, session_id: str):
        auth = app.state.auth
        uid = ""
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
            uid = principal.uid
        from sim.adapters.llm.request_context import current_uid
        uid_token = current_uid.set(uid)
        try:
            await _ws_loop(websocket, session_id)
        finally:
            current_uid.reset(uid_token)

    async def _streamed_turn(websocket: WebSocket, svc, session_id: str, content: str, target):
        """Run one chat turn on the threadpool while forwarding the persona's
        reply fragments as `delta` frames (cumulative text) so the bubble grows
        as the model writes. The final `message` frames follow unchanged."""
        import asyncio
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cast = getattr(svc, "cast", {}) or {}
        persona_key = target if target in cast else getattr(svc, "primary_key", target)
        channel = f"dm:{persona_key}"

        def on_delta(chunk: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, chunk)

        turn = asyncio.ensure_future(run_in_threadpool(
            svc.post_tester_message, session_id, content, target, on_delta=on_delta))
        sofar = ""

        async def flush() -> None:
            nonlocal sofar
            grew = False
            while not queue.empty():
                sofar += queue.get_nowait()
                grew = True
            if grew:
                await websocket.send_json({"kind": "delta", "sender": persona_key,
                                           "channel": channel, "content": sofar})

        while not turn.done():
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getter, turn}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                sofar += getter.result()
                while not queue.empty():          # coalesce a burst into one frame
                    sofar += queue.get_nowait()
                await websocket.send_json({"kind": "delta", "sender": persona_key,
                                           "channel": channel, "content": sofar})
            else:
                getter.cancel()
        await flush()
        return turn.result()

    async def _ws_loop(websocket: WebSocket, session_id: str):
        from sim.adapters.llm.request_context import forget_user
        await websocket.accept()
        svc = b(session_id).session_service
        try:
            while True:
                data = await websocket.receive_json()
                content = (data or {}).get("content", "").strip()
                target = (data or {}).get("target")
                if not content:
                    continue
                forget_user()          # a key saved mid-chat is picked up next turn
                try:
                    msgs = await _streamed_turn(websocket, svc, session_id, content, target)
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
                app.state.bus.notify(session_id, "turn")
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/watch/{session_id}")
    async def ws_watch(websocket: WebSocket, session_id: str):
        """Read-only live feed for instructors: replays the transcript, then
        sends new rows as they land (woken by the bus, re-checked every 20 s)."""
        import asyncio
        auth = app.state.auth
        if auth.gated:
            token = websocket.query_params.get("token") or ""
            try:
                principal = auth.principal_from_token(token)
            except IdentityError:
                await websocket.close(code=4401)
                return
            if not auth.allow_session(principal, session_id, grade=True):
                await websocket.close(code=4403)
                return
        elif not _instr_ok(websocket.query_params.get("itoken") or ""):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        q = app.state.bus.subscribe(session_id)
        last_id = 0
        try:
            while True:
                rows = await run_in_threadpool(app.state.repo.list_for_session, session_id)
                fresh = [m for m in rows if (m.id or 0) > last_id]
                if fresh:
                    last_id = max((m.id or 0) for m in fresh)
                    await websocket.send_json({"rows": [
                        {"id": m.id, "sender": m.sender, "content": m.content,
                         "channel": m.channel, "ts": m.ts, "kind": m.kind} for m in fresh]})
                try:
                    await asyncio.wait_for(q.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            return
        finally:
            app.state.bus.unsubscribe(session_id, q)


    # published for the modules registered after this one
    ctx._streamed_turn = _streamed_turn
    ctx._ws_loop = _ws_loop
    ctx.ws = ws
    ctx.ws_watch = ws_watch
