import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="급등주 2차 타점 검색기 PRO", layout="wide")
st.title("🚀 급등주 2차 타점 검색기 PRO (갭돌파 & 윗꼬리 필터링)")

st.markdown("""
**[핵심 매매 철학]**  
1. 첫 거래량 폭발은 패스, 두 번째 기회를 노린다.
2. 하락 시 거래량은 무조건 줄어야 한다. 터지면 위험!
3. 윗꼬리가 긴 캔들은 악성 매물이므로 피한다.
4. 강력한 저항인 '하락 갭'을 갭상승으로 돌파하면 스윙(Swing) 기회다.
""")

# 사이드바 설정
st.sidebar.header("검색 조건 설정")
target_value = st.sidebar.number_input("기준 거래대금 (원)", value=1000000000, step=100000000)
volume_spike_ratio = st.sidebar.slider("첫날 거래량 급등 기준 (몇 배?)", 2.0, 10.0, 5.0)

tickers_input = st.sidebar.text_area("종목 티커 입력 (쉼표로 구분)", "005930.KS, 035420.KS, 035720.KS, 000660.KS")
tickers = [t.strip() for t in tickers_input.split(",")]

@st.cache_data(ttl=3600)
def fetch_data(ticker):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=180)
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    return df

# 윗꼬리 판별 함수
def is_long_upper_shadow(candle):
    open_p, close_p, high_p = candle['Open'], candle['Close'], candle['High']
    # .item()을 사용하여 Series 1차원 데이터를 안전하게 스칼라값으로 변환
    if isinstance(open_p, pd.Series): open_p = open_p.item()
    if isinstance(close_p, pd.Series): close_p = close_p.item()
    if isinstance(high_p, pd.Series): high_p = high_p.item()
    
    body = abs(open_p - close_p)
    if body == 0: body = 1 # 0으로 나누는 것 방지 (도지 캔들)
    upper_shadow = high_p - max(open_p, close_p)
    
    # 윗꼬리가 몸통보다 1.5배 이상 길면 True (위험)
    return upper_shadow > (body * 1.5)

# 하락 갭(Gap Down) 저항선 찾기 함수
def find_recent_falling_gap(df, days_lookback=20):
    gap_resistance = None
    for i in range(len(df) - days_lookback, len(df) - 2):
        prev_low = df['Low'].iloc[i-1]
        curr_high = df['High'].iloc[i]
        
        # Series인 경우 값 추출
        if isinstance(prev_low, pd.Series): prev_low = prev_low.item()
        if isinstance(curr_high, pd.Series): curr_high = curr_high.item()
        
        if curr_high < prev_low:
            gap_resistance = prev_low # 하락 갭의 상단을 저항선으로 설정
    return gap_resistance

