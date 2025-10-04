import os
from fastapi import FastAPI
from supabase import create_client, Client
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# FastAPI 앱 생성
app = FastAPI()

# Supabase 클라이언트 초기화
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# --- 디버깅 코드 시작 ---
print("="*80)
print(f"[DEBUG] FastAPI is attempting to connect to Supabase URL: {url}")
print("="*80)
# --- 디버깅 코드 끝 ---

@app.get("/")
def get_tables_list():
    """
    데이터베이스의 public 스키마에 있는 테이블 목록을 조회합니다.
    """
    try:
        # Supabase RPC를 통해 'get_public_tables' 함수를 호출합니다.
        response = supabase.rpc('get_public_tables').execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}

# 프로필 목록을 조회하는 API 엔드포인트
@app.get("/profiles")
def get_profiles():
    """
    'profiles' 테이블에서 모든 사용자 프로필을 조회합니다.
    """
    try:
        response = supabase.table('profiles').select("*").execute()
        
        # API 응답에서 실제 데이터만 추출하여 반환
        return response.data
    except Exception as e:
        return {"error": str(e)}

# 특정 ID의 제품을 조회하는 예시
@app.get("/products/{product_id}")
def get_product(product_id: int):
    """
    'products' 테이블에서 특정 ID의 제품을 조회합니다.
    """
    try:
        response = supabase.table('products').select("*").eq('id', product_id).single().execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}