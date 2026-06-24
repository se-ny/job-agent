import json
import logging
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from app.core.config import settings
from app.agent.tools import extract_keywords, analyze_stack, analyze_gap
from app.agent.prompts import SYSTEM_PROMPT, REPORT_PROMPT

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0,
)


# ── 상태 정의 ──────────────────────────────────────────────
class AgentState(TypedDict):
    job_posts: list[dict]          # 입력: 크롤링된 공고 리스트
    user_profile_id: int           # 입력: 갭 분석에 사용할 프로필 ID
    keywords_list: list[dict]      # 추출된 키워드 모음
    stack_analysis: dict           # 스택 빈도 분석 결과
    gap_analysis: dict             # 갭 분석 결과
    report_md: str                 # 최종 마크다운 리포트
    errors: Annotated[list[str], operator.add]  # 누적 에러


# ── 노드 함수 ──────────────────────────────────────────────
def node_extract(state: AgentState) -> dict:
    """각 공고에서 키워드를 추출하는 노드"""
    logger.info(f"[extract] 공고 {len(state['job_posts'])}개 키워드 추출 시작")
    keywords_list = []
    errors = []

    for post in state["job_posts"]:
        job_text = f"{post.get('title', '')}\n{post.get('description', '')}"
        try:
            result = extract_keywords.invoke({"job_text": job_text})
            # 공고 ID 추적용으로 같이 저장
            result["job_post_id"] = post.get("id")
            keywords_list.append(result)
        except Exception as e:
            msg = f"키워드 추출 실패 (id={post.get('id')}): {e}"
            logger.error(msg)
            errors.append(msg)

    logger.info(f"[extract] 완료 — 성공 {len(keywords_list)}개, 실패 {len(errors)}개")
    return {"keywords_list": keywords_list, "errors": errors}


def node_analyze_stack(state: AgentState) -> dict:
    """키워드 리스트를 받아 스택 빈도를 분석하는 노드"""
    logger.info("[analyze_stack] 스택 분석 시작")
    try:
        result = analyze_stack.invoke({"keywords_list": state["keywords_list"]})
        logger.info("[analyze_stack] 완료")
        return {"stack_analysis": result}
    except Exception as e:
        msg = f"스택 분석 실패: {e}"
        logger.error(msg)
        return {"stack_analysis": {}, "errors": [msg]}


async def node_analyze_gap(state: AgentState) -> dict:
    """사용자 프로필과 스택 분석 결과로 갭을 분석하는 노드"""
    logger.info(f"[analyze_gap] user_profile_id={state['user_profile_id']} 갭 분석 시작")
    try:
        result = await analyze_gap.ainvoke({
            "stack_analysis": state["stack_analysis"],
            "user_profile_id": state["user_profile_id"],
        })
        logger.info("[analyze_gap] 완료")
        return {"gap_analysis": result}
    except Exception as e:
        msg = f"갭 분석 실패: {e}"
        logger.error(msg)
        return {"gap_analysis": {}, "errors": [msg]}


def node_report(state: AgentState) -> dict:
    """최종 마크다운 리포트를 생성하는 노드"""
    logger.info("[report] 리포트 생성 시작")
    try:
        prompt = REPORT_PROMPT.format(
            stack_analysis=json.dumps(state["stack_analysis"], ensure_ascii=False, indent=2),
            gap_analysis=json.dumps(state["gap_analysis"], ensure_ascii=False, indent=2),
            total_count=len(state["job_posts"]),
            user_name=state["gap_analysis"].get("user_name", "사용자"),
        )
        response = llm.invoke(prompt)
        logger.info("[report] 완료")
        return {"report_md": response.content}
    except Exception as e:
        msg = f"리포트 생성 실패: {e}"
        logger.error(msg)
        return {"report_md": "리포트 생성에 실패했습니다.", "errors": [msg]}


# ── 그래프 조립 ────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract", node_extract)
    graph.add_node("analyze_stack", node_analyze_stack)
    graph.add_node("analyze_gap", node_analyze_gap)
    graph.add_node("report", node_report)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "analyze_stack")
    graph.add_edge("analyze_stack", "analyze_gap")
    graph.add_edge("analyze_gap", "report")
    graph.add_edge("report", END)

    return graph.compile()


# 싱글턴으로 컴파일
job_agent = build_graph()