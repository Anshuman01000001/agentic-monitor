from fastapi import FastAPI
from config.settings import settings
from database import db
from dashboard.routes import router as dashboard_router
from pipeline.scheduler import start_scheduler
from agent.rag import init_rag_store

app = FastAPI(title="Agentic Monitor")
app.include_router(dashboard_router)


@app.on_event("startup")
async def startup_event():
    # initialize database (create tables)
    db.init_db(settings.DATABASE_URL)
    # initialize RAG store (embeds runbooks if present)
    init_rag_store(settings.CHROMA_PERSIST_DIR)
    # start scheduler
    start_scheduler(app)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
