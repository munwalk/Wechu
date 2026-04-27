# chat_logic.py (하이브리드 최종판 - 출처 보강)
# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import requests
from typing import List, Dict, Any, Tuple, Callable
import re

# ===== 설정 (기존과 동일) =====
REASONING_ENDPOINT = "https://clovastudio.stream.ntruss.com/v1/api-tools/rag-reasoning"
RERANKER_URL = "https://clovastudio.stream.ntruss.com/v1/api-tools/reranker"

API_KEY = os.getenv("NCLOUD_API_KEY", "")
if not API_KEY:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")

# ===== 분기 로직 키워드 =====
# ✅ 1. 주제 이탈 방지를 위한 포괄적인 주제 키워드 목록
TOPIC_KEYWORDS = {
    # 학사 관련
    "재수강", "휴학", "복학", "전과", "복수전공", "부전공", "졸업", "장학", "수강신청", 
    "성적", "규정", "학사", "학점", "이수", "클래스", "klas", "수강포기", "등록금", 
    "논문", "교양", "계절학기", "증명서", "강의", "과목", "수업",
    "장학금", "국가장학금", "교내장학금", "장학 기준", "장학 신청", "자퇴" # ✅ 추가!
    
    # 진로/취업 관련
    "진로", "취업", "커리어", "로드맵", "자격증", "포트폴리오", "프로젝트", "인턴", 
    "대외활동", "공모전", "대학원", "스터디", "개발자", "디자이너", "기획자",
    "개발", "디자인", "프론트엔드", "백엔드", "React", "Vue", "Figma", "공부","자퇴"
    ,"자퇴하고 싶어"
    # 학교 관련
    "광운대", "광운대학교", "학교", "학과", "전공", "교수님"
}

# 2. RAG 모드 결정을 위한 정책 키워드 목록
POLICY_KEYWORDS = {
    "재수강", "휴학", "복학", "전과", "복수전공", "부전공", "졸업", "장학", "수강신청", 
    "성적정정", "규정", "학사", "조건", "학점", "이수", "클래스", "klas", "수강포기", 
    "수강철회", "등록금", "장학금", "성적", "이의신청", "논문", "자격", "요건", "필수", 
    "교양", "계절학기", "증명서", "발급", "제출","전시회","졸업 전시회","참빛","설계학기","참빛 설계학기","자퇴"
    
    # ✅ 추가!
    "선수과목", "선수 과목", "수강", "강의", "과목",  # UX/UI 질문용
    "국가장학금", "장학 기준",  # 장학금 질문용
    "졸업요건", "졸업 요건", "이수 조건", "이수조건",  # 졸업 질문용
    "졸업논문", "졸업 논문", "논문 필수"  # 논문 질문용
}

QUESTION_CUES = {
    "뭐야", "뭔가요", "가능", "규정", "조건", "알려줘", "어떻게", "무엇", "얼마", 
    "몇", "최대", "제한", "언제", "기간", "방법", "궁금", "알아", "되나요", "뭔지", 
    "뭐가", "어떤"
}

SOLUTION_CUES = {"어떻게", "방법", "해결", "로드맵", "추천", "해줄래", "알려줘", "정리해줘"}

def _norm(text: str) -> str: return (text or "").lower()

# ===== 분기 함수 (기존과 동일) =====
def is_on_topic(text: str) -> bool:
    """사용자 질문이 챗봇의 주제(학사/진로)와 관련 있는지 확인합니다."""
    t = _norm(text)
    
    # ✅ 1. 먼저 학사/진로 키워드 체크
    is_related = any(keyword.lower() in t for keyword in TOPIC_KEYWORDS)
    
    if is_related:
        # 관련 있으면 바로 True 반환
        return True
    
    # ✅ 2. 관련 없을 때만 off_topic 체크
    off_topic_keywords = [
        # 음식 관련
        '김치', '찌개', '요리', '레시피', '맛집', '먹방', '음식', '카페', '식당',
        '메뉴', '치킨', '피자', '햄버거', '라면', '국', '밥', '반찬',
        
        # 날씨/일상
        '날씨', '비', '눈', '기온', '춥', '덥',
        
        # 엔터테인먼트
        '게임', '영화', '드라마', '유튜브', '넷플릭스', '아이돌', '노래',
        
        # 기타
        '축구', '야구', '운동', '여행', '쇼핑'
    ]
    
    if any(keyword in t for keyword in off_topic_keywords):
        print(f"[주제 이탈] 관련 없는 키워드 감지")
        return False
    
    # ✅ 3. 둘 다 아니면 False
    return False

