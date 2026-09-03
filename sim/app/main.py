"""ASGI entrypoint. Run with:  uvicorn sim.app.main:app --reload"""
from sim.app.composition_root import build_app

app = build_app()
