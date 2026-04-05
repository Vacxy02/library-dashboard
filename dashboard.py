import streamlit as st
import pandas as pd
import os
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 기본 설정
st.set_page_config(page_title="강남자리: 실시간 AI 리포트", layout="wide", page_icon="🧠")

# 2. CSS 스타일: 슬라이더 및 운영 종료 안내 디자인
st.markdown("""
    <style>
    .slider-title { font-size: 1.5rem !important; font-weight: 800 !important; color: #FFFFFF; margin-bottom: 10px; }
    .stSlider [data-baseweb="typo"] { font-size: 1.1rem !important; font-weight: 600 !important; color: #00CC96 !important; }
    .predict-box { 
        text-align: center; border: 1px solid rgba(0, 204, 150, 0.3); 
        padding: 15px; border-radius: 15px; background-color: rgba(255,255,255,0.03); min-height: 140px;
    }
    .predict-time { color: #00CC96; font-weight: bold; font-size: 1.2rem; margin-bottom: 5px; }
    .closed-msg { color: #FF4B4B; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

# 3. [운영 로직] 도서관별/열람실별/요일별 상세 운영시간 판단 함수
def check_room_open(lib_name, room_name):
    now = datetime.now()
    weekday = now.weekday() # 0(월)~6(일)
    hour = now.hour
    is_weekend = weekday >= 5

    # [대치도서관]
    if lib_name == "대치도서관":
        if weekday == 1: return False, "화요일 정기 휴관"
        if any(keyword in room_name for keyword in ["자료실", "노트북"]):
            limit_end = 18 if is_weekend else 21
            if 9 <= hour < limit_end: return True, ""
            return False, f"운영종료 (09:00~{limit_end}:00)"
        else: # 일반 열람실
            if 6 <= hour < 21: return True, ""
            return False, "운영종료 (06:00~21:00)"

    # [도곡정보문화도서관]
    elif lib_name == "도곡정보문화도서관":
        if weekday == 0: return False, "월요일 정기 휴관"
        if "5층" in room_name:
            if 9 <= hour < 22: return True, ""
            return False, "운영종료 (09:00~22:00)"
        else: # 6층 및 기타
            if 7 <= hour < 22: return True, ""
            return False, "운영종료 (07:00~22:00)"

    # [기타 도서관]
    defaults = {
        "논현정보도서관": {"start": 7, "end": 22, "off": 1},
        "못골도서관": {"start": 9, "end": 22, "off": 1},
        "역삼2동작은도서관": {"start": 9, "end": 18, "off": 6},
        "역삼푸른솔도서관": {"start": 7, "end": 22, "off": 1}
    }
    
    if lib_name in defaults:
        conf = defaults[lib_name]
        if weekday == conf["off"]: return False, "정기 휴관일"
        if conf["start"] <= hour < conf["end"]: return True, ""
        return False, f"운영종료 ({conf['start']}:00~{conf['end']}:00)"

    return True, ""

# 4. 데이터 경로 설정 (사용자 지정 파일명 반영)
API_KEY = "3af9544717cb3978ea6884210598450b71882f047ca2286f6f81f8ad61c4b7e4"
FILE_NAME = "gangnam_lib.csv"
COMMENTS_FILE = "comments.csv"

def sync_api_data():
    now = datetime.now()
    # 수집 타이틀: 정각~3분, 30분~33분
    if not (0 <= now.minute <= 3 or 30 <= now.minute <= 33): return
    log_time = now.replace(minute=0 if now.minute < 15 else 30, second=0, microsecond=0)
    url = "http://apis.data.go.kr/B551982/plr_v2/rlt_rdrm_info_v2"
    try:
        res = requests.get(url, params={'serviceKey': API_KEY, '_type': 'json', 'pageNo': '1', 'numOfRows': '300'}, timeout=10).json()
        items = res.get('body', {}).get('item', [])
        new_rows = [{'수집시간': log_time.strftime('%Y-%m-%d %H:%M:%S'), '도서관명': i.get('pblibNm'), '열람실명': i.get('rdrmNm'), '전체좌석': int(i.get('tseatCnt') or 0), '사용좌석': int(i.get('useSeatCnt') or 0)} 
                    for i in items if i.get('lclgvNm') == '서울특별시 강남구']
        if new_rows:
            df = pd.DataFrame(new_rows)
            if os.path.exists(FILE_NAME):
                old = pd.read_csv(FILE_NAME)
                # 중복 수집 방지
                if old.empty or str(old.iloc[-1]['수집시간']) != df.iloc[0]['수집시간']:
                    pd.concat([old, df], ignore_index=True).to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
            else: df.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
    except: pass

@st.cache_data(ttl=60)
def load_data():
    sync_api_data()
    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)
        if df.empty: return None
        df['수집시간'] = pd.to_datetime(df['수집시간'])
        df['날짜'] = df['수집시간'].dt.date
        df['시분'] = df['수집시간'].dt.strftime('%H:%M')
        df['혼잡도'] = (df['사용좌석'] / df['전체좌석'] * 100).fillna(0).clip(0, 100)
        return df
    return None

def predict_dynamic(df, lib_name, room_name, predict_min):
    room_df = df[(df['도서관명'] == lib_name) & (df['열람실명'] == room_name)].sort_values('수집시간')
    if len(room_df) < 3: return 0, 0
    now_count = int(room_df.iloc[-1]['사용좌석'])
    total_seats = int(room_df.iloc[-1]['전체좌석'])
    recent = room_df.iloc[-6:] # 최근 3시간 추세
    trend = recent['사용좌석'].diff().mean() if len(recent) > 1 else 0
    delta = trend * (predict_min / 30)
    pred_count = max(0, min(total_seats, int(round(now_count + delta))))
    return pred_count, round(delta, 1)

# --- 5. 메인 UI 실행부 ---
df = load_data()

if df is not None:
    st.sidebar.title("🏛️ 강남자리")
    lib_list = sorted(df['도서관명'].unique())
    selected_lib = st.sidebar.selectbox("도서관 선택", lib_list)
    if st.sidebar.button("🔄 수동 새로고침"):
        st.cache_data.clear()
        st.rerun()

    lib_df = df[df['도서관명'] == selected_lib]
    latest_dt = lib_df['수집시간'].max()
    
    st.title(f"🚀 {selected_lib} AI 리포트")
    st.markdown(f"### 📍 실시간 좌석 현황 <small style='color:gray;'>({latest_dt.strftime('%H:%M')} 기준)</small>", unsafe_allow_html=True)

    # 예측 시점 선택 슬라이더
    st.write("")
    st.markdown('<p class="slider-title">🔮 도착 예정 시점 선택</p>', unsafe_allow_html=True)
    predict_min = st.select_slider("예측 시간", options=[30, 60, 90, 120, 150, 180], value=30, label_visibility="collapsed")
    future_time_str = (latest_dt + timedelta(minutes=predict_min)).strftime('%H:%M')
    st.write("")

    # 카드 섹션: 실시간 및 열람실별 개별 운영시간 반영
    realtime_df = lib_df[lib_df['수집시간'] == latest_dt]
    cols = st.columns(len(realtime_df))
    
    for i, (idx, row) in enumerate(realtime_df.iterrows()):
        with cols[i]:
            room_name = row['열람실명']
            is_open, msg = check_room_open(selected_lib, room_name)
            
            curr_c = int(row['사용좌석']) if is_open else 0
            total_c = int(row['전체좌석'])
            pred_c, d_val = predict_dynamic(df, selected_lib, room_name, predict_min) if is_open else (0, 0)

            # 차트 시각화
            chart_color = '#00CC96' if is_open else '#555555'
            if is_open and row['혼잡도'] >= 80: chart_color = '#EF553B'
            
            fig = go.Figure(go.Pie(values=[curr_c, max(1, total_c - curr_c)], hole=.75, marker=dict(colors=[chart_color, '#E5ECF6']), textinfo='none'))
            fig.update_layout(title={'text': f"<b>{room_name}</b>", 'x': 0.5}, showlegend=False, height=230, margin=dict(t=50, b=0, l=10, r=10))
            fig.add_annotation(text=f"<b>{curr_c}/{total_c}</b>", showarrow=False, font=dict(size=24))
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{i}")
            
            if is_open:
                st.markdown(f"""
                    <div class="predict-box">
                        <div class="predict-time">{future_time_str} 예상</div>
                        <span style="font-size: 1.5rem; font-weight: bold;">{pred_c} / {total_c}</span><br>
                        <span style="color: {'#EF553B' if d_val > 0 else '#00CC96' if d_val < 0 else 'gray'};">
                            {'🔺' if d_val > 0 else '🔻' if d_val < 0 else '➖'} {abs(d_val)}명
                        </span>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div class="predict-box" style="border-color: #FF4B4B;">
                        <div class="closed-msg">{msg}</div>
                        <div style="color: #777; font-size: 0.9rem; margin-top: 10px;">이용 불가 시간입니다.</div>
                    </div>
                """, unsafe_allow_html=True)

    st.divider()

    # SECTION: 7일 전 동일 패턴 분석
    st.subheader(f"📅 7일 전 동일 시점 패턴")
    past_7_days = latest_dt.date() - timedelta(days=7)
    history_7d_df = lib_df[lib_df['날짜'] == past_7_days]
    if not history_7d_df.empty:
        time_options = sorted(history_7d_df['시분'].unique())
        current_time_str = latest_dt.strftime('%H:%M')
        default_idx = time_options.index(current_time_str) if current_time_str in time_options else 0
        target_time = st.select_slider("조회 시간", options=time_options, value=time_options[default_idx], key="hist_slider")
        past_time_df = history_7d_df[history_7d_df['시분'] == target_time]
        cols2 = st.columns(len(past_time_df))
        for j, (idx2, row2) in enumerate(past_time_df.iterrows()):
            with cols2[j]:
                fig_p = go.Figure(go.Pie(values=[int(row2['사용좌석']), int(row2['전체좌석'])-int(row2['사용좌석'])], hole=.75, marker=dict(colors=['#00CC96', '#E5ECF6']), textinfo='none'))
                fig_p.update_layout(title={'text': f"<b>{row2['열람실명']}</b>", 'x': 0.5}, showlegend=False, height=180, margin=dict(t=40, b=0))
                fig_p.add_annotation(text=f"<b>{int(row2['사용좌석'])}/{int(row2['전체좌석'])}</b>", showarrow=False, font=dict(size=18))
                st.plotly_chart(fig_p, use_container_width=True, key=f"hist_{j}")
    else:
        st.info("ℹ️ 7일 전 데이터가 아직 `gangnam_lib.csv`에 쌓이지 않았습니다.")

    # SECTION: 실시간 게시판
    st.divider()
    st.subheader("💬 이용자 실시간 게시판")
    if os.path.exists(COMMENTS_FILE): comm_df = pd.read_csv(COMMENTS_FILE)
    else: comm_df = pd.DataFrame(columns=['도서관명', '날짜', '닉네임', '내용'])

    with st.form("comment_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 4])
        nick = c1.text_input("닉네임", placeholder="익명")
        text = c2.text_area("내용", placeholder="오늘 도서관 분위기는 어떤가요?")
        if st.form_submit_button("등록") and text:
            new_data = pd.DataFrame({'도서관명': [selected_lib], '날짜': [datetime.now().strftime('%Y-%m-%d %H:%M')], '닉네임': [nick if nick else "익명"], '내용': [text]})
            pd.concat([comm_df, new_data], ignore_index=True).to_csv(COMMENTS_FILE, index=False, encoding='utf-8-sig')
            st.rerun()

    for _, r in comm_df[comm_df['도서관명'] == selected_lib].sort_values(by='날짜', ascending=False).iterrows():
        with st.chat_message("user"):
            st.write(f"**{r['닉네임']}** | <small style='color: gray;'>{r['날짜']}</small>", unsafe_allow_html=True)
            st.write(r['내용'])
else:
    st.info("📊 `gangnam_lib.csv` 파일을 읽어오는 중이거나 수집된 데이터가 없습니다. 정각/30분 업데이트를 기다려주세요.")
