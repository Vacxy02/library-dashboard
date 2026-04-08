import streamlit as st
import pandas as pd
import os
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 기본 설정
st.set_page_config(page_title="강남자리: 실시간 AI 리포트", layout="wide", page_icon="🧠")

# 2. CSS 스타일
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

# 3. 상수 및 설정
API_KEY = "3af9544717cb3978ea6884210598450b71882f047ca2286f6f81f8ad61c4b7e4"
FILE_NAME = "gangnam_lib.csv"
COMMENTS_FILE = "comments.csv"

# 4. 운영 시간 판단 함수
def check_room_open(lib_name, room_name):
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    is_weekend = weekday >= 5

    if lib_name == "대치도서관":
        if weekday == 1: return False, "화요일 정기 휴관"
        if any(keyword in room_name for keyword in ["자료실", "노트북"]):
            limit_end = 18 if is_weekend else 21
            if 9 <= hour < limit_end: return True, ""
            return False, f"운영종료 (09:00~{limit_end}:00)"
        else:
            if 6 <= hour < 21: return True, ""
            return False, "운영종료 (06:00~21:00)"
    elif lib_name == "도곡정보문화도서관":
        if weekday == 0: return False, "월요일 정기 휴관"
        limit_start = 9 if "5층" in room_name else 7
        if limit_start <= hour < 22: return True, ""
        return False, f"운영종료 ({limit_start}:00~22:00)"
    elif lib_name == "논현도서관":
        if weekday == 1: return False, "화요일 정기 휴관"
        if 7 <= hour < 22: return True, ""
        return False, "운영종료 (07:00~22:00)"
    elif lib_name == "못골도서관":
        if weekday == 1: return False, "화요일 정기 휴관"
        if 9 <= hour < 22: return True, ""
        return False, "운영종료 (09:00~22:00)"
    elif lib_name == "역삼2동작은도서관":
        if weekday == 6: return False, "일요일 정기 휴관"
        if 9 <= hour < 18: return True, ""
        return False, "운영종료 (09:00~18:00)"
    elif lib_name == "역삼푸른솔도서관":
        if weekday == 1: return False, "화요일 정기 휴관"
        if 7 <= hour < 22: return True, ""
        return False, "운영종료 (07:00~22:00)"
    return True, ""

# 5. 실시간 API 호출 및 데이터 저장
def get_realtime_data():
    url = "http://apis.data.go.kr/B551982/plr_v2/rlt_rdrm_info_v2"
    now = datetime.now()
    try:
        res = requests.get(url, params={'serviceKey': API_KEY, '_type': 'json', 'pageNo': '1', 'numOfRows': '300'}, timeout=8).json()
        items = res.get('body', {}).get('item', [])
        rows = []
        for i in items:
            if i.get('lclgvNm') == '서울특별시 강남구':
                t = int(i.get('tseatCnt') or 0)
                u = int(i.get('useSeatCnt') or 0)
                rows.append({
                    '수집시간': now.strftime('%Y-%m-%d %H:%M:%S'),
                    '요일': now.strftime('%A'),
                    '도서관명': i.get('pblibNm'),
                    '열람실명': i.get('rdrmNm'),
                    '전체좌석': t,
                    '사용좌석': u,
                    '잔여좌석': float(t - u),
                    '혼잡도': (u / t * 100) if t > 0 else 0
                })
        rt_df = pd.DataFrame(rows)
        
        # 파일 저장 (정각/30분 기준)
        if not rt_df.empty and (0 <= now.minute <= 5 or 30 <= now.minute <= 35):
            log_time = now.replace(minute=0 if now.minute < 15 else 30, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            save_df = rt_df.copy()
            save_df['수집시간'] = log_time
            if os.path.exists(FILE_NAME):
                old = pd.read_csv(FILE_NAME)
                if old.empty or str(old.iloc[-1]['수집시간']) != log_time:
                    pd.concat([old, save_df], ignore_index=True).to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
            else:
                save_df.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
        return rt_df
    except:
        return None

# 6. 데이터 로드 및 예측 함수
@st.cache_data(ttl=60)
def load_history():
    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)
        df['수집시간'] = pd.to_datetime(df['수집시간'])
        df['날짜'] = df['수집시간'].dt.date
        df['시분'] = df['수집시간'].dt.strftime('%H:%M')
        return df
    return None

def predict_dynamic(history_df, lib_name, room_name, current_used, predict_min):
    if history_df is None: return current_used, 0
    room_df = history_df[(history_df['도서관명'] == lib_name) & (history_df['열람실명'] == room_name)].sort_values('수집시간')
    if len(room_df) < 3: return current_used, 0
    recent = room_df.iloc[-6:]
    trend = recent['사용좌석'].diff().mean() if len(recent) > 1 else 0
    delta = trend * (predict_min / 30)
    pred_count = max(0, int(round(current_used + delta)))
    return pred_count, round(delta, 1)

