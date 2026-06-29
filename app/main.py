from fastapi import FastAPI
from app.core.database import engine, Base
from app.api.jobs import router as jobs_router
from app.api.profiles import router as profiles_router
from app.api.bookmarks import router as bookmarks_router

app = FastAPI(title="Job Agent API")

app.include_router(bookmarks_router)
app.include_router(jobs_router)
app.include_router(profiles_router)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        print("✅ DB connected")

@app.get("/health")
async def health():
    return {"status": "ok"}