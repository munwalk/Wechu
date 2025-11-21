# search_api.py (출처 컬럼 포함 버전)
# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

from __future__ import annotations
import io
try:
    import chardet  # 없으면 아래에서 자동으로 처리
    HAS_CHARDET = True
except Exception:
    HAS_CHARDET = False

import os
import ast
import requests
import pandas as pd
import numpy as np
from numpy import dot
from numpy.linalg import norm
from typing import List, Dict, Any, Callable, Optional # Optional, Callable, Dict, Any 추가
from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request # request 임포트

# chat_logic.py에서 사용되는 함수/상수 등을 위한 임포트 (chat_logic이 필요로 할 수 있음)
REASONING_ENDPOINT = "https://clovastudio.stream.ntruss.com/v1/api-tools/rag-reasoning"

API_KEY_PURE = os.getenv("NCLOUD_API_KEY", "")
if not API_KEY_PURE:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")
API_KEY_WITH_BEARER = f"Bearer {API_KEY_PURE}"

# -----------------------------
# 1) 임베딩 API 호출
# -----------------------------
def get_embedding(input_text: str, api_key: str):
    EMBEDDING_API_URL = "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2"
    headers = {
        # get_embedding 내에서는 순수 키(Bearer 없음)를 받도록 수정해야 하나, 
        # 기존 코드를 유지하고 API_KEY_PURE를 사용
        "Authorization": f"Bearer {api_key}",  
        "Content-Type": "application/json",
    }
    data = {"text": input_text}
    resp = requests.post(EMBEDDING_API_URL, headers=headers, json=data, timeout=15)
    if resp.status_code != 200:
        try:
            print("[embedding error]", resp.status_code, resp.text)
        except Exception:
            pass
        resp.raise_for_status()
    emb = resp.json()["result"]["embedding"]
    return emb


