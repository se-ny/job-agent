from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from app.models.job_post import JobPost

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

from app.models.user_profile import UserProfile

# ── 공고 목록 ─────────────────────────────────────────────

@router.get("/posts")
async def list_job_posts(
    limit: int = 20,
    source: str | None = None,       # "saramin" | "jobkorea"
    keyword: str | None = None,       # 제목/회사명 검색
    job_role: str | None = None,      # "백엔드" | "AI/ML" 등
):
    """크롤링된 공고 목록 조회 (필터링 지원)"""
    from sqlalchemy import or_
    async with AsyncSessionLocal() as session:
        query = select(JobPost).order_by(JobPost.created_at.desc())

        if source:
            query = query.where(JobPost.source == source)
        if keyword:
            query = query.where(
                or_(
                    JobPost.title.ilike(f"%{keyword}%"),
                    JobPost.company.ilike(f"%{keyword}%"),
                )
            )

        query = query.limit(limit)
        result = await session.execute(query)
        posts = result.scalars().all()

    # job_role 필터는 JSON 컬럼이라 Python에서 처리
    if job_role:
        posts = [
            p for p in posts
            if p.keywords and job_role in p.keywords.get("job_role", "")
        ]

    return [
        {
            "id": p.id,
            "source": p.source,
            "title": p.title,
            "company": p.company,
            "url": p.url,
            "required_skills": p.keywords.get("required_skills", []) if p.keywords else [],
            "preferred_skills": p.keywords.get("preferred_skills", []) if p.keywords else [],
            "experience_years": p.keywords.get("experience_years", 0) if p.keywords else 0,
            "job_role": p.keywords.get("job_role", "") if p.keywords else "",
            "summary": p.raw_text[:200] if p.raw_text else "",
            "created_at": p.created_at,
        }
        for p in posts
    ]


# ── AI 추천 ───────────────────────────────────────────────

class RecommendRequest(BaseModel):
    job_post_ids: list[str]
    user_profile_id: int


@router.post("/recommend")
async def recommend_jobs(req: RecommendRequest):
    """내 프로필 기반 Top3 공고 추천"""
    from langchain_groq import ChatGroq
    from app.core.config import settings
    import json

    async with AsyncSessionLocal() as session:
        # 공고 조회
        result = await session.execute(
            select(JobPost).where(JobPost.id.in_(req.job_post_ids))
        )
        posts = result.scalars().all()

        # 프로필 조회
        profile_result = await session.execute(
            select(UserProfile).where(UserProfile.id == req.user_profile_id)
        )
        profile = profile_result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")

    if not posts:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

    # LLM 추천 요청
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.GROQ_API_KEY,
        temperature=0,
    )

    posts_summary = "\n\n".join([
        f"[공고 ID: {p.id}]\n제목: {p.title}\n회사: {p.company}\n내용: {p.raw_text[:300]}"
        for p in posts
    ])

    prompt = f"""다음은 사용자 프로필과 채용공고 목록입니다.

사용자 프로필:
- 이름: {profile.name}
- 보유 스킬: {", ".join(profile.current_skills)}
- 경력: {profile.experience_months}개월
- 소개: {profile.bio or "없음"}

채용공고 목록:
{posts_summary}

위 프로필을 바탕으로 가장 적합한 공고 Top3를 추천하고 이유를 설명하세요.
반드시 JSON 형식으로만 응답하세요.

{{
  "recommendations": [
    {{
      "rank": 1,
      "job_post_id": "공고ID",
      "title": "공고제목",
      "company": "회사명",
      "reason": "추천 이유 (보유 스킬과의 연관성, 성장 가능성 등 구체적으로)",
      "match_score": 85.0,
      "required_skills": ["필수스킬1", "필수스킬2"],
      "preferred_skills": ["우대스킬1"]
    }}
  ]
}}"""

    response = llm.invoke(prompt)

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 파싱 실패: {e}")