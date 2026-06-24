import json
import logging
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from sqlalchemy import select
from app.core.config import settings
from app.models.user_profile import UserProfile
from app.core.database import AsyncSessionLocal
from app.agent.prompts import (
    KEYWORD_EXTRACT_PROMPT,
    STACK_ANALYZE_PROMPT,
    GAP_ANALYZE_PROMPT,
)

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0,
)


def _parse_llm_json(response_text: str) -> dict:
    """LLM 응답에서 JSON 파싱 (코드블록 제거 포함)"""
    text = response_text.strip()
    # ```json ... ``` 또는 ``` ... ``` 제거
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


@tool
def extract_keywords(job_text: str) -> dict:
    """채용공고 텍스트에서 기술 스택, 필수/우대 조건, 경력, 직무를 추출합니다."""
    prompt = KEYWORD_EXTRACT_PROMPT.format(job_text=job_text)
    response = llm.invoke(prompt)
    try:
        return _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"extract_keywords 파싱 실패: {e}\n원문: {response.content}")
        return {
            "required_skills": [],
            "preferred_skills": [],
            "experience_years": 0,
            "job_role": "기타",
        }


@tool
def analyze_stack(keywords_list: list[dict]) -> dict:
    """여러 공고에서 추출한 키워드를 묶어 스택 빈도를 분석합니다."""
    total_count = len(keywords_list)
    if total_count == 0:
        return {"stack_frequency": {}, "top_required": [], "top_preferred": [], "common_roles": {}}

    prompt = STACK_ANALYZE_PROMPT.format(
        keywords_json=json.dumps(keywords_list, ensure_ascii=False, indent=2),
        total_count=total_count,
    )
    response = llm.invoke(prompt)
    try:
        return _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"analyze_stack 파싱 실패: {e}\n원문: {response.content}")
        return {"stack_frequency": {}, "top_required": [], "top_preferred": [], "common_roles": {}}


@tool
async def analyze_gap(stack_analysis: dict, user_profile_id: int) -> dict:
    """DB에서 사용자 프로필을 조회하고 스택 분석 결과와 갭을 분석합니다."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == user_profile_id)
        )
        profile = result.scalar_one_or_none()

    if not profile:
        return {"error": f"user_profile_id={user_profile_id} 프로필을 찾을 수 없습니다."}

    prompt = GAP_ANALYZE_PROMPT.format(
        user_name=profile.name,
        user_skills=", ".join(profile.current_skills),
        experience_months=profile.experience_months,
        user_bio=profile.bio or "없음",
        stack_analysis=json.dumps(stack_analysis, ensure_ascii=False, indent=2),
    )
    response = llm.invoke(prompt)
    try:
        result = _parse_llm_json(response.content)
        result["user_name"] = profile.name  # 리포트 생성에서 재사용
        return result
    except Exception as e:
        logger.error(f"analyze_gap 파싱 실패: {e}\n원문: {response.content}")
        return {"error": "갭 분석 파싱 실패", "user_name": profile.name}