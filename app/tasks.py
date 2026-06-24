import asyncio
import logging
from celery import shared_task
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.job_post import JobPost
from app.models.analysis import AnalysisResult
from app.crawler.base import get_crawler
from app.agent.graph import job_agent

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="crawl_jobs_task")
def crawl_jobs_task(self, site: str, keyword: str, pages: int = 1):
    """사람인/잡코리아 크롤링 → DB 저장"""
    async def _run():
        crawler = get_crawler(site)
        posts = await crawler.crawl(keyword=keyword, limit=pages)

        async with AsyncSessionLocal() as session:
            saved_ids = []
            for post in posts:
                job = JobPost(
                    source=post.source,
                    title=post.title,
                    company=post.company,
                    raw_text=post.raw_text,
                    url=post.url,
                )
                session.add(job)
                await session.flush()
                saved_ids.append(job.id)
            await session.commit()

        logger.info(f"[crawl] {site} '{keyword}' — {len(saved_ids)}개 저장")
        return {"saved_ids": saved_ids, "count": len(saved_ids)}

    return asyncio.run(_run())


@celery_app.task(bind=True, name="analyze_jobs_task")
def analyze_jobs_task(self, job_post_ids: list[str], user_profile_id: int):
    """크롤링된 공고 ID 리스트 → Agent 분석 → DB 저장"""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings

    async def _run():
        # 매번 새 엔진/세션 생성 (asyncio.run() 내부에서 루프 충돌 방지)
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        async with SessionLocal() as session:
            # 1. DB에서 공고 조회
            from sqlalchemy import select
            result = await session.execute(
                select(JobPost).where(JobPost.id.in_(job_post_ids))
            )
            job_posts = result.scalars().all()

            if not job_posts:
                await engine.dispose()
                return {"error": "공고를 찾을 수 없습니다."}

            # 2. Agent 입력 포맷
            posts_input = [
                {
                    "id": p.id,
                    "title": p.title,
                    "description": p.raw_text,
                }
                for p in job_posts
            ]

            # 3. LangGraph Agent 실행
            logger.info(f"[analyze] Agent 시작 — 공고 {len(posts_input)}개, user_profile_id={user_profile_id}")
            final_state = await job_agent.ainvoke({
                "job_posts": posts_input,
                "user_profile_id": user_profile_id,
                "keywords_list": [],
                "stack_analysis": {},
                "gap_analysis": {},
                "report_md": "",
                "errors": [],
            })

            # 4. AnalysisResult 저장
            analysis = AnalysisResult(
                job_post_ids=job_post_ids,
                stack_analysis=final_state["stack_analysis"],
                gap_analysis=final_state["gap_analysis"],
                report_md=final_state["report_md"],
                errors=final_state["errors"],
            )
            session.add(analysis)
            await session.commit()
            await session.refresh(analysis)

            await engine.dispose()

            logger.info(f"[analyze] 완료 — analysis_id={analysis.id}")
            return {
                "analysis_id": analysis.id,
                "errors": final_state["errors"],
            }

    return asyncio.run(_run())