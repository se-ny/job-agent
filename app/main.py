from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import engine, Base
from app.api.jobs import router as jobs_router
from app.api.profiles import router as profiles_router
from app.api.bookmarks import router as bookmarks_router


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as conn:
        print("✅ DB connected")
    yield


app = FastAPI(
    title="Job Agent API",
    description="""
## 채용공고 분석 AI 에이전트

사람인/잡코리아 채용공고를 자동 수집하고 LangGraph AI 에이전트가 분석합니다.

### 주요 기능
- 채용공고 자동 크롤링 (사람인/잡코리아)
- LangGraph 기반 키워드 추출 및 스택 분석
- 내 프로필과의 갭 분석 리포트 생성
- AI Top3 공고 추천
""",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(bookmarks_router)
app.include_router(jobs_router)
app.include_router(profiles_router)


@app.get("/health")
async def health():
    return {"status": "ok"}