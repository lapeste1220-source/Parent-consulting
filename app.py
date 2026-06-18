# -*- coding: utf-8 -*-
"""
3학년 학부모 상담 예약 프로그램
(Streamlit + GitHub 저장소를 데이터베이스로 사용 - 외부 DB/구글시트 불필요)

영구저장 원리
 - 예약 데이터를 같은 GitHub 저장소의 data/bookings.csv 파일에 저장(커밋)한다.
 - GitHub Contents API(requests)로 파일을 읽고/쓴다. PAT(토큰)만 있으면 된다.
 - 저장 시 파일 SHA를 함께 보내므로, 동시에 같은 칸을 신청하면 한쪽만 성공(409) → 재시도.
   => 별도 잠금 없이 '선착순' 충돌이 자동 방지된다.

기능
 - 관리자 메뉴(사이드바)는 기본으로 접혀 있음
 - 첫 화면에 접속용 QR 코드 표시(Secrets app_url)
 - 학반/학생명/연락처 입력 -> 학반별 노출(해당 반 담임 + 학년부장 박호종)
 - 첨부 캘린더(1차/2차) 양식 그대로, 선택 가능한 신청 박스
 - 선착순 예약(찬 칸/강제 마감 칸은 '마감' 표시 + 선택불가)
 - 1명당 1회만 신청(학반+학생명+연락처 기준 중복 차단)
 - 최종확인 + 확정 -> 확정 후 최종 일정 안내
 - 관리자 모드: 현황 조회/검색/CSV, 직접 수정/취소, 강제 마감
 - 모바일 세로형 기본 + 반응형, 다크/라이트 모드 어디서나 글씨 잘 보이게 색상 고정
"""
import re, io, csv, json, base64, datetime
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="3학년 학부모 상담 예약", page_icon="🗓️",
                   layout="centered", initial_sidebar_state="collapsed")

HOMEROOM = {"3-1": "박호종", "3-2": "유진솔", "3-3": "정재성", "3-4": "문다영"}
HEAD_TEACHER = "박호종"
CLASSES = list(HOMEROOM.keys())

def visible_teachers(cls):
    seen, out = set(), []
    for t in [HOMEROOM[cls], HEAD_TEACHER]:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def norm_phone(p): return re.sub(r"\D", "", p or "")

