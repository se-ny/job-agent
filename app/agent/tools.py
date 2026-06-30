import json
import logging
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
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
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


@tool
def assess_post_quality(job_text: str) -> dict:
    """채용공고 텍스트가 분석 가능한 품질인지 판단합니다.
    너무 짧거나, 정보가 없거나, 광고성 텍스트면 스킵을 권장합니다."""
    prompt = f"""다음 채용공고 텍스트를 보고 키워드 추출이 가능한 품질인지 판단하세요.

공고 텍스트:
{job_text[:1000]}

판단 기준:
- 텍스트 길이가 너무 짧음 (50자 미만)
- 자격요건/기술스택 관련 정보가 전혀 없음
- 광고/홍보성 문구만 있고 실질적인 채용 정보가 없음

반드시 JSON 형식으로만 응답하세요.
{{
  "is_analyzable": true,
  "reason": "판단 이유 (한 문장)"
}}"""
    response = llm.invoke(prompt)
    try:
        return _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"assess_post_quality 파싱 실패: {e}")
        return {"is_analyzable": True, "reason": "판단 실패로 기본 진행"}


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


# ── ReAct: 공고 품질 판단 → 키워드 추출 ─────────────────────
extraction_tools = [assess_post_quality]
llm_with_tools = llm.bind_tools(extraction_tools)


def extract_keywords_react(job_text: str) -> dict:
    """ReAct 패턴: LLM이 먼저 품질을 판단(tool call)한 후, 적합하면 키워드를 추출"""
    messages = [
        SystemMessage(content="당신은 채용공고 분석 에이전트입니다. 먼저 공고 품질을 판단한 후 작업을 진행하세요."),
        HumanMessage(content=f"다음 공고를 분석해야 합니다. 먼저 품질을 판단해주세요.\n\n{job_text[:1000]}")
    ]

    ai_msg = llm_with_tools.invoke(messages)

    quality_result = {"is_analyzable": True, "reason": "판단 생략"}

    if ai_msg.tool_calls:
        for tool_call in ai_msg.tool_calls:
            if tool_call["name"] == "assess_post_quality":
                quality_result = assess_post_quality.invoke(tool_call["args"])

    if not quality_result.get("is_analyzable", True):
        return {
            "skip": True,
            "reason": quality_result.get("reason", "품질 미달"),
        }

    extraction = extract_keywords.invoke({"job_text": job_text})
    extraction["skip"] = False
    return extraction


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
async def analyze_gap(stack_analysis: dict, user_profile_id: int, session=None) -> dict:
    """DB에서 사용자 프로필을 조회하고 스택 분석 결과와 갭을 분석합니다."""
    if session is not None:
        # 외부에서 세션을 주입받은 경우 (Celery 태스크 컨텍스트)
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == user_profile_id)
        )
        profile = result.scalar_one_or_none()
    else:
        # 독립 실행 시 (테스트 등)
        async with AsyncSessionLocal() as local_session:
            result = await local_session.execute(
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
        result["user_name"] = profile.name
        return result
    except Exception as e:
        logger.error(f"analyze_gap 파싱 실패: {e}\n원문: {response.content}")
        return {"error": "갭 분석 파싱 실패", "user_name": profile.name}
    
@tool
def reflect_on_gap_analysis(gap_analysis: dict, stack_analysis: dict) -> dict:
    """갭 분석 결과의 신뢰도를 검토합니다."""
    from app.agent.prompts import GAP_REFLECTION_PROMPT

    prompt = GAP_REFLECTION_PROMPT.format(
        gap_analysis=json.dumps(gap_analysis, ensure_ascii=False, indent=2),
        stack_analysis=json.dumps(stack_analysis, ensure_ascii=False, indent=2),
    )
    response = llm.invoke(prompt)
    try:
        return _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"reflect_on_gap_analysis 파싱 실패: {e}")
        return {"is_reliable": True, "reason": "검토 실패로 기본 통과"}