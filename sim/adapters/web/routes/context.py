"""Shared state for the route modules. Each module's register(app, ctx) reads
the helpers it needs from ctx and publishes the ones it defines, so modules
stay closures over one context instead of one 3,000-line function. A helper
that lives in a module registered later is reached as ctx.<name> at call
time (see ROUTE_MODULES in sim/adapters/web/app.py for the order)."""
from __future__ import annotations


class WebContext:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)

    def __getattr__(self, name: str):
        raise AttributeError(f"web context has no {name!r}; is the module that defines it registered?")