# -----------------------------
# 2) 데이터 로드(임베딩/텍스트 자동 처리)
# -----------------------------
def start() -> pd.DataFrame:
    # 📌 수정 1: 임베딩 파일 경로 및 이름 조정
    file_path = os.getenv("DATA_FILE_PATH", "./data_final_emb_with_src.csv")
    if not os.path.isfile(file_path):
        print(f"임베딩 파일을 찾을 수 없습니다: {file_path}")
        return pd.DataFrame(columns=["text", "embedding", "ID"])

    print(f"{file_path} 파일이 존재합니다.")

    # --- 인코딩 감지 + 안전 로드 ---
    with open(file_path, "rb") as f:
        raw = f.read()

    if HAS_CHARDET:
        det = chardet.detect(raw)
        enc = det.get("encoding") or "utf-8"
    else:
        enc = "utf-8-sig" 

    try:
        text = raw.decode(enc, errors="replace")
    except Exception:
        text = raw.decode("cp949", errors="replace")

    df = pd.read_csv(io.StringIO(text))

    df["ID"] = df.index

    # --- 임베딩 파싱 ---
    def parse_vec(x):
        try:
            if isinstance(x, str):
                v = ast.literal_eval(x)
            else:
                v = x
            v = [float(t) for t in v]
            return v
        except Exception:
            return []
    if "embedding" not in df.columns:
        raise ValueError("CSV에 'embedding' 컬럼이 없습니다.")

    df["embedding"] = df["embedding"].apply(parse_vec)
    df = df[df["embedding"].apply(lambda v: isinstance(v, list) and len(v) > 0)].reset_index(drop=True)

    # --- 텍스트 컬럼 통일 (대/소문자 무시) ---
    text_candidates = ["text","content","contents","body","document","doc",
                       "passage","chunk","sentence","value","title","Text","내용", "dialog_text"] # dialog_text 추가
    lower_map = {c.lower(): c for c in df.columns}
    text_col = next((lower_map[c.lower()] for c in text_candidates if c.lower() in lower_map), None)
    if text_col is None:
        ignore = {"embedding", "ID", "similarity"}
        cols_to_join = [c for c in df.columns if c not in ignore]
        df["text"] = "" if not cols_to_join else df[cols_to_join].astype(str).apply(
            lambda r: " | ".join([f"{k}:{v}" for k, v in r.items()]), axis=1)
    elif text_col != "text":
        df = df.rename(columns={text_col: "text"})

    # --- 답변 컬럼 통일 (대/소문자 무시) ---
    answer_candidates = ["answer","answers","completion","output","response","label","답변","Completion"]
    answer_col = next((lower_map[c.lower()] for c in answer_candidates if c.lower() in lower_map), None)
    if answer_col is not None and answer_col != "answer":
        df = df.rename(columns={answer_col: "answer"})

    # 📌 수정 2: 출처 컬럼 통일 (대/소문자 무시)
    source_candidates = ["source","source_name","출처","Source_Name","source_file"]
    source_col = next((lower_map[c.lower()] for c in source_candidates if c.lower() in lower_map), None)
    if source_col is not None and source_col != "source":
        df = df.rename(columns={source_col: "source"})

    # (옵션) Completion에 '/n' 들어간 경우 줄바꿈 정리
    if "answer" in df.columns:
        import re
        df["answer"] = df["answer"].astype(str).apply(lambda s: re.sub(r"\s*/n\s*", "\n", s).strip())

    # --- 모지바케 복구 시도 (이미 깨진 경우) ---
    def fix_mojibake(s):
        if not isinstance(s, str):
            return s
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(fix_mojibake)

    # --- 혼합 차원 정리(최빈 차원)
    lens = df["embedding"].apply(len)
    if not lens.empty:
        major_dim = lens.mode().iloc[0]
        df = df[lens == major_dim].reset_index(drop=True)
        print(f"유지 차원: {major_dim}, 행수: {len(df)}")

    # ✅ 최종적으로 ID를 '현재' 인덱스와 일치시켜 다시 세팅!
    df["ID"] = df.index.astype(int)

    print("로드된 컬럼:", list(df.columns))
    return df


# -----------------------------
# 3) 유틸: 안전한 코사인 유사도
# -----------------------------
def cos_sim(A: np.ndarray, B: np.ndarray) -> float:
    if A.shape != B.shape:
        return -1.0
    a, b = norm(A), norm(B)
    if a == 0 or b == 0:
        return -1.0
    return float(dot(A, B) / (a * b))


# -----------------------------
# 4) 검색 로직
# -----------------------------
def return_answer_candidate(df, query, top_k, api_key, min_score=None):
    embedding = get_embedding(query, api_key.replace("Bearer ", "")) # 순수 키 전달
    q = np.array(embedding, dtype=float)

    # 쿼리와 길이가 같은 임베딩만
    same_dim = df["embedding"].apply(lambda v: len(v) == q.shape[0])
    safe_df = df.loc[same_dim].copy()
    if safe_df.empty:
        return safe_df

    # 유사도 계산
    safe_df["similarity"] = safe_df["embedding"].apply(
        lambda x: cos_sim(np.array(x, dtype=float), q)
    )

    # 음수(차원 불일치/0벡터 등) 제거
    safe_df = safe_df[safe_df["similarity"] >= 0]

    # min_score 있으면 필터
    if min_score is not None:
        try:
            thr = float(min_score)
            safe_df = safe_df[safe_df["similarity"] >= thr]
        except Exception:
            pass

    return safe_df.sort_values("similarity", ascending=False).head(top_k)

