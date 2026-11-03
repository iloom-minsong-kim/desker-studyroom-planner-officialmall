# DESKER 학생방 플래너 — 공식몰 버전

고객용 설문 페이지 + 익명 응답 수집 + 관리자 인사이트 페이지 (FastAPI 단일 컨테이너)

| 주소 | 용도 |
|---|---|
| `/` | 고객용 설문 (학생방 플래너 v3, 이름·연락처 항목 제거·운영 도구 끔). `/?start=1` 은 설문 1단계로 바로 진입 |
| `/admin` | 관리자 (비밀번호) — 인사이트 · 응답 목록 · 엑셀 · 접속 QR |
| `/health` | 헬스체크 |

## 수집 범위
- 이름·연락처 미수집. 기기 종류(휴대폰/태블릿/PC)와 접속 시각만 함께 저장
- 방문 → 단계 도달 → 설문 완료(응답 + 추천안 3개) → 결과 화면 행동(상담표·구매 안내·공유 등)
- 추가 요청(자유기입)의 전화번호·이메일 형태는 저장 전에 자동 삭제

## 설정값
`.env.example` 참고. `ADMIN_PASSWORD` 필수, `DATABASE_URL` 비우면 `DATA_DIR/responses.db`(SQLite) 사용.

- 운영 DB: **미설정** (공식몰용 전용 스키마를 새로 발급받아 `DATABASE_URL` 에 넣을 것). 비워두면 `DATA_DIR/responses.db`(SQLite)로 동작. 연결 풀은 최대 3개(계정당 동시 접속 5개 제한).
- 사진·제품가이드 PDF 파일은 DB가 아니라 서버 보존 폴더(`DATA_DIR/files`)에 저장된다. 기본 사진은 서버가 처음 켜질 때 한 번 채운다.

## 로컬 실행
```sh
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010     # .env 의 COOKIE_SECURE=0
```

## 고객 페이지 갱신 (예: 네이버 링크 반영본)
`source/customer_v3.html` 을 새 파일로 교체 → `python tools/build_public.py` → `app/public/index.html` 생성


## 공식몰 버전 변경 계획
- 제품 탭에 프로모션 체크 · 혜택가 · 공식몰 링크 컬럼 추가
- 결과 페이지: 혜택 구성(혜택가) / 혜택 외 구성 별도 노출
- 스마트스토어 링크는 공식몰 링크로 교체(수기 입력 예정)
