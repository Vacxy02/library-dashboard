import streamlit as st
import pandas as pd
import os
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="강남자리: 고도화 AI 리포트", layout="wide", page_icon="🧠")

# 2. 데이터 파일 경로 설정
DATA_FILE = 'gangnam_lib.csv'
COMMENTS_FILE = 'comments.csv'

# 3. 데이터 로드 함수 (캐시 적용)
@st.cache_data(ttl=60)
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df['수집시간'] = pd.to_datetime(df['수집시간'])
        df['날짜'] = df['수집시간'].dt.date
        df['시분'] = df['수집시간'].dt.strftime('%H:%M')
        df['혼잡도'] = (df['사용좌석'] / df['전체좌석'] * 100).fillna(0).clip(0, 100)
        return df
    return None

# 4. 댓글 관련 함수
def load_comments():
    if os.path.exists(COMMENTS_FILE):
        return pd.read_csv(COMMENTS_FILE)
    return pd.DataFrame(columns=['도서관명', '날짜', '닉네임', '내용'])

def save_comment(lib, nickname, content):
    df_comm = load_comments()
    new_comm = pd.DataFrame({
        '도서관명': [lib], 
        '날짜': [datetime.now().strftime('%Y-%m-%d %H:%M')],
        '닉네임': [nickname], 
        '내용': [content]
    })
    final_comm = pd.concat([df_comm, new_comm], ignore_index=True)
    final_comm.to_csv(COMMENTS_FILE, index=False, encoding='utf-8-sig')

# --- [핵심 AI] 고도화된 하이브리드 예측 함수 ---
def predict_hybrid(df, lib_name, room_name):
    room_df = df[(df['도서관명'] == lib_name) & (df['열람실명'] == room_name)].sort_values('수집시간')
    if len(room_df) < 10: return None, 0, 0, 100, False
    
    now_row = room_df.iloc[-1]
    now_count, total_seats = int(now_row['사용좌석']), int(now_row['전체좌석'])
    remaining_seats = total_seats - now_count
    now_time = now_row['수집시간']
    
    recent_points = room_df.iloc[-7:] 
    delta_now = (recent_points['사용좌석'].diff().mean() * 6) if len(recent_points) > 1 else 0

    target_past_date = now_time.date() - timedelta(days=7)
    past_week_df = room_df[room_df['날짜'] == target_past_date]
    
    delta_week, has_past_data = 0, False
    if not past_week_df.empty:
        t_str, t_30_str = now_time.strftime('%H:%M'), (now_time + timedelta(minutes=30)).strftime('%H:%M')
        p_t = past_week_df[past_week_df['시분'] == t_str]
        p_t_30 = past_week_df[past_week_df['시분'] == t_30_str]
        if not p_t.empty and not p_t_30.empty:
            delta_week = int(p_t_30.iloc[0]['사용좌석']) - int(p_t.iloc[0]['사용좌석'])
            has_past_data = True

    combined_delta = (delta_week * 0.7 + delta_now * 0.3) if has_past_data else (delta_now * 0.5)
    final_delta = min(combined_delta, float(remaining_seats)) if combined_delta > 0 else max(combined_delta, -float(now_count))
    
    predicted_count = int(round(now_count + final_delta))
    return predicted_count, round(final_delta, 1), (predicted_count/total_seats*100), total_seats, has_past_data

# --- 메인 화면 로직 ---
df = load_data()

if df is not None:
    selected_lib = st.sidebar.selectbox("🏛️ 도서관 선택", sorted(df['도서관명'].unique()))
    lib_df = df[df['도서관명'] == selected_lib]
    latest_dt = lib_df['수집시간'].max()
    
    st.title(f"🚀 {selected_lib} AI 리포트")
    
    # ---------------------------------------------------------
    # SECTION 1: 실시간 현황 (숫자 폰트 확대)
    # ---------------------------------------------------------
    update_time_str = latest_dt.strftime('%H:%M')
    st.markdown(f"### 📍 실시간 현황 <span style='color: #00CC96; font-size: 1.2rem; margin-left: 10px;'>({update_time_str} 기준)</span>", unsafe_allow_html=True)
    
    realtime_df = lib_df[lib_df['수집시간'] == latest_dt]
    cols1 = st.columns(len(realtime_df))
    
    for i, (idx, row) in enumerate(realtime_df.iterrows()):
        with cols1[i]:
            room = row['열람실명']
            curr_c, total_c = int(row['사용좌석']), int(row['전체좌석'])
            pred_c, d_val, p_pct, _, has_past = predict_hybrid(df, selected_lib, room)
            
            # 그래프 설정
            color = '#EF553B' if row['혼잡도'] >= 80 else '#FFD700' if row['혼잡도'] >= 50 else '#00CC96'
            fig = go.Figure(go.Pie(values=[curr_c, total_c-curr_c], hole=.75, marker=dict(colors=[color, '#E5ECF6']), textinfo='none'))
            fig.update_layout(
                title={'text': f"<b>{room}</b>", 'x': 0.5, 'y': 0.95}, 
                showlegend=False, 
                height=220, # 폰트가 커짐에 따라 높이 소폭 조정
                margin=dict(t=50, b=0, l=10, r=10)
            )
            # --- 숫자 폰트 크기 대폭 확대 (22px + Bold) ---
            fig.add_annotation(
                text=f"<b>{curr_c} / {total_c}</b>", 
                showarrow=False, 
                font=dict(size=22, color="#FFFFFF") # 다크모드 대응 흰색 숫자
            )
            st.plotly_chart(fig, use_container_width=True, key=f"realtime_{i}")
            
            mode_tag = "Hybrid" if has_past else "Trend"
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

    # ---------------------------------------------------------
    # SECTION 2: 7일 전 동일 시점 패턴 분석 (숫자 폰트 확대)
    # ---------------------------------------------------------
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
                p_room = row['열람실명']
                p_used, p_total = int(row['사용좌석']), int(row['전체좌석'])
                p_pct = (p_used / p_total) * 100
                p_color = '#EF553B' if p_pct >= 80 else '#FFD700' if p_pct >= 50 else '#00CC96'
                
                fig_p = go.Figure(go.Pie(values=[p_used, p_total-p_used], hole=.75, marker=dict(colors=[p_color, '#E5ECF6']), textinfo='none'))
                fig_p.update_layout(
                    title={'text': f"<b>{p_room}</b>", 'x': 0.5}, 
                    showlegend=False, 
                    height=200, 
                    margin=dict(t=40, b=0)
                )
                # 폰트 20px로 확대
                fig_p.add_annotation(text=f"<b>{p_used}/{p_total}</b>", showarrow=False, font=dict(size=20))
                st.plotly_chart(fig_p, use_container_width=True, key=f"history_{i}")
                st.caption(f"7일 전 {target_time} 상태")
    else:
        st.warning(f"⚠️ {past_7_days} (7일 전) 데이터가 없습니다.")

    # ---------------------------------------------------------
    # SECTION 3: 이용자 게시판
    # ---------------------------------------------------------
    st.divider()
    st.subheader("💬 실시간 이용자 게시판")
    with st.form("comment_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 4])
        nick = c1.text_input("닉네임", placeholder="익명")
        text = c2.text_area("내용", placeholder="오늘 도서관 분위기를 공유해주세요!")
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
    st.error("데이터 파일을 찾을 수 없습니다.") 