def analyze_pattern(df):
    if len(df) < 65:
        return "데이터 부족"
    
    df['Trading_Value'] = df['Close'] * df['Volume']
    df['Vol_60MA'] = df['Volume'].rolling(window=60).mean()
    
    day_0 = df.iloc[-2]
    day_1 = df.iloc[-1]
    
    # [추가 조건 2] 윗꼬리 필터링 (Day 0, Day 1 모두 체크)
    if is_long_upper_shadow(day_0) or is_long_upper_shadow(day_1):
        return "패스: 🚨 [위험] 일봉 상 악성 윗꼬리 발생"
        
    # [추가 조건 1] 하락 시 거래량 폭발 필터링 (빠지면서 내려와야 함)
    day_1_close = day_1['Close'].item() if isinstance(day_1['Close'], pd.Series) else day_1['Close']
    day_0_close = day_0['Close'].item() if isinstance(day_0['Close'], pd.Series) else day_0['Close']
    day_1_vol = day_1['Volume'].item() if isinstance(day_1['Volume'], pd.Series) else day_1['Volume']
    day_0_vol = day_0['Volume'].item() if isinstance(day_0['Volume'], pd.Series) else day_0['Volume']
    
    if day_1_close < day_0_close and day_1_vol >= day_0_vol:
        return "패스: 🚨 [위험] 하락 중 거래량 증가 (세력 이탈 의심)"

    # [추가 조건 3] 갭(Gap) 돌파 스윙 타점 체크
    gap_resistance = find_recent_falling_gap(df)
    day_1_open = day_1['Open'].item() if isinstance(day_1['Open'], pd.Series) else day_1['Open']
    
    if gap_resistance and day_1_open > gap_resistance:
        return f"🚀 [스윙 타점] 철벽같던 하락 갭 저항선({gap_resistance:,.0f}원)을 갭상승으로 돌파!"

    # --- 기존 조건 확인 ---
    past_60 = df.iloc[-62:-2]
    avg_trading_value = past_60['Trading_Value'].mean().item() if isinstance(past_60['Trading_Value'].mean(), pd.Series) else past_60['Trading_Value'].mean()
    
    if avg_trading_value > target_value:
        return f"패스: 3개월 횡보/저유동성 조건 미달"
        
    vol_60ma = day_0['Vol_60MA'].item() if isinstance(day_0['Vol_60MA'], pd.Series) else day_0['Vol_60MA']
    if day_0_vol < vol_60ma * volume_spike_ratio:
        return "패스: Day 0 첫 거래량 폭발 조건 미달"
        
    day_0_open = day_0['Open'].item() if isinstance(day_0['Open'], pd.Series) else day_0['Open']
    
    day_0_is_yang = day_0_close > day_0_open
    day_1_is_yin = day_1_close < day_1_open
    day_1_is_yang = day_1_close > day_1_open
    
    vol_drop_ratio = day_1_vol / day_0_vol
    
    if day_0_is_yang:
        if day_1_is_yin and vol_drop_ratio < 0.3:
            return "🔥 [눌림목 진입] 양봉 폭등 후 강한 음봉 + 거래량 70% 이상 급감 (숨 고르기)"
        else:
            return "패스: 양봉 이후 조건 불일치"
            
    else: 
        if day_1_is_yin and vol_drop_ratio < 0.2:
            target_price = day_0_close * 0.6
            return f"🔥 [타점 대기] 음봉마감 후 거래량 소멸. 목표 진입가: 약 {target_price:,.0f}원 부근"
        elif vol_drop_ratio >= 0.8 and (abs(day_1_close - day_1_open) / day_1_open < 0.02):
            return "패스: 🚨 거래량 유지 + 약한 움직임 (설거지 가능성)"
        elif vol_drop_ratio > 1.0 and day_1_is_yang:
            return "🔥 [진입 후 보유] 음봉 이후 거래량 증가 + 약한 양봉 출현"
        else:
            return "패스: 일치하는 시나리오 없음"

if st.button("조건 검색 실행"):
    with st.spinner("최신 데이터 다운로드 및 패턴 분석 중..."):
        results = []
        for ticker in tickers:
            try:
                df = fetch_data(ticker)
                status = analyze_pattern(df)
                results.append({"종목(Ticker)": ticker, "분석 결과": status})
            except Exception as e:
                results.append({"종목(Ticker)": ticker, "분석 결과": f"오류 발생: {str(e)}"})
                
        result_df = pd.DataFrame(results)
        
        st.subheader("📊 검색 결과")
        
        # 타점이나 스윙 자리가 발견된 종목은 눈에 띄게 하이라이트 처리
        def highlight_rows(val):
            if "위험" in str(val) or "설거지" in str(val):
                return "background-color: #ffe6e6; color: #cc0000"
            elif "스윙" in str(val):
                return "background-color: #e6f2ff; color: #0000ff; font-weight: bold"
            elif "타점" in str(val) or "진입" in str(val):
                return "background-color: #e6ffe6; color: #006600; font-weight: bold"
            return ""
            
        st.dataframe(result_df.style.applymap(highlight_rows, subset=['분석 결과']), use_container_width=True)
