# app.py (검색 + 챗봇 통합 완성판)
# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

import os
import json
import pandas as pd
import numpy as np
from numpy import dot
from numpy.linalg import norm
import ast
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import requests
import time

API_KEY = os.getenv("NCLOUD_API_KEY", "")
if not API_KEY:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")

FILE_PATH = os.getenv("DATA_FILE_PATH", "./data_final_emb.csv")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ============================================================================
# chat_logic.py import
# ============================================================================
try:
    from chat_logic import chat_turn
    CHAT_ENABLED = True
    print("✅ chat_logic.py 로드 성공")
except ImportError as e:
    print(f"⚠️ chat_logic.py를 찾을 수 없습니다: {e}")
    CHAT_ENABLED = False
    chat_turn = None

# ============================================================================
# FastAPI 앱 생성
# ============================================================================
app = FastAPI(title="WECHu 통합 API (검색 + 챗봇)")

# CORS 설정 (프론트엔드 연결용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중: 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 검색 API 설정 (기존 코드)
# ============================================================================
EMBEDDING_API_URL = "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2"

embedding_cache = {}
# ============================================================================
# 검색 관련 함수 (기존 코드 유지)
# ============================================================================
def get_embedding(input_text: str, api_key: str, max_retries: int = 3):
    # 캐시 확인
    if input_text in embedding_cache:
        print(f"[Embedding 캐시 사용] {input_text[:50]}...")
        return embedding_cache[input_text]
    
    if not api_key or api_key == "API_KEY_HERE":
        raise HTTPException(status_code=500, detail="API 키가 비어있습니다.")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {"text": input_text}
    
    # 재시도 로직
    for attempt in range(max_retries):
        try:
            resp = requests.post(EMBEDDING_API_URL, headers=headers, json=data, timeout=20)
            resp.raise_for_status()
            
            embedding = resp.json()["result"]["embedding"]
            
            # 캐시에 저장
            embedding_cache[input_text] = embedding
            
            return embedding
        
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:  # Rate limit
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 5초, 10초, 15초...
                    print(f"[Embedding API] Rate limit 초과, {wait_time}초 대기 중...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise HTTPException(
                        status_code=502, 
                        detail="Embedding API rate limit 초과. 잠시 후 다시 시도하세요."
                    )
            else:
                raise HTTPException(
                    status_code=502, 
                    detail=f"Embedding API 오류: {resp.status_code}"
                )
        
        except Exception as e:
            raise HTTPException(
                status_code=502, 
                detail=f"Embedding API 오류: {str(e)}"
            )

def start():
    if not os.path.isfile(FILE_PATH):
        raise FileNotFoundError(FILE_PATH)
    
    print(f"📂 {FILE_PATH} 파일 로드 중...")
    df = pd.read_csv(FILE_PATH, encoding="utf-8")
    
    # ✅ 컬럼 확인 및 변환 (대소문자 구분 없이)
    if "text" not in df.columns:
        if "Completion" in df.columns:  # ← 대문자!
            print("[데이터 통합] Completion → text")
            df["text"] = df["Completion"]
        elif "answer" in df.columns:
            print("[데이터 통합] answer → text")
            df["text"] = df["answer"]
        elif "Text" in df.columns:  # ← 대문자!
            print("[데이터 통합] Text → text")
            df["text"] = df["Text"]
        elif "dialog_text" in df.columns:
            print("[데이터 통합] dialog_text → text")
            df["text"] = df["dialog_text"]
        elif "content" in df.columns:
            print("[데이터 통합] content → text")
            df["text"] = df["content"]
        else:
            print(f"❌ 사용 가능한 컬럼: {df.columns.tolist()}")
            raise ValueError("CSV 파일에 적절한 텍스트 컬럼이 없습니다.")
    
    # ID 컬럼 확인
    if "ID" not in df.columns:
        if "C_ID" in df.columns:  # ← 대문자!
            df["ID"] = df["C_ID"]
        else:
            df["ID"] = df.index
    
    # 임베딩 파싱
    def parse_emb(x):
        try:
            return json.loads(x)
        except Exception:
            return ast.literal_eval(x)
    
    df["embedding"] = df["embedding"].apply(parse_emb)
    
    print(f"✅ DataFrame 로드 완료: {len(df)}개 문서")
    
    # 샘플 확인
    print("\n[샘플 데이터]")
    if len(df) > 0:
        sample_idx = df[df['text'].str.contains('재수강', na=False)].index
        if len(sample_idx) > 0:
            sample = df.loc[sample_idx[0]]
            print(f"ID: {sample['ID']}")
            print(f"내용: {sample['text'][:200]}...")
        else:
            print("재수강 관련 데이터 없음")
    
    return df

def cos_sim(A, B):
    A = np.array(A, dtype=float)
    B = np.array(B, dtype=float)
    denom = norm(A) * norm(B)
    return float(dot(A, B) / denom) if denom else 0.0

