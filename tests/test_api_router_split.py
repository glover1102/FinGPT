from __future__ import annotations

from app.api.server import app


def _route_module(path: str, method: str) -> str:
    method = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return getattr(route.endpoint, "__module__", "")
    raise AssertionError(f"route not found: {method} {path}")


def test_quant_lab_compatibility_routes_live_in_dedicated_routers() -> None:
    assert _route_module("/api/v1/research", "POST") == "app.api.routers.research"
    assert _route_module("/api/v1/research/analyze", "POST") == "app.api.routers.research"
    assert _route_module("/api/v1/research/universal", "POST") == "app.api.routers.research"
    assert _route_module("/api/v1/research/compare", "POST") == "app.api.routers.research"
    assert _route_module("/api/v1/research/portfolio/risk", "POST") == "app.api.routers.research"
    assert _route_module("/api/v1/data/health", "GET") == "app.api.routers.data"
    assert _route_module("/api/v1/dashboard/market", "GET") == "app.api.routers.dashboard"
    assert _route_module("/api/v1/dashboard/equity-heatmap", "GET") == "app.api.routers.dashboard"
    assert _route_module("/api/v1/backtest/run", "POST") == "app.api.routers.backtest"
    assert _route_module("/api/v1/portfolio/optimize", "POST") == "app.api.routers.portfolio"
    assert _route_module("/api/v1/watchlist", "GET") == "app.api.routers.watchlist"
    assert _route_module("/api/v1/config", "GET") == "app.api.routers.system"
    assert _route_module("/api/v1/health", "GET") == "app.api.routers.system"
    assert _route_module("/api/v1/macro/overview", "GET") == "app.api.routers.macro"
    assert _route_module("/api/v1/macro/series", "GET") == "app.api.routers.macro"
    assert _route_module("/api/v1/macro/report", "GET") == "app.api.routers.macro"
    assert _route_module("/api/macro/overview", "GET") == "app.api.routers.macro"
