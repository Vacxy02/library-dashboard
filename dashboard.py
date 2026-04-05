import streamlit as st
import pandas as pd
import os
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 기본 설정
st.set_page_config(page_title="강남자리: 실시간 AI 리포트", layout="wide", page_icon="🧠")

# 2. 상수 및 경로 설정
API_KEY = "3af9544717cb3978ea6884210598450b71882f047ca2286f6f81f8ad61c4b7e4"
FILE_NAME = "gangnam_lib.csv"
COMMENTS_FILE = "comments.csv"

# 3. [핵심] API 데이터 수집 및 정기 업데이트 로직
def sync_api_data():
    """정각과 30분 주기에 맞춰 API 데이터를 수집하고 CSV에 저장합니다."""
    now = datetime.now()
    current_min = now.minute
    
    # 업데이트 주기 판단 (정각 0~2분 사이 또는 30~32분 사이)
    is_update_time = (0 <= current_min <= 2) or (30 <= current_min <= 32)
    
    if not is_update_time:
        return False

    # 기록 시각 정규화 (예: 14:02 -> 14:00, 14:31 -> 14:30)
    log_time = now.replace(minute=0 if current_min < 15 else 30, second=0, microsecond=0)
    log_time_str = log_time.strftime('%Y-%m-%d %H:%M:%S')

    url = "http://apis.data.go.kr/B551982/plr_v2/rlt_rdrm_info_v2"
    params = {'serviceKey': API_KEY, '_type': 'json', 'pageNo': '1', 'numOfRows': '300'}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'body' in data and 'item' in data['body']:
            items = data['body']['item']
            new_rows = []
            
            for item in items:
                # 강남구 데이터만 필터링
                if item.get('lclgvNm') == '서울특별시 강남구':
                    new_rows.append({
                        '수집시간': log_time_str,
                        '도서관명': item.get('pblibNm'),
                        '열람실명': item.get('rdrmNm'),
                        '전체좌석': int(item.get('tseatCnt') or 0),
                        '사용좌석': int(item.get('useSeatCnt') or 0)
                    })
            
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                if os.path.exists(FILE_NAME):
                    old_df = pd.read_csv(FILE_NAME)
                    # 동일 시각 데이터 중복 저장 방지
                    if old_df.empty or str(old_df.iloc[-1]['수집시간']) != log_time_str:
                        pd.concat([old_df, new_df], ignore_index=True).to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
                        return True
                else:
                    new_df.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
                    return True
    except Exception as e:
        st.sidebar.error(f"API 연결 오류: {e}")
    return False

# 4. 데이터 로드 함수
@st.cache_data(ttl=60)
def load_data():
    sync_api_data() # 데이터 로드 시마다 업데이트 타임 체크
    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)
        df['수집시간'] = pd.to_datetime(df['수집시간'])
        df['날짜'] = df['수집시간'].dt.date
        df['시분'] = df['수집시간'].dt.strftime('%H:%M')
        df['혼잡도'] = (df['사용좌석'] / df['전체좌석'] * 100).fillna(0).clip(0, 100)
        return df
    return None

# 5. 댓글 관리 함수
def load_comments():
    if os.path.exists(COMMENTS_FILE): return pd.read_csv(COMMENTS_FILE)
    return pd.DataFrame(columns=['도서관명', '날짜', '닉네임', '내용'])

def save_comment(lib, nickname, content):
    df_comm = load_comments()
    new_comm = pd.DataFrame({
        '도서관명': [lib], 
        '날짜': [datetime.now().strftime('%Y-%m-%d %H:%M')],
        '닉네임': [nickname], 
        '내용': [content]
    })
    pd.concat([df_comm, new_comm], ignore_index=True).to_csv(COMMENTS_FILE, index=False, encoding='utf-8-sig')