@st.cache_data(show_spinner=False)
def make_qr_b64(url: str) -> str:
    """접속 링크(url)를 QR 코드 PNG(base64)로 생성. 첫 화면 표시용."""
    import qrcode
    qr = qrcode.QRCode(version=None, box_size=10, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white")
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

# ──────────────────────────────────────────────────────────────
# 캘린더 데이터 (첨부 이미지 그대로)
# ──────────────────────────────────────────────────────────────
TIMES = ["13:00", "14:00", "15:00", "16:00", "18:00", "19:00"]

PHASES = {
    "1차": {
        "title": "1차 상담 예약 (7/20 월 ~ 7/25 토)",
        "dates": ["7/20(월)", "7/21(화)", "7/22(수)", "7/23(목)", "7/24(금)", "7/25(토)"],
        "cells": {
            ("7/21(화)", "13:00"): {"blocked": "방학식"},
            ("7/21(화)", "14:00"): {"blocked": "이그나이트"},
            ("7/22(수)", "13:00"): {"teachers": ["문다영"]},
            ("7/22(수)", "14:00"): {"teachers": ["문다영"]},
            ("7/22(수)", "15:00"): {"teachers": ["문다영"]},
            ("7/22(수)", "16:00"): {"teachers": ["문다영"]},
            ("7/22(수)", "18:00"): {"teachers": ["문다영"]},
            ("7/23(목)", "13:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/23(목)", "14:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/23(목)", "15:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/23(목)", "16:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/24(금)", "13:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/24(금)", "14:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/24(금)", "15:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/24(금)", "16:00"): {"teachers": ["박호종", "유진솔"]},
            ("7/24(금)", "18:00"): {"teachers": ["박호종"]},
            ("7/24(금)", "19:00"): {"teachers": ["박호종"]},
        },
    },
    "2차": {
        "title": "2차 상담 예약 (7/27 월 ~ 8/1 토)",
        "dates": ["7/27(월)", "7/28(화)", "7/29(수)", "7/30(목)", "7/31(금)", "8/1(토)"],
        "cells": {
            ("7/27(월)", "13:00"): {"teachers": ["박호종", "정재성"]},
            ("7/27(월)", "14:00"): {"teachers": ["박호종", "정재성"]},
            ("7/27(월)", "15:00"): {"teachers": ["박호종", "정재성"]},
            ("7/27(월)", "16:00"): {"teachers": ["박호종", "정재성"]},
            ("7/27(월)", "18:00"): {"teachers": ["정재성"]},
            ("7/27(월)", "19:00"): {"teachers": ["정재성"]},
            ("7/28(화)", "14:00"): {"teachers": ["유진솔"]},
            ("7/28(화)", "15:00"): {"teachers": ["유진솔"]},
            ("7/28(화)", "16:00"): {"teachers": ["유진솔"]},
            ("7/28(화)", "18:00"): {"teachers": ["유진솔"]},
            ("7/29(수)", "13:00"): {"teachers": ["박호종"]},
            ("7/29(수)", "14:00"): {"teachers": ["박호종"]},
            ("7/29(수)", "15:00"): {"teachers": ["박호종"]},
            ("7/29(수)", "16:00"): {"teachers": ["박호종"]},
            ("7/29(수)", "18:00"): {"teachers": ["박호종"]},
            ("7/29(수)", "19:00"): {"teachers": ["박호종"]},
            ("7/30(목)", "13:00"): {"teachers": ["박호종", "문다영"]},
            ("7/30(목)", "14:00"): {"teachers": ["박호종", "문다영"]},
            ("7/30(목)", "15:00"): {"teachers": ["박호종", "문다영"]},
            ("7/30(목)", "16:00"): {"teachers": ["박호종", "문다영"]},
            ("7/30(목)", "18:00"): {"teachers": ["박호종"]},
            ("7/30(목)", "19:00"): {"teachers": ["박호종"]},
            ("7/31(금)", "13:00"): {"teachers": ["박호종", "정재성"]},
            ("7/31(금)", "14:00"): {"teachers": ["박호종", "정재성"]},
            ("7/31(금)", "15:00"): {"teachers": ["박호종", "정재성"]},
            ("7/31(금)", "16:00"): {"teachers": ["박호종", "정재성"]},
            ("7/31(금)", "18:00"): {"teachers": ["박호종"]},
            ("7/31(금)", "19:00"): {"teachers": ["박호종"]},
            ("8/1(토)", "13:00"): {"teachers": ["박호종"], "t": "09:00"},
            ("8/1(토)", "14:00"): {"teachers": ["박호종"], "t": "10:00"},
            ("8/1(토)", "15:00"): {"teachers": ["박호종"], "t": "11:00"},
        },
    },
}

def real_time(cell, row_time):
    return cell.get("t", row_time) if cell else row_time

# ──────────────────────────────────────────────────────────────
# GitHub 저장소 = 데이터베이스
#   data/bookings.csv (헤더 포함). 컬럼:
#   phase,date,time,teacher,class,student,phone,created_at,status
# ──────────────────────────────────────────────────────────────
HEADERS = ["phase", "date", "time", "teacher", "class",
           "student", "phone", "created_at", "status"]
DATA_PATH = "data/bookings.csv"
API = "https://api.github.com"

def gh_ready():
    g = st.secrets.get("github", {})
    return all(k in g for k in ("token", "repo")) and g.get("token") and g.get("repo")

def _cfg():
    g = st.secrets["github"]
    return g["token"], g["repo"], g.get("branch", "main")

def _headers(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def gh_get_file():
    """(rows, sha) 반환. 파일 없으면 ([], None)."""
    token, repo, branch = _cfg()
    r = requests.get(f"{API}/repos/{repo}/contents/{DATA_PATH}",
                     headers=_headers(token), params={"ref": branch}, timeout=15)
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    j = r.json()
    raw = base64.b64decode(j["content"]).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw))) if raw.strip() else []
    return rows, j["sha"]

