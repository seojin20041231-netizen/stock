import yfinance as yf
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

def advanced_premarket_scanner(tickers):
    print("🔥 [고급] 본장 슈팅 대기 종목 스캔을 시작합니다...\n")
    results = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 1. 기본 필터링 (주가 및 유통주식수)
            price = info.get('preMarketPrice') or info.get('regularMarketPrice', 0)
            if not (0.5 <= price <= 5.0):
                continue
                
            float_shares = info.get('floatShares') or info.get('sharesOutstanding', float('inf'))
            if float_shares > 20000000:  # 2천만 주 이하
                continue

            # 2. 1분봉 데이터 다운로드 (프리마켓 포함)
            # 오늘 하루 치 1분봉 데이터를 가져옵니다.
            df = stock.history(period="1d", interval="1m", prepost=True)
            if df.empty:
                continue
                
            # 시간대 설정 (미국 동부 표준시 기준)
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize('UTC').tz_convert('America/New_York')
            else:
                df.index = df.index.tz_convert('America/New_York')
                
            # 정규장 개장(09:30) 이전 데이터만 추출 (프리마켓 데이터)
            market_open_time = pd.to_datetime('09:30').time()
            pm_df = df[df.index.time < market_open_time]
            
            if pm_df.empty:
                continue

            # 3. 프리마켓 거래량 및 갭 상승률 계산
            pm_volume = pm_df['Volume'].sum()
            if pm_volume < 500000:  # API 지연 고려 최소 50만 주 이상
                continue
                
            prev_close = info.get('previousClose', pm_df['Close'].iloc[0])
            latest_price = pm_df['Close'].iloc[-1]
            gap_pct = ((latest_price - prev_close) / prev_close) * 100
            
            if gap_pct < 15.0:  # 15% 이상 상승
                continue

            # 4. 고급 차트 로직: VWAP 및 PMH(프리마켓 고점) 계산
            # VWAP = (전형적 가격 * 거래량)의 누적합 / 거래량의 누적합
            pm_df['Typical_Price'] = (pm_df['High'] + pm_df['Low'] + pm_df['Close']) / 3
            pm_df['Cumulative_Vol'] = pm_df['Volume'].cumsum()
            pm_df['Cumulative_Vol_Price'] = (pm_df['Typical_Price'] * pm_df['Volume']).cumsum()
            pm_df['VWAP'] = pm_df['Cumulative_Vol_Price'] / (pm_df['Cumulative_Vol'] + 1e-5)

            current_vwap = pm_df['VWAP'].iloc[-1]
            pm_high = pm_df['High'].max()
            
            # 🎯 핵심 조건 A: 주가가 VWAP 위에서 지지받고 있는가?
            is_above_vwap = latest_price >= current_vwap
            
            # 🎯 핵심 조건 B: 주가가 프리마켓 고점(PMH) 대비 -5% 이내에서 횡보/버티고 있는가?
            is_near_high = latest_price >= (pm_high * 0.95)

            # 두 조건을 모두 만족해야 찐 슈팅 대기 종목
            if is_above_vwap and is_near_high:
                results.append({
                    "티커": ticker.upper(),
                    "현재가($)": f"${latest_price:.2f}",
                    "상승률(%)": f"+{gap_pct:.2f}%",
                    "PM 고점($)": f"${pm_high:.2f}",
                    "VWAP($)": f"${current_vwap:.2f}",
                    "유통주식": f"{float_shares / 1000000:.1f}M",
                    "상태": "🔥 돌파 임박"
                })
                
        except Exception as e:
            continue
            
    # 결과 출력
    df_results = pd.DataFrame(results)
    
    if df_results.empty:
        print("❌ 현재 모든 조건(VWAP 지지 및 고점 근접)을 완벽하게 만족하는 종목이 없습니다.")
    else:
        print("✅ [슈팅 대기] 본장 개장 시 고점 돌파가 유력한 종목입니다:\n")
        print(df_results.to_string(index=False))

# HTS에서 상승률 상위에 뜬 종목 티커들을 여기에 넣습니다.
test_tickers = ["HOLO", "FFIE", "GWAV", "CRKN", "MIRA", "BDRX", "PEGY"] 
advanced_premarket_scanner(test_tickers)
