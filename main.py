import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.api.auth import router as auth_router
from src.api.contacts import router as contacts_router
from src.api.users import limiter as users_limiter
from src.api.users import router as users_router
from src.conf.config import settings

app = FastAPI(
    title="Contacts REST API",
    description="REST API для зберігання та управління контактами (FastAPI + SQLAlchemy + PostgreSQL).",
    version="2.0.0",
)

app.state.limiter = users_limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")


@app.get("/", tags=["root"])
def root():
    return {"message": "Contacts REST API is running. See /docs for Swagger UI."}


@app.get("/healthz", tags=["root"])
def healthcheck():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
