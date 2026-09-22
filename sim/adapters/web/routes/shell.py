from __future__ import annotations

from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from sim.adapters.web.app_base import _STATIC
import os
from sim.core.workflow import resolve_workflow


def register(app, ctx):
    """Routes and helpers for the shell area (moved verbatim from create_web_app)."""
    manager = ctx.manager
    _repo_writable = ctx._repo_writable
    _scenario_config = ctx._scenario_config
    _session_level = ctx._session_level
    b = ctx.b

    # ---- static / shell -------------------------------------------------
    _health_cache: dict = {}

    def _health_checks() -> dict:
        """store: one cheap read (3 s budget; failure = 503). model: a ping of
        the provider when a classroom key is set (5 s; failure only warns, so a
        provider outage never takes the site down). Cached for 30 s."""
        import time
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
        hit = _health_cache.get("checks")
        if hit and time.monotonic() - hit[0] < 30:
            return hit[1]
        cfg = manager._config
        checks: dict = {"store": {"ok": True}, "model": {"ok": True, "checked": False},
                        "keys": {"groq": bool(os.environ.get("GROQ_API_KEY")),
                                 "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
                                 "github": bool(cfg.github_token),
                                 "byok_secret": bool(cfg.byok_secret)}}
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut = ex.submit(lambda: app.state.settings.get_instructor())
            t0 = time.monotonic()
            try:
                fut.result(timeout=3.0)
                checks["store"]["ms"] = int((time.monotonic() - t0) * 1000)
            except _Timeout:
                checks["store"] = {"ok": False, "error": "store read timed out after 3 s"}
            except Exception as e:
                checks["store"] = {"ok": False, "error": str(e)[:200]}
            if cfg.llm_provider == "groq" and os.environ.get("GROQ_API_KEY"):
                from sim.adapters.llm.groq_client import validate_groq_key
                fut = ex.submit(validate_groq_key, os.environ.get("GROQ_API_KEY", ""))
                t0 = time.monotonic()
                try:
                    fut.result(timeout=5.0)
                    checks["model"] = {"ok": True, "checked": True,
                                       "ms": int((time.monotonic() - t0) * 1000)}
                except _Timeout:
                    checks["model"] = {"ok": False, "checked": True, "error": "model ping timed out after 5 s"}
                except Exception as e:
                    checks["model"] = {"ok": False, "checked": True, "error": str(e)[:200]}
        _health_cache["checks"] = (time.monotonic(), checks)
        return checks

    @app.get("/health")
    def health():
        cfg = manager._config
        checks = _health_checks()
        ok = bool(checks["store"]["ok"])
        body = {"status": "ok" if ok else "degraded",
                "commit": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("GIT_COMMIT") or "")[:12],
                "llm_provider": cfg.llm_provider,
                "model": {"groq": cfg.groq_model, "anthropic": cfg.anthropic_model,
                          "ollama": cfg.ollama_model}.get(cfg.llm_provider, ""),
                "checks": checks, "llm_failover": ctx._failover_status(),
                "github_oauth": bool(cfg.github_oauth_client_id),
                "gitlab_url": cfg.gitlab_url,
                "gitlab_oauth": bool(cfg.gitlab_url and cfg.gitlab_oauth_client_id)}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/scenarios")
    def scenarios():
        out = []
        cfg = _scenario_config()
        for m in manager.scenarios_meta():
            m = dict(m)
            m["starter_url"] = (cfg.get(m["key"]) or {}).get("starter_url")
            m["workflow"] = resolve_workflow(m.get("track", "product"), app.state.hosted).as_dict()
            out.append(m)
        return {"scenarios": out, "default": manager.default_scenario_key(),
                "hosted": app.state.hosted}

    def _workflow_payload_for(sc) -> dict:
        wf = resolve_workflow(sc.track, app.state.hosted).as_dict()
        if wf["kind"] == "repo" and _repo_writable(""):
            wf["editable"] = True
            wf["writes_to_repo"] = True
        return wf

    def _scenario_info(sc):
        starter_url = (app.state.settings.get_scenario_starter_url(sc.key)
                       if app.state.settings else None)
        return {"key": sc.key, "title": sc.title, "difficulty": sc.difficulty,
                "track": sc.track, "role_label": sc.role_label,
                "starter_url": starter_url,
                "timebox_minutes": getattr(sc, "timebox_minutes", 0),
                "hosted": app.state.hosted,
                "workflow": _workflow_payload_for(sc),
                "personas": [{"key": p.key, "name": p.name, "role": p.role,
                              "lane": getattr(p, "lane", "")}
                             for p in sc.personas]}

    @app.get("/api/session/{session_id}/scenario")
    def session_scenario(session_id: str):
        bundle = b(session_id)
        info = _scenario_info(bundle.scenario)
        info["started_at"] = bundle.session_service.started_at(session_id)
        return info

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


    # published for the modules registered after this one
    ctx._health_cache = _health_cache
    ctx._health_checks = _health_checks
    ctx._scenario_info = _scenario_info
    ctx._workflow_payload_for = _workflow_payload_for
    ctx.get_level = get_level
    ctx.health = health
    ctx.index = index
    ctx.levels = levels
    ctx.scenarios = scenarios
    ctx.session_scenario = session_scenario