# 6. AI 하이브리드 예측 함수
def predict_hybrid(df, lib_name, room_name):
    room_df = df[(df['도서관명'] == lib_name) & (df['열람실명'] == room_name)].sort_values('수집시간')
    if len(room_df) < 5: return None, 0, 100, False
    
    now_row = room_df.iloc[-1]
    now_count, total_seats = int(now_row['사용좌석']), int(now_row['전체좌석'])
    now_time = now_row['수집시간']
    
    # [1] 최근 실시간 추세 (기울기)
    recent = room_df.iloc[-6:] # 최근 수집된 데이터들
    delta_now = (recent['사용좌석'].diff().mean() * 1) if len(recent) > 1 else 0

    # [2] 7일 전 동일 시간 패턴
    target_past = now_time.date() - timedelta(days=7)
    past_df = room_df[room_df['날짜'] == target_past]
    delta_week, has_past = 0, False
    if not past_df.empty:
        t_str = now_time.strftime('%H:%M')
        t30_str = (now_time + timedelta(minutes=30)).strftime('%H:%M')
        p_t = past_df[past_df['시분'] == t_str]
        p_t30 = past_df[past_df['시분'] == t30_str]
        if not p_t.empty and not p_t30.empty:
            delta_week = int(p_t30.iloc[0]['사용좌석']) - int(p_t.iloc[0]['사용좌석'])
            has_past = True

    # 결합 가중치 및 최종 예측
    combined_delta = (delta_week * 0.7 + delta_now * 0.3) if has_past else (delta_now * 0.5)
    final_delta = min(combined_delta, float(total_seats - now_count)) if combined_delta > 0 else max(combined_delta, -float(now_count))
    
    predicted_count = int(round(now_count + final_delta))
    return predicted_count, round(final_delta, 1), total_seats, has_past

# --- 메인 화면 실행부 ---
df = load_data()