def return_answer_candidate(df, query, top_k, api_key):
    q_emb = get_embedding(query, api_key)
    tmp = df.copy()
    tmp["similarity"] = tmp["embedding"].apply(lambda x: cos_sim(x, q_emb))
    return tmp.sort_values("similarity", ascending=False).head(top_k)

def return_results(df, query, top_k, api_key, include_scores=False):
    top_k = min(top_k, len(df))
    if top_k <= 0:
        return []
    result = return_answer_candidate(df, query, top_k, api_key)
    
    results = []
    for i in range(top_k):
        item = {
            "id": str(result.iloc[i]['ID']), 
            "content": str(result.iloc[i]['text'])
        }
        if include_scores:
            item["score"] = float(result.iloc[i].get('similarity', 0.0))
        results.append(item)
    
    return results

# ============================================================================
# 검색 API 모델
# ============================================================================
class SearchInput(BaseModel):
    query: str
    top_k: int

class SearchResult(BaseModel):
    id: str
    content: str

class SearchOutput(BaseModel):
    result: List[SearchResult]

# ============================================================================
# 챗봇 API 모델
# ============================================================================
class ChatInput(BaseModel):
    query: str
    history: List[Dict[str, Any]] = []
    state: Dict[str, Any] = {"phase": "explore"}

class ChatOutput(BaseModel):
    answer: str
    history: List[Dict[str, Any]]
    state: Dict[str, Any]

# ============================================================================
# 데이터 로드
# ============================================================================
try:
    DF = start()
    
    # ✅ chat_logic.py가 search_api를 import할 때 사용할 수 있도록 설정
    app.state.df = DF
    app.state.api_key = API_KEY
    
except Exception as e:
    print(f"❌ DataFrame 로드 실패: {e}")
    DF = pd.DataFrame()
    app.state.df = DF
    app.state.api_key = API_KEY

# ============================================================================
# 엔드포인트 1: 루트
# ============================================================================
@app.get("/")
def root():
    return {
        "status": "ok", 
        "service": "WECHu 통합 API",
        "rows": len(DF), 
        "endpoints": {
            "search": "/search/",
            "chat": "/chat_unified"
        },
        "chat_enabled": CHAT_ENABLED
    }

# ============================================================================
# 엔드포인트 2: 검색 API (기존)
# ============================================================================
@app.post("/search/", response_model=SearchOutput)
async def search(input: SearchInput) -> SearchOutput:
    """유사도 기반 문서 검색"""
    results = return_results(DF, input.query, input.top_k, API_KEY)
    return SearchOutput(result=results)

# ============================================================================
# 엔드포인트 3: 챗봇 API (신규!)
# ============================================================================
@app.post("/chat_unified", response_model=ChatOutput)
async def chat_unified(input: ChatInput) -> ChatOutput:
    """
    통합 채팅 엔드포인트
    - 정책/규정 질문 → RAG (검색 기반)
    - 진로/상담 질문 → 일반 생성형 대화
    """
    
    # 1. chat_turn 함수 가용성 확인
    if not CHAT_ENABLED or chat_turn is None:
        error_msg = "챗봇 모듈을 로드할 수 없습니다. chat_logic.py 파일을 확인하세요."
        return ChatOutput(
            answer=error_msg,
            history=input.history + [{"role": "assistant", "content": error_msg}],
            state=input.state,
        )
    
    try:
        # 2. chat_logic.py의 chat_turn 호출
        reply, new_history, new_state = chat_turn(
            input.query, 
            input.history, 
            input.state,
            search_func=lambda query, top_k, include_scores=True: return_results(
                DF, query, top_k, API_KEY, include_scores
            )
        )
        
        # 3. 응답 반환
        return ChatOutput(
            answer=reply,
            history=new_history,
            state=new_state,
        )
    
    except Exception as e:
        # 4. 오류 처리
        import traceback
        tb = traceback.format_exc()
        print(f"❌ CHAT UNIFIED ERROR: {e}")
        print(tb)
        
        error_msg = f"서버 오류가 발생했습니다. ({type(e).__name__})"
        
        return ChatOutput(
            answer=error_msg,
            history=input.history + [{"role": "assistant", "content": error_msg}],
            state=input.state,
        )

# ============================================================================
# 서버 실행
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*70)
    print("🚀 WECHu 통합 서버 시작")
    print("="*70)
    print(f"📊 검색 문서: {len(DF)}개")
    print(f"💬 챗봇 모듈: {'✅ 활성화' if CHAT_ENABLED else '❌ 비활성화'}")
    print(f"🌐 엔드포인트:")
    print(f"   - GET  /              : 서버 상태")
    print(f"   - POST /search/       : 문서 검색")
    print(f"   - POST /chat_unified  : 챗봇 대화")
    print("="*70)
    print(f"📂 데이터 파일: {FILE_PATH}")
    print(f"🔑 API 키: {API_KEY[:20]}...")
    print("="*70 + "\n")
    
    uvicorn.run(app, host=HOST, port=PORT)
