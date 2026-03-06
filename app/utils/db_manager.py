import sqlite3
import os
import pandas as pd
import bcrypt
from contextlib import contextmanager

DB_PATH = 'database/user_db.sqlite'
CSV_PATH = 'data/processed/math_tutor_dataset.csv'

# ──────────────────────────────────────────────
# 🔧 내부 유틸: DB 연결을 Context Manager로 관리
# with 블록이 끝나면 자동으로 commit & close 처리
# ──────────────────────────────────────────────

@contextmanager
def get_db():
    """
    DB 연결을 안전하게 열고 닫는 Context Manager.
    
    [변경 이유]
    기존: 함수마다 conn = sqlite3.connect(...) / conn.close() 를 반복
    → 예외 발생 시 close()가 호출되지 않아 연결이 누수될 위험이 있었음.
    변경: with get_db() as (conn, c): 로 호출하면 자동으로 정리됨.
    """
    if not os.path.exists('database'):
        os.makedirs('database')
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        yield conn, c
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# 🔐 내부 유틸: bcrypt 비밀번호 해싱 / 검증
# ──────────────────────────────────────────────
def hash_password(plain_password: str) -> str:
    """
    평문 비밀번호를 bcrypt로 해싱하여 반환합니다.
    
    [변경 이유]
    기존: 비밀번호를 '1234' 형태로 DB에 평문 저장
    → DB가 유출되면 비밀번호가 그대로 노출됨.
    변경: bcrypt는 해싱할 때마다 내부에 salt를 자동 생성하여
          같은 비밀번호도 매번 다른 해시값이 나와 보안에 강함.
    
    예시:
        hash_password("1234")
        → "$2b$12$eW3Fq...xyz" (매번 다른 값)
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    입력한 평문 비밀번호가 DB의 해시값과 일치하는지 검증합니다.
    
    예시:
        verify_password("1234", "$2b$12$eW3Fq...xyz") → True
        verify_password("wrong", "$2b$12$eW3Fq...xyz") → False
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


# ──────────────────────────────────────────────
# 1. 데이터베이스 초기화 (테이블 생성)
# ──────────────────────────────────────────────
def init_db():
    with get_db() as (conn, c):

        # 사용자 테이블
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT, current_unit TEXT)''')
        
        # 학습 이력 테이블
        c.execute('''CREATE TABLE IF NOT EXISTS learning_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT, 
                      problem_id TEXT, 
                      unit TEXT, 
                      is_correct INTEGER, 
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # ✅ [변경] 테스트 계정 비밀번호를 bcrypt 해시로 저장
        # 기존: INSERT OR IGNORE INTO users VALUES ('student01', '1234', 'None')
        # → 평문 '1234'가 DB에 그대로 저장되는 보안 취약점
        hashed_pw = hash_password("1234")
        c.execute(
            "INSERT OR IGNORE INTO users (username, password, current_unit) VALUES (?, ?, ?)",
            ('student01', hashed_pw, 'None')
        )


# ──────────────────────────────────────────────
# 2. 유저 조회 (로그인 인증용)
# ──────────────────────────────────────────────
def get_user(username: str) -> dict | None:
    """
    username으로 유저를 조회합니다. 없으면 None 반환.
    
    [변경 이유]
    기존: login.py에서 SELECT * WHERE username=? AND password=? 로 평문 비밀번호를 직접 비교
    → 비밀번호 해싱 도입 후에는 DB에서 유저를 먼저 가져온 뒤,
      verify_password()로 비교하는 방식으로 변경해야 함.
    
    사용 예시 (auth.py 라우터에서):
        user = get_user("student01")
        if user and verify_password(입력비밀번호, user["password"]):
            # 로그인 성공 → JWT 발급
    """
    with get_db() as (conn, c):
        # ✅ [변경] f-string 대신 파라미터 바인딩(?)으로 SQL Injection 방지
        # 기존 취약 코드: f"SELECT * FROM users WHERE username='{username}'"
        # → username에 "admin'--" 같은 값이 들어오면 쿼리 구조 자체가 변형됨
        c.execute(
            "SELECT username, password, current_unit FROM users WHERE username = ?",
            (username,)
        )
        row = c.fetchone()
    
    if row is None:
        return None
    return {"username": row[0], "password": row[1], "current_unit": row[2]}


# ──────────────────────────────────────────────
# 3. 유저 등록
# ──────────────────────────────────────────────
def create_user(username: str, plain_password: str) -> bool:
    """
    새 유저를 등록합니다. 이미 존재하면 False 반환.
    
    [추가 이유]
    기존 코드에는 회원가입 함수가 없었음.
    FastAPI 라우터에서 POST /auth/register 엔드포인트 구현 시 사용.
    """
    try:
        hashed_pw = hash_password(plain_password)
        with get_db() as (conn, c):
            c.execute(
                "INSERT INTO users (username, password, current_unit) VALUES (?, ?, ?)",
                (username, hashed_pw, 'None')
            )
        return True
    except sqlite3.IntegrityError:
        # username PRIMARY KEY 중복 시
        return False


# ──────────────────────────────────────────────
# 4. 학습 결과 저장
# ──────────────────────────────────────────────
def save_history(username: str, problem_id: str, unit: str, is_correct: bool):
    """
    문제 풀이 결과를 학습 이력에 저장합니다.
    
    [변경 사항] 기존 로직 유지, get_db() Context Manager로 교체
    """
    with get_db() as (conn, c):
        c.execute(
            "INSERT INTO learning_history (username, problem_id, unit, is_correct) VALUES (?, ?, ?, ?)",
            (username, str(problem_id), unit, 1 if is_correct else 0)
        )


# ──────────────────────────────────────────────
# 5. 학생의 전체 학습 이력 조회 (리포트용)
# ──────────────────────────────────────────────
def get_user_history(username: str) -> pd.DataFrame:
    """
    [변경 이유]
    기존: f"SELECT ... WHERE username = '{username}'"
    → SQL Injection 취약점. 파라미터 바인딩으로 교체.
    
    pd.read_sql_query()는 파라미터를 두 번째 인자(params)로 받음.
    """
    with get_db() as (conn, c):
        query = "SELECT unit, is_correct, timestamp FROM learning_history WHERE username = ?"
        df = pd.read_sql_query(query, conn, params=(username,))
    return df


# ──────────────────────────────────────────────
# 6. 틀린 문제 목록 조회 (오답 노트용)
# ──────────────────────────────────────────────
def get_incorrect_problems(username: str) -> list[dict]:
    """
    [변경 이유]
    기존: f-string으로 username 직접 삽입 → SQL Injection 취약점
    변경: params=(username,) 파라미터 바인딩으로 교체
    """
    with get_db() as (conn, c):
        query = """
            SELECT problem_id FROM learning_history 
            WHERE username = ?
            GROUP BY problem_id 
            HAVING SUM(is_correct) = 0
        """
        incorrect_ids = pd.read_sql_query(query, conn, params=(username,))['problem_id'].tolist()

    df = pd.read_csv(CSV_PATH)
    return df[df['ID'].astype(str).isin(incorrect_ids)].to_dict('records')