if df is not None:
    # 사이드바 설정
    st.sidebar.title("🏛️ 강남자리 메뉴")
    lib_list = sorted(df['도서관명'].unique())
    selected_lib = st.sidebar.selectbox("도서관을 선택하세요", lib_list)
    
    if st.sidebar.button("🔄 즉시 새로고침"):
        st.cache_data.clear()
        st.rerun()

    # 데이터 필터링
    lib_df = df[df['도서관명'] == selected_lib]
    latest_dt = lib_df['수집시간'].max()
    
    # 상단 타이틀 및 시간 정보
    st.title(f"🚀 {selected_lib} AI 리포트")
    st.markdown(f"### 📍 실시간 현황 <span style='color: #00CC96; font-size: 1.2rem; margin-left: 10px;'>({latest_dt.strftime('%H:%M')} 기준)</span>", unsafe_allow_html=True)
    st.caption("📢 데이터는 매시 정각과 30분에 공공데이터포털 API를 통해 자동 업데이트됩니다.")

    # SECTION 1: 실시간 현황 및 예측 카드
    realtime_df = lib_df[lib_df['수집시간'] == latest_dt]
    cols1 = st.columns(len(realtime_df))
    
    for i, (idx, row) in enumerate(realtime_df.iterrows()):
        with cols1[i]:
            room = row['열람실명']
            curr_c, total_c = int(row['사용좌석']), int(row['전체좌석'])
            pred_c, d_val, _, has_p = predict_hybrid(df, selected_lib, room)
            
            # 원형 그래프
            color = '#EF553B' if row['혼잡도'] >= 80 else '#FFD700' if row['혼잡도'] >= 50 else '#00CC96'
            fig = go.Figure(go.Pie(values=[curr_c, total_c-curr_c], hole=.75, marker=dict(colors=[color, '#E5ECF6']), textinfo='none'))
            fig.update_layout(title={'text': f"<b>{room}</b>", 'x': 0.5, 'y': 0.95}, showlegend=False, height=220, margin=dict(t=50, b=0, l=10, r=10))
            fig.add_annotation(text=f"<b>{curr_c} / {total_c}</b>", showarrow=False, font=dict(size=22, color="#FFFFFF" if curr_c > 0 else "gray"))
            st.plotly_chart(fig, use_container_width=True, key=f"rt_{i}")
            
            # 예측 정보 박스
            mode_tag = "Hybrid" if has_p else "Trend"
            st.markdown(f"""
                <div style="text-align: center; border: 1px solid rgba(255,255,255,0.1); padding: 12px; border-radius: 12px; background-color: rgba(255,255,255,0.03);">
                    <small style="color: gray;">{mode_tag} 30분 뒤 예상</small><br>
                    <span style="font-size: 1.3rem; font-weight: bold;">{pred_c} / {total_c}</span><br>
                    <span style="color: {'#EF553B' if d_val > 0 else '#00CC96' if d_val < 0 else 'gray'}; font-size: 0.9rem;">
                        {'🔺' if d_val > 0 else '🔻' if d_val < 0 else '➖'} {abs(d_val)}명 {'증가' if d_val > 0 else '감소' if d_val < 0 else '유지'}
                    </span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # SECTION 2: 7일 전 동일 시점 패턴 분석
    past_7_days = latest_dt.date() - timedelta(days=7)
    st.subheader(f"📅 7일 전 동일 시점 패턴 ({past_7_days})")
    
    history_7d_df = lib_df[lib_df['날짜'] == past_7_days]
    if not history_7d_df.empty:
        time_options = sorted(history_7d_df['시분'].unique())
        current_time_str = latest_dt.strftime('%H:%M')
        default_idx = time_options.index(current_time_str) if current_time_str in time_options else 0
        
        target_time = st.select_slider("조회 시간 선택", options=time_options, value=time_options[default_idx])
        past_time_df = history_7d_df[history_7d_df['시분'] == target_time].groupby('열람실명').mean(numeric_only=True).reset_index()
        
        cols2 = st.columns(len(past_time_df))
        for i, (idx, row) in enumerate(past_time_df.iterrows()):
            with cols2[i]:
                p_room, p_used, p_total = row['열람실명'], int(row['사용좌석']), int(row['전체좌석'])
                p_color = '#EF553B' if (p_used/p_total*100) >= 80 else '#00CC96'
                fig_p = go.Figure(go.Pie(values=[p_used, p_total-p_used], hole=.75, marker=dict(colors=[p_color, '#E5ECF6']), textinfo='none'))
                fig_p.update_layout(title={'text': f"<b>{p_room}</b>", 'x': 0.5}, showlegend=False, height=180, margin=dict(t=40, b=0))
                fig_p.add_annotation(text=f"<b>{p_used}/{p_total}</b>", showarrow=False, font=dict(size=18))
                st.plotly_chart(fig_p, use_container_width=True, key=f"hist_{i}")
    else:
        st.warning(f"⚠️ {past_7_days} (7일 전) 데이터가 부족하여 패턴 분석이 어렵습니다.")

    # SECTION 3: 이용자 게시판
    st.divider()
    st.subheader("💬 실시간 이용자 게시판")
    with st.form("comment_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 4])
        nick = c1.text_input("닉네임", placeholder="익명")
        text = c2.text_area("내용", placeholder="오늘의 도서관 분위기를 공유해주세요!")
        if st.form_submit_button("댓글 등록") and text:
            save_comment(selected_lib, nick if nick else "익명", text)
            st.toast("댓글이 등록되었습니다!")
            st.rerun()

    comm_df = load_comments()
    lib_comm = comm_df[comm_df['도서관명'] == selected_lib].sort_values(by='날짜', ascending=False)
    for _, r in lib_comm.iterrows():
        with st.chat_message("user"):
            st.write(f"**{r['닉네임']}** | <small style='color: gray;'>{r['날짜']}</small>", unsafe_allow_html=True)
            st.write(r['내용'])

else:
    st.error("데이터 파일이 없거나 API 수집 중입니다. 잠시 후 새로고침 해주세요.")
    if st.button("초기 데이터 수집 시도"):
        st.cache_data.clear()
        st.rerun()
