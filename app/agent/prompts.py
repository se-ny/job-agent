SYSTEM_PROMPT = """당신은 채용공고 분석 전문 AI 에이전트입니다.
주어진 채용공고 데이터를 분석하여 다음 작업을 수행합니다:

1. 기술 스택 및 키워드 추출
2. 여러 공고의 스택 빈도 분석  
3. 사용자 프로필과의 갭 분석

항상 도구(tool)를 사용하여 단계적으로 분석을 수행하세요.
분석 결과는 구체적인 수치와 함께 마크다운 형식으로 작성하세요."""


KEYWORD_EXTRACT_PROMPT = """다음 채용공고에서 기술 스택과 요구사항을 추출하세요.

채용공고:
{job_text}

추출 항목:
- required_skills: 필수 기술 스택 리스트
- preferred_skills: 우대 기술 스택 리스트  
- experience_years: 요구 경력 (숫자, 없으면 0)
- job_role: 직무 분류 (예: 백엔드, 프론트엔드, AI/ML 등)

반드시 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.
예시:
{{
  "required_skills": ["Python", "FastAPI"],
  "preferred_skills": ["Docker", "Redis"],
  "experience_years": 3,
  "job_role": "백엔드"
}}"""


STACK_ANALYZE_PROMPT = """다음은 여러 채용공고에서 추출한 키워드 데이터입니다.

키워드 데이터:
{keywords_json}

전체 공고 수: {total_count}개

각 스킬의 등장 빈도를 분석하여 아래 형식으로 응답하세요.
반드시 JSON 형식으로만 응답하세요.

{{
  "stack_frequency": {{
    "Python": 85.5,
    "FastAPI": 60.0
  }},
  "top_required": ["가장 많이 요구되는 스킬 top5"],
  "top_preferred": ["가장 많이 우대되는 스킬 top5"],
  "common_roles": {{"백엔드": 10, "AI/ML": 5}}
}}"""


GAP_ANALYZE_PROMPT = """채용공고 분석 결과와 사용자 프로필을 비교하여 갭을 분석하세요.

사용자 프로필:
- 이름: {user_name}
- 보유 스킬: {user_skills}
- 경력: {experience_months}개월
- 소개: {user_bio}

스택 분석 결과:
{stack_analysis}

아래 형식으로 응답하세요. 반드시 JSON 형식으로만 응답하세요.

{{
  "matched_skills": ["보유 중이며 요구되는 스킬"],
  "missing_required": ["없는 필수 스킬"],
  "missing_preferred": ["없는 우대 스킬"],
  "match_score": 75.0,
  "recommendations": ["학습 우선순위 추천 (구체적으로)"]
}}"""


REPORT_PROMPT = """다음 분석 데이터를 바탕으로 채용공고 분석 마크다운 리포트를 작성하세요.

스택 분석: {stack_analysis}
갭 분석: {gap_analysis}
분석 공고 수: {total_count}개
사용자: {user_name}

리포트 구조:
# 채용공고 분석 리포트

## 1. 분석 개요
## 2. 주요 요구 기술 스택 (빈도 포함)
## 3. 나의 현황 (매칭 스킬 / 부족 스킬)
## 4. 갭 분석 결과 (매칭 점수 포함)
## 5. 학습 로드맵 추천

실용적이고 구체적으로 작성하세요."""

GAP_REFLECTION_PROMPT = """다음은 채용공고 갭 분석 결과입니다. 이 결과가 충분히 신뢰할 만한지 검토하세요.

갭 분석 결과:
{gap_analysis}

스택 분석 원본 데이터:
{stack_analysis}

검토 기준:
- matched_skills와 missing_required가 모두 비어있으면 신뢰 불가
- match_score가 0인데 사용자가 일부 스킬을 보유하고 있다면 의심스러움
- recommendations가 비어있거나 너무 추상적이면 부족함

반드시 JSON 형식으로만 응답하세요.
{{
  "is_reliable": true,
  "reason": "판단 이유 (한 문장)"
}}"""