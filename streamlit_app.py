import time
import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Job Agent", page_icon="🤖", layout="wide")
st.title("🤖 Job Agent — 채용공고 분석")

# ── 사이드바: 프로필 설정 ───────────────────────────────────
with st.sidebar:
    st.header("👤 내 프로필")

    profiles_res = requests.get(f"{API_BASE}/profiles/")
    profiles = profiles_res.json() if profiles_res.ok else []

    if profiles:
        profile_options = {f"{p['name']} (id:{p['id']})": p["id"] for p in profiles}
        selected = st.selectbox("프로필 선택", list(profile_options.keys()))
        user_profile_id = profile_options[selected]

        selected_profile = next(p for p in profiles if p["id"] == user_profile_id)
        st.write("**보유 스킬:**", ", ".join(selected_profile["current_skills"]))
        st.write("**경력:**", f"{selected_profile['experience_months']}개월")
        if selected_profile["bio"]:
            st.write("**소개:**", selected_profile["bio"])
    else:
        st.warning("프로필이 없습니다. 아래에서 생성하세요.")
        user_profile_id = None

    st.divider()

    with st.expander("➕ 프로필 생성"):
        new_name = st.text_input("이름")
        new_skills = st.text_input("보유 스킬 (쉼표로 구분)", placeholder="Python, FastAPI, Docker")
        new_exp = st.number_input("경력 (개월)", min_value=0, value=0)
        new_bio = st.text_area("소개 (선택)")

        if st.button("프로필 생성"):
            if new_name and new_skills:
                skills_list = [s.strip() for s in new_skills.split(",")]
                res = requests.post(f"{API_BASE}/profiles/", json={
                    "name": new_name,
                    "current_skills": skills_list,
                    "experience_months": new_exp,
                    "bio": new_bio or None,
                })
                if res.ok:
                    st.success(f"프로필 생성 완료! (id: {res.json()['id']})")
                    st.rerun()
                else:
                    st.error("프로필 생성 실패")
            else:
                st.warning("이름과 스킬을 입력하세요")

# ── 탭 구성 ────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🔍 크롤링", "📋 공고 목록", "🏆 AI 추천", "📊 갭 분석"])

# ── 탭1: 크롤링 ────────────────────────────────────────────
with tab1:
    st.header("🔍 채용공고 크롤링")

    source = st.selectbox("사이트", ["saramin", "jobkorea"])
    keyword = st.text_input("검색 키워드", placeholder="예: FastAPI, AI 에이전트")
    limit = st.slider("크롤링 개수", min_value=1, max_value=10, value=3)

    if st.button("🚀 크롤링 시작", disabled=not keyword):
        with st.spinner("크롤링 중..."):
            res = requests.post(f"{API_BASE}/jobs/crawl", json={
                "source": source,
                "keyword": keyword,
                "limit": limit,
            })
            if not res.ok:
                st.error("크롤링 요청 실패")
                st.stop()

            task_id = res.json()["task_id"]
            st.info(f"task_id: `{task_id}`")

            for _ in range(60):
                time.sleep(3)
                result_res = requests.get(f"{API_BASE}/jobs/crawl/{task_id}")
                result = result_res.json()

                if result["status"] == "success":
                    saved_ids = result["result"]["saved_ids"]
                    st.success(f"✅ {len(saved_ids)}개 공고 저장 완료!")
                    st.session_state["saved_ids"] = saved_ids
                    break
                elif result["status"] == "failure":
                    st.error(f"크롤링 실패: {result['error']}")
                    st.stop()
            else:
                st.warning("타임아웃")

