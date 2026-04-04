import streamlit as st
import pandas as pd
import os
import plotly.express as px

# 1. 페이지 설정
st.set_page_config(page_title="도서관 좌석 예측 시스템", layout="wide")

# 2. 데이터 로드 및 전처리
file_path = 'gangnam_lib.csv'
if os.path.exists(file_path):
    df = pd.read_csv(file_path)
    df['수집시간'] = pd.to_datetime(df['수집시간'])
    # 분석을 위해 '시간'만 따로 추출 (예: 09:30)
    df['시분'] = df['수집시간'].dt.strftime('%H:%M')
else:
    st.error("데이터 파일이 없습니다. 'make_weekly_sample.py'를 먼저 실행해 주세요.")
    st.stop()

# --- 사이드바 컨트롤 ---
st.sidebar.title("🛠️ 분석 설정")
selected_lib = st.sidebar.selectbox("🏛️ 도서관 선택", sorted(df['도서관명'].unique()))

# 요일 선택 (한국어 매핑)
day_map = {
    'Monday': '월요일', 'Tuesday': '화요일', 'Wednesday': '수요일',
    'Thursday': '목요일', 'Friday': '금요일', 'Saturday': '토요일', 'Sunday': '일요일'
}
selected_day_en = st.sidebar.selectbox("📅 예측할 요일 선택", list(day_map.keys()), format_func=lambda x: day_map[x])

# --- 데이터 필터링 ---
# 선택한 도서관 + 선택한 요일의 데이터만 추출
predict_df = df[(df['도서관명'] == selected_lib) & (df['요일'] == selected_day_en)]

# 3. 메인 화면
st.title(f"📊 {selected_lib} {day_map[selected_day_en]} 좌석 예측 리포트")
st.markdown(f"**과거 데이터를 기반으로 분석한 {day_map[selected_day_en]}의 시간대별 평균 혼잡도입니다.**")

# --- 4. 시간대별 평균 예측값 계산 ---
# 열람실별, 시간대별(시분)로 평균 사용좌석 계산
avg_prediction = predict_df.groupby(['열람실명', '시분'])['사용좌석'].mean().reset_index()

# 그래프 그리기
st.subheader("📈 시간대별 예상 혼잡도 추이 (09:00 - 18:00)")
if not avg_prediction.empty:
    fig = px.line(avg_prediction, x='시분', y='사용좌석', color='열람실명',
                  markers=True, line_shape='spline',
                  title=f"{day_map[selected_day_en]} 평균 이용 패턴",
                  labels={'시분': '시간', '사용좌석': '평균 예상 인원'})
    
    # 가독성을 위해 x축 시간 순서 정렬
    fig.update_layout(xaxis={'categoryorder':'category ascending'})
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("해당 요일의 데이터가 충분하지 않습니다.")

st.divider()

# --- 5. 상세 시간대별 수치 확인 ---
st.subheader("🔢 상세 예측 데이터 (30분 단위)")
# 사용자가 궁금한 특정 시간을 선택하면 해당 시간의 열람실별 예측값 출력
target_time = st.select_slider("확인하고 싶은 시간을 선택하세요", 
                               options=sorted(avg_prediction['시분'].unique()))

time_filtered = avg_prediction[avg_prediction['시분'] == target_time]

cols = st.columns(len(time_filtered))
for i, (idx, row) in enumerate(time_filtered.iterrows()):
    with cols[i]:
        # 전체 좌석수는 원본 데이터에서 가져옴 (가장 첫 번째 값)
        total = df[(df['도서관명'] == selected_lib) & (df['열람실명'] == row['열람실명'])]['전체좌석'].iloc[0]
        pred_used = int(row['사용좌석'])
        usage_pct = round((pred_used / total) * 100, 1)
        
        st.metric(f"{row['열람실명']}", f"평균 {pred_used}명 이용", f"{usage_pct}% 혼잡")
        st.progress(int(usage_pct))