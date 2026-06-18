# 3학년 학부모 상담 예약 (Streamlit + GitHub 저장)

외부 데이터베이스나 구글 시트 없이, **GitHub 저장소 자체에 예약 데이터를 영구 저장**하는
학부모 상담 선착순 예약 앱입니다. 필요한 것은 **GitHub 토큰 1개**뿐입니다.

- 예약 데이터는 같은 저장소의 `data/bookings.csv` 에 커밋되어 **앱 재배포에도 유지**됩니다.
- **학생 1명당 1회만** 신청, **선착순** 마감, **관리자**가 조회·수정·취소·강제마감 가능.
- GitHub API가 파일 버전(SHA)을 비교하므로 동시 신청 충돌도 자동 방지됩니다.

---

## 1. 구성 파일
| 파일 | 역할 |
|---|---|
| `app.py` | 앱 본체 |
| `requirements.txt` | streamlit, requests, pandas |
| `.streamlit/config.toml` | 테마 |
| `.streamlit/secrets.toml` | 비밀값 예시 (실제 값은 Streamlit Cloud Secrets에 입력, GitHub엔 올리지 않음) |
| `.gitignore` | secrets.toml 등 제외 |
| `data/.gitkeep` | 데이터 폴더 자리 유지용 (bookings.csv는 첫 신청 때 자동 생성) |

## 2. 준비 (딱 두 가지)

### (1) GitHub 저장소 만들기
1. GitHub에서 새 저장소 생성 (예: `parent-consult`). **Private 권장**.
2. 위 구성 파일들을 업로드 (`secrets.toml` 은 올리지 않습니다).

### (2) GitHub 토큰(PAT) 발급  — 1분
1. GitHub 우상단 프로필 → **Settings** → 맨 아래 **Developer settings**
2. **Personal access tokens → Fine-grained tokens → Generate new token**
3. 설정:
   - **Repository access** → *Only select repositories* → 위에서 만든 저장소 선택
   - **Permissions → Repository permissions → Contents** → **Read and write** 로 변경
   - (Expiration은 상담 기간보다 길게)
4. **Generate token** → 나온 `github_pat_...` 문자열을 복사 (이 화면 벗어나면 다시 못 봄)

> 참고: 기존 Classic 토큰을 쓰려면 `repo` 권한을 체크하면 됩니다.

## 3. Streamlit Cloud 배포
1. https://share.streamlit.io → **Create app** → 저장소·`app.py` 선택 → Deploy.
2. **App settings → Secrets** 에 아래를 붙여넣고 저장:
   ```toml
   admin_pw = "원하는관리자비번"

   [github]
   token  = "github_pat_복사한값"
   repo   = "본인깃허브아이디/parent-consult"
   branch = "main"
   ```
3. 발급된 주소(`https://OOO.streamlit.app`)를 학부모에게 안내하면 끝.

## 4. 사용 방법
- **학부모**: 신청하기 → 학반·이름·연락처 입력 → 캘린더에서 칸 선택 → 최종 확인 → 확정 →
  일정 안내. 이미 신청한 학생은 자동으로 기존 예약을 안내받습니다.
- **관리자**: 왼쪽 사이드바에서 비밀번호 로그인 → **관리자 패널**
  - `현황·검색` : 차수/학반 필터, 이름·번호 검색, CSV 다운로드
  - `직접 수정/취소` : 표를 직접 편집·행 삭제(취소)·새 행 추가 후 **저장** → GitHub에 커밋
  - `강제 마감` : 특정 날짜·시간·교사 칸 막기/해제

## 5. 동작 규칙
- **영구저장**: 모든 예약은 `data/bookings.csv` 에 커밋됩니다. GitHub에서 직접 열람·다운로드 가능.
- **선착순**: 확정 직전 파일을 다시 읽어 검증하고, 저장 시 SHA가 어긋나면(동시 신청) 자동 재시도.
- **1인 1회**: 학반 + 학생명 + 연락처(숫자만) 가 같으면 중복 신청을 막습니다.
- **강제 마감 칸**: CSV에 `status=CLOSED` 행으로 저장되어 캘린더에서 '마감'으로 표시됩니다.

## 6. 일정·선생님 수정
`app.py` 상단 `PHASES` / `HOMEROOM` 만 고치면 됩니다.
- `{"teachers":["박호종","유진솔"]}` → 선택 가능한 선생님
- `{"teachers":["박호종"], "t":"09:00"}` → 표시 시간이 다른 칸(토요일)
- `{"blocked":"방학식"}` → 막힌 칸 / 키 없으면 빈 칸

## 7. 참고
- 데이터가 많아도 학부모 상담 규모(수백 건)에서는 GitHub 커밋 방식으로 충분합니다.
- 토큰은 절대 코드/저장소에 직접 적지 말고 **Streamlit Secrets** 에만 넣으세요.
- 저장소를 Private 으로 두면 예약자 개인정보(이름·연락처)가 외부에 노출되지 않습니다.