# ── 탭2: 공고 목록 ─────────────────────────────────────────
with tab2:
    st.header("📋 크롤링된 공고 목록")

    if st.button("🔄 목록 불러오기"):
        res = requests.get(f"{API_BASE}/jobs/posts?limit=20")
        if res.ok:
            st.session_state["posts"] = res.json()
        else:
            st.error("공고 목록 조회 실패")

    posts = st.session_state.get("posts", [])

    if posts:
        st.write(f"**총 {len(posts)}개 공고**")
        for post in posts:
            with st.expander(f"🏢 {post['company']} — {post['title']}"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    # 필수/우대 스킬
                    if post["required_skills"]:
                        st.write("**🔴 필수 스킬**")
                        st.write(" · ".join(post["required_skills"]))
                    if post["preferred_skills"]:
                        st.write("**🔵 우대 스킬**")
                        st.write(" · ".join(post["preferred_skills"]))
                    if not post["required_skills"] and not post["preferred_skills"]:
                        st.caption("갭 분석 후 스킬 정보가 표시됩니다")
                with col2:
                    st.write(f"**플랫폼:** {post['source']}")
                    if post["job_role"]:
                        st.write(f"**직무:** {post['job_role']}")
                    if post["experience_years"]:
                        st.write(f"**경력:** {post['experience_years']}년")
                    if post["url"] and post["url"] != "manual":
                        st.link_button("🔗 원문 보기", post["url"])
    else:
        st.info("'목록 불러오기' 버튼을 눌러주세요")

# ── 탭3: AI 추천 ───────────────────────────────────────────
with tab3:
    st.header("🏆 AI Top3 공고 추천")

    saved_ids = st.session_state.get("saved_ids", [])

    if not saved_ids:
        st.info("먼저 크롤링 탭에서 공고를 수집하세요")
    elif not user_profile_id:
        st.warning("사이드바에서 프로필을 선택하세요")
    else:
        st.write(f"**분석 대상:** {len(saved_ids)}개 공고")

        if st.button("🤖 AI 추천 받기"):
            with st.spinner("AI가 공고를 분석 중..."):
                res = requests.post(f"{API_BASE}/jobs/recommend", json={
                    "job_post_ids": saved_ids,
                    "user_profile_id": user_profile_id,
                })

                if res.ok:
                    data = res.json()
                    recommendations = data.get("recommendations", [])

                    medals = ["🥇", "🥈", "🥉"]
                    for rec in recommendations:
                        rank = rec["rank"] - 1
                        medal = medals[rank] if rank < 3 else "🏅"

                        with st.container(border=True):
                            st.subheader(f"{medal} {rec['rank']}위 — {rec['title']}")
                            st.write(f"**회사:** {rec['company']}")

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("매칭 점수", f"{rec['match_score']}%")
                            with col2:
                                st.write("**필수 스킬**")
                                for s in rec.get("required_skills", []):
                                    st.badge(s, color="red")
                            with col3:
                                st.write("**우대 스킬**")
                                for s in rec.get("preferred_skills", []):
                                    st.badge(s, color="blue")

                            st.write("**💡 추천 이유**")
                            st.info(rec["reason"])
                else:
                    st.error(f"추천 실패: {res.text}")

# ── 탭4: 갭 분석 ───────────────────────────────────────────
with tab4:
    st.header("📊 갭 분석 리포트")

    saved_ids = st.session_state.get("saved_ids", [])

    if saved_ids:
        st.write(f"**분석 대상:** {len(saved_ids)}개 공고")
    else:
        st.info("먼저 크롤링 탭에서 공고를 수집하세요")

    if st.button("🔬 분석 시작", disabled=not saved_ids or not user_profile_id):
        with st.spinner("Agent 분석 중... (1~2분 소요)"):
            res = requests.post(f"{API_BASE}/jobs/analyze", json={
                "job_post_ids": saved_ids,
                "user_profile_id": user_profile_id,
            })
            if not res.ok:
                st.error("분석 요청 실패")
                st.stop()

            task_id = res.json()["task_id"]

            for _ in range(60):
                time.sleep(5)
                result_res = requests.get(f"{API_BASE}/jobs/analyze/{task_id}")
                result = result_res.json()

                if result["status"] == "success":
                    analysis_id = result["result"]["analysis_id"]
                    st.success("✅ 분석 완료!")
                    st.session_state["analysis_id"] = analysis_id
                    break
                elif result["status"] == "failure":
                    st.error(f"분석 실패: {result['error']}")
                    st.stop()
            else:
                st.warning("타임아웃")

    analysis_id = st.session_state.get("analysis_id")
    if analysis_id:
        report_res = requests.get(f"{API_BASE}/jobs/report/{analysis_id}/markdown")
        if report_res.ok:
            st.markdown(report_res.text)
            st.download_button(
                label="📥 리포트 다운로드 (.md)",
                data=report_res.text,
                file_name=f"report_{analysis_id[:8]}.md",
                mime="text/markdown",
            )