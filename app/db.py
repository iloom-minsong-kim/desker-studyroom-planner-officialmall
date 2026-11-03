"""응답 저장소.

- DATABASE_URL 이 있으면 PostgreSQL(사내 Supabase) 사용
  · 사내 발급 DB는 전용 스키마에서만 쓸 수 있어 접속할 때마다 search_path 를 그 스키마로 맞춘다
    (DB_SCHEMA 가 없으면 계정 이름 app_<YYMMDD>_<코드>_user.<ref> 에서 app_<YYMMDD>_<코드> 를 읽는다)
  · 계정당 동시 접속 5개 제한 → 풀 최대 DB_POOL_MAX(기본 3)
- 없으면 DATA_DIR/responses.db (SQLite) 사용 — 로컬 개발·승인 전 테스트용

쿼리는 '?' 자리표시자로 쓰고 PostgreSQL 에서는 '%s' 로 바꿔 실행한다.
"""
import os
import re
import sqlite3
from urllib.parse import unquote, urlparse
import threading
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
POOL_MAX = max(1, min(4, int(os.getenv("DB_POOL_MAX", "3"))))


def _schema():
    name = os.getenv("DB_SCHEMA", "").strip()
    if not name and IS_PG:
        user = unquote(urlparse(DATABASE_URL).username or "")
        m = re.match(r"^(app_\d{6}_[a-z0-9]+)_user\.", user)
        name = m.group(1) if m else ""
    if name and not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ValueError("DB_SCHEMA 형식이 올바르지 않아요.")
    return name


SCHEMA = _schema()

_pool = None
_sqlite_lock = threading.Lock()

SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS studyroom_sessions (
        sid TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        device TEXT,
        entry TEXT,
        max_step INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT,
        submit_count INTEGER NOT NULL DEFAULT 0,
        data_version TEXT,
        answers TEXT,
        results TEXT,
        selected INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sid TEXT NOT NULL,
        at TEXT NOT NULL,
        type TEXT NOT NULL,
        plan INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_settings (
        name TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_datasets (
        name TEXT PRIMARY KEY,
        rows TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_catalog_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        note TEXT,
        summary TEXT,
        payload TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_files (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        size INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS studyroom_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sid TEXT NOT NULL,
        created_at TEXT NOT NULL,
        category TEXT NOT NULL,
        message TEXT NOT NULL,
        place TEXT,
        device TEXT,
        status TEXT NOT NULL DEFAULT 'new',
        updated_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_studyroom_events_sid ON studyroom_events(sid)",
    "CREATE INDEX IF NOT EXISTS idx_studyroom_feedback_created ON studyroom_feedback(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_studyroom_sessions_created ON studyroom_sessions(created_at)",
]
SCHEMA_PG = [s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY") for s in SCHEMA_SQLITE]
# 기존 테이블에 나중에 추가한 컬럼(이미 있으면 오류 → 무시)
MIGRATIONS = ["ALTER TABLE studyroom_files ADD COLUMN sha256 TEXT"]


def describe_url() -> str:
    """접속 정보 점검용 요약 — 비밀번호 대신 글자 수와 지문(sha256 앞 8자리)만 보여준다."""
    import hashlib
    u = urlparse(DATABASE_URL)
    pw = unquote(u.password or "")
    return (f"계정={unquote(u.username or '')} 호스트={u.hostname} 포트={u.port} DB={u.path.lstrip('/')} "
            f"비밀번호={len(pw)}자 지문={hashlib.sha256(pw.encode()).hexdigest()[:8]}")


def _pg_pool():
    global _pool
    if _pool is None:
        from psycopg2.pool import ThreadedConnectionPool
        try:
            _pool = ThreadedConnectionPool(1, POOL_MAX, DATABASE_URL, connect_timeout=10)
        except Exception as e:
            print(f"[studyroom] DB 접속 실패 — {describe_url()} — {str(e).strip().splitlines()[0]}", flush=True)
            raise
    return _pool


@contextmanager
def connect():
    if IS_PG:
        pool = _pg_pool()
        conn = pool.getconn()
        if conn.closed:  # 풀러가 끊은 연결은 버리고 새로
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        try:
            if SCHEMA:
                conn.cursor().execute(f"SET search_path TO {SCHEMA}")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _sqlite_lock:
            conn = sqlite3.connect(DATA_DIR / "responses.db", timeout=10)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()


def _q(sql: str) -> str:
    return sql.replace("?", "%s") if IS_PG else sql


def execute(sql: str, params=()):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)


def insert_returning_id(sql: str, params=()):
    """INSERT 후 새 행 id (SQLite lastrowid / PostgreSQL RETURNING id)."""
    with connect() as conn:
        cur = conn.cursor()
        if IS_PG:
            cur.execute(_q(sql) + " RETURNING id", params)
            return cur.fetchone()[0]
        cur.execute(sql, params)
        return cur.lastrowid


def fetch_all(sql: str, params=()):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def init():
    with connect() as conn:
        cur = conn.cursor()
        for stmt in (SCHEMA_PG if IS_PG else SCHEMA_SQLITE):
            cur.execute(stmt)
    for stmt in MIGRATIONS:
        try:
            execute(stmt)
        except Exception:
            pass  # 이미 적용됨


def backend_name() -> str:
    return (f"PostgreSQL (schema {SCHEMA or '기본'}, pool ≤{POOL_MAX}, {describe_url()})" if IS_PG
            else f"SQLite ({DATA_DIR / 'responses.db'})")
