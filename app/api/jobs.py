from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.tasks import crawl_jobs_task, analyze_jobs_task
from app.models.analysis import AnalysisResult

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CrawlRequest(BaseModel):
    source: str        # "saramin" | "jobkorea"
    keyword: str
    limit: int = 5


class ManualRequest(BaseModel):
    source: str = "manual"
    title: str
    company: str
    raw_text: str


class AnalyzeRequest(BaseModel):
    job_post_ids: list[str]   # 분석할 공고 ID 리스트
    user_profile_id: int      # UserProfile.id


# ── 크롤링 ─────────────────────────────────────────────────

@router.post("/crawl")
async def start_crawl(req: CrawlRequest):
    """크롤링 태스크 시작 — 바로 task_id 반환"""
    if req.source not in ("saramin", "jobkorea"):
        raise HTTPException(status_code=400, detail="source는 saramin 또는 jobkorea만 가능합니다")

    task = crawl_jobs_task.delay(req.source, req.keyword, req.limit)
    return {"task_id": task.id, "status": "started"}


@router.get("/crawl/{task_id}")
async def get_crawl_result(task_id: str):
    """task_id로 크롤링 결과 조회"""
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    elif task.state == "STARTED":
        return {"task_id": task_id, "status": "started"}
    elif task.state == "SUCCESS":
        return {"task_id": task_id, "status": "success", "result": task.result}
    elif task.state == "FAILURE":
        return {"task_id": task_id, "status": "failure", "error": str(task.info)}
    else:
        return {"task_id": task_id, "status": task.state}


@router.post("/manual")
async def manual_input(req: ManualRequest):
    """공고 텍스트 직접 입력"""
    from app.crawler.base import CrawledJobPost
    job = CrawledJobPost(
        source=req.source,
        title=req.title,
        company=req.company,
        raw_text=req.raw_text,
        url="manual",
    )
    return {"status": "received", "job": job.model_dump()}


# ── 분석 ─────────────────────────────────────────────────

@router.post("/analyze")
async def start_analyze(req: AnalyzeRequest):
    """Agent 분석 태스크 시작 — 바로 task_id 반환"""
    if not req.job_post_ids:
        raise HTTPException(status_code=400, detail="job_post_ids가 비어 있습니다")

    task = analyze_jobs_task.delay(req.job_post_ids, req.user_profile_id)
    return {"task_id": task.id, "status": "started"}


@router.get("/analyze/{task_id}")
async def get_analyze_result(task_id: str):
    """task_id로 분석 태스크 상태 조회"""
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    elif task.state == "STARTED":
        return {"task_id": task_id, "status": "started"}
    elif task.state == "SUCCESS":
        return {"task_id": task_id, "status": "success", "result": task.result}
    elif task.state == "FAILURE":
        return {"task_id": task_id, "status": "failure", "error": str(task.info)}
    else:
        return {"task_id": task_id, "status": task.state}


# ── 리포트 ─────────────────────────────────────────────────

@router.get("/report/{analysis_id}")
async def get_report(analysis_id: str):
    """분석 결과 JSON 조회"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisResult).where(AnalysisResult.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")

    return {
        "analysis_id": analysis.id,
        "job_post_ids": analysis.job_post_ids,
        "stack_analysis": analysis.stack_analysis,
        "gap_analysis": analysis.gap_analysis,
        "errors": analysis.errors,
        "created_at": analysis.created_at,
    }


@router.get("/report/{analysis_id}/markdown", response_class=PlainTextResponse)
async def get_report_markdown(analysis_id: str):
    """마크다운 리포트 텍스트 반환"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisResult).where(AnalysisResult.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")

    return analysis.report_md