def gh_put_file(rows, sha, message):
    """rows 전체를 CSV로 커밋. 성공 True / SHA 충돌 False / 그 외 예외."""
    token, repo, branch = _cfg()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADERS)
    w.writeheader()
    for row in rows:
        w.writerow({h: row.get(h, "") for h in HEADERS})
    content = base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")
    payload = {"message": message, "content": content, "branch": branch}
    if sha:
        payload["sha"] = sha
    r = requests.put(f"{API}/repos/{repo}/contents/{DATA_PATH}",
                     headers=_headers(token), data=json.dumps(payload), timeout=15)
    if r.status_code in (200, 201):
        return True
    if r.status_code == 409:       # SHA 불일치 = 그 사이 누가 커밋함
        return False
    r.raise_for_status()
    return False

def fetch_rows():
    rows, _ = gh_get_file()
    return rows

def taken_keys(rows):
    return {f"{r['phase']}|{r['date']}|{r['time']}|{r['teacher']}" for r in rows}

def find_my_booking(rows, cls, student, phone):
    ph = norm_phone(phone)
    for r in rows:
        if (str(r.get("status", "")).upper() != "CLOSED"
                and r["class"] == cls
                and str(r["student"]).strip() == student.strip()
                and norm_phone(str(r["phone"])) == ph):
            return r
    return None

def try_book(sel, retries=4):
    """선착순 + 1인1회 검증 후 GitHub에 커밋.
       반환: 'ok' / 'taken' / 'dup'(+기존예약) / 'busy'(동시충돌 반복)"""
    key = f"{sel['phase']}|{sel['date']}|{sel['time']}|{sel['teacher']}"
    for _ in range(retries):
        rows, sha = gh_get_file()
        if key in taken_keys(rows):
            return "taken", None
        dup = find_my_booking(rows, sel["class"], sel["student"], sel["phone"])
        if dup:
            return "dup", dup
        rows.append({
            "phase": sel["phase"], "date": sel["date"], "time": sel["time"],
            "teacher": sel["teacher"], "class": sel["class"],
            "student": sel["student"], "phone": sel["phone"],
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "",
        })
        msg = f"book: {sel['class']} {sel['student']} {sel['phase']} {sel['date']} {sel['time']} {sel['teacher']}"
        if gh_put_file(rows, sha, msg):
            return "ok", None
        # 409 → 누군가 먼저 썼다. 다시 읽어 재검증/재시도
    return "busy", None

def overwrite_rows(rows, message, retries=4):
    """관리자 전체 덮어쓰기(수정/취소). 성공 True."""
    for _ in range(retries):
        _, sha = gh_get_file()
        if gh_put_file(rows, sha, message):
            return True
    return False

