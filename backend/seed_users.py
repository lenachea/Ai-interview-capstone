"""
seed_users.py
-------------
최초 1회만 실행하세요.

수행 작업:
  1. users.db 초기화 (users 테이블 생성)
  2. 아래 ACCOUNTS 목록으로 계정 생성
  3. results_db.json 기존 기록에 username='admin' 필드 추가

실행:
    cd backend
    python seed_users.py
"""
import json
import sys
from pathlib import Path

# backend/ 디렉터리가 sys.path에 있어야 auth 모듈을 찾습니다
sys.path.insert(0, str(Path(__file__).parent))

from auth import init_users_db, create_user

# ── 생성할 계정 목록 (원하는 대로 수정하세요) ────────────────────────────────
ACCOUNTS = [
    # (username,  password,     role)
    ("admin",   "admin1234",  "admin"),
    ("test01",  "test1234",   "user"),
    ("test02",  "test1234",   "user"),
    ("test03",  "test1234",   "user"),
]
# ─────────────────────────────────────────────────────────────────────────────


def seed():
    # 1. DB 초기화
    init_users_db()
    print("✓ users.db 초기화 완료\n")

    # 2. 계정 생성
    print("── 계정 생성 ──────────────────────────")
    for username, password, role in ACCOUNTS:
        ok = create_user(username, password, role)
        status = "생성" if ok else "이미 존재 (건너뜀)"
        print(f"  [{role:5s}] {username:10s} → {status}")

    # 3. results_db.json 마이그레이션
    db_path = Path(__file__).parent / "results_db.json"
    print("\n── results_db.json 마이그레이션 ────────")
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            records = json.load(f)

        updated = 0
        for r in records:
            if "username" not in r:
                r["username"] = "admin"
                updated += 1

        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        print(f"  {updated}개 레코드에 username='admin' 추가")
        print(f"  (이미 있는 {len(records) - updated}개는 그대로 유지)")
    else:
        print("  results_db.json 없음 — 건너뜀")

    print("\n✓ 완료! 이제 서버를 시작하세요.")
    print("  uvicorn main:app --reload --port 8000")


if __name__ == "__main__":
    seed()