def looks_like_policy_q(text: str) -> bool:
    t = _norm(text)
    hit_kw = any(k.lower() in t for k in POLICY_KEYWORDS)
    return hit_kw

def wants_solution(text: str) -> bool:
    t = _norm(text)
    return any(c in t for c in SOLUTION_CUES)

def is_policy_question(text: str) -> bool:
    """정책/규정 질문 여부 판단 (더 엄격하게)"""
    
    text_normalized = text.replace('.', ' ').replace('\n', ' ')
    
    # ✅ 특정 키워드는 무조건 정책 질문
    strong_policy_keywords = [
        # 수강 관련
        '재수강', '수강신청', '수강 신청', '정정', '폐강', 
        '수강포기', '수강 포기', '철회',
        '선수과목', '선수 과목', "자퇴" # ✅ 추가!
        
        # 졸업 관련
        '졸업요건', '졸업 요건', '이수학점', '이수 학점', '이수 조건', '이수조건',  # ✅ 수정!
        '졸업논문', '졸업 논문', '논문 필수', '논문',  # ✅ 수정!
        '졸업시험', '졸업 시험',
        '졸업인정', '졸업 인정',"자퇴"
        
        # 성적 관련
        '학점', '성적', '평점', 'GPA',
        
        # 등록/장학 관련
        '등록금', '등록', '납부', '환불',
        '국가장학금', '장학 기준', '장학금',  # ✅ 추가!
        
        # 학사 일정
        '개강', '종강', '휴학', '복학', '자퇴',
        
        # 기타
        '학칙', '규정', '필수', '선택', '전공', '교양'
    ]
    for keyword in strong_policy_keywords:
        if keyword in text_normalized:
            print(f"[정책 질문 확정] '{keyword}' 키워드 감지")
            return True
    
    # 1차 필터: 감정 표현 (강화!)
    emotion_phrases = [
        '힘들', '우울', '걱정', 'ㅠㅠ', 'ㅜㅜ', 'ㅡㅡ', '시발', 'ㅠ', 'ㅜ',
        '자퇴하고 싶어', '그만두고 싶어', '포기하고 싶어',  # ✅ 추가!
        '안 좋아서', '나빠져서', '떨어지고'  # ✅ 추가!
    ]
    if any(phrase in text_normalized for phrase in emotion_phrases):
        print(f"[1차 필터] 감정/고민 표현 감지 → 일반 상담")
        return False
    
    # 2차 필터: 건강 관련 (강화!)
    if re.search(r'(건강|몸|아프)', text_normalized):
        if not re.search(r'(규정|제도|신청|방법)', text_normalized):
            print(f"[2차 필터] 건강 관련 고민 → 일반 상담")
            return False
    
    # 3차 필터: 성적 고민 (진행형) - 강화!
    if re.search(r'(학점|성적).*?(떨어|나빠|안\s*좋|망)', text_normalized):
        print(f"[3차 필터] 성적 고민 표현 → 일반 상담")
        return False
    
    # 4차 필터: 진로 고민
    general_patterns = [
        r'(고민|선택|결정|추천|조언).*?(대학원|취업)',
        r'(어떤게|뭐가|어느게|어떤걸)\s*(나을까|좋을까|맞을까|선택)',  # ✅ 수정!
        r'(하는 게|하는게)\s*(나을까|좋을까)',
        r'vs', r'or', r'아니면', r'이랑',  # ✅ 추가!
        r'(진로|취업|대학원).*?(모르|고민|선택)',
        r'(휴학|복학).*?할까',
    ]
    
    for pattern in general_patterns:
        if re.search(pattern, text_normalized, re.IGNORECASE):
            print(f"[일반 상담 패턴 감지]: {pattern}")
            return False
    
    # 정책 질문 패턴
    policy_patterns = [
        r'(졸업|이수).*?(요건|학점|조건|규정)',
        r'(전공|교양|학점).*?(몇|얼마)',
        r'(휴학|복학|전과).*?(신청|방법|절차)',
        r'최대|최소.*?(학점|과목)',
        r'평점.*?만점',
        r'조기\s*졸업',
        r'(선수|추천).*?과목',  # ✅ 추가!
        r'장학.*?기준',  # ✅ 추가!
    ]
    
    for pattern in policy_patterns:
        if re.search(pattern, text_normalized, re.IGNORECASE):
            print(f"[정책 질문 패턴 감지]: {pattern}")
            return True
    
    # 정책 키워드 (2개 이상)
    policy_keywords = ['규정', '제도', '신청방법', '졸업', '이수', '학점']
    keyword_count = sum(1 for kw in policy_keywords if kw in text_normalized)
    if keyword_count >= 2:
        print(f"[정책 키워드 {keyword_count}개 감지]")
        return True
    
    print("[최종 판단] 일반 상담")
    return False


