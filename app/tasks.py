import asyncio
import logging
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.models.job_post import JobPost
from app.models.analysis import AnalysisResult
from app.crawler.base import get_crawler
from app.agent.graph import job_agent

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="crawl_jobs_task", max_retries=3)
def crawl_jobs_task(self, site: str, keyword: str, limit: int = 1):
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.core.config import settings

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        try:
            crawler = get_crawler(site)
            posts = await crawler.crawl(keyword=keyword, limit=limit)

            if not posts:
                raise ValueError(f"'{keyword}' 검색 결과가 없습니다")

            async with SessionLocal() as session:
                jobs = []
                for post in posts:
                    job = JobPost(
                        source=post.source,
                        title=post.title,
                        company=post.company,
                        raw_text=post.raw_text,
                        url=post.url,
                    )
                    jobs.append(job)

                session.add_all(jobs)
                await session.commit()

                saved_ids = []
                for job in jobs:
                    await session.refresh(job)
                    saved_ids.append(job.id)

            await engine.dispose()
            logger.info(f"[crawl] {site} '{keyword}' — {len(saved_ids)}개 저장")
            return {"saved_ids": saved_ids, "count": len(saved_ids)}

        except Exception as e:
            await engine.dispose()
            logger.error(f"[crawl] 실패: {e}")
            raise

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[crawl] 재시도 {self.request.retries + 1}/{self.max_retries}: {exc}")
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(bind=True, name="analyze_jobs_task", max_retries=2)
def analyze_jobs_task(self, job_post_ids: list[str], user_profile_id: int):
    """크롤링된 공고 ID 리스트 → Agent 분석 → DB 저장"""
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.core.config import settings

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with SessionLocal() as session:
                result = await session.execute(
                    select(JobPost).where(JobPost.id.in_(job_post_ids))
                )
                job_posts = result.scalars().all()

                if not job_posts:
                    raise ValueError("공고를 찾을 수 없습니다")

                posts_input = [
                    {
                        "id": p.id,
                        "title": p.title,
                        "description": p.raw_text,
                    }
                    for p in job_posts
                ]

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

                # 공고별 키워드 DB 저장
                keywords_list = final_state.get("keywords_list", [])
                for kw in keywords_list:
                    job_id = kw.get("job_post_id")
                    if job_id:
                        kw_result = await session.execute(
                            select(JobPost).where(JobPost.id == job_id)
                        )
                        job = kw_result.scalar_one_or_none()
                        if job:
                            job.keywords = {
                                "required_skills": kw.get("required_skills", []),
                                "preferred_skills": kw.get("preferred_skills", []),
                                "experience_years": kw.get("experience_years", 0),
                                "job_role": kw.get("job_role", ""),
                            }
                            session.add(job)

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

        except Exception as e:
            await engine.dispose()
            logger.error(f"[analyze] 실패: {e}")
            raise

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[analyze] 재시도 {self.request.retries + 1}/{self.max_retries}: {exc}")
        raise self.retry(exc=exc, countdown=10)