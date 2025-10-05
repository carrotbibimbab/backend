import os
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, constr

# (선택) .env 로컬 개발 시만 필요 — Render에서는 Environment에 넣으면 자동 주입
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ────────────────────────────────────────────────────────────
# Supabase: 환경변수로 초기화. 없으면 None(엔드포인트는 정상 동작, 로그만 패스)
# ────────────────────────────────────────────────────────────
supabase = None
try:
    from supabase import create_client, Client  # type: ignore
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Optional["Client"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        supabase = None
except Exception:
    supabase = None

# ────────────────────────────────────────────────────────────
# FastAPI & CORS
# ────────────────────────────────────────────────────────────
app = FastAPI(title="Backend API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # 운영에서는 허용 도메인만 넣으세요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────────────
# 기존 엔드포인트 (그대로 유지)
# ────────────────────────────────────────────────────────────
@app.get("/")
def get_tables_list():
    """
    데이터베이스의 public 스키마에 있는 테이블 목록을 조회합니다 (Supabase RPC: get_public_tables).
    """
    if not supabase:
        return {"warning": "Supabase not configured", "data": []}
    try:
        response = supabase.rpc("get_public_tables").execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}

@app.get("/profiles")
def get_profiles():
    """
    'profiles' 테이블에서 모든 사용자 프로필을 조회합니다.
    """
    if not supabase:
        return {"warning": "Supabase not configured", "data": []}
    try:
        response = supabase.table("profiles").select("*").execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}

