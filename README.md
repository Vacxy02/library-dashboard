📚 강남구 도서관 실시간 좌석 현황 및 혼잡도 예측 서비스
공공데이터 API를 활용하여 사용자가 도서관 방문 전 여유 좌석을 확인하고, 요일별 데이터를 통해 최적의 방문 시간을 결정할 수 있도록 돕는 대시보드입니다.

🌐 바로가기
실행 URL: https://library-dashboard-kuhstmrgmkzfnep8m7nbiu.streamlit.app

✨ 주요 기능
실시간 좌석 모니터링: 강남구 주요 도서관 및 열람실별 잔여 좌석 상태를 실시간으로 시각화합니다.

열람실별 상세 조회: 도서관 내 일반열람실, 노트북실 등 세부 공간별 이용률을 직관적인 카드로 제공합니다.

요일별 혼잡도 예측: 과거 7일간의 누적 데이터를 분석하여 특정 요일, 특정 시간대의 평균 예상 혼잡도를 그래프로 보여줍니다.

인터랙티브 분석: 타임 슬라이더를 통해 09:00~18:00 사이의 시간대별 이용 패턴을 미리 확인할 수 있습니다.

🛠 사용 기술 (Tech Stack)
Language: Python 3.x

Framework: Streamlit (Web Dashboard)

Data Analysis: Pandas

Visualization: Plotly Express

Deployment: Streamlit Community Cloud

📂 파일 구조
dashboard.py: 메인 대시보드 실행 소스 코드

gangnam_lib.csv: 시계열 데이터가 축적된 데이터베이스 파일

requirements.txt: 서비스 실행을 위한 라이브러리 의존성 명세

make_weekly_sample.py: (개발용) 주간 시계열 데이터 생성 스크립트

📈 서비스 기대 효과
사용자 편의성: 헛걸음 방지 및 효율적인 시간 관리 가능

데이터 기반 의사결정: 혼잡한 시간을 피해 쾌적한 학습 환경 선택 유도

확장성: 향후 기상 데이터 및 시험 기간 변수를 추가하여 예측 정확도 향상 가능