# 7. 그래프 생성 함수 (12시 방향 고정)
def create_unified_chart(used, total, is_open, room_name, density):
    chart_color = '#00CC96' if is_open else '#555555'
    if is_open and density >= 80: chart_color = '#EF553B'
    
    fig = go.Figure(go.Pie(
        values=[used, max(0.1, total - used)], # 0이 되면 그래프가 안 그려지므로 최소값 설정
        hole=.75,
        marker=dict(colors=[chart_color, '#E5ECF6']),
        textinfo='none',
        sort=False,            # 데이터 순서 고정
        direction='clockwise', # 시계 방향
        rotation=0            # 12시 방향 시작 (Plotly 기준 90도 = 상단)
    ))
    
    fig.update_layout(
        title={'text': f"<b>{room_name}</b>", 'x': 0.5},
        showlegend=False,
        height=230,
        margin=dict(t=50, b=0, l=10, r=10),
        annotations=[dict(text=f"<b>{used}/{total}</b>", showarrow=False, font=dict(size=24))]
    )
    return fig

# --- 메인 UI ---
st.sidebar.title("🏛️ 강남자리")
realtime_df = get_realtime_data()
history_df = load_history()

if realtime_df is not None and not realtime_df.empty:
    lib_list = sorted(realtime_df['도서관명'].unique())
    selected_lib = st.sidebar.selectbox("도서관 선택", lib_list)
    if st.sidebar.button("🔄 실시간 새로고침"):
        st.cache_data.clear()
        st.rerun()

    current_lib_df = realtime_df[realtime_df['도서관명'] == selected_lib]
    latest_dt_str = current_lib_df['수집시간'].iloc[0]
    
    st.title(f"🚀 {selected_lib} AI 리포트")
    st.markdown(f"### 📍 실시간 좌석 현황 <small style='color:gray;'>({latest_dt_str} 기준)</small>", unsafe_allow_html=True)

    st.markdown('<p class="slider-title">🔮 도착 예정 시점 선택</p>', unsafe_allow_html=True)
    predict_min = st.select_slider("예측 시간", options=[30, 60, 90, 120, 150, 180], value=30, label_visibility="collapsed")
    future_time_str = (datetime.now() + timedelta(minutes=predict_min)).strftime('%H:%M')

    cols = st.columns(len(current_lib_df))
    for i, (idx, row) in enumerate(current_lib_df.iterrows()):
        with cols[i]:
            room_name = row['열람실명']
            is_open, msg = check_room_open(selected_lib, room_name)
            curr_c = int(row['사용좌석']) if is_open else 0
            total_c = int(row['전체좌석'])
            pred_c, d_val = predict_dynamic(history_df, selected_lib, room_name, curr_c, predict_min) if is_open else (0, 0)

            st.plotly_chart(create_unified_chart(curr_c, total_c, is_open, room_name, row['혼잡도']), use_container_width=True, key=f"chart_{i}")
            
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
                st.markdown(f'<div class="predict-box" style="border-color: #FF4B4B;"><div class="closed-msg">{msg}</div></div>', unsafe_allow_html=True)

    # 7일 전 패턴 분석
    st.divider()
    if history_df is not None:
        st.subheader(f"📅 7일 전 동일 시점 패턴")
        past_7_days = datetime.now().date() - timedelta(days=7)
        history_7d_df = history_df[(history_df['도서관명'] == selected_lib) & (history_df['날짜'] == past_7_days)]
        
        if not history_7d_df.empty:
            time_options = sorted(history_7d_df['시분'].unique())
            target_time = st.select_slider("조회 시간", options=time_options, key="hist_slider")
            past_time_df = history_7d_df[history_7d_df['시분'] == target_time]
            cols2 = st.columns(len(past_time_df))
            for j, (idx2, row2) in enumerate(past_time_df.iterrows()):
                with cols2[j]:
                    h_used = int(row2['사용좌석'])
                    h_total = int(row2['전체좌석'])
                    st.plotly_chart(create_unified_chart(h_used, h_total, True, row2['열람실명'], (h_used/h_total*100)), use_container_width=True, key=f"hist_{j}")
        else:
            st.info(f"ℹ️ 7일 전({past_7_days}) 데이터가 아직 파일에 없습니다.")

    # 실시간 게시판
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
    st.error("📡 실시간 데이터를 불러올 수 없습니다.")