"""
auth.py
-------
인증 유틸리티 모듈

- SQLite users DB 관리
- bcrypt 비밀번호 해싱/검증
- JWT 토큰 발급/검증
- 유저 CRUD
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt

# ── 설정 ──────────────────────────────────────────────────────────────────────
# 실제 배포 시 환경변수(SECRET_KEY)로 교체하세요
SECRET_KEY = "preview-capstone-secret-2026"
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 24

USERS_DB   = Path(__file__).parent / "users.db"
pwd_ctx    = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── DB 초기화 ─────────────────────────────────────────────────────────────────

def init_users_db() -> None:
    """users 테이블 생성 (없을 때만)"""
    with sqlite3.connect(USERS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role            TEXT NOT NULL DEFAULT 'user',
                created_at      TEXT NOT NULL
            )
        """)
        conn.commit()


# ── 비밀번호 ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """유효한 토큰이면 payload dict 반환, 아니면 None"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── 유저 CRUD ────────────────────────────────────────────────────────────────

def get_user(username: str) -> Optional[dict]:
    """username으로 유저 조회 (hashed_password 포함)"""
    with sqlite3.connect(USERS_DB) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    """전체 유저 목록 (비밀번호 제외)"""
    with sqlite3.connect(USERS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "user") -> bool:
    """유저 생성. username 중복이면 False 반환."""
    try:
        with sqlite3.connect(USERS_DB) as conn:
            conn.execute(
                """INSERT INTO users (username, hashed_password, role, created_at)
                   VALUES (?, ?, ?, ?)""",
                (username, hash_password(password), role,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_user(username: str) -> bool:
    """
    유저 삭제. admin 계정은 삭제 불가.
    삭제 성공이면 True, 없거나 admin이면 False.
    """
    with sqlite3.connect(USERS_DB) as conn:
        cursor = conn.execute(
            "DELETE FROM users WHERE username = ? AND role != 'admin'",
            (username,),
        )
        conn.commit()
    return cursor.rowcount > 0
