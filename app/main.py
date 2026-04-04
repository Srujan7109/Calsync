from fastapi import FastAPI

from app.routers.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="Calsync API", version="0.1.0")
    app.include_router(webhooks_router)
    return app


app = create_app()
