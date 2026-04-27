# chat_logic_embedding_with_source.py (임베딩에 출처 포함 버전)
# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
load_dotenv()

import http.client
import json
import time
import pandas as pd
from typing import Dict, Any

SRC = os.getenv("SOURCE_CSV_PATH", "./data_final.csv")
OUT = os.getenv("OUTPUT_CSV_PATH", "./data_final_emb_with_src.csv")
API_KEY = os.getenv("NCLOUD_API_KEY", "")

if not API_KEY:
    raise ValueError("NCLOUD_API_KEY가 설정되지 않았습니다.")

# --- [기존 CompletionExecutor 클래스 그대로 유지] --------------------------------
class CompletionExecutor:
    """CLOVA Studio Embedding API V2 호출을 위한 Executor"""
    def __init__(self, host, api_key, request_id):
        self._host = host
        self._api_key = api_key
        self._request_id = request_id

    def _send_request(self, completion_request):
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': self._api_key, 
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id
        }
        conn = http.client.HTTPSConnection(self._host)
        conn.request('POST', '/v1/api-tools/embedding/v2', json.dumps(completion_request), headers)
        response = conn.getresponse()
        result = json.loads(response.read().decode(encoding='utf-8'))
        conn.close()
        return result

    def execute(self, completion_request):
        res = self._send_request(completion_request)
        if res['status']['code'] == '20000':
            return res['result']
        else:
            print(f"[Embedding Error] Code: {res['status']['code']}, Message: {res['status']['message'][:100]}")
            return 'Error'
# ---------------------------------------------------------------------------

# ---------- 여기서부터 수정된 임베딩 로직 ---------------------------------------
SLEEP_SEC = 1.0                   # 레이트리밋 완화용 간격(필요시 조절)

def build_first_turn_text(row: Dict[str, Any]) -> str:
    """
    대화의 첫 턴(U:Text + A:Completion)과 출처(Source_Name)를 합쳐 
    임베딩 요청 텍스트 생성
    """
    u = (row.get("Text") or "").strip()
    a = (row.get("Completion") or "").strip()
    src = (row.get("Source_Name") or "출처없음").strip()
    
    # U: / A: 형식으로 대화 구성
    parts = []
    if u: parts.append(f"U: {u}")
    if a: parts.append(f"A: {a}")
    
    dialog_text = "\n".join(parts)
    
    # 출처를 텍스트 맨 뒤에 추가하여 임베딩에 포함 (핵심 수정 부분)
    if dialog_text:
        return f"{dialog_text}\n(출처: {src})"
    else:
        return f"(출처: {src})" # 대화 내용이 없을 경우 최소한 출처라도 포함

if __name__ == '__main__':
    # 1) 실행기 생성 (api_key는 'Bearer {키}' 형태로 직접 넣어줘)
    completion_executor = CompletionExecutor(
        host='clovastudio.stream.ntruss.com',
        
        api_key=f"Bearer {API_KEY}",
        
        request_id='15f38c1a973444628154ff3a242df590'
    )

    # 2) CSV 로드 & 대화별 첫 턴만 추출
    if not os.path.isfile(SRC):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {SRC}")

    df = pd.read_csv(SRC, encoding="utf-8")
    
    # 실제 데이터의 컬럼 이름에 맞게 수정 (T_ID, Text, Completion, Source_Name 필요)
    # *사용자의 데이터 예시를 보면 Source_Name이 Text/Completion과 합쳐져 보였으나, 
    # 일반적인 CSV 구조를 가정하고 "Source_Name" 컬럼이 있다고 가정합니다.*
    NEED_COLUMNS = {"C_ID", "T_ID", "Text", "Completion", "Source_Name"} 
    if not NEED_COLUMNS.issubset(df.columns):
        missing = NEED_COLUMNS - set(df.columns)
        print(f"[경고] 필수 컬럼 누락: {missing}")
        # 누락된 컬럼에 빈 문자열 또는 '출처없음'으로 대체 (Source_Name 누락 시 에러 방지)
        for col in missing:
            df[col] = "" if col != "Source_Name" else "출처없음"

    # C_ID별 T_ID 오름차순 → 첫 행만(=첫 턴) 사용
    first_turns = (
        df.sort_values(["C_ID","T_ID"])
          .groupby("C_ID", as_index=False)
          .first()
    )

    # 3) 대화당 1회 임베딩 호출
    rows = []
    total = len(first_turns)
    print(f"총 {total}개의 대화 턴 임베딩 시작...")
    
    for idx, row in first_turns.iterrows():
        cid = row["C_ID"]
        source_name = row["Source_Name"] # 출처 이름 별도 저장
        
        # 임베딩 요청 텍스트 생성 (여기에 출처 정보가 포함됨)
        req_text = build_first_turn_text(row) 
        
        # 네 executor가 원하는 요청 포맷 생성
        request_data = json.loads(
            json.dumps({"text": req_text}, ensure_ascii=False),
            strict=False
        )

        result = completion_executor.execute(request_data) 
        if result == "Error":
            emb = [] 
        else:
            emb = result.get("embedding", [])

        # 결과 저장 시, 임베딩된 텍스트와 출처 이름을 모두 저장
        rows.append({
            "C_ID": cid, 
            "dialog_text": req_text, 
            "source_name": source_name, # 원본 출처 이름 (나중에 찾기 쉽게)
            "embedding": json.dumps(emb)
        })

        # 과호출 경고 완화용 간격
        if (idx + 1) % 10 == 0:
            print(f"progress {idx+1}/{total}")
        time.sleep(SLEEP_SEC)

    # 4) 저장
    out_df = pd.DataFrame(rows, columns=["C_ID", "dialog_text", "source_name", "embedding"])
    out_df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {OUT} (conversations={len(out_df)})")