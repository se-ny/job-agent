import json
import logging
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from app.core.config import settings
from app.agent.tools import extract_keywords_react, analyze_stack, analyze_gap
from app.agent.prompts import SYSTEM_PROMPT, REPORT_PROMPT

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0,
)


# ── 상태 정의 ──────────────────────────────────────────────
class AgentState(TypedDict):
    # [입력 및 기본 데이터]
    job_posts: list[dict]
    user_profile_id: int

    # 루프 제어용
    current_post_index: int

    # [중간 분석 데이터]
    keywords_list: list[dict]
    stack_analysis: dict
    gap_analysis: dict
    report_md: str

    # [에이전트 판단 기록 및 반성 지표]
    skipped_posts: Annotated[list[dict], operator.add]
    retry_count: int
    total_retry_count: int

    reflection_notes: list[str]
    is_report_approved: bool
    errors: Annotated[list[str], operator.add]


# ── 노드 함수 ──────────────────────────────────────────────
def node_extract(state: AgentState) -> dict:
    """공고를 하나씩 순회하며 품질 판단 후 키워드 추출 (ReAct)"""
    idx = state.get("current_post_index", 0)
    posts = state["job_posts"]

    if idx >= len(posts):
        return {}

    post = posts[idx]
    job_text = f"{post.get('title', '')}\n{post.get('description', '')}"

    logger.info(f"[extract] ({idx+1}/{len(posts)}) 공고 판단 중: {post.get('title', '')[:30]}")

    try:
        result = extract_keywords_react(job_text)
    except Exception as e:
        msg = f"키워드 추출 실패 (id={post.get('id')}): {e}"
        logger.error(msg)
        return {
            "current_post_index": idx + 1,
            "errors": [msg],
        }

    if result.get("skip"):
        logger.info(f"[extract] 스킵: {result.get('reason')}")
        return {
            "current_post_index": idx + 1,
            "skipped_posts": [{"id": post.get("id"), "reason": result.get("reason")}],
        }

    result["job_post_id"] = post.get("id")
    existing_keywords = state.get("keywords_list", [])
    return {
        "current_post_index": idx + 1,
        "keywords_list": existing_keywords + [result],
    }


def should_continue_extract(state: AgentState) -> str:
    """모든 공고를 처리했으면 다음 단계로, 아니면 계속 루프"""
    idx = state.get("current_post_index", 0)
    if idx >= len(state["job_posts"]):
        return "analyze_stack"
    return "extract"


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


async def node_analyze_gap(state: AgentState, config=None) -> dict:
    """사용자 프로필과 스택 분석 결과로 갭을 분석하는 노드"""
    logger.info(f"[analyze_gap] user_profile_id={state['user_profile_id']} 갭 분석 시작")
    session = config["configurable"].get("session") if config else None
    try:
        result = await analyze_gap.ainvoke({
            "stack_analysis": state["stack_analysis"],
            "user_profile_id": state["user_profile_id"],
            "session": session,
        })
        logger.info("[analyze_gap] 완료")
        return {"gap_analysis": result}
    except Exception as e:
        msg = f"갭 분석 실패: {e}"
        logger.error(msg)
        return {"gap_analysis": {}, "errors": [msg]}
    

def node_reflect_gap(state: AgentState) -> dict:
    """갭 분석 결과의 신뢰도를 검토 (Reflection)"""
    from app.agent.tools import reflect_on_gap_analysis

    logger.info("[reflect] 갭 분석 신뢰도 검토 중")
    try:
        result = reflect_on_gap_analysis.invoke({
            "gap_analysis": state["gap_analysis"],
            "stack_analysis": state["stack_analysis"],
        })
        is_reliable = result.get("is_reliable", True)
        reason = result.get("reason", "")

        logger.info(f"[reflect] 결과: {'신뢰함' if is_reliable else '재분석 필요'} — {reason}")

        notes = state.get("reflection_notes", [])
        return {
            "reflection_notes": notes + [reason],
            "is_report_approved": is_reliable,
        }
    except Exception as e:
        logger.error(f"[reflect] 실패: {e}")
        # 검토 실패 시 통과 처리 (무한루프 방지)
        return {"is_report_approved": True}


def should_retry_gap(state: AgentState) -> str:
    """신뢰도 검토 결과에 따라 재분석 또는 다음 단계로 분기"""
    is_approved = state.get("is_report_approved", True)
    total_retry = state.get("total_retry_count", 0)

    if not is_approved and total_retry < 2:
        logger.info(f"[reflect] 재분석 진행 (시도 {total_retry + 1}/2)")
        return "retry"

    if not is_approved:
        logger.info("[reflect] 최대 재시도 도달 — 현재 결과로 진행")

    return "proceed"


def node_increment_retry(state: AgentState) -> dict:
    """재시도 카운트 증가"""
    total_retry = state.get("total_retry_count", 0)
    return {"total_retry_count": total_retry + 1}



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
    graph.add_node("reflect_gap", node_reflect_gap)
    graph.add_node("increment_retry", node_increment_retry)
    graph.add_node("report", node_report)

    graph.set_entry_point("extract")

    graph.add_conditional_edges(
        "extract",
        should_continue_extract,
        {
            "extract": "extract",
            "analyze_stack": "analyze_stack",
        }
    )

    graph.add_edge("analyze_stack", "analyze_gap")
    graph.add_edge("analyze_gap", "reflect_gap")

    # ✅ 재시도 분기
    graph.add_conditional_edges(
        "reflect_gap",
        should_retry_gap,
        {
            "retry": "increment_retry",
            "proceed": "report",
        }
    )
    graph.add_edge("increment_retry", "analyze_gap")  # 재분석 루프

    graph.add_edge("report", END)

    return graph.compile()


job_agent = build_graph()