"""
Routes Module

所有 API 路由定义入口。
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from routes_agent import register_agent_routes
from routes_market import register_market_routes
from routes_misc import register_misc_routes
from routes_shared import RouteContext
from routes_signals import register_signal_routes
from routes_trading import register_trading_routes
from routes_users import register_user_routes


def create_app() -> FastAPI:
    app = FastAPI(title='AI-Trader API')

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.middleware('http')
    async def add_process_time_header(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        response.headers['X-Process-Time'] = str(time.time() - start_time)
        return response

    ctx = RouteContext()
    register_market_routes(app)
    register_agent_routes(app, ctx)
    register_signal_routes(app, ctx)
    register_trading_routes(app, ctx)
    register_user_routes(app, ctx)
    register_misc_routes(app)
    return app
