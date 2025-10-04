# FastAPI Supabase 백엔드 프로젝트

이 프로젝트는 FastAPI를 사용하여 구축된 백엔드 서버이며, Supabase 데이터베이스와 연동됩니다.

## 사전 준비

- Python 3.8 이상

## 프로젝트 설정 절차

1.  **저장소 복제 (Clone Repository)**
    ```shell
    # git clone <your-repository-url>
    # cd backend
    ```

2.  **가상 환경 생성**
    프로젝트 폴더 내에 `venv`라는 이름의 가상 환경을 생성합니다.
    ```shell
    python -m venv venv
    ```

3.  **가상 환경 활성화**
    -   **Windows의 경우:**
        ```shell
        venv\Scripts\activate
        ```
    -   **macOS / Linux의 경우:**
        ```shell
        source venv/bin/activate
        ```

4.  **필요 패키지 설치**
    `requirements.txt` 파일에 명시된 모든 라이브러리를 한 번에 설치합니다.
    ```shell
    pip install -r requirements.txt
    ```

5.  **`.env` 환경 변수 파일 생성**
    프로젝트 루트 위치에 `.env` 파일을 직접 생성하고, 아래 내용을 채워넣으세요.
    ```ini
    SUPABASE_URL="YOUR_SUPABASE_URL"
    SUPABASE_KEY="YOUR_SUPABASE_SERVICE_ROLE_KEY"
    ```
    -   `SUPABASE_URL`: Supabase 대시보드의 **Project Settings > API** 페이지에서 찾을 수 있습니다.
    -   `SUPABASE_KEY`: 같은 페이지에 있는 **`service_role` 비밀 키**를 사용해야 합니다.

## 개발 서버 실행

모든 설정이 완료되면, 아래 명령어로 로컬 개발 서버를 실행할 수 있습니다.

```shell
uvicorn main:app --reload
```

서버는 `http://127.0.0.1:8000` 주소에서 실행됩니다.
