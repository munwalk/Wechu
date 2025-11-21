# rag_chain.py
# 전체 체이닝: RAG Reasoning → (tool call) → 로컬 검색 API → 리랭커 → 최종 답변
import os
from dotenv import load_dotenv
load_dotenv()

import json
import requests

# ===================== 설정 =====================
RERANKER_API_URL = "https://clovastudio.stream.ntruss.com/v1/api-tools/reranker"
REASONING_ENDPOINT = "https://clovastudio.stream.ntruss.com/v1/api-tools/rag-reasoning"

# 테스트 쿼리
USER_QUERY = "재수강 규정 뭐야?"

API_KEY = os.getenv("NCLOUD_API_KEY", "")
if not API_KEY:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")

SEARCH_API_URL = os.getenv("LOCAL_SEARCH_URL", "http://127.0.0.1:8000/search/")

# ===================== 2.2.1 build_reasoning =====================
def build_reasoning(query=None, document_list=None, sugquery_list=None, messages=None, tool_calls=None):
    """RAG Reasoning에 전달할 payload 생성"""
    msg_list = []
    if messages:
        msg_list = list(messages)  # 사본

    if query:
        msg_list.append({"role": "user", "content": query})

    if tool_calls:
        # 도구 호출 사실을 assistant 메시지로 기록
        msg_list.append({"role": "assistant", "content": "", "toolCalls": tool_calls})

        # 리랭커 결과(document_list)를 도구 응답(tool)으로 전달
        if document_list:
            formatted = [{"id": f"doc-{doc['id']}", "doc": doc["doc"]} for doc in document_list]
            tool_content = json.dumps({"search_result": formatted}, ensure_ascii=False)
            for tc in tool_calls:
                msg_list.append({
                    "role": "tool",
                    "name": tc["function"]["name"],
                    "content": tool_content,
                    "toolCallId": tc["id"],
                })

    payload = {
        "messages": msg_list,
        "maxTokens": 4000,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "ncloud_cs_retrieval",
                    "description": (
                        "NCloud 관련 검색 도구.\n"
                        "필요 시 쿼리를 나눠 여러 번 호출 가능.\n"
                        "정보를 찾지 못하면 suggestedQueries를 참고해 재검색."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "사용자 검색어(정제)"},
                            "url": {"type": "string", "description": "검색 API 엔드포인트 URL"},
                        },
                        "required": ["query", "url"],
                    },
                },
            }
        ],
        "toolChoice": "auto",
    }

    if sugquery_list:
        payload["suggestedQueries"] = sugquery_list

    return payload