def return_results(df, query, top_k, api_key, include_scores=True, min_score=None):
    result = return_answer_candidate(df, query, top_k, api_key, min_score=min_score)
    out = []
    for _, row in result.iterrows():
        item = {
            "id": str(row["ID"]),
            "content": str(row["text"]),
        }
        
        # ✅ 추가: answer(Completion) 컬럼 포함
        if "answer" in row.index:
            item["answer"] = str(row["answer"])
        
        # 📌 수정 3: source 컬럼 포함
        if "source" in row.index: 
            item["source"] = str(row.get("source", ""))
        
        if include_scores:
            item["score"] = round(float(row.get("similarity", 0.0)), 4)
        out.append(item)
    return out

# chat_logic.py에 포함되어야 할 함수지만, search_api.py에서 사용되므로 임시로 정의 (전체 구조 유지)
# SYSTEM_DATADRIVEN, REASONING_ENDPOINT, call_api, reranker_function 등이 chat_logic.py에 정의되어야 함
# 이 함수는 chat_logic.py에서 정의된 후 search_api.py에서 사용된다고 가정합니다.
# *********************************************************************************
# 아래 rag_with_reranker 코드는 chat_logic.py의 내용으로, search_api.py에서 실행되면
# 에러가 발생합니다. (chat_logic.py의 함수들을 임포트하지 않았기 때문입니다.)
# 원본 코드 구조 유지를 위해 주석 처리하고, 필요한 임포트만 추가했습니다.
# *********************************************************************************
# def rag_with_reranker(user_query: str, history: List[Dict[str, Any]], search_func: Callable) -> str:
#     ... (원본 코드)
#     return content or "답변을 생성할 수 없습니다."


# -----------------------------
# 5) FastAPI 모델/앱
# -----------------------------
class SearchInput(BaseModel):
    query: str
    top_k: int


class SearchResult(BaseModel):
    id: str
    content: str
    score: Optional[float] = None # response_model에 포함되어 있지 않아 response_model=SearchOutput에서 에러 발생 가능성 있음


class SearchOutput(BaseModel):
    result: List[SearchResult]


# API 키: 환경변수 권장 (PowerShell:  $env:NCLOVA_API_KEY="nv-..." )
# 기존 API_KEY를 API_KEY_WITH_BEARER로 사용
API_KEY = API_KEY_WITH_BEARER

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ① CSV 로드
    df = start()
    app.state.df = df

    # ② API 키 세팅
    app.state.api_key = API_KEY # Bearer 포함
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중에는 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# 6) 엔드포인트
# -----------------------------
@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}


@app.get("/health")
def health():
    df = getattr(app.state, "df", None)
    cols = list(df.columns) if df is not None else []
    n_rows = len(df) if df is not None else 0
    sample_dim = None
    if n_rows and "embedding" in cols:
        for v in df["embedding"]:
            if isinstance(v, list) and len(v) > 0:
                sample_dim = len(v)
                break
    return {
        "ok": True,
        "rows": n_rows,
        "columns": cols,
        "sample_embedding_dim": sample_dim
    }

import traceback

@app.post("/search/", response_model=SearchOutput)
async def search(input: SearchInput) -> SearchOutput:
    try:
        df = getattr(app.state, "df", None)
        api_key = getattr(app.state, "api_key", None)
        if df is None:
            raise RuntimeError("DF not loaded")
        if not api_key:
            raise RuntimeError("API key missing (set CLOVA_API_KEY env or app.state.api_key).")

        # return_results 내부에서 api_key의 "Bearer "를 제거하고 사용
        results = return_results(df, input.query, input.top_k, api_key, include_scores=False) # response_model에 score가 없으므로 False로 변경

        # SearchResult 모델에 score가 없으므로 SearchOutput에 맞게 필터링
        filtered_results = [{"id": r["id"], "content": r["content"]} for r in results]

        return SearchOutput(result=filtered_results)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("SEARCH ERROR:", e)
        print(tb)
        raise HTTPException(status_code=500, detail={"error": str(e), "trace": tb[:2000]})


# 📌 수정 4: 출처 필드를 포함하도록 모델 확장
class QASource(BaseModel):
    id: str
    question: str
    answer: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None # 출처 필드 추가

