# rag_request.py  (핵심 수정판)
from dotenv import load_dotenv
load_dotenv()

import os, json, uuid, requests
from typing import List, Dict, Any, Optional

# ============= 0) 설정 =============
REASONING_ENDPOINT = "https://clovastudio.stream.ntruss.com/v1/api-tools/rag-reasoning"
RERANKER_URL       = "https://clovastudio.stream.ntruss.com/v1/api-tools/reranker"

API_KEY_RAW = os.getenv("NCLOUD_API_KEY", "")
RERANKER_KEY_RAW = os.getenv("NCLOUD_API_KEY", "")
PROJECT_ID = os.getenv("NCLOUD_PROJECT_ID", "")
LOCAL_SEARCH_URL = os.getenv("LOCAL_SEARCH_URL", "http://127.0.0.1:8000/search/")

if not API_KEY_RAW:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")

def make_headers(raw_key: str) -> Dict[str, str]:
    if not raw_key:
        raise RuntimeError("API key is empty. Set NCLOUD_API_KEY environment variable.")
    h = {
        "Authorization": f"Bearer {raw_key}",
        "Content-Type": "application/json",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
    }
    if PROJECT_ID:
        h["X-NCP-CLOVASTUDIO-PROJECT-ID"] = PROJECT_ID
    return h

# ============= 1) payload 생성기 =============
def build_reasoning(query: Optional[str] = None,
                    document_list: Optional[List[Dict[str, Any]]] = None,
                    sugquery_list: Optional[List[str]] = None,
                    messages: Optional[List[Dict[str, Any]]] = None,
                    tool_calls: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    msg_list: List[Dict[str, Any]] = []
    if messages: msg_list = list(messages)
    if query:    msg_list.append({"role": "user", "content": query})

    if tool_calls:
        msg_list.append({"role": "assistant", "content": "", "toolCalls": tool_calls})
        if document_list:
            formatted = [{"id": f"doc-{d['id']}", "doc": d["doc"]} for d in document_list]
            tool_content = json.dumps({"search_result": formatted}, ensure_ascii=False)
            for tc in tool_calls:
                msg_list.append({
                    "role": "tool",
                    "name": tc["function"]["name"],
                    "content": tool_content,
                    "toolCallId": tc["id"],
                })

    payload: Dict[str, Any] = {
        "messages": msg_list,
        "maxTokens": 4000,
        "tools": [{
            "type": "function",
            "function": {
                "name": "ncloud_cs_retrieval",
                "description": "NCloud 관련 검색 도구. 필요 시 쿼리를 나누어 여러 번 호출. 정보가 없으면 suggestedQueries 참고.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "정제된 검색어"},
                        "url":   {"type": "string", "description": "검색 API 엔드포인트(원본 URL, 인코딩하지 말 것)"},
                    },
                    "required": ["query", "url"]
                }
            }
        }],
        "toolChoice": "auto",
    }
    if sugquery_list:
        payload["suggestedQueries"] = sugquery_list
    return payload