# ===== 시스템 프롬프트 (기존과 동일) =====
SYSTEM_DATADRIVEN = """
너는 광운대 학생을 돕는 다정한 코치다.

스타일:
- 자연스러운 문단으로 작성 (라벨/머릿말 없이)
- 각 문단 끝에 이모지 1개씩 (총 3~4개)
- 친근한 말투: "~이에요", "~할 수 있어요"
- 5~8줄 내외
- 답변은 반드시 한국어로

근거 사용:
- 학사/정책/수치는 제공된 search_result에서만 인용
- **문서에 정보가 부족하면 솔직히 인정하고, 대안 제시**
  예: "검색된 자료에 구체적인 정보가 없네요. 😔 학과 사무실에 문의해보시는 걸 추천드려요."
- 절대로 추측하거나 지어내지 않음
- 출처는 시스템이 자동 추가 (절대 직접 표기 금지)

답변 구조:
1. 공감/인사 1문장
2. 핵심 정보 제공 (또는 정보 부족 안내)
3. 추가 조언 또는 대안
4. 마지막 질문 1개
""".strip()

SYSTEM_GENERAL = """
너는 광운대 학생을 돕는 다정한 진로 코치다.

스타일:
- 자연스러운 문단으로 작성 (라벨/머릿말 없이)
- 각 문단 끝에 이모지 1개씩 배치 (총 3~4개)
- 친근한 말투: "~이에요", "~할 수 있어요", "~인가요?"
- 첫 턴: 공감 1~2문장 + 상황 파악 질문 2~3개
- 5~8줄 내외
- **절대로 출처를 표기하지 않습니다.**

조언 제공:
- 진로, 학습 방법, 개발자 커리어, 정서적 고민에 대한 실용적인 조언
- 구체적이지만 공감을 우선

**답변 예시:**

사용자: "우울해서 공부가 잘 안 돼"
✅ 좋은 답변:
"우울하면 집중하기 정말 힘들죠. 😔

우선 자신을 너무 몰아세우지 마세요. 작은 목표부터 시작해보는 건 어떨까요? 예를 들어 하루에 30분만 공부하거나, 좋아하는 과목 한 가지만 집중해보는 거예요. 💪

요즘 특별히 힘든 일이 있나요? 혹시 학생상담센터나 보건실에 상담 받아본 적 있으세요? 🌱

스트레스 풀 때 주로 뭐 하시나요? 🤔"

사용자: "대학원 vs 취업 고민돼"
✅ 좋은 답변:
"졸업 앞두고 진로 고민 많으시겠어요. 🎓

대학원은 전문성을 키우고 연구 경력을 쌓을 수 있지만, 시간과 학비가 필요해요. 취업은 바로 실무 경험과 소득을 얻을 수 있죠. 💼

혹시 관심 있는 분야가 연구 중심인가요, 아니면 실무 중심인가요? 📚

주변에 조언 구할 만한 교수님이나 선배가 있으세요? 🤔"

**필수 규칙:**
- 각 문단마다 이모지 1개 (총 3~4개)
- 5~8줄 분량
- 공감 → 조언 → 질문 순서
- 출처 절대 금지
""".strip()