# ──────────────────────────────────────────────────────────────
# 스타일 (모바일 세로형 기본 + 반응형 / 다크·라이트 어디서나 글씨 선명)
#   ※ 카드·안내 영역은 글자색을 진한 색으로 '명시'해 다크 모드에서도 보이게 함
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
:root{ --pri:#2563EB; --pri-d:#1E40AF; --ink:#111827; --sub:#4B5563; --line:#E5E7EB; }
.block-container{ max-width:760px; padding-top:1.1rem; padding-bottom:3rem; }
html, body, [class*="css"]{ font-family:'Pretendard',-apple-system,'Segoe UI',sans-serif; }

.hero{ background:var(--pri); color:#fff !important; border-radius:16px; padding:22px 20px; }
.hero h1{ font-size:1.45rem; font-weight:800; margin:0 0 6px; color:#fff !important; }
.hero p{ margin:0; opacity:.96; font-size:.95rem; line-height:1.55; color:#fff !important; }

/* 흰 카드: 배경 흰색 + 글자 진한색 명시 (다크모드에서도 선명) */
.card{ border:1px solid var(--line); border-radius:14px; padding:18px;
       background:#FFFFFF !important; color:var(--ink) !important;
       box-shadow:0 1px 2px rgba(16,24,40,.04); }
.card, .card *{ color:var(--ink) !important; }
.card b{ color:var(--pri-d) !important; }
.card ul{ margin:10px 0 0; padding-left:18px; line-height:1.9; font-size:.95rem; }
.card li{ color:var(--ink) !important; margin-bottom:4px; }
.card li b{ color:var(--pri-d) !important; }

.notice{ background:#EFF4FF; border:1px solid #C7D7FE; border-radius:12px;
         padding:12px 14px; font-size:.92rem; color:#1E3A8A !important; line-height:1.6; }
.notice b{ color:#1E3A8A !important; }
.summary b{ color:var(--pri-d) !important; }
.bigok{ background:#ECFDF5; border:1px solid #A7F3D0; border-radius:14px; padding:18px;
        color:#065F46 !important; font-size:1.02rem; line-height:1.7; }
.bigok b{ color:#065F46 !important; }
.warnbox{ background:#FFF7ED; border:1px solid #FED7AA; border-radius:14px; padding:18px;
          color:#9A3412 !important; font-size:1rem; line-height:1.7; }
.warnbox b{ color:#9A3412 !important; }

div[data-testid="stHorizontalBlock"]{ gap:4px !important; }
.cell-time{ display:flex;align-items:center;justify-content:center;height:42px;
            font-weight:700;font-size:.85rem;color:var(--ink) !important;background:#F3F4F6;border-radius:8px; }
.cell-head{ display:flex;align-items:center;justify-content:center;height:38px;
            font-weight:700;font-size:.82rem;color:#fff !important;background:var(--pri);border-radius:8px; }
.cell-head.time{ background:#374151; }
.cell-empty{ height:42px;border-radius:8px;background:#EDEFF2; }
.cell-block{ display:flex;align-items:center;justify-content:center;height:42px;
             font-size:.78rem;font-weight:600;color:#4B5563 !important;background:#E5E7EB;border-radius:8px; }
.stButton>button{ width:100%; border-radius:8px; height:42px; padding:0 2px;
                  font-size:.82rem; font-weight:700; line-height:1.15;
                  border:1px solid var(--pri); color:#fff !important; background:var(--pri); }
.stButton>button:hover{ background:var(--pri-d); border-color:var(--pri-d); color:#fff !important; }
.stButton>button:disabled{ background:#E5E7EB; color:#9CA3AF !important; border:1px dashed #CBD0D8; }

@media (max-width:640px){
  .block-container{ padding-left:.6rem; padding-right:.6rem; }
  .stButton>button{ font-size:.72rem; height:40px; }
  .cell-time,.cell-empty,.cell-block{ height:40px; }
  .cell-time{ font-size:.72rem; }
  .cell-head{ font-size:.68rem; height:36px; }
  .hero h1{ font-size:1.2rem; }
}
</style>
""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("step", "intro")
ss.setdefault("info", {})
ss.setdefault("sel", None)
ss.setdefault("mine", None)
ss.setdefault("is_admin", False)
def goto(step): ss.step = step

# ──────────────────────────────────────────────────────────────
def view_intro():
    st.markdown("""
    <div class="hero">
      <h1>🗓️ 3학년 학부모 상담 예약</h1>
      <p>여름방학 1·2차 학부모 상담 신청 페이지입니다.<br>
      아래 안내를 확인하신 뒤 <b>신청하기</b>를 눌러 진행해 주세요.</p>
    </div>""", unsafe_allow_html=True)
    st.write("")
    st.markdown("""
    <div class="card">
      <b>📌 신청 안내</b>
      <ul>
        <li>학반·학생 이름·보호자 연락처를 입력합니다.</li>
        <li>선택하신 <b>학반의 담임 선생님</b>과 <b>학년부장(박호종)</b> 선생님 일정만 표시됩니다.</li>
        <li>원하는 날짜·시간 칸을 누르면 신청됩니다. <b>선착순</b>이며 마감된 칸은 선택할 수 없습니다.</li>
        <li><b>학생 1명당 1회만 신청</b> 가능합니다. 변경이 필요하면 담임 선생님께 연락 바랍니다.</li>
        <li>잘못 선택을 방지하기 위해 <b>최종 확인 후 확정</b> 단계를 거칩니다.</li>
      </ul>
    </div>""", unsafe_allow_html=True)
    st.write("")

    # ── 접속용 QR 코드 (Secrets의 app_url 사용) ──
    app_url = st.secrets.get("app_url", "")
    if app_url:
        try:
            qr_b64 = make_qr_b64(app_url)
            st.markdown(f"""
            <div class="card" style="text-align:center;">
              <b>📱 이 페이지 공유용 QR 코드</b>
              <div style="margin:12px 0 4px;">
                <img src="data:image/png;base64,{qr_b64}" alt="접속 QR 코드"
                     style="width:190px;height:190px;border:1px solid var(--line);
                            border-radius:12px;padding:8px;background:#fff;" />
              </div>
              <div style="font-size:.82rem;color:#6B7280 !important;word-break:break-all;">{app_url}</div>
            </div>""", unsafe_allow_html=True)
            st.write("")
        except Exception:
            pass  # QR 생성 실패 시에도 화면은 정상 진행

    if st.button("✏️  신청하기", use_container_width=True, type="primary"):
        goto("form"); st.rerun()

def view_form():
    st.markdown('<div class="hero"><h1>① 학생 정보 입력</h1>'
                '<p>학반을 선택하면 해당 반 선생님 일정만 보입니다.</p></div>',
                unsafe_allow_html=True)
    st.write("")
    with st.form("info_form"):
        cls = st.selectbox("학반", CLASSES, index=None, placeholder="학반을 선택하세요")
        name = st.text_input("학생 성명")
        phone = st.text_input("보호자 연락처", placeholder="예) 010-1234-5678")
        c1, c2 = st.columns(2)
        back = c1.form_submit_button("← 처음으로", use_container_width=True)
        nxt = c2.form_submit_button("다음 →", use_container_width=True, type="primary")
    if back:
        goto("intro"); st.rerun()
    if nxt:
        if not cls or not name.strip() or not phone.strip():
            st.error("학반·학생 성명·연락처를 모두 입력해 주세요."); return
        ss.info = {"class": cls, "student": name.strip(), "phone": phone.strip()}
        try:
            mine = find_my_booking(fetch_rows(), cls, name, phone)
        except Exception as e:
            st.error(f"데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요. ({e})"); return
        if mine:
            ss.mine = mine; goto("already"); st.rerun()
        else:
            goto("calendar"); st.rerun()

def view_already():
    m = ss.mine
    st.markdown('<div class="hero"><h1>이미 신청 내역이 있습니다</h1>'
                '<p>학생 1명당 1회만 신청할 수 있습니다.</p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(f"""
    <div class="warnbox">
      <b>📅 기존 예약 내역</b><br><br>
      ▪ {m['class']} {m['student']} 학생<br>
      ▪ <b>{m['phase']} 상담 · {m['date']} {m['time']}</b><br>
      ▪ <b>{m['teacher']} 선생님</b><br><br>
      일정 변경·취소가 필요하시면 <b>담임 선생님</b>께 연락 바랍니다.
    </div>""", unsafe_allow_html=True)
    st.write("")
    if st.button("처음으로 돌아가기", use_container_width=True):
        ss.info = {}; ss.mine = None; goto("intro"); st.rerun()

def view_calendar():
    info = ss.info
    vis = visible_teachers(info["class"])
    st.markdown(f'<div class="hero"><h1>② 상담 시간 선택</h1>'
                f'<p>{info["class"]} · {info["student"]} 학생 / 선택 가능 선생님: '
                f'<b>{", ".join(vis)}</b></p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="notice">파란 칸을 누르면 신청됩니다. '
                '회색 칸은 <b>마감</b>되어 선택할 수 없습니다.</div>', unsafe_allow_html=True)
    phase = st.radio("상담 차수", list(PHASES.keys()), horizontal=True, key="phase_sel")
    pdata = PHASES[phase]; dates = pdata["dates"]; cells = pdata["cells"]
    try:
        taken = taken_keys(fetch_rows())
    except Exception as e:
        st.error(f"예약 현황을 불러오지 못했습니다. 새로고침 해주세요. ({e})"); return
    st.caption(pdata["title"])
    head = st.columns([0.8] + [1] * len(dates))
    head[0].markdown('<div class="cell-head time">시간</div>', unsafe_allow_html=True)
    for i, d in enumerate(dates):
        head[i + 1].markdown(f'<div class="cell-head">{d}</div>', unsafe_allow_html=True)
    for row in TIMES:
        cols = st.columns([0.8] + [1] * len(dates))
        cols[0].markdown(f'<div class="cell-time">{row}</div>', unsafe_allow_html=True)
        for i, d in enumerate(dates):
            col = cols[i + 1]; cell = cells.get((d, row))
            if not cell:
                col.markdown('<div class="cell-empty"></div>', unsafe_allow_html=True); continue
            if "blocked" in cell:
                col.markdown(f'<div class="cell-block">{cell["blocked"]}</div>', unsafe_allow_html=True); continue
            shown = [t for t in cell["teachers"] if t in vis]
            if not shown:
                col.markdown('<div class="cell-empty"></div>', unsafe_allow_html=True); continue
            rt = real_time(cell, row)
            with col:
                for tc in shown:
                    key = f"{phase}|{d}|{rt}|{tc}"
                    is_taken = key in taken
                    label = "마감" if is_taken else (f"{rt} {tc}" if "t" in cell else tc)
                    if st.button(label, key="b_" + key, disabled=is_taken, use_container_width=True):
                        ss.sel = {"phase": phase, "date": d, "time": rt, "teacher": tc, **info}
                        goto("confirm"); st.rerun()
    st.write("")
    if st.button("← 정보 다시 입력", use_container_width=True):
        goto("form"); st.rerun()

def view_confirm():
    s = ss.sel
    st.markdown('<div class="hero"><h1>③ 신청 내용 최종 확인</h1>'
                '<p>아래 내용이 맞는지 확인 후 확정해 주세요.</p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(f"""
    <div class="card summary" style="line-height:2; font-size:1rem;">
      차　　수 : <b>{s['phase']} 상담</b><br>
      학　　반 : <b>{s['class']}</b><br>
      학생성명 : <b>{s['student']}</b><br>
      연 락 처 : <b>{s['phone']}</b><br>
      상담일시 : <b>{s['date']} {s['time']}</b><br>
      상담교사 : <b>{s['teacher']} 선생님</b>
    </div>""", unsafe_allow_html=True)
    st.write("")
    c1, c2 = st.columns(2)
    if c1.button("← 다시 선택", use_container_width=True):
        ss.sel = None; goto("calendar"); st.rerun()
    if c2.button("✅ 이대로 확정하기", use_container_width=True, type="primary"):
        with st.spinner("예약을 저장하는 중입니다..."):
            try:
                result, extra = try_book(s)
            except Exception as e:
                st.error(f"저장 중 오류가 발생했습니다. 다시 시도해 주세요. ({e})"); return
        if result == "ok":
            goto("done"); st.rerun()
        elif result == "dup":
            ss.mine = extra; goto("already"); st.rerun()
        elif result == "busy":
            st.warning("지금 신청이 몰리고 있습니다. 잠시 후 다시 확정해 주세요.")
        else:  # taken
            st.error("죄송합니다. 방금 해당 시간이 마감되었습니다. 다른 시간을 선택해 주세요.")
            ss.sel = None
            if st.button("다른 시간 선택하기", use_container_width=True):
                goto("calendar"); st.rerun()

def view_done():
    s = ss.sel
    st.markdown('<div class="hero"><h1>🎉 예약이 확정되었습니다</h1>'
                '<p>아래 일정으로 상담이 예약되었습니다.</p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(f"""
    <div class="bigok">
      <b>📅 최종 상담 일정 안내</b><br><br>
      ▪ {s['class']} {s['student']} 학생<br>
      ▪ <b>{s['phase']} 상담 · {s['date']} {s['time']}</b><br>
      ▪ <b>{s['teacher']} 선생님</b><br><br>
      예약 시간 5분 전까지 도착해 주세요. 변경·취소는 담임 선생님께 연락 바랍니다.
    </div>""", unsafe_allow_html=True)
    st.write("")
    if st.button("처음으로 돌아가기", use_container_width=True):
        ss.sel = None; ss.info = {}; ss.mine = None; goto("intro"); st.rerun()

# ──────────────────────────────────────────────────────────────
def admin_login_sidebar():
    with st.sidebar:
        st.markdown("### 🔐 관리자 메뉴")
        if ss.is_admin:
            st.success("관리자 로그인 상태")
            if st.button("관리자 패널 열기", use_container_width=True):
                goto("admin"); st.rerun()
            if st.button("로그아웃", use_container_width=True):
                ss.is_admin = False; goto("intro"); st.rerun()
        else:
            pw = st.text_input("비밀번호", type="password", key="admin_pw_in")
            if st.button("로그인", use_container_width=True):
                if pw and pw == st.secrets.get("admin_pw", "teacher2025"):
                    ss.is_admin = True; goto("admin"); st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")

def view_admin():
    if not ss.is_admin:
        goto("intro"); st.rerun(); return
    import pandas as pd
    st.markdown('<div class="hero"><h1>🔐 관리자 패널</h1>'
                '<p>예약 현황을 확인하고 직접 수정·취소할 수 있습니다.</p></div>', unsafe_allow_html=True)
    st.write("")
    try:
        rows = fetch_rows()
    except Exception as e:
        st.error(f"데이터를 불러오지 못했습니다. ({e})"); return
    df = pd.DataFrame(rows, columns=HEADERS) if rows else pd.DataFrame(columns=HEADERS)
    actual = df[df["status"].astype(str).str.upper() != "CLOSED"] if not df.empty else df
    m1, m2, m3 = st.columns(3)
    m1.metric("총 예약", f"{len(actual)}건")
    if not actual.empty:
        m2.metric("1차", f"{(actual['phase']=='1차').sum()}건")
        m3.metric("2차", f"{(actual['phase']=='2차').sum()}건")
    tab1, tab2, tab3 = st.tabs(["📋 현황·검색", "✏️ 직접 수정/취소", "⛔ 강제 마감"])

    with tab1:
        f1, f2 = st.columns(2)
        fp = f1.selectbox("차수 필터", ["전체", "1차", "2차"])
        fc = f2.selectbox("학반 필터", ["전체"] + CLASSES)
        kw = st.text_input("학생명/연락처 검색", placeholder="이름 또는 번호 일부")
        view = actual.copy()
        if fp != "전체": view = view[view["phase"] == fp]
        if fc != "전체": view = view[view["class"] == fc]
        if kw.strip():
            k = kw.strip()
            view = view[view["student"].astype(str).str.contains(k, na=False) |
                        view["phone"].astype(str).str.contains(k, na=False)]
        st.dataframe(view, use_container_width=True, hide_index=True)
        if not actual.empty:
            buf = io.StringIO(); w = csv.writer(buf); w.writerow(HEADERS)
            for _, r in actual.iterrows():
                w.writerow([r[h] for h in HEADERS])
            st.download_button("예약현황 CSV 다운로드", buf.getvalue().encode("utf-8-sig"),
                               file_name="bookings.csv", mime="text/csv", use_container_width=True)

    with tab2:
        st.caption("표를 직접 수정하거나 행을 삭제(취소)한 뒤 저장하세요. "
                   "맨 아래 빈 행에 새 예약을 추가할 수도 있습니다.")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                hide_index=True, key="admin_editor")
        if st.button("💾 변경사항 저장(GitHub 커밋)", type="primary", use_container_width=True):
            out = []
            for _, r in edited.iterrows():
                out.append({h: ("" if pd.isna(r[h]) else r[h]) for h in HEADERS})
            with st.spinner("저장 중..."):
                ok = overwrite_rows(out, "admin: edit bookings")
            if ok: st.success("저장되었습니다."); st.rerun()
            else: st.error("저장에 실패했습니다. 잠시 후 다시 시도해 주세요.")

    with tab3:
        st.caption("특정 칸을 학부모가 선택하지 못하도록 강제 마감합니다.")
        cph = st.selectbox("차수", list(PHASES.keys()), key="cl_ph")
        pdata = PHASES[cph]
        cdt = st.selectbox("날짜", pdata["dates"], key="cl_dt")
        ctm = st.selectbox("시간", TIMES, key="cl_tm")
        cell = pdata["cells"].get((cdt, ctm))
        opts = cell["teachers"] if (cell and "teachers" in cell) else []
        if not opts:
            st.info("선택한 칸에는 상담 가능한 선생님이 없습니다.")
        else:
            ctc = st.selectbox("선생님", opts, key="cl_tc")
            rt = real_time(cell, ctm)
            cc1, cc2 = st.columns(2)
            if cc1.button("⛔ 이 칸 강제 마감", use_container_width=True):
                cur = fetch_rows()
                cur.append({"phase": cph, "date": cdt, "time": rt, "teacher": ctc,
                            "class": "-", "student": "[강제마감]", "phone": "",
                            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "CLOSED"})
                if overwrite_rows(cur, f"admin: close {cph} {cdt} {rt} {ctc}"):
                    st.success("강제 마감했습니다."); st.rerun()
                else: st.error("처리 실패. 다시 시도해 주세요.")
            if cc2.button("✅ 마감 해제", use_container_width=True):
                cur = fetch_rows(); keep = []; removed = False
                for r in cur:
                    is_t = (str(r.get("status","")).upper()=="CLOSED" and r["phase"]==cph and
                            r["date"]==cdt and r["time"]==rt and r["teacher"]==ctc)
                    if is_t and not removed: removed = True; continue
                    keep.append(r)
                if overwrite_rows(keep, f"admin: open {cph} {cdt} {rt} {ctc}"):
                    st.success("마감을 해제했습니다." if removed else "해당 강제 마감이 없습니다.")
                    st.rerun()
                else: st.error("처리 실패. 다시 시도해 주세요.")
    st.write("")
    if st.button("← 신청 화면으로", use_container_width=True):
        goto("intro"); st.rerun()

# ──────────────────────────────────────────────────────────────
if not gh_ready():
    st.error("⚠️ GitHub 저장소 연결 정보가 없습니다. Streamlit Secrets에 "
             "`admin_pw` 와 `[github] token / repo / branch` 를 등록해 주세요. "
             "(설정 방법은 README 참고)")
    st.stop()

admin_login_sidebar()
{
    "intro": view_intro, "form": view_form, "already": view_already,
    "calendar": view_calendar, "confirm": view_confirm, "done": view_done,
    "admin": view_admin,
}[ss.step]()