# ===================== 2.2.2 ncloud_cs_retrieval =====================
def ncloud_cs_retrieval(query: str, search_api_url: str):
    """로컬 FastAPI 검색(/search) 호출 → [{id, content}, ...] 반환"""
    # URL 정규화
    url = search_api_url
    if not url.rstrip("/").endswith("search"):
        url = url.rstrip("/") + "/search/"

    headers = {"accept": "application/json", "Content-Type": "application/json"}
    data = {"query": query, "top_k": 5}

    resp = requests.post(url, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    # body 는 {"result": [...]} 형태
    return body.get("result", [])


# ===================== 2.2.3 reranker_function =====================
def reranker_function(query: str, documents: list, api_url: str, api_key: str):
    """리랭커 호출 → (citedDocuments, suggestedQueries)만 반환"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    indexed_documents = [
        {"id": str(doc.get("id")), "doc": doc.get("content", "")}
        for doc in documents
        if doc and str(doc.get("content", "")).strip() not in ("", "None", "nan", "NaN")
    ]

    payload = {"query": query, "documents": indexed_documents, "maxTokens": 4000}

    resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    cited = result.get("result", {}).get("citedDocuments", [])
    sugg = result.get("result", {}).get("suggestedQueries", [])
    return cited, sugg


# ===================== 유틸: tool call 파싱 =====================
def _extract_message_obj(resp: dict) -> dict:
    if not isinstance(resp, dict):
        return {}
    msg = resp.get("result", {}).get("message")
    if isinstance(msg, dict):
        return msg
    # 호환: choices[0].message
    choices = resp.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict):
            return msg
    return {}

def extract_tool_calls(resp: dict) -> list:
    """message.toolCalls / tool_calls 모두 지원. arguments를 dict로 정규화."""
    msg = _extract_message_obj(resp)
    raw = msg.get("toolCalls") or msg.get("tool_calls") or []
    norm = []
    for tc in raw:
        fn = (tc or {}).get("function") or {}
        args = fn.get("arguments")
        # 문자열이면 JSON 파싱 시도
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        elif not isinstance(args, dict):
            args = {}
        norm.append({
            "id": tc.get("id"),
            "type": tc.get("type", "function"),
            "function": {"name": fn.get("name"), "arguments": args},
        })
    return norm


# ===================== 2.2.4 전체 실행(run_reasoning) =====================
def run_reasoning(user_query_or_messages, search_api_url, reranker_api_url, api_key, reasoning_endpoint):
    all_document_list = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 멀티턴 처리
    current_query = user_query_or_messages
    message_history = None
    if isinstance(user_query_or_messages, list) and user_query_or_messages:
        current_query = user_query_or_messages[-1]["content"]
        message_history = user_query_or_messages[:-1] or None

    for iteration in range(3):
        # 1) payload 구성
        if iteration == 0:
            payload = build_reasoning(query=current_query, messages=message_history)
            print("🔧 1차 payload:", json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            payload = build_reasoning(query=current_query, messages=message_history, document_list=all_document_list)
            print("🔧 재호출 payload(문서 포함):", json.dumps(payload, ensure_ascii=False, indent=2))

        # 2) Reasoning 호출
        r = requests.post(reasoning_endpoint, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        rjson = r.json()
        print("🧠 reasoning 응답:", json.dumps(rjson, ensure_ascii=False, indent=2))

        # 3) toolCalls 파싱
        tool_calls = extract_tool_calls(rjson)
        content = _extract_message_obj(rjson).get("content") or ""

        # 도구 안 쓰면 그게 최종 답
        if not tool_calls:
            return content if content else "답변을 생성할 수 없습니다."

        all_sugquery_list = []

        # 4) 각 도구 호출에 대해 검색→리랭커
        for i, tc in enumerate(tool_calls):
            args = (tc.get("function") or {}).get("arguments") or {}
            search_query = args.get("query") or current_query
            url_from_model = args.get("url")  # 모델이 제안한 URL 무시하고 로컬 API 사용
            print(f"→ 도구 호출[{i}] ncloud_cs_retrieval(query='{search_query}', url='{url_from_model}')")

            # 4-1 검색
            try:
                search_results = ncloud_cs_retrieval(search_query, search_api_url)
            except Exception as e:
                print("[retrieval ERROR]", str(e))
                continue

            # 4-2 리랭커
            try:
                document_list, sugquery_list = reranker_function(search_query, search_results, reranker_api_url, api_key)
            except Exception as e:
                print("[reranker ERROR]", str(e))
                continue

            # 4-3 결과 누적
            if document_list:
                for doc in document_list:
                    if not any(d["id"] == doc["id"] for d in all_document_list):
                        all_document_list.append(doc)
            elif sugquery_list:
                all_sugquery_list.extend(sugquery_list)

        # 5) 문서가 모였으면 최종 답변 생성
        if all_document_list:
            payload2 = build_reasoning(
                query=current_query,
                messages=message_history,
                document_list=all_document_list,
                tool_calls=tool_calls,
            )
            print("🔧 최종 생성 payload:", json.dumps(payload2, ensure_ascii=False, indent=2))
            r2 = requests.post(reasoning_endpoint, headers=headers, json=payload2, timeout=60)
            r2.raise_for_status()
            final = r2.json()
            return final  # 전체 결과 그대로 반환

        # 6) 추천 검색어가 있으면 다음 라운드에서 재검색
        if all_sugquery_list:
            continue

        break  # 아무것도 없으면 중단

    return "검색된 문서가 없어 답변을 생성할 수 없습니다."


# ===================== 실행 예시 =====================
if __name__ == "__main__":
    print("🔧 4단계: run_reasoning 함수 호출 (최종 답변 생성)")
    result = run_reasoning(USER_QUERY, SEARCH_API_URL, RERANKER_API_URL, API_KEY, REASONING_ENDPOINT)
    print(json.dumps(result, indent=2, ensure_ascii=False))