# ===== API/Reranker 함수 (기존과 동일) =====
def make_headers(raw_key: str) -> Dict[str, str]:
    if not raw_key: raise RuntimeError("API key is empty.")
    return { "Authorization": f"Bearer {raw_key}", "Content-Type": "application/json", "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()) }

def call_api(url: str, payload: dict, timeout: int = 30) -> dict:
    headers = make_headers(API_KEY)
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        raise TimeoutError(f"API call to {url} timed out after {timeout} seconds.")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"API call to {url} failed: {e.response.status_code} {e.response.text[:300]}")

def reranker_function(query: str, documents: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    valid_docs = [{"id": str(d.get("id")), "doc": (d.get("content") or "").strip()} for d in documents if (d.get("content") or "").strip()]
    if not valid_docs: return [], []
    payload = {"query": query, "documents": valid_docs, "maxTokens": 4000}
    try:
        data = call_api(RERANKER_URL, payload)
        result = data.get("result", {})
        cited_docs = result.get("citedDocuments") or []
        suggested_queries = result.get("suggestedQueries") or []
        return cited_docs, list(suggested_queries)
    except Exception as e:
        print(f"[리랭커 오류] {e}. 원본 문서 상위 5개로 대체합니다.")
        # content 대신 doc 필드를 사용하는 문서 형식으로 변환하여 반환
        fallback_docs = [{"id": d["id"], "doc": d.get("content", "")} for d in documents[:5]]
        return fallback_docs, []


# ===== 일반 생성형 LLM 함수 =====
def call_general_llm(messages: List[Dict[str, Any]]) -> str:
    """일반 상담 답변 (문서 검색 없음)"""
    print("[일반 대화 모드] LLM 답변 생성")
    
    messages_with_system = [{"role": "system", "content": SYSTEM_GENERAL}] + messages
    
    payload = {
        "messages": messages_with_system, 
        "maxTokens": 1000, 
        "temperature": 0.7, 
        "topP": 0.8, 
        "topK": 0, 
        "repeatPenalty": 5.0
    }
    
    response = call_api(REASONING_ENDPOINT, payload)
    content = response.get("result", {}).get("message", {}).get("content", "").strip()
    
    # ✅ 강화된 안전장치: 일반 모드에서는 모든 출처 제거
    if content:
        content = re.sub(r'\(출처:[^)]*\)', '', content)
        content = re.sub(r'\[출처:[^\]]*\]', '', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()
    
    return content or "죄송합니다, 답변을 생성할 수 없습니다."

# ===== RAG 통합 함수 (출처 로직 대폭 개선) =====
def rag_with_reranker(user_query: str, history: List[Dict[str, Any]], search_func: Callable) -> str:
    print("[RAG 모드] 1. 유사도 기반 문서 검색")
    raw_docs = search_func(user_query, 15, True)
    if not raw_docs: 
        return "관련 정책/규정 정보를 찾지 못했습니다."
    
    print("[RAG 모드] 2. 리랭커로 문서 재정렬")
    docs_for_reranker = [{"id": d.get('id'), "content": d.get('content')} for d in raw_docs]
    reranked_docs_content, _ = reranker_function(user_query, docs_for_reranker)
    
    # ✅ 핵심 수정 1: 3개만 선택하고 원본 매칭
    top3_original = []
    for d_reranked in reranked_docs_content[:3]:  # ← 3개만!
        doc_id = d_reranked.get('id', '-')
        original = next((d for d in raw_docs if str(d.get('id')) == str(doc_id)), None)
        if original:
            top3_original.append(original)
    
    if not top3_original:
        top3_original = raw_docs[:3]
    
    print(f"[RAG 모드] 3. 상위 3개 문서: {[d.get('id') for d in top3_original]}")
    
    # LLM 입력 구성
    docs_for_llm = []
    for d in top3_original:
        docs_for_llm.append(
            f"[문서 ID: {d.get('id')}]\n"
            f"질문: {d.get('content', '')}\n"
            f"답변: {d.get('answer', '')}"
        )
    
    docs_text = "\n\n".join(docs_for_llm)
    
    # ✅ 개선된 프롬프트
    system_prompt = f"""{SYSTEM_DATADRIVEN}

    # 검색된 학사 정보
    {docs_text}

    **답변 작성 규칙 (엄격히 준수!):**

    1. **필수 형식:**
    재수강 규정 알려드릴게요! 📚
    
    재수강은 **C+ 이하** 과목만 가능하고, **최대 2회**까지 할 수 있어요. ✏️
    
    혹시 재수강 고려 중인 과목이 있으세요? 🤔

    2. **볼드 필수:**
    - 성적 등급: **C+**, **A0**, **F**
    - 숫자: **2회**, **8과목**, **18학점**
    - 중요한 조건: **선수과목**, **필수**, **제한**

    3. **이모지 필수:**
    - 각 문단 끝에 1개씩 (총 3~4개)
    - 첫 문단: 📚
    - 중간 문단: ✏️ 또는 📞
    - 마지막 질문: 🤔

    4. **답변 길이:**
    - 3~5개 문단 (5~8줄)
    - 너무 짧거나 길지 않게

    5. **절대 금지:**
    - 출처 표기 금지 (시스템이 자동 추가)
    - 이모지 남발 금지 (문단당 1개만)

    **답변 예시:**

    ✅ 정보가 있을 때:
    "재수강 규정 알려드릴게요! 📚

    재수강은 **C+ 이하** 과목만 가능하고, **최대 2회**까지 할 수 있어요. 성적은 **A0**로 제한되고요. ✏️

    혹시 재수강 고려 중인 과목이 있으세요? 🤔"

    ✅ 정보가 부족할 때:
    "검색된 자료에 UX/UI디자인 강의의 선수과목에 대한 구체적인 정보가 없네요. 😔

    일반적으로 선수과목은 강의계획서나 포털의 수강신청 페이지에서 확인할 수 있어요. 정보융합학부 학과 사무실에 문의하시면 정확한 답변을 받으실 수 있을 거예요. 📞

    혹시 해당 강의를 언제 수강하실 계획이세요? 🤔"
    """
    
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_query}]
    payload = {"messages": messages, "maxTokens": 800, "temperature": 0.5, "topP": 0.8, "repeatPenalty": 5.0}
    
    print("[RAG 모드] 4. LLM 답변 생성")
    response = call_api(REASONING_ENDPOINT, payload)
    content = response.get("result", {}).get("message", {}).get("content", "").strip()
    
    # =========================================================================
    # ✅ 출처 처리 로직 (완벽판)
    # =========================================================================
    if content and top3_original:
        # 1. LLM이 만든 출처 제거
        content = re.sub(r'\(출처:[^)]*\)', '', content).strip()
        
        # 2. 볼드 강제 추가
        if '**' not in content:
            print("[경고] 볼드 없음! 자동 추가")
            content = re.sub(r'\b(C\+|A0|A\+|F|NP|GPA)\b', r'**\1**', content)
            content = re.sub(r'([0-9]+)(회|과목|학점)', r'**\1\2**', content)
        
        # 3. 이모지 조절
        emoji_count = len(re.findall(r'[📚✏️💯🤔😊💪🎓📖💬]', content))
        if emoji_count < 2:
            paragraphs = content.split('\n\n')
            if len(paragraphs) >= 1: paragraphs[0] += ' 📚'
            if len(paragraphs) >= 2: paragraphs[1] += ' ✏️'
            if len(paragraphs) >= 3: paragraphs[-1] += ' 🤔'
            content = '\n\n'.join(paragraphs)
        elif emoji_count > 4:
            emojis = re.findall(r'[📚✏️💯🤔😊💪🎓📖💬]', content)
            for emoji in emojis[3:]:
                content = content.replace(emoji, '', 1)
        
        # 4. 모든 출처를 한 곳에 모음
        all_sources_raw = []

        for doc in top3_original:
            # source 컬럼
            source_col = doc.get('source') or doc.get('source_name')
            if source_col:
                all_sources_raw.append(source_col.strip())
            
            # answer에서 추출
            answer = doc.get('answer', '')
            source_matches = re.findall(r'\(출처:\s*([^)]+)\)', answer)
            for match in source_matches:
                clean = match.strip()
                if clean and not re.match(r'^[––-]+$', clean):
                    all_sources_raw.append(clean)

        print(f"[디버깅] 원본 출처 모음: {all_sources_raw}")

        # 5. 각 출처를 개별로 분리 (쉼표, 줄바꿈, 연속 공백으로 분리)
        all_sources_split = []
        for source in all_sources_raw:
            # 쉼표나 줄바꿈으로 분리
            parts = re.split(r'[,\n]+', source)
            for part in parts:
                clean = part.strip()
                if clean and len(clean) > 3:
                    all_sources_split.append(clean)

        print(f"[디버깅] 분리된 출처: {all_sources_split}")

        # 6. 중복 제거 (정규화 후 비교)
        seen_normalized = set()
        unique_sources = []

        for src in all_sources_split:
            # 정규화: 숫자, 공백, 특수문자 제거 후 소문자로
            normalized = re.sub(r'[\d\s\-··]+', '', src.lower())
            
            if normalized and normalized not in seen_normalized:
                seen_normalized.add(normalized)
                unique_sources.append(src)

        # 7. 최대 3개
        unique_sources = unique_sources[:3]

        print(f"[디버깅] ✅ 최종 출처 ({len(unique_sources)}개): {unique_sources}")

        # 8. 출처 표기 (출처 없으면 아예 표기 안 함)
        if unique_sources:
            if len(unique_sources) == 1:
                content += f"\n\n(출처: {unique_sources[0]})"
            else:
                sources_text = " | ".join(unique_sources)
                content += f"\n\n(출처: {sources_text})"
            
    print(f"\n[최종 답변 길이: {len(content)}]\n")
    return content

