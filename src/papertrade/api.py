from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select

from papertrade.config import Settings
from papertrade.db import Database
from papertrade.engine import TradingEngine
from papertrade.models import AuditLog, TABLES
from papertrade.monitoring import system_status
from papertrade.security import issue_token, valid_login, valid_token

log = logging.getLogger(__name__)


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class ControlAction(BaseModel):
    action: str
    market: str | None = None


def create_app(settings: Settings | None = None, db: Database | None = None,
               engine: TradingEngine | None = None):
    settings = settings or Settings()
    db = db or Database(settings)
    # Never migrate automatically in a web worker; deployment runs init-db first.
    app = FastAPI(title="PaperTrade", docs_url=None, redoc_url=None, openapi_url=None)
    bearer = HTTPBearer(auto_error=False)
    attempts = defaultdict(deque)

    def authorized(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials or not valid_token(credentials.credentials, settings):
            raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
        return settings.admin_username

    @app.middleware("http")
    async def secure_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(Exception)
    async def safe_error(request, exc):
        from fastapi.responses import JSONResponse
        log.error("api_error type=%s path=%s", type(exc).__name__, request.url.path)
        return JSONResponse(status_code=503, content={"detail": "Service unavailable; check local operational logs"})

    @app.get("/healthz")
    def healthz():
        return {"api": "up", "mode": "paper"}

    @app.get("/readyz")
    def readyz():
        status = system_status(db)
        if not status["online"]:
            raise HTTPException(503, "Trading scheduler not ready")
        return {"ready": True, "mode": "paper"}

    @app.post("/auth/login")
    def login(payload: Login, request: Request):
        host = request.client.host if request.client else "local"
        bucket = attempts[host]
        now = time.monotonic()
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= 5:
            raise HTTPException(429, "Too many login attempts")
        bucket.append(now)
        if len(settings.api_token.get_secret_value()) < 32 or not valid_login(payload.username, payload.password, settings):
            with db.session() as session:
                session.add(AuditLog(actor="anonymous", action="login_failed", detail={}))
            raise HTTPException(401, "Invalid credentials or authentication not configured")
        with db.session() as session:
            session.add(AuditLog(actor=settings.admin_username, action="login", detail={}))
        return {"access_token": issue_token(settings), "token_type": "bearer", "expires_in": 3600}

    @app.get("/status")
    def status(actor=Depends(authorized)):
        return system_status(db)

    @app.get("/tables/{table}")
    def table_rows(table: str, limit: int = Query(200, ge=1, le=1000), actor=Depends(authorized)):
        cls = TABLES.get(table)
        if cls is None:
            raise HTTPException(404, "Unknown table")
        primary = list(cls.__table__.primary_key.columns)[0]
        with db.session() as session:
            rows = session.scalars(select(cls).order_by(primary.desc()).limit(limit)).all()
            result = [{column.name: getattr(row, column.name) for column in cls.__table__.columns} for row in rows]
        # Controls include execution state and cursors only, never environment/credentials.
        return {"rows": jsonable_encoder(result)}

    @app.post("/controls")
    def controls(payload: ControlAction, actor=Depends(authorized)):
        try:
            return (engine or TradingEngine(settings, db)).control(payload.action, payload.market, actor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    return app
