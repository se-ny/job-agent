from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    name: str
    current_skills: list[str]
    experience_months: int = 0
    bio: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    current_skills: list[str] | None = None
    experience_months: int | None = None
    bio: str | None = None


# ── CRUD ───────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_profile(req: ProfileCreate):
    """프로필 생성"""
    async with AsyncSessionLocal() as session:
        profile = UserProfile(
            name=req.name,
            current_skills=req.current_skills,
            experience_months=req.experience_months,
            bio=req.bio,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

    return {
        "id": profile.id,
        "name": profile.name,
        "current_skills": profile.current_skills,
        "experience_months": profile.experience_months,
        "bio": profile.bio,
        "created_at": profile.created_at,
    }


@router.get("/")
async def list_profiles():
    """프로필 목록 조회"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserProfile))
        profiles = result.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "current_skills": p.current_skills,
            "experience_months": p.experience_months,
            "bio": p.bio,
            "created_at": p.created_at,
        }
        for p in profiles
    ]


@router.get("/{profile_id}")
async def get_profile(profile_id: int):
    """프로필 단건 조회"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")

    return {
        "id": profile.id,
        "name": profile.name,
        "current_skills": profile.current_skills,
        "experience_months": profile.experience_months,
        "bio": profile.bio,
        "created_at": profile.created_at,
    }


@router.patch("/{profile_id}")
async def update_profile(profile_id: int, req: ProfileUpdate):
    """프로필 수정"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")

        if req.name is not None:
            profile.name = req.name
        if req.current_skills is not None:
            profile.current_skills = req.current_skills
        if req.experience_months is not None:
            profile.experience_months = req.experience_months
        if req.bio is not None:
            profile.bio = req.bio

        await session.commit()
        await session.refresh(profile)

    return {
        "id": profile.id,
        "name": profile.name,
        "current_skills": profile.current_skills,
        "experience_months": profile.experience_months,
        "bio": profile.bio,
        "created_at": profile.created_at,
    }


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: int):
    """프로필 삭제"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")

        await session.delete(profile)
        await session.commit()