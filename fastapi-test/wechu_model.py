# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

import os, json, requests, re

# -----------------------
# 유틸: 태그 제거/중복 제거
# -----------------------
def strip_citation_tags(text: str) -> str:
    return re.sub(r'</?doc[^>]*>', '', text)

def dedup_lines(text: str) -> str:
    seen, out = set(), []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out)

def uniq_docs(docs):
    seen, uniq = set(), []
    for d in docs or []:
        key = (d.get("id"), (d.get("content") or d.get("doc") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return uniq

import re

def sentence_overlap(sent: str, sources: list[str], thr: float=0.35) -> bool:
    # 간단한 토큰 유사도(한글/숫자 위주)
    def tokens(s):
        return set([w for w in re.findall(r"[가-힣A-Za-z0-9]+", s) if len(w)>=2])
    ts = tokens(sent)
    if not ts: return False
    best = 0.0
    for src in sources:
        ss = tokens(src)
        if not ss: continue
        inter = len(ts & ss)
        score = inter / max(1, len(ts))
        best = max(best, score)
    return best >= thr

def clip_to_grounded(answer: str, docs: list[dict]) -> str:
    sources = [(d.get("doc") or d.get("content") or "") for d in (docs or [])]
    kept = []
    for s in re.split(r"(?<=[.!?…\n])\s+", answer.strip()):
        s_clean = s.strip()
        if not s_clean: continue
        if not sources:  # 근거가 없으면 전부 제거
            continue
        if sentence_overlap(s_clean, sources):
            kept.append(s_clean)
    return "\n".join(kept)

# -----------------------
# 엔드포인트 / 키
# -----------------------
REASONING_ENDPOINT = "https://clovastudio.stream.ntruss.com/v1/api-tools/rag-reasoning"
ANSWER_URL = os.getenv("LOCAL_SEARCH_URL", "http://127.0.0.1:8000") + "/search_answer"
SEARCH_URL = os.getenv("LOCAL_SEARCH_URL", "http://127.0.0.1:8000/search/")

API_KEY_PURE = os.getenv("NCLOUD_API_KEY", "")
if not API_KEY_PURE:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")
API_KEY = f"Bearer {API_KEY_PURE}"

# -----------------------
# --- cues & detectors (DROP-IN REPLACEMENT) ---

# 정책 관련 키워드(되도록 소문자/원형)
POLICY_KEYWORDS = {
    "재수강","휴학","복학","전과","복수전공","부전공","졸업","장학",
    "수강신청","성적정정","클래스","klas","규정","정원","학사",
    "최대","제한","조건","수강포기","수강삭제","학점포기","드롭"
}

# 질문 티 나는 표현(정책과 함께 등장할 때에만 정책질문으로 본다)
QUESTION_CUES = {
    "뭐야","뭔가요","얼마","몇","가능","규정","조건","최대","제한",
    "해야","되나","되니","되나요","알려줘","어케","어떻게","어떡해"
}

# 건강/이유 제시 탐지(공감/탐색 단계 제어용)
HEALTH_CUES = {"건강","아파","병원","컨디션","우울","불안","스트레스","피곤","지쳤"}

# 해결책 요구 표시
SOLUTION_CUES = {"어떻게","방법","할 수 있을까","해결","개선","로드맵","추천","알려줘","정리해줘","수정해줘","뭐가좋아","해줄래","어케","어떡해"}

def _norm(text: str) -> str:
    return (text or "").lower()

def needs_policy_search(text: str) -> bool:
    """(느슨) 정책 키워드가 하나라도 들어가면 True."""
    t = _norm(text)
    return any(k.lower() in t for k in POLICY_KEYWORDS)

def looks_like_policy_q(text: str) -> bool:
    """(권장) 정책 키워드 + 질문 표현이 같이 있을 때만 True → 오탐 감소."""
    t = _norm(text)
    hit_kw = any(k.lower() in t for k in POLICY_KEYWORDS)
    hit_q  = any(q in t for q in QUESTION_CUES)
    return hit_kw and hit_q

def wants_solution(text: str) -> bool:
    """사용자가 해결책/실행안을 원한다고 명시했는지 판별 (중복 정의 금지!)"""
    t = _norm(text)
    return any(c in t for c in SOLUTION_CUES)

def user_gave_reason(text: str) -> bool:
    """사용자가 건강/컨디션 등 이유를 언급했는지"""
    t = _norm(text)
    return any(k in t for k in HEALTH_CUES)


# -----------------------
# 시스템 프롬프트
# -----------------------
SYSTEM_DATADRIVEN = """

# 시스템 프롬프트: 광운대학교 학사정보 기반 진로상담 챗봇

## 1) 역할 정의

당신은 **광운대학교 학사정보 기반 진로상담 챗봇**입니다. 학생(또는 취준생)의 학업·수업·전공·진로·취업·장학 관련 고민에 **따뜻하게 공감**하고, **RAG(Search → Retrieval → Answer) 모델**로 검색된 **정확한 학사정보**만을 근거로 **실질적인 해결책**을 제시합니다.

---

## 2) 핵심 원칙

### 2-1. 대화 흐름 구조(일반 턴)

항상 아래 **3단계 구조**로 답변합니다.

1. **공감**: 학생의 상황·감정에 공감하며 시작
2. **해결책**: RAG 검색 결과를 근거로 구체·실용 정보 제시
3. **맥락 질문**: 다음 대화를 자연스럽게 이끌 **후속 질문**

> **길이 가이드**: 2~3문단 이내, 과도하게 길지 않게 구성. 각 단락에 **이모지 1~2개**(예: 😊🤔💭📚🎯✨💡🌟📊👍).
> **가독성**: 줄바꿈을 활용해 핵심만 명확히.

### 2-2. 첫 턴(초응답) 특수 규칙

* **형식**: **공감 1문장 → 상황 파악 질문 2~3개**만 제시(해결책은 **추가 정보**를 받은 뒤 제공).
* **톤**: 친구처럼 편안하고 따뜻하되, **존중감** 유지. 중복/상투어/이모지 남용 금지. **5~8줄 이내**.

### 2-3. 답변 스타일

* **친근·따뜻** + **간결·핵심 중심**.
* 절차·신청·유의사항 등 **복잡한 내용은 단계/번호로 분해**.
* 표기 일관(학적용어, 마감일, 요건 등은 **숫자·날짜**를 명확히 기재).

---

## 3) 정보 제공 방식(근거 규칙)

### 3-1. RAG 기반 답변

* **반드시** `search_result`(RAG로 검색된 학사문서) 근거로 작성.
* 중요한 정책/수치/학사 규정은 **근거를 괄호로 출처 표기**:
  예) **마지막 줄**에 한 번만: `(출처: QnA#ID)`
* 동일 턴에서 **복수 문서**를 쓸 경우, 가장 핵심 문서의 QnA#ID만 표기.
* **근거가 없을 때**: “**데이터에 근거가 없어 확인 불가**”라고 명시하고, **다음 행동 1가지만** 제안(예: 담당부서 문의, 관련 문서명 제시 등).

### 3-2. 단계별 안내 예시

* “① 자격요건 확인 → ② 기간·마감일 확인 → ③ 신청 경로(포털/링크) → ④ 제출서류 → ⑤ 처리 일정/결과 확인”

---

## 4) 주의사항(금지/권장)

* ❌ **확인되지 않은 정보** 제공 금지(추정, 경험담, 인터넷 검색 추측 불가).
* ❌ RAG 결과가 없을 때 **추측 보완 금지**.
* ❌ **지나친 장문** 금지(핵심만).
* ✅ **질문 의도 정확 파악**, 핵심만 전달.
* ✅ **애매하면** 먼저 **명확화 질문**을 던진 뒤 해결책 제시.
* ✅ 날짜·숫자는 **절대오류 없이**(예: “2025-10-13 ~ 2025-10-17”).

---

## 5) 예외·한계 대응

1. **정보 부족 시**

   * “이 부분은 학과 사무실에 직접 문의하시는 게 더 정확할 것 같아요 😊”
   * 다음 행동 1가지만 제안(예: “학과 홈페이지의 공지 ‘졸업요건 안내’ 확인”).

2. **복잡한 상담 필요 시**

   * “이 경우는 **진로상담센터 1:1 상담**을 받아보시는 걸 추천드려요 💡”

3. **긴급 상황(마감 임박/제출 오류 등)**

   * “빠른 처리가 필요한 사안이니 **학사팀(연락처)**에 바로 연락해보세요! ⚡”

4. **주제 범위 밖(학사·수업·전공·진로·취업·장학과 무관)**

   * 정중히 고지: “이 챗봇은 **학사·진로 상담 전용**이에요. 관련 문의를 남겨주시면 정확히 도와드릴게요!”

---

## 6) 출력 순서(가능하면 준수)

* **현재 턴**: 공감 1문장 → **질문 2~3개**
* **다음 턴(학생이 정보 제공 후)**: **실행 가능한 선택지 1~2개** + 핵심 절차 요약 + `(출처: QnA#ID)`
* 항상 **간결성 유지**, 불필요한 수식어·반복 제거.

---

## 7) 응답 예시 템플릿

### 7-1. 첫 턴(초응답)

* 공감(1문장) 😊
* 상황 파악 질문 2~3개(불릿 또는 짧은 문장). 🤔

> 예)
> “지금 상황이 꽤 답답하고 걱정되셨겠어요. 😊
> 우선 확인하고 싶은 게 있어요:
>
> 1. 해당 학기의 **평점/이수학점**이 어떻게 되나요?
> 2. **복수전공/부전공** 계획이 있으신가요?
> 3. 이번 학기에 꼭 들어야 하는 **필수 과목**이 있나요?”

### 7-2. 일반 턴(정보 제공)

* 공감(짧게) + 해결책(핵심 절차/요건/기간/경로) + 맥락 질문(1개).
* **마지막 줄**에 한 번만 **출처 표기**: `(출처: QnA#ID)`
* 근거가 없으면: “데이터에 근거가 없어 확인 불가” + **다음 행동 1개**만.

> 예)
> “말씀해주신 조건이면 **전과 신청 자격**은 충족 가능성이 높아요. 😊
> ① **신청 기간**에 포털 접속 → ② **학과 변경 신청서** 업로드 → ③ **성적증명서** 첨부 → ④ 결과 공지 확인 순서로 진행해요.
> 다음으로, 목표 학과의 **필수 기초과목** 이수 계획을 세워볼까요? ✨
> (출처: QnA#27)”

---

## 8) 운영 체크리스트(시스템 내부용)

* [ ] 질의 의도 파악(학사/수업/전공/진로/취업/장학 범주 여부)
* [ ] `search_result`에서 **정확 일치 문서 우선** 검색
* [ ] 날짜·수치·요건 **상호검증 후** 노출
* [ ] **첫 턴 규칙** 준수(공감+질문만)
* [ ] 일반 턴에서 **절차를 번호로** 분해
* [ ] **근거 표기 형식** 고정: `(출처: QnA#ID)` **마지막 줄 1회**
* [ ] 근거 부재 시 **확인 불가 + 다음 행동 1개**
* [ ] 톤: 따뜻·간결, **이모지 각 단락 1~2개**
* [ ] 2~3문단 내, **불필요 반복 금지**

---

## 9) 금칙/형식 요약(빠른 레퍼런스)

* **금지**: 추정·카더라, 장문, 중복, 이모지 과다, 비학사 주제 임의 답변
* **필수**: 첫 턴 질문만, 일반 턴 3단계 구조, 번호 절차, 마지막 줄 출처, 불명확 시 명확화 질문

---

""".strip()

# --- 온토픽/오프토픽 필터 ---------------------------------

TOPIC_WHITELIST = {
    "재수강","휴학","복학","전과","복수전공","부전공","졸업","장학",
    "수강","수강신청","학점","성적","성적정정","클래스","klas",
    "규정","정원","학사","교과목","전공","과목","시간표","수업",
    "캡스톤","프로젝트","공모전","인턴","취업","이력서","자소서",
    "포트폴리오","코딩테스트","진로","로드맵","멘토","학습계획"
}
TOPIC_BLACKLIST = {"레시피","요리","김치찌개","된장찌개","여행코스","주식추천","연예","가십",
                   "게임공략","연애상담","육아","반려동물","자동차튜닝"}

ACADEMIC_HINTS = {"학점","공부","수업","수강","전공","성적","재수강","졸업","시험","과제","시간표"}
WELLBEING = {"건강","아파","우울","불안","스트레스","컨디션","피곤","지쳤","멘탈"}

# === 맥락 기반 온토픽 판별 ===
def is_on_topic(text: str, history: list[dict]|None=None, state: dict|None=None) -> bool:
    t = (text or "").lower()

    # 이미 도메인 대화가 시작됐으면(첫 온토픽 이후) 계속 온토픽으로 간주
    if state and state.get("domain_locked"):
        return True

    # 블랙리스트이지만, '건강+학사 맥락' 조합이면 허용 (예: 건강 때문에 학점이…)
    if any(k.lower() in t for k in TOPIC_BLACKLIST):
        if any(w in t for w in WELLBEING) and any(a in t for a in ACADEMIC_HINTS):
            pass
        else:
            return False

    # 현재 발화 자체에 학사/진로 힌트가 있으면 허용
    if any(k.lower() in t for k in TOPIC_WHITELIST) or any(a in t for a in ACADEMIC_HINTS):
        return True

    # 직전 유저 발화가 온토픽이었으면(대화 연속성) 허용
    if history:
        for m in reversed(history):
            if m.get("role") == "user":
                prev = (m.get("content","") or "").lower()
                if (any(k.lower() in prev for k in TOPIC_WHITELIST)
                    or any(a in prev for a in ACADEMIC_HINTS)):
                    return True
                break

    return False

# -----------------------
# Reasoning 호출 공통
# -----------------------
def call_reasoning(payload: dict) -> dict:
    headers = {"Authorization": API_KEY, "Content-Type":"application/json"}
    r = requests.post(REASONING_ENDPOINT, headers=headers, json=payload, timeout=40)
    print("reasoning status:", r.status_code) # 로그 
    if r.status_code >= 400:
        print(r.text)
        r.raise_for_status()
    return r.json()

# -----------------------
# 페이로드 빌더
# -----------------------
def build_reasoning(messages, tool_calls=None, docs=None, tool_choice="auto"):
    msgs = list(messages)
    if tool_calls:
        msgs.append({"role":"assistant","content":"", "toolCalls": tool_calls})
        if docs:
            tool_content = json.dumps(
                {"search_result":[{"id":f"doc-{d['id']}", "doc": d["content"]} for d in docs]},
                ensure_ascii=False
            )
            for tc in tool_calls:
                msgs.append({
                    "role":"tool",
                    "name":tc["function"]["name"],
                    "content":tool_content,
                    "toolCallId":tc["id"]
                })
    return {
        "messages": msgs,
        "maxTokens": 3500,
        "tools": [{
            "type":"function",
            "function":{
                "name":"ncloud_cs_retrieval",
                "description":"로컬 검색/답변 API 호출 도구",
                "parameters":{
                    "type":"object",
                    "properties":{
                        "query":{"type":"string","description":"정제된 검색어"},
                        "url":{"type":"string","description":"검색/답변 API 엔드포인트"}
                    },
                    "required":["query","url"]
                }
            }
        }],
        "toolChoice": tool_choice,   # ← 여기!
    }
    

def extract_tool_calls(resp: dict):
    msg = resp.get("result", {}).get("message", {}) if isinstance(resp, dict) else {}
    tcs = msg.get("toolCalls") or []
    norm = []
    for tc in tcs:
        fn = tc.get("function", {}) or {}
        norm.append({
            "id": tc.get("id"),
            "type": tc.get("type", "function"),
            "function": {"name": fn.get("name"), "arguments": fn.get("arguments")}
        })
    return norm

# -----------------------
# 로컬 검색/답변 + 출처 1개
# -----------------------
def local_fetch_answer(query: str, top_k:int=1) -> tuple[list[dict], str]:
    # 실제 답
    r1 = requests.post(ANSWER_URL, json={"query": query, "top_k": top_k}, timeout=10)
    r1.raise_for_status()
    ans = (r1.json() or {}).get("answer") or ""
    docs = [{"id": "ans-1", "content": ans}] if ans else []

    # 출처 후보 1개
    citation = ""
    try:
        r2 = requests.post(SEARCH_URL, json={"query": query, "top_k": 1}, timeout=8)
        if r2.ok:
            hit = (r2.json() or {}).get("result", [])[:1]
            if hit:
                citation = f"QnA#{hit[0].get('id','-')}"
    except Exception:
        pass

    return docs, citation

# 간단 관련도 체크(근거가 엉뚱하면 버림)
def related(ans:str, q:str)->bool:
    ks = [w for w in re.findall(r"[가-힣A-Za-z0-9]+", q) if len(w)>=2]
    hit = sum(1 for k in ks if k in ans)
    return hit >= max(1, len(ks)//6)

# -----------------------
# 한 턴 처리
# -----------------------
def chat_turn(user_text: str, history: list[dict], state: dict) -> tuple[str, list[dict], dict]:
   
    # 0) 온토픽 필터 (맥락/세션 기반)
    if not is_on_topic(user_text, history, state):
        content = (
            "미안해요! 저는 광운대 **학사·수업·전공·진로/취업 상담 전용** 봇이에요.\n"
            "예) 재수강 규정, 휴학/복학, 전공·과목 선택, 취업/인턴 준비, 장학, 학점 관리 등\n"
            "이 주제 안에서 무엇이든 물어봐 주세요 🙂"
        )
        history = history + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": content},
        ]
        return content, history, state

    # 온토픽이면 세션 고정
    if not state.get("domain_locked"):
        state["domain_locked"] = True

    # 1) phase 전환
    if state.get("phase") != "solve" and wants_solution(user_text):
        state["phase"] = "solve"

    # 2) 메시지 구성
    N = 6
    head = [{"role":"system","content": SYSTEM_DATADRIVEN}]
    tail = history[-N*2:]
    messages = head + tail + [{"role":"user","content": user_text}]

    # 3) 정책 근거는 solve 단계에서만
    use_policy = looks_like_policy_q(user_text) and state.get("phase") == "solve"

    tool_calls = None
    docs = []
    citation_label = ""

    if use_policy:
        # --- 정책 체인 ---
        p1 = build_reasoning(messages)
        r1 = call_reasoning(p1)
        tool_calls = extract_tool_calls(r1)

        # 검색 쿼리
        if tool_calls:
            raw = (tool_calls[0].get("function") or {}).get("arguments") or {}
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except Exception:
                args = {}
            search_query = args.get("query") or user_text
        else:
            search_query = user_text

        # /search_answer + 출처
        docs, citation_label = local_fetch_answer(search_query, top_k=1)
        if docs and not related(docs[0]["content"], search_query):
            docs, citation_label = [], ""
        docs = uniq_docs(docs)

        # toolCalls 정규화
        if not tool_calls:
            tool_calls = [{
                "id": "tc-1",
                "type": "function",
                "function": {"name": "ncloud_cs_retrieval", "arguments": {}}
            }]
        fixed = []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            a = fn.get("arguments") or {}
            if isinstance(a, str):
                try: a = json.loads(a)
                except: a = {}
            if not a.get("query"):
                a["query"] = search_query
            a["url"] = ANSWER_URL
            fixed.append({
                "id": tc.get("id","tc-1"),
                "type": "function",
                "function": {"name": fn.get("name","ncloud_cs_retrieval"), "arguments": a}
            })
        tool_calls = fixed

        # 최종 호출(근거 주입)
        p2 = build_reasoning(messages, tool_calls=tool_calls, docs=docs)
        r2 = call_reasoning(p2)
        content = r2.get("result",{}).get("message",{}).get("content","")

        # --- 후처리(정책 브랜치에만 적용!) ---
        content = strip_citation_tags(content)
        content = dedup_lines(content)
        content = clip_to_grounded(
            content,
            [{"content": d.get("content",""), "doc": d.get("content","")} for d in (docs or [])]
        )
        if not content:
            # 폴백도 여기서만
            content = "데이터에 근거가 없어 확인 불가입니다. 학사에 문의해 주세요."

        if docs and citation_label:
            content += f"\n(출처: {citation_label})"

    else:
        # --- 탐색/비정책: 도구 금지, 공감+질문만 ---
        p = build_reasoning(messages, tool_choice="none")
        r = call_reasoning(p)
        content = (r.get("result",{}).get("message",{}).get("content","") or "").strip()

        # 빈 응답일 때 안전망(공감 + 질문 2~3개)
        if not content:
            content = (
                "학점 때문에 마음이 무거울 수 있어요. 상황을 조금 더 알고 싶어요.\n"
                "최근에 특히 힘들었던 과목이나 시기가 있었나요?\n"
                "하루·주당 공부 가능 시간은 대략 어느 정도인가요?"
            )

        # 탐색 브랜치에서는 태그 제거/중복 제거만 (❌ clip_to_grounded 금지)
        content = strip_citation_tags(content)
        content = dedup_lines(content)

        # 탐색 단계면 해결책 자제 유도
        if state.get("phase") == "explore" and wants_solution(content):
            content = (
                "지금은 상황을 조금 더 정확히 알고 싶어요. 최근에 가장 힘들었던 지점이 무엇이었나요?\n"
                "특정 과목 때문에인지, 전반적으로 시간이 부족했는지 알려주실 수 있을까요?\n"
                "하루·주당 공부 가능 시간도 대략 어느 정도인지 감이 있을까요?"
            )

    # 4) 히스토리 업데이트
    history = history + [
        {"role":"user","content":user_text},
        {"role":"assistant","content":content}
    ]
    return content, history, state

# -----------------------
# 콘솔 루프
# -----------------------
if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("환경변수 API_KEY 를 설정하세요. 예)  PowerShell: setx API_KEY \"nv-...\"  (재시작 필요)")

    print("WECHu 상담 시작! (종료: exit)")
    state = {"phase":"explore"}
    history = []
    while True:
        user = input("\n👤 You: ").strip()
        if user.lower() in {"exit","quit","q"}:
            break
        try:
            reply, history, state = chat_turn(user, history, state)
            print("\n🤖 Coach:\n" + reply)
        except Exception as e:
            print(f"❌ 오류: {e}")
