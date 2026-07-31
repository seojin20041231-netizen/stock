import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="프리마켓 타임머신 스캐너", layout="wide")

st.title("🕰️ 프리마켓 타임머신 스캐너 (주말/과거 테스트용)")
st.markdown("""
주말이나 장 마감 후에도 **'가장 최근 거래일'**의 데이터를 바탕으로, 특정 시간대(예: 장전 8시 30분)의 차트 흐름을 시뮬레이션합니다.
""")

# --- 사이드바 UI 설정 ---
st.sidebar.header("⚙️ 스캐너 및 타임머신 설정")
default_tickers = "HOLO, FFIE, GWAV, CRKN, MIRA, BDRX, PEGY, GME, AMC, PLTR"
ticker_input = st.sidebar.text_area("검색할 티커 목록 (쉼표로 구분)", value=default_tickers)

st.sidebar.markdown("---")
st.sidebar.subheader("⏳ 시간 시뮬레이션")
st.sidebar.caption("한국시간 21:30 = 뉴욕시간 08:30 (서머타임 적용)")
sim_time = st.sidebar.time_input("시뮬레이션 시간 (뉴욕 기준)", value=datetime.time(8, 30))

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 필터링 강도 조절 (테스트용)")
gap_threshold = st.sidebar.slider("최소 갭 상승률 (%)", min_value=0, max_value=50, value=5, step=1)
vol_threshold = st.sidebar.number_input("최소 거래량 (주)", min_value=10000, max_value=5000000, value=100000, step=50000)
pmh_range = st.sidebar.slider("고점 근접 허용범위 (-%)", min_value=0, max_value=15, value=5, step=1)

if st.sidebar.button("🚀 타임머신 스캔 시작"):
    tickers = [t.strip().upper() for t in ticker_input.split(",")]
    
    with st.spinner(f"마지막 거래일 뉴욕시간 {sim_time.strftime('%H:%M')} 기준으로 스캔 중..."):
        results = []
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                
                # 1. 일봉 데이터로 전일 종가(Previous Close) 구하기
                daily_df = stock.history(period="5d", interval="1d")
                if len(daily_df) < 2:
                    continue
                
                # 2. 1분봉 데이터 다운로드 (최근 5일)
                df = stock.history(period="5d", interval="1m", prepost=True)
                if df.empty:
                    continue
                    
                # 시간대 변환 (뉴욕 기준)
                if df.index.tzinfo is None:
                    df.index = df.index.tz_localize('UTC').tz_convert('America/New_York')
                else:
                    df.index = df.index.tz_convert('America/New_York')
                    
                # 🎯 핵심: 데이터 중 가장 마지막 거래일만 추출
                latest_date = df.index.date.max()
                df_latest = df[df.index.date == latest_date]
                
                # 일봉 기준 전일 종가 세팅 (마지막 거래일의 바로 전날)
                try:
                    prev_close = daily_df.loc[daily_df.index.date < latest_date]['Close'].iloc[-1]
                except:
                    prev_close = df_latest['Close'].iloc[0]
                
                # 🎯 핵심: 사용자가 설정한 '시뮬레이션 시간' 이전의 데이터만 잘라내기
                pm_df = df_latest[df_latest.index.time <= sim_time]
                
                if pm_df.empty:
                    continue

                # 3. 거래량 및 갭 상승률 필터링
                pm_volume = pm_df['Volume'].sum()
                if pm_volume < vol_threshold:
                    continue
                    
                latest_price = pm_df['Close'].iloc[-1]
                gap_pct = ((latest_price - prev_close) / prev_close) * 100
                
                if gap_pct < gap_threshold:
                    continue

                # 4. VWAP 및 PMH(프리마켓 고점) 계산
                pm_df['Typical_Price'] = (pm_df['High'] + pm_df['Low'] + pm_df['Close']) / 3
                pm_df['Cumulative_Vol'] = pm_df['Volume'].cumsum()
                pm_df['Cumulative_Vol_Price'] = (pm_df['Typical_Price'] * pm_df['Volume']).cumsum()
                pm_df['VWAP'] = pm_df['Cumulative_Vol_Price'] / (pm_df['Cumulative_Vol'] + 1e-5)

                current_vwap = pm_df['VWAP'].iloc[-1]
                pm_high = pm_df['High'].max()
                
                # VWAP 지지 여부 및 고점 근접도 계산
                is_above_vwap = latest_price >= current_vwap
                pmh_limit = pm_high * (1 - (pmh_range / 100))
                is_near_high = latest_price >= pmh_limit

                # 두 조건을 만족하면 결과에 추가
                if is_above_vwap and is_near_high:
                    results.append({
                        "티커": ticker,
                        "시뮬레이션 일자": str(latest_date),
                        "현재가(시점기준)": f"${latest_price:.2f}",
                        "갭 상승률": f"+{gap_pct:.2f}%",
                        "PM 고점": f"${pm_high:.2f}",
                        "VWAP": f"${current_vwap:.2f}",
                        "거래량": f"{int(pm_volume):,} 주",
                        "상태": "✅ 셋업 통과"
                    })
                    
            except Exception as e:
                continue
                
        # 결과 출력
        st.markdown(f"### 📊 결과 보고서 (뉴욕시간 **{sim_time.strftime('%H:%M')}** 기준)")
        
        if not results:
            st.error("❌ 해당 시간대 기준으로 조건을 만족하는 종목이 없습니다. (좌측 사이드바에서 조건 강도를 낮추고 다시 테스트해 보세요!)")
        else:
            st.success(f"✅ 총 {len(results)}개의 종목이 포착되었습니다.")
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True, hide_index=True)