class QAOutput(BaseModel):
    answer: str
    sources: List[QASource]

@app.post("/search_answer", response_model=QAOutput)
async def search_answer(input: SearchInput) -> QAOutput:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key missing")

    hits = return_results(
        app.state.df, input.query, input.top_k, API_KEY,
        include_scores=True,  # 점수 포함
        min_score=None,
    )
    if not hits:
        return QAOutput(answer="관련 자료를 찾지 못했습니다.", sources=[])

    has_answer = "answer" in app.state.df.columns
    has_source = "source" in app.state.df.columns # 출처 컬럼 확인
    sources: List[QASource] = []

    def get_row_by_id(df, sid: str):
        try:
            iid = int(sid)
        except Exception:
            return None
        rows = df.loc[df["ID"] == iid]
        if not rows.empty:
            return rows.iloc[0]
        if 0 <= iid < len(df):
            return df.iloc[iid]
        return None

    for h in hits:
        row = get_row_by_id(app.state.df, h["id"])
        
        # 📌 수정 5: QASource에 source 필드 추가
        if row is None:
            sources.append(QASource(
                id=str(h["id"]),
                question=str(h.get("content", "")),
                answer=None,
                score=float(h.get("score")) if "score" in h else None,
                source=str(h.get("source", None)) if "source" in h else None,
            ))
            continue

        sources.append(QASource(
            id=str(h["id"]),
            question=str(row.get("text", "")),
            answer=str(row.get("answer")) if has_answer else None,
            score=float(h.get("score")) if "score" in h else None,
            source=str(row.get("source", None)) if has_source else None, # 출처 추가
        ))

    # 최종 답: 유사도 1등의 answer 우선, 없으면 질문 텍스트
    top = sources[0]
    final = (top.answer or top.question[:400] or "관련 자료를 찾지 못했습니다.").strip()
    return QAOutput(answer=final, sources=sources)

# ============================================================================
# chat_logic.py import
# ============================================================================
try:
    from chat_logic import chat_turn
    CHAT_LOGIC_AVAILABLE = True
except ImportError:
    print("[경고] chat_logic.py를 찾을 수 없습니다.")
    CHAT_LOGIC_AVAILABLE = False
    chat_turn = None


# ============================================================================
# 통합 채팅 엔드포인트
# ============================================================================
class ChatInput(BaseModel):
    query: str
    history: List[Dict[str, Any]] = []
    state: Dict[str, Any] = {"phase": "explore"}


class ChatOutput(BaseModel):
    answer: str
    history: List[Dict[str, Any]]
    state: Dict[str, Any]


@app.post("/chat_unified", response_model=ChatOutput)
async def chat_unified(input: ChatInput) -> ChatOutput:
    """
    통합 채팅 엔드포인트
    정책/규정 → RAG, 진로/상담 → 일반 생성형 대화
    """
    if not CHAT_LOGIC_AVAILABLE or chat_turn is None:
        raise HTTPException(
            status_code=500, 
            detail="chat_logic.py 모듈을 로드할 수 없습니다."
        )

    try:
        # chat_turn 함수가 search_func를 인자로 받도록 수정되어 있었으므로 유지
        reply, new_history, new_state = chat_turn(
            user_text=input.query,
            history=input.history,
            state=input.state,
            # search_func 인자를 넘겨줌
            search_func=lambda query, top_k, include_scores=True: return_results(
                app.state.df, query, top_k, API_KEY, include_scores, None
            ) 
        )

        return ChatOutput(
            answer=reply,
            history=new_history,
            state=new_state,
        )

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"CHAT UNIFIED ERROR: {e}")
        print(tb)

        error_msg = f"서버 오류가 발생했습니다. ({type(e).__name__})"

        return ChatOutput(
            answer=error_msg,
            history=input.history + [{"role": "assistant", "content": error_msg}],
            state=input.state,
        )