# ===== 메인 분기 함수 (기존과 동일) =====
def chat_turn(user_text: str, history: List[Dict[str, Any]], state: Dict[str, Any], search_func: Callable) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:

    print(f"\n[사용자 입력] {user_text}")
    
    is_policy = is_policy_question(user_text)
    print(f"[분기 판단] 정책/규정 질문 여부: {is_policy}")

    # STEP 1: 주제 이탈 방지
    if not is_on_topic(user_text):
        print("[분기 판단] 주제 이탈. 가드레일 메시지 반환.")
        content = "이 대화는 광운대학교 학생을 위한 진로 및 학사 관련 질문을 위한 챗봇입니다. 다른 질문이 있으시면 관련 내용으로 질문해주세요."
        new_history = history + [{"role": "user", "content": user_text}, {"role": "assistant", "content": content}]
        return content, new_history, state

    # STEP 2: 상태 전환
    if state.get("phase") != "solve" and wants_solution(user_text):
        state["phase"] = "solve"
        print("[상태 변경] explore -> solve")

    messages_for_llm = history + [{"role": "user", "content": user_text}]
    
    # ✅ 분기 실행
    if is_policy:
        content = rag_with_reranker(user_text, history, search_func)
    else:
        content = call_general_llm(messages_for_llm)
            
    new_history = messages_for_llm + [{"role": "assistant", "content": content}]
    print(f"[답변 생성 완료] 길이: {len(content)}")
    return content, new_history, state