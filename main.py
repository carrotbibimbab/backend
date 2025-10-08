import os
from datetime import datetime, timedelta  # ← datetime 유지 + timedelta 추가
from typing import List, Optional, Literal, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends  # ← Depends 포함
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from itsdangerous import URLSafeSerializer
from dotenv import load_dotenv
from pydantic import BaseModel, Field, constr
from fastapi.routing import APIRoute
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # ← 추가
import jwt  # ← 추가 (PyJWT)

# ────────────────────────────────────────────────────────────
# Env
# ────────────────────────────────────────────────────────────
try:
    load_dotenv()  # 로컬 개발 시에만 의미 있음 (Render는 Dashboard 환경변수 사용)
except Exception:
    pass

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# ────────────────────────────────────────────────────────────
# FastAPI
# ────────────────────────────────────────────────────────────
app = FastAPI(title="Backend API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 운영에서는 허용 도메인만 지정 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 세션 (구글 로그인에 필요)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60*60*24*7)

templates = Jinja2Templates(directory="templates")

# ────────────────────────────────────────────────────────────
# Supabase (옵셔널)
# ────────────────────────────────────────────────────────────
supabase = None
try:
    from supabase import create_client, Client  # type: ignore
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # type: ignore
except Exception:
    supabase = None

# ────────────────────────────────────────────────────────────
# Google OAuth (Authlib)
# ────────────────────────────────────────────────────────────
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID or "",
    client_secret=GOOGLE_CLIENT_SECRET or "",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile", "prompt": "select_account"},
)

state_signer = URLSafeSerializer(SECRET_KEY, salt="oauth-state")

# ────────────────────────────────────────────────────────────
# JWT 발급/검증 (우리 서버용)
# ────────────────────────────────────────────────────────────
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

def create_access_token(subject: dict, expires_minutes: int | None = None) -> str:
    """우리 서버용 액세스 토큰 발급 (PyJWT)"""
    exp = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": exp, **subject}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """우리 서버용 액세스 토큰 검증 (PyJWT)"""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

_bearer = HTTPBearer(auto_error=False)

def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """
    보호 라우트에서 호출되는 공용 의존성.
    1) Authorization: Bearer <JWT> 있으면 → JWT 검증해서 사용자 리턴
    2) 없으면 세션 로그인 사용자(request.session['user'])를 대체로 허용
    """
    # 1) Authorization 헤더 우선 (앱/클라이언트 사용)
    if creds and creds.scheme.lower() == "bearer":
        try:
            payload = decode_token(creds.credentials)
            # 우리 JWT는 발급 시 user 정보를 그대로 넣음
            return {
                "sub": payload.get("sub"),
                "email": payload.get("email"),
                "name": payload.get("name"),
                "picture": payload.get("picture"),
            }
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 2) 세션 로그인(브라우저 사용)
    user = request.session.get("user")
    if user:
        return user

    # 둘 다 없으면 미인증
    raise HTTPException(status_code=401, detail="Not authenticated")

# ────────────────────────────────────────────────────────────
# 기본 페이지
# ────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("login.html", {"request": request, "user": user})

@app.get("/login")
async def login(request: Request):
    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/google/callback"  # ← 경로 통일 + rstrip로 슬래시 중복 방지
    state = state_signer.dumps({"next": request.query_params.get("next", "/profile")})
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)

@app.get("/auth/google/callback")
async def auth_callback(request: Request):
    raw_state = request.query_params.get("state")
    try:
        parsed = state_signer.loads(raw_state) if raw_state else {"next": "/profile"}
    except Exception:
        return RedirectResponse(url="/?error=invalid_state")

    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            resp = await oauth.google.parse_id_token(request, token)
            userinfo = resp
    except Exception:
        return RedirectResponse(url="/?error=oauth_error")

    request.session["user"] = {
        "sub": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    return RedirectResponse(url=parsed.get("next", "/profile"))

@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@app.get("/me")
def me_api(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "user": user}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# ────────────────────────────────────────────────────────────
# 우리 JWT 발급 / 검증 라우트
# ────────────────────────────────────────────────────────────
@app.post("/auth/google/jwt")
def issue_our_jwt(request: Request):
    """
    (사용 시나리오)
    - 브라우저에서 구글 로그인(세션 저장) 완료 후 앱으로 토큰 전달하거나,
    - 앱이 /login → /auth/google/callback 흐름을 밟은 후에 JWT가 필요할 때 호출.
    동작: 세션에 저장된 user로 우리 JWT를 발급해 줍니다.
    """
    user = request.session.get("user")
    if not user:
        # 세션이 없으면, 프런트에서 받아온 Google ID Token을 검증해서 발급하는 방식으로 바꿔도 됨
        # (현재 구조 유지 위해, 세션 기반으로만 발급)
        raise HTTPException(status_code=401, detail="Login required (session)")

    token = create_access_token(
        {
            "sub": user.get("sub"),
            "email": user.get("email"),
            "name": user.get("name"),
            "picture": user.get("picture"),
            "provider": "google",
        }
    )
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me-jwt")
def me_jwt(user: dict = Depends(get_current_user)):
    """
    보호 엔드포인트 예시.
    - 앱: Authorization: Bearer <our JWT> 로 접근
    - 브라우저: 세션으로도 접근 가능 (위 get_current_user가 세션도 허용)
    """
    return {"authenticated": True, "user": user}

# --- app 관련 라우트들 아래쪽(예: /logout 다음)에 추가 ---
@app.get("/__routes", tags=["debug"])
def list_routes():
    # 앱에 등록된 실제 경로만 보기 좋게 정리
    return sorted([r.path for r in app.routes if isinstance(r, APIRoute)])

# ────────────────────────────────────────────────────────────
# 기존 API (Supabase 사용 예시들)
# ────────────────────────────────────────────────────────────
@app.get("/tables")
def get_tables_list():
    if not supabase:
        return {"warning": "Supabase not configured", "data": []}
    try:
        resp = supabase.rpc("get_public_tables").execute()
        return resp.data
    except Exception as e:
        return {"error": str(e)}

@app.get("/profiles")
def get_profiles():
    if not supabase:
        return {"warning": "Supabase not configured", "data": []}
    try:
        resp = supabase.table("profiles").select("*").execute()
        return resp.data
    except Exception as e:
        return {"error": str(e)}

@app.get("/products/{product_id}")
def get_product(product_id: int):
    if not supabase:
        return {"warning": "Supabase not configured", "data": None}
    try:
        resp = supabase.table("products").select("*").eq("id", product_id).single().execute()
        return resp.data
    except Exception as e:
        return {"error": str(e)}

# ────────────────────────────────────────────────────────────
# 분석 엔드포인트 (요청하신 4개 요약)
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
    ingredients_reactions: List[constr(strip_whitespace=True, min_length=1)] = Field(default_factory=list)
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

@app.get("/api/v1/analysis/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}

@app.post("/api/v1/analysis/personal-color", response_model=PersonalColorResult)
def api_personal_color(req: PersonalColorRequest):
    try:
        res = analyze_personal_color(req)
        save_log("personal-color", req.user_id, req.model_dump(), res.model_dump())
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/analysis/sensitivity", response_model=SensitivityResult)
def api_sensitivity(req: SensitivityRequest):
    try:
        res = analyze_sensitivity(req)
        save_log("sensitivity", req.user_id, req.model_dump(), res.model_dump())
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