# ============= 2) Reasoning 호출 =============
def call_reasoning(payload: dict) -> dict:
    headers = make_headers(API_KEY_RAW)
    r = requests.post(REASONING_ENDPOINT, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        print("[reasoning error]", r.status_code, r.text[:500])
        r.raise_for_status()
    return r.json()

# ============= 3) tool call 파싱 =============
def _extract_message_obj(resp: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(resp, dict): return {}
    msg = resp.get("result", {}).get("message")
    if isinstance(msg, dict): return msg
    choices = resp.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict): return msg
    return {}

def extract_tool_calls(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    msg = _extract_message_obj(resp)
    tcs = msg.get("toolCalls") or msg.get("tool_calls") or []
    norm: List[Dict[str, Any]] = []
    for tc in tcs:
        fn = (tc or {}).get("function", {}) or {}
        args = fn.get("arguments")
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        norm.append({
            "id": tc.get("id"),
            "type": tc.get("type", "function"),
            "function": {"name": fn.get("name"), "arguments": args},
        })
    return norm

# ============= 4) 로컬 검색 API 호출 (/search/) =============
def call_local_retrieval(url: str, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    try:
        body = {"query": query, "top_k": top_k, "include_scores": True}
        r = requests.post(url, json=body, timeout=20)
        r.raise_for_status()
        items = r.json().get("result", [])
        items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
        # Reranker 입력 스키마에 맞추기
        return [{"id": str(it.get("id")), "content": it.get("content", "")} for it in items]
    except Exception as e:
        print("[retrieval error]", e)
        return []

# ============= 5) 리랭커 호출 =============
def reranker_function(query: str, documents: List[Dict[str, Any]],
                      api_url: str = RERANKER_URL,
                      api_key_raw: str = RERANKER_KEY_RAW,
                      max_tokens: int = 4000, timeout: int = 30) -> tuple[List[Dict[str, Any]], List[str]]:
    headers = make_headers(api_key_raw)  # ← 여기서 Bearer를 ‘한번만’ 붙임
    indexed = []
    for d in documents:
        text = (d.get("content") or "").strip()
        if text and text.lower() not in {"none", "nan"}:
            indexed.append({"id": str(d.get("id")), "doc": text})
    if not indexed:
        return [], []
    payload = {"query": query, "documents": indexed, "maxTokens": max_tokens}
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("[reranker error]", e)
        # 폴백: 상위 5개만 전달
        fb = [{"id": f"doc-{d['id']}", "doc": d["content"]} for d in documents[:5]]
        return fb, []
    result = data.get("result", {})
    docs = result.get("citedDocuments") or []
    sugq = result.get("suggestedQueries") or []
    cleaned = []
    for i, doc in enumerate(docs):
        did = str(doc.get("id", f"doc-{i}"))
        dtx = (doc.get("doc") or "").strip()
        if dtx:
            cleaned.append({"id": did, "doc": dtx})
    return cleaned, (list(sugq) if isinstance(sugq, list) else [])

# ============= 6) 전체 체이닝 =============
def run_reasoning(user_query_or_messages):
    # 멀티턴 분리
    current_query = user_query_or_messages
    message_history = None
    if isinstance(user_query_or_messages, list) and user_query_or_messages:
        current_query = user_query_or_messages[-1]["content"]
        message_history = user_query_or_messages[:-1] or None

    all_docs: List[Dict[str, Any]] = []

    for _ in range(3):  # 무한루프 방지
        payload = build_reasoning(query=current_query, messages=message_history,
                                  document_list=(all_docs or None))
        r1 = call_reasoning(payload)
        msg = _extract_message_obj(r1)
        tool_calls = extract_tool_calls(r1)
        content = msg.get("content") or ""

        # 검색 없이 답변하면 종료
        if not tool_calls:
            return r1 if not content else {"result": {"message": {"content": content}}}

        # 도구 호출 → 로컬 검색 → 리랭커
        suggested_all: List[str] = []
        raw_docs: List[Dict[str, Any]] = []

        for tc in tool_calls:
            args_s = (tc.get("function") or {}).get("arguments") or "{}"
            try:
                args = json.loads(args_s) if isinstance(args_s, str) else (args_s or {})
            except Exception:
                args = {}
            q = args.get("query") or current_query

            # ★ 모델이 준 url은 무시, 항상 LOCAL_SEARCH_URL 사용
            sr = call_local_retrieval(LOCAL_SEARCH_URL, q, top_k=8)
            raw_docs.extend(sr)

        if raw_docs:
            doc_list, sug_list = reranker_function(current_query, raw_docs)
            if doc_list:
                # 중복 제거 후 누적
                for d in doc_list:
                    if not any(x["id"] == d["id"] for x in all_docs):
                        all_docs.append(d)
            elif sug_list:
                suggested_all.extend(sug_list)

        # 문서가 모였으면, toolCalls + tool(search_result)로 2차 호출하여 최종 답변
        if all_docs:
            payload2 = build_reasoning(query=current_query, messages=message_history,
                                       document_list=all_docs, tool_calls=tool_calls)
            r2 = call_reasoning(payload2)
            return r2

        if suggested_all:
            # 다음 루프에서 재검색 유도 (필요시 build_reasoning에 suggestedQueries 넣을 수도 있음)
            continue

        break

    return {"result": {"message": {"content": "검색된 문서가 없어 답변을 생성할 수 없습니다."}}}

# ============= 7) 실행 =============
if __name__ == "__main__":
    uq = "재수강 조건이 뭐야? 그리고 재수강 하면, 최대 점수가 얼마인지 알려줘"
    print("\n[질문]\n" + uq + "\n")
    try:
        out = run_reasoning(uq)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[실행 오류] {e}")