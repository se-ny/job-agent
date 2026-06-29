from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.bookmark import Bookmark
from app.models.job_post import JobPost

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


class BookmarkCreate(BaseModel):
    job_post_id: str
    user_profile_id: int


@router.post("/", status_code=201)
async def add_bookmark(req: BookmarkCreate):
    """북마크 추가"""
    async with AsyncSessionLocal() as session:
        # 중복 체크
        existing = await session.execute(
            select(Bookmark).where(
                Bookmark.job_post_id == req.job_post_id,
                Bookmark.user_profile_id == req.user_profile_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="이미 북마크된 공고입니다")

        bookmark = Bookmark(
            job_post_id=req.job_post_id,
            user_profile_id=req.user_profile_id,
        )
        session.add(bookmark)
        await session.commit()
        await session.refresh(bookmark)

    return {"bookmark_id": bookmark.id, "job_post_id": bookmark.job_post_id}


@router.get("/{user_profile_id}")
async def get_bookmarks(user_profile_id: int):
    """북마크 목록 조회"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Bookmark, JobPost)
            .join(JobPost, Bookmark.job_post_id == JobPost.id)
            .where(Bookmark.user_profile_id == user_profile_id)
            .order_by(Bookmark.created_at.desc())
        )
        rows = result.all()

    return [
        {
            "bookmark_id": b.id,
            "job_post_id": b.job_post_id,
            "title": p.title,
            "company": p.company,
            "source": p.source,
            "url": p.url,
            "required_skills": p.keywords.get("required_skills", []) if p.keywords else [],
            "preferred_skills": p.keywords.get("preferred_skills", []) if p.keywords else [],
            "created_at": b.created_at,
        }
        for b, p in rows
    ]


@router.delete("/{bookmark_id}", status_code=204)
async def delete_bookmark(bookmark_id: str):
    """북마크 삭제"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()

        if not bookmark:
            raise HTTPException(status_code=404, detail="북마크를 찾을 수 없습니다")

        await session.delete(bookmark)
        await session.commit()