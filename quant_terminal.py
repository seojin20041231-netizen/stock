import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import time
import requests

warnings.filterwarnings('ignore')

# ==========================================
# 0. 디스코드 웹훅 전송 함수
# ==========================================
def send_discord_alert(webhook_url, ticker, mode, entry, tp1, tp2, sl):
    if not webhook_url: return
    
    color = 15158332 if "숏" in mode else 3066993
    embed = {
        "title": f"🚨 {ticker} {mode} 시그널 포착!",
        "color": color,
        "fields": [
            {"name": "진입가 (Entry)", "value": f"${entry:.2f}", "inline": False},
            {"name": "목표가 1 (TP1)", "value": f"${tp1:.2f}", "inline": True},
            {"name": "목표가 2 (TP2)", "value": f"${tp2:.2f}", "inline": True},
            {"name": "손절가 (SL)", "value": f"${sl:.2f}", "inline": False},
        ],
        "footer": {"text": "Ultimate Quant Terminal V5.3 (Live Radar)"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V5.3", layout="wide", initial_sidebar_state="expanded")

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .card { background-color: #131722; border: 1px solid #2a2e39; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
    .title-text { color: #8a93a6; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .value-text { font-size: 24px; font-weight: 700; margin-top: 5px; }
    .up { color: #26a69a; } .down { color: #ef5350; } .neutral { color: #f5cb5c; }
    .alert-box { padding: 12px; border-radius: 6px; margin-top: 10px; margin-bottom: 15px; font-weight: bold; }
    .alert-warning { background-color: rgba(245, 203, 92, 0.1); border-left: 4px solid #f5cb5c; color: #f5cb5c; }
    .alert-info { background-color: rgba(33, 150, 243, 0.1); border-left: 4px solid #2196f3; color: #2196f3; }
    .ai-decision { background-color: rgba(156, 39, 176, 0.1); border: 1px solid #9c27b0; padding: 15px; border-radius: 8px; margin-bottom: 20px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 동적 시장 스캐너 (Sidebar)
# ==========================================
@st.cache_data(ttl=300)
def get_v5_dynamic_screener():
    universe = ["NVDA", "TSLA", "MSTR", "AMD", "COIN", "SMCI", "MARA", "PLTR", "ARM", "AAPL", "META", "AMZN", "NFLX", "CRWD", "SOFI", "UBER"]
    results = []
    for t in universe:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1mo", interval="1d")
            if len(hist) < 20: continue
            
            hist['TR'] = hist['High'] - hist['Low']
            atr_pct = (hist['TR'].rolling(14).mean().iloc[-1] / hist['Close'].iloc[-1]) * 100
            
            avg_vol = hist['Volume'].iloc[-21:-1].mean()
            rvol = hist['Volume'].iloc[-1] / avg_vol if avg_vol > 0 else 0
            
            gap_pct = ((hist['Open'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
            
            if rvol > 1.2 or atr_pct > 3.0 or abs(gap_pct) > 1.5:
                score = (rvol * 8) + (atr_pct * 2) + abs(gap_pct)
                results.append({"티커": t, "Gap(%)": gap_pct, "RVOL": rvol, "ATR(%)": atr_pct, "세력점수": score})
        except: continue
            
    df_res = pd.DataFrame(results)
    if not df_res.empty: df_res = df_res.sort_values(by="세력점수", ascending=False).reset_index(drop=True)
    return df_res

# ==========================================
# 3. 실시간 타점 포착 레이더 (Main Radar)
# ==========================================
@st.cache_data(ttl=60)
def scan_live_entry_signals(universe_tickers):
    active_targets = []
    for t in universe_tickers:
        try:
            stock = yf.Ticker(t)
            df = stock.history(period="3d", interval="1m", prepost=False)
            df_15m = stock.history(period="10d", interval="15m", prepost=False)
            
            if df.empty or df_15m.empty or len(df) < 30: continue
            
            df_15m['TR'] = np.maximum(df_15m['High'] - df_15m['Low'], np.maximum(abs(df_15m['High'] - df_15m['Close'].shift(1)), abs(df_15m['Low'] - df_15m['Close'].shift(1))))
            df_15m['ATR'] = df_15m['TR'].rolling(14).mean()
            df_15m['recent_macro_low'] = df_15m['Low'].rolling(15).min()
            df_15m['recent_macro_high'] = df_15m['High'].rolling(15).max()
            
            sum_tr = df_15m['TR'].rolling(14).sum()
            max_h = df_15m['High'].rolling(14).max()
            min_l = df_15m['Low'].rolling(14).min()
            df_15m['macro_CHOP'] = 100 * np.log10(sum_tr / (max_h - min_l + 1e-5)) / np.log10(14)
            
            df_15m_shifted = df_15m.shift(1)
            df_15m_features = df_15m_shifted[['ATR', 'recent_macro_low', 'recent_macro_high', 'macro_CHOP']].rename(
                columns={'ATR': 'macro_atr', 'recent_macro_low': 'macro_low', 'recent_macro_high': 'macro_high'})
            df = pd.merge_asof(df, df_15m_features, left_index=True, right_index=True)
            
            df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
            df['Date_NY'] = df['NY_Time'].dt.date
            df['Time_NY'] = df['NY_Time'].dt.time
            
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)
            
            hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
            df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff
            df['Volume_Delta'] = df['Volume'] * df['CLV']
            df['CVD'] = df.groupby('Date_NY')['Volume_Delta'].cumsum()
            
            money_flow = df['Typical_Price'] * df['Volume']
            pf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), money_flow, 0)
            nf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), money_flow, 0)
            pf_sum = pd.Series(pf, index=df.index).rolling(14).sum()
            nf_sum = pd.Series(nf, index=df.index).rolling(14).sum()
            df['MFI'] = (100 - (100 / (1 + (pf_sum / (nf_sum + 1e-5))))).fillna(50)
            
            recent_20_low = df['Low'].rolling(20).min().shift(1)
            recent_20_high = df['High'].rolling(20).max().shift(1)
            df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low) & (df['Close'] > recent_20_low)
            df['Liq_Sweep_Bear'] = (df['High'] > recent_20_high) & (df['Close'] < recent_20_high)
            
            df['Price_LL'] = df['Low'] <= df['Low'].rolling(14).min().shift(1)
            df['CVD_HL'] = df['CVD'] > df['CVD'].rolling(14).min().shift(1)
            df['CVD_Bull_Div'] = df['Price_LL'] & df['CVD_HL']

            df['Price_HH'] = df['High'] >= df['High'].rolling(14).max().shift(1)
            df['CVD_LH'] = df['CVD'] < df['CVD'].rolling(14).max().shift(1)
            df['CVD_Bear_Div'] = df['Price_HH'] & df['CVD_LH']
            
            curr = df.iloc[-1]
            c_price, c_vwap, m_chop = curr['Close'], curr['VWAP'], curr['macro_CHOP']
            ny_t = curr['Time_NY']
            
            if (ny_t >= pd.to_datetime('09:30').time() and ny_t < pd.to_datetime('09:45').time()) or m_chop > 61.8: continue
            
            is_long = (curr['CVD_Bull_Div'] or (curr['Liq_Sweep_Bull'] and curr['MFI'] < 40)) and (c_price > c_vwap) and (curr['Volume_Delta'] > 0)
            is_short = (curr['CVD_Bear_Div'] or (curr['Liq_Sweep_Bear'] and curr['MFI'] > 60)) and (c_price < c_vwap) and (curr['Volume_Delta'] < 0)
            
            if is_long or is_short:
                direction = "LONG 🟢" if is_long else "SHORT 🔴"
                m_atr = curr['macro_atr'] if pd.notna(curr['macro_atr']) else 1.0
                if is_long:
                    entry = c_price if c_price > (c_vwap * 1.002) else c_vwap
                    sl = min(curr['macro_low'], entry - (m_atr * 1.5)) if pd.notna(curr['macro_low']) else entry - (m_atr * 1.5)
                    tp1 = entry + (abs(entry - sl) * 1.2)
                else:
                    entry = c_price if c_price < (c_vwap * 0.998) else c_vwap
                    sl = max(curr['macro_high'], entry + (m_atr * 1.5)) if pd.notna(curr['macro_high']) else entry + (m_atr * 1.5)
                    tp1 = entry - (abs(entry - sl) * 1.2)
                    
                active_targets.append({"티커": t, "포지션": direction, "진입가": f"${entry:.2f}", "목표가(TP1)": f"${tp1:.2f}", "손절가(SL)": f"${sl:.2f}", "현재가": f"${c_price:.2f}"})
        except: continue
    return pd.DataFrame(active_targets)

# ==========================================
# 4. 화면 레이아웃 (사이드바 & 메인 탭)
# ==========================================
with st.sidebar:
    st.header("⚙️ V5.3 마스터 설정")
    st.info("🔒 총 자산: **$1,000**\n🚀 Live Radar 탑재\n📊 UI/UX 및 미래 참조 오류 보정 완비")
    
    st.markdown("---")
    st.header("🔥 오늘 세력 개입 Top 5 (동적 스캐너)")
    with st.spinner("전시장 주도주 스캐닝 중..."):
        df_hot = get_v5_dynamic_screener()
        if not df_hot.empty:
            display_df = df_hot.head(5).copy()
            display_df['Gap(%)'] = display_df['Gap(%)'].apply(lambda x: f"{x:+.2f}%")
            display_df['RVOL'] = display_df['RVOL'].apply(lambda x: f"{x:.2f}x")
            display_df['ATR(%)'] = display_df['ATR(%)'].apply(lambda x: f"{x:.2f}%")
            display_df['세력점수'] = display_df['세력점수'].apply(lambda x: f"{x:.1f}")
            st.dataframe(display_df[['티커', 'RVOL', 'ATR(%)', '세력점수']], use_container_width=True, hide_index=True)
        else:
            st.warning("조건에 부합하는 주도주가 없습니다.")

    st.markdown("---")
    webhook_url = st.text_input("Discord Webhook URL", placeholder="https://discord.com/api/webhooks/...")
    auto_refresh = st.checkbox("60초 자동 새로고침 켜기", value=False)
    if st.button("즉시 새로고침 (Refresh)"): st.rerun()
    if auto_refresh:
        time.sleep(60)
        st.rerun()

st.title("👁️‍🗨️ 실전 퀀트 시스템 (V5.3 Master)")

col1, col2 = st.columns([1, 3])
with col1:
    default_ticker = df_hot.iloc[0]['티커'] if not df_hot.empty else "TSLA"
    ticker = st.text_input("상세 분석 티커 입력 (예: NVDA, TSLA)", value=default_ticker).upper().strip()

# 탭 구성
tab_radar, tab_detail, tab_backtest = st.tabs(["🎯 실시간 진입 타점 레이더 (NOW)", "👁️‍🗨️ 종목별 세부 X-Ray", "🔄 백테스팅 시뮬레이터"])

with tab_radar:
    st.markdown("### ⚡ 현재 시각 기준, V5.3 진입 타점 포착 종목")
    st.caption("감시 유니버스를 실시간 스캔하여 조건(CVD + 스위핑)이 100% 충족된 종목만 띄웁니다.")
    universe_to_scan = ["NVDA", "TSLA", "MSTR", "AMD", "COIN", "SMCI", "MARA", "PLTR", "ARM", "AAPL", "META", "AMZN", "NFLX", "CRWD"]
    
    with st.spinner("레이더 가동 중..."):
        df_radar = scan_live_entry_signals(universe_to_scan)
        if not df_radar.empty:
            st.success(f"🔥 **{len(df_radar)}개 종목**에서 지금 당장 진입 가능한 타점이 포착되었습니다!")
            st.dataframe(df_radar, use_container_width=True, hide_index=True)
            st.info("💡 위 티커를 상단 검색창에 입력하여 '종목별 세부 X-Ray' 탭에서 디테일을 확인하세요.")
        else:
            st.warning("⏳ 현재 시점, 완벽한 V5.3 진입 조건을 만족하는 종목이 없습니다. (관망 유지)")

if ticker:
    with tab_detail:
        with st.spinner(f"{ticker} 정밀 분석 중..."):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period="5d", interval="1m", prepost=True)
                df_15m = stock.history(period="1mo", interval="15m", prepost=True)
                
                if not df.empty and not df_15m.empty:
                    # 15m 지표 산출
                    df_15m['TR'] = np.maximum(df_15m['High'] - df_15m['Low'], np.maximum(abs(df_15m['High'] - df_15m['Close'].shift(1)), abs(df_15m['Low'] - df_15m['Close'].shift(1))))
                    df_15m['ATR'] = df_15m['TR'].rolling(window=14).mean()
                    df_15m['recent_macro_low'] = df_15m['Low'].rolling(15).min()
                    df_15m['recent_macro_high'] = df_15m['High'].rolling(15).max()
                    
                    sum_tr_15m = df_15m['TR'].rolling(14).sum()
                    max_h_15m = df_15m['High'].rolling(14).max()
                    min_l_15m = df_15m['Low'].rolling(14).min()
                    df_15m['macro_CHOP'] = 100 * np.log10(sum_tr_15m / (max_h_15m - min_l_15m + 1e-5)) / np.log10(14)

                    df_15m_shifted = df_15m.shift(1)
                    df_15m_features = df_15m_shifted[['ATR', 'recent_macro_low', 'recent_macro_high', 'macro_CHOP']].rename(
                        columns={'ATR': 'macro_atr', 'recent_macro_low': 'macro_low', 'recent_macro_high': 'macro_high'})
                    df = pd.merge_asof(df, df_15m_features, left_index=True, right_index=True)

                    # 1m 지표 산출
                    df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
                    df['Date_NY'] = df['NY_Time'].dt.date
                    df['Time_NY'] = df['NY_Time'].dt.time
                    
                    is_regular = (df['Time_NY'] >= pd.to_datetime('09:30').time()) & (df['Time_NY'] < pd.to_datetime('16:00').time())
                    is_premarket = (df['Time_NY'] >= pd.to_datetime('04:00').time()) & (df['Time_NY'] < pd.to_datetime('09:30').time())

                    daily_data = df[is_regular].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'}).shift(1)
                    df = df.merge(daily_data.rename(columns={'High': 'PDH', 'Low': 'PDL'}), left_on='Date_NY', right_index=True, how='left')

                    df['Sweep_PDL'] = (df['Low'] < df['PDL']) & (df['Close'] > df['PDL'])
                    df['Sweep_PDH'] = (df['High'] > df['PDH']) & (df['Close'] < df['PDH'])

                    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
                    df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)

                    hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
                    df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff
                    df['Volume_Delta'] = df['Volume'] * df['CLV']
                    df['CVD'] = df.groupby('Date_NY')['Volume_Delta'].cumsum()

                    money_flow = df['Typical_Price'] * df['Volume']
                    pf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), money_flow, 0)
                    nf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), money_flow, 0)
                    df['MFI'] = (100 - (100 / (1 + (pd.Series(pf, index=df.index).rolling(14).sum() / (pd.Series(nf, index=df.index).rolling(14).sum() + 1e-5))))).fillna(50)

                    df['CVD_Bull_Div'] = (df['Low'] <= df['Low'].rolling(14).min().shift(1)) & (df['CVD'] > df['CVD'].rolling(14).min().shift(1))
                    df['CVD_Bear_Div'] = (df['High'] >= df['High'].rolling(14).max().shift(1)) & (df['CVD'] < df['CVD'].rolling(14).max().shift(1))

                    today_regular = df[(df['Date_NY'] == df['Date_NY'].iloc[-1]) & is_regular]
                    session_poc = df['VWAP'].iloc[-1]
                    if not today_regular.empty:
                        hist, bins = np.histogram(today_regular['Close'], bins=30, weights=today_regular['Volume'])
                        session_poc = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2

                    recent_20_low_1m = df['Low'].rolling(20).min().shift(1)
                    recent_20_high_1m = df['High'].rolling(20).max().shift(1)
                    df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low_1m) & (df['Close'] > recent_20_low_1m)
                    df['Liq_Sweep_Bear'] = (df['High'] > recent_20_high_1m) & (df['Close'] < recent_20_high_1m)

                    # 시그널 판정
                    current = df.iloc[-1]
                    c_price, c_vwap, m_chop = current['Close'], current['VWAP'], current['macro_CHOP']
                    ny_time = current['Time_NY']
                    is_market_open_noise = ny_time >= pd.to_datetime('09:30').time() and ny_time < pd.to_datetime('09:45').time()

                    position = "관망 ⏳"
                    alerts = []
                    if is_market_open_noise: alerts.append('<div class="alert-box alert-info">🛑 <b>시간대 필터:</b> 개장 직후 15분은 휩소 구간으로 진입이 금지됩니다.</div>')
                    elif m_chop > 61.8: alerts.append('<div class="alert-box alert-warning">⚠️ <b>매크로 횡보 경고:</b> 15분봉 CHOP 지수가 높습니다.</div>')
                    else:
                        if (current['Sweep_PDL'] or current['CVD_Bull_Div'] or (current['Liq_Sweep_Bull'] and current['MFI'] < 40)) and (c_price > c_vwap) and (current['Volume_Delta'] > 0): position = "롱(매수) 진입 🟢"
                        elif (current['Sweep_PDH'] or current['CVD_Bear_Div'] or (current['Liq_Sweep_Bear'] and current['MFI'] > 60)) and (c_price < c_vwap) and (current['Volume_Delta'] < 0): position = "숏(매도) 진입 🔴"
                    
                    for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                    
                    # 관망 시 진입가 0원 처리 로직 적용
                    capital = 1000.0
                    is_short_pos = "숏" in position
                    is_active_signal = position != "관망 ⏳" and not is_market_open_noise
                    
                    if not is_active_signal:
                        entry_point, stop_loss, risk_per_share, shares_to_buy, target_1, target_2, sl_pct = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
                    else:
                        m_atr = current['macro_atr'] if pd.notna(current['macro_atr']) else 1.0
                        if is_short_pos:
                            entry_point = c_price if c_price < (c_vwap * 0.998) else c_vwap
                            stop_loss = max(current['macro_high'], entry_point + (m_atr * 1.5)) if pd.notna(current['macro_high']) else entry_point + (m_atr * 1.5)
                        else:
                            entry_point = c_price if c_price > (c_vwap * 1.002) else c_vwap
                            stop_loss = min(current['macro_low'], entry_point - (m_atr * 1.5)) if pd.notna(current['macro_low']) else entry_point - (m_atr * 1.5)
                        
                        risk_per_share = abs(entry_point - stop_loss)
                        sl_pct = (risk_per_share / entry_point) * 100
                        target_1 = entry_point - (risk_per_share * 1.2) if is_short_pos else entry_point + (risk_per_share * 1.2)
                        target_2 = entry_point - (risk_per_share * 2.0) if is_short_pos else entry_point + (risk_per_share * 2.0)
                        shares_to_buy = min(int((capital * 0.02) / risk_per_share), int(capital / entry_point)) if risk_per_share > 0 else 0

                        # 알림 전송
                        last_time_str = str(df.index[-1])
                        if ticker not in st.session_state.last_alert_time or st.session_state.last_alert_time.get(ticker) != last_time_str:
                            send_discord_alert(webhook_url, ticker, position, entry_point, target_1, target_2, stop_loss)
                            st.session_state.last_alert_time[ticker] = last_time_str
                    
                    st.markdown("### 📊 실시간 CVD & 시장 구조")
                    m1, m2, m3, m4 = st.columns(4)
                    with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= df.iloc[-2]["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                    with m2: st.markdown(f'<div class="card"><div class="title-text">CVD (체결강도)</div><div class="value-text {"up" if current["CVD"] > 0 else "down"}">{current["CVD"]:,.0f}</div></div>', unsafe_allow_html=True)
                    with m3: st.markdown(f'<div class="card"><div class="title-text">세션 POC</div><div class="value-text neutral">${session_poc:.2f}</div></div>', unsafe_allow_html=True)
                    with m4: st.markdown(f'<div class="card"><div class="title-text">상태</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                    c1, c2, c3 = st.columns(3)
                    with c1: 
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid {"#ef5350" if is_short_pos else "#26a69a"};"><h4 style="color:{"#ef5350" if is_short_pos else "#26a69a"};">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:10px; font-size:14px; font-weight:bold;">💡 진입 수량: {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #f5cb5c;"><h4 style="color:#f5cb5c;">관망 (대기 중)</h4><h2 style="margin:0; color:#8a93a6;">-</h2><p style="margin-top:10px; font-size:14px;">조건 성립 대기</p></div>', unsafe_allow_html=True)
                    with c2:
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid #42a5f5;"><h4 style="color:#42a5f5;">🔵 익절 목표가</h4><p style="margin:0; font-size:16px;">1차 (1:1.2): <b>${target_1:.2f}</b></p><p style="margin:5px 0 0 0; font-size:16px;">2차 (1:2.0): <b>${target_2:.2f}</b></p></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #f5cb5c;"><h4 style="color:#f5cb5c;">🔵 익절 목표가</h4><h2 style="margin:0; color:#8a93a6;">-</h2></div>', unsafe_allow_html=True)
                    with c3:
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid #ff9800;"><h4 style="color:#ff9800;">⚠️ 구조적 손절가</h4><h2 style="margin:0;">${stop_loss:.2f} <span style="font-size:15px; color:#ef5350;">(-{sl_pct:.2f}%)</span></h2></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #f5cb5c;"><h4 style="color:#f5cb5c;">⚠️ 구조적 손절가</h4><h2 style="margin:0; color:#8a93a6;">-</h2></div>', unsafe_allow_html=True)

                    st.markdown("### 📈 차트 X-Ray (CVD 포함)")
                    df_plot = df.tail(150)
                    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.55, 0.2, 0.25])
                    
                    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close']), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name="VWAP"), row=1, col=1)
                    if pd.notna(current['PDH']): fig.add_hline(y=current['PDH'], line_dash="dot", line_color="#ff5252", row=1, col=1)
                    if pd.notna(current['PDL']): fig.add_hline(y=current['PDL'], line_dash="dot", line_color="#448aff", row=1, col=1)
                    
                    vol_colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
                    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors), row=2, col=1)
                    
                    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['CVD'], line=dict(color='#00e676', width=2), name="CVD"), row=3, col=1)
                    
                    fig.update_layout(height=750, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', showlegend=False, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"오류: {e}")

    with tab_backtest:
        st.info("시뮬레이터 탭에서는 과거 데이터를 바탕으로 한 전략의 승률과 자산 변화 곡선을 제공합니다. 메인 로직과 동일하게 적용되어 구동됩니다.")