@app.get("/products/{product_id}")
def get_product(product_id: int):
    """
    'products' 테이블에서 특정 ID의 제품을 조회합니다.
    """
    if not supabase:
        return {"warning": "Supabase not configured", "data": None}
    try:
        response = (
            supabase.table("products")
            .select("*")
            .eq("id", product_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        return {"error": str(e)}

# ────────────────────────────────────────────────────────────
# 새로 요청하신 4개 엔드포인트 (모델 + 로직 + API)
# ────────────────────────────────────────────────────────────

Undertone = Literal["cool", "warm", "neutral"]
SkinType = Literal["dry", "oily", "combination", "sensitive", "normal"]

class PersonalColorRequest(BaseModel):
    user_id: Optional[str] = None
    skin_tone: Optional[Literal["fair", "light", "medium", "tan", "deep"]] = None
    vein_color: Optional[Literal["blue", "green", "mixed"]] = None
    jewelry_preference: Optional[Literal["silver", "gold", "both"]] = None
    undertone_hint: Optional[Undertone] = None

class PersonalColorResult(BaseModel):
    undertone: Undertone
    season: Literal["spring", "summer", "autumn", "winter"]
    palette: List[str]

class SensitivityRequest(BaseModel):
    user_id: Optional[str] = None
    skin_type: Optional[SkinType] = None
    ingredients_reactions: List[constr(strip_whitespace=True, min_length=1)] = Field(
        default_factory=list
    )
    fragrance_sensitive: bool = False
    acne_prone: bool = False

class SensitivityResult(BaseModel):
    flags: List[str]
    avoid_ingredients: List[str]
    notes: str

class ComprehensiveRequest(BaseModel):
    user_id: Optional[str] = None
    personal: Optional[PersonalColorRequest] = None
    sensitivity: Optional[SensitivityRequest] = None

class ComprehensiveResult(BaseModel):
    user_id: Optional[str] = None
    personal: Optional[PersonalColorResult] = None
    sensitivity: Optional[SensitivityResult] = None
    recommendations: Dict[str, Any] = {}

# 내부 로직
def infer_undertone(req: PersonalColorRequest) -> Undertone:
    if req.undertone_hint in ("cool", "warm", "neutral"):
        return req.undertone_hint  # type: ignore
    if req.vein_color == "blue":
        return "cool"
    if req.vein_color == "green":
        return "warm"
    if req.jewelry_preference == "silver":
        return "cool"
    if req.jewelry_preference == "gold":
        return "warm"
    return "neutral"

def undertone_to_season(undertone: Undertone, skin_tone: Optional[str]) -> str:
    if undertone == "cool":
        return "summer" if skin_tone in ("fair", "light") else "winter"
    if undertone == "warm":
        return "spring" if skin_tone in ("fair", "light", "medium") else "autumn"
    return "spring" if skin_tone in ("fair", "light") else "autumn"

def season_palette(season: str) -> List[str]:
    palettes = {
        "spring": ["peach", "coral", "warm beige", "light olive", "mint"],
        "summer": ["cool pink", "lavender", "soft blue", "rose", "mauve"],
        "autumn": ["terracotta", "olive", "mustard", "warm brown", "teal"],
        "winter": ["true red", "black", "white", "emerald", "cobalt"],
    }
    return palettes.get(season, ["neutral"])

def analyze_personal_color(req: PersonalColorRequest) -> PersonalColorResult:
    u = infer_undertone(req)
    s = undertone_to_season(u, req.skin_tone)
    p = season_palette(s)
    return PersonalColorResult(undertone=u, season=s, palette=p)

def analyze_sensitivity(req: SensitivityRequest) -> SensitivityResult:
    flags: List[str] = []
    avoid: List[str] = []

    low = [i.lower() for i in req.ingredients_reactions]

    if req.fragrance_sensitive or "fragrance" in low:
        flags.append("fragrance_sensitive")
        avoid.append("fragrance")

    if req.acne_prone or "pore clogging" in low:
        flags.append("acne_prone")
        avoid.extend(["heavy oils", "isopropyl myristate"])

    if req.skin_type == "dry":
        flags.append("dry_skin");     avoid.append("high alcohol")
    if req.skin_type == "oily":
        flags.append("oily_skin");    avoid.append("heavy occlusives")
    if req.skin_type == "sensitive":
        flags.append("sensitive_skin"); avoid.extend(["strong AHA/BHA", "retinoid (high)"])

    if "alcohol" in low:
        avoid.append("alcohol")
    if "aha" in low:
        avoid.append("strong AHA")

    avoid = sorted(set(avoid))
    notes = "개인 민감도와 피부 타입에 맞춰 성분 라벨을 확인하세요."
    return SensitivityResult(flags=flags, avoid_ingredients=avoid, notes=notes)

def save_log(kind: str, user_id: Optional[str], payload: dict, result: dict) -> None:
    if not supabase:
        return
    try:
        supabase.table("analysis_logs").insert({
            "kind": kind,
            "user_id": user_id,
            "payload": payload,
            "result": result,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }).execute()
    except Exception:
        pass

# ① Health
@app.get("/api/v1/analysis/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}

# ② Personal Color
@app.post("/api/v1/analysis/personal-color", response_model=PersonalColorResult)
def api_personal_color(req: PersonalColorRequest):
    try:
        res = analyze_personal_color(req)
        save_log("personal-color", req.user_id, req.model_dump(), res.model_dump())
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ③ Sensitivity
@app.post("/api/v1/analysis/sensitivity", response_model=SensitivityResult)
def api_sensitivity(req: SensitivityRequest):
    try:
        res = analyze_sensitivity(req)
        save_log("sensitivity", req.user_id, req.model_dump(), res.model_dump())
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ④ Comprehensive
@app.post("/api/v1/analysis/comprehensive", response_model=ComprehensiveResult)
def api_comprehensive(req: ComprehensiveRequest):
    try:
        personal_res = analyze_personal_color(req.personal or PersonalColorRequest()) if req.personal is not None else None
        sensi_res = analyze_sensitivity(req.sensitivity or SensitivityRequest()) if req.sensitivity is not None else None

        recs: Dict[str, Any] = {}
        if personal_res:
            recs["palette"] = personal_res.palette
        if sensi_res:
            recs["avoid"] = sensi_res.avoid_ingredients

        res = ComprehensiveResult(
            user_id=req.user_id,
            personal=personal_res,
            sensitivity=sensi_res,
            recommendations=recs,
        )
        save_log("comprehensive", req.user_id, req.model_dump(), res.model_dump())
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
