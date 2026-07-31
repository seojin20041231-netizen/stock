import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import time
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')

# ==========================================
# 0. 디스코드 웹훅 전송 함수 (롱 전용 컬러)
# ==========================================
def send_discord_alert(webhook_url, ticker, mode, entry, tp1, tp2, sl):
    if not webhook_url: return
    
    embed = {
        "title": f"🚀 {ticker} {mode} 시그널 포착!",
        "color": 3066993, 
        "fields": [
            {"name": "진입가 (Entry)", "value": f"${entry:.2f}", "inline": False},
            {"name": "목표가 1 (TP1)", "value": f"${tp1:.2f}", "inline": True},
            {"name": "목표가 2 (TP2)", "value": f"${tp2:.2f}", "inline": True},
            {"name": "손절가 (SL)", "value": f"${sl:.2f}", "inline": False},
        ],
        "footer": {"text": "Ultimate Quant Terminal V5.5 (Strict Long-Only)"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 감시 종목 (섹터별 핵심 주도주 60선 + 크롤링)
# ==========================================
@st.cache_data(ttl=600)
def get_dynamic_market_leaders():
    mega_tech = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]
    semiconductors = ["AMD", "SMCI", "AVGO", "MU", "INTC", "QCOM", "ARM", "ASML", "TSM"]
    crypto_meme = ["MSTR", "COIN", "MARA", "RIOT", "GME", "AMC", "HOOD"]
    ai_software = ["PLTR", "CRWD", "SNOW", "ADBE", "CRM", "DDOG", "NET", "PATH"]
    ev_energy = ["RIVN", "LCID", "XPEV", "NIO", "ENPH", "FSLR"]
    finance_others = ["JPM", "V", "MA", "PYPL", "SQ", "SOFI", "AFRM", "UPST", "CVNA", "DKNG", "UBER", "SHOP"]
    
    robust_universe = mega_tech + semiconductors + crypto_meme + ai_software + ev_energy + finance_others
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = 'https://finance.yahoo.com/most-active'
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        scraped_tickers = []
        
        for a in soup.find_all('a', {'data-test': 'quoteLink'}):
            ticker = a.text.strip()
            if ticker.isalpha() and len(ticker) <= 5:
                scraped_tickers.append(ticker)
                
        combined = scraped_tickers + robust_universe
        unique_tickers = list(dict.fromkeys(combined))[:65]
        return unique_tickers
        
    except Exception:
        return robust_universe[:65]

# ==========================================
# 2. 동적 시장 스캐너
# ==========================================
@st.cache_data(ttl=300)
def get_v5_dynamic_screener(universe):
    results = []
    for t in universe[:15]:
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
                score = (rvol * 8) + (atr_pct * 2) + gap_pct 
                results.append({"티커": t, "Gap(%)": gap_pct, "RVOL": rvol, "ATR(%)": atr_pct, "세력점수": score})
        except: continue
            
    df_res = pd.DataFrame(results)
    if not df_res.empty: df_res = df_res.sort_values(by="세력점수", ascending=False).reset_index(drop=True)
    return df_res

# ==========================================
# 3. 다관점 4중 레이더 (매수 관점 위주)
# ==========================================
@st.cache_data(ttl=60)
def scan_multi_perspective_radar(universe):
    radar_results = []
    for t in universe:
        try:
            stock = yf.Ticker(t)
            df = stock.history(period="2d", interval="1m", prepost=False)
            if df.empty or len(df) < 30: continue
            
            df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
            df['Date_NY'] = df['NY_Time'].dt.date
            
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)
            
            hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
            df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff
            df['Volume_Delta'] = df['Volume'] * df['CLV']
            df['CVD'] = df.groupby('Date_NY')['Volume_Delta'].cumsum()
            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            
            recent_20_low_val = df['Low'].rolling(20).min().shift(1).iloc[-1]
            recent_20_high_val = df['High'].rolling(20).max().shift(1).iloc[-1]
            
            curr = df.iloc[-1]
            c_price = curr['Close']
            c_vwap = curr['VWAP']
            
            # 레이더는 감시 목적이므로 기존 조건 유지
            if curr['Volume'] > (curr['Vol_SMA20'] * 2.5) and curr['Close'] > curr['Open']:
                radar_results.append({"포착 관점": "🐋 단기 매수 수급 유입 🟢", "티커": t, "현재가": f"${c_price:.2f}", "특이사항": f"평균 대비 {(curr['Volume']/curr['Vol_SMA20']):.1f}배 매수 거래량"})
                
            vwap_dist_pct = abs(c_price - c_vwap) / c_vwap * 100
            if vwap_dist_pct <= 0.5 and curr['CVD'] > df.iloc[-2]['CVD']:
                radar_results.append({"포착 관점": "⏳ VWAP 눌림/반등 대기", "티커": t, "현재가": f"${c_price:.2f}", "특이사항": f"VWAP 지지 및 CVD 상승 중"})
                
            liq_sweep = (curr['Low'] < recent_20_low_val) and (c_price > recent_20_low_val)
            cvd_rising = curr['CVD'] > df['CVD'].rolling(10).min().iloc[-2]
            if liq_sweep and cvd_rising and (c_price > c_vwap):
                radar_results.append({"포착 관점": "🚨 V5 정밀 롱 타점", "티커": t, "현재가": f"${c_price:.2f}", "특이사항": "매물대 스위핑 및 CVD 동의"})
                
            if (c_price > recent_20_high_val) and (curr['Volume_Delta'] > 0):
                radar_results.append({"포착 관점": "📈 단기 고점 돌파 (모멘텀)", "티커": t, "현재가": f"${c_price:.2f}", "특이사항": "매수세 유입 동반 단기 고점 돌파"})
                
        except: continue
            
    df_radar = pd.DataFrame(radar_results)
    if not df_radar.empty:
        df_radar['Rank'] = df_radar['포착 관점'].map(lambda x: 1 if "🚨" in x else (2 if "📈" in x else (3 if "🐋" in x else 4)))
        df_radar = df_radar.sort_values(by=['Rank', '티커']).drop(columns=['Rank']).reset_index(drop=True)
    return df_radar

# ==========================================
# 4. 터미널 UI 및 메인 로직
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V5.5", layout="wide", initial_sidebar_state="expanded")

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
    </style>
""", unsafe_allow_html=True)

live_universe = get_dynamic_market_leaders()

with st.sidebar:
    st.header("⚙️ V5.5 롱 전용 설정 (Strict Mode)")
    st.info(f"🔒 총 자산: **$1,000**\n🚀 AI 주도주 크롤링 탑재 (현재 감시: {len(live_universe)}개)\n📈 고승률 매수(Long) 시그널 필터 적용")
    
    st.markdown("---")
    st.header("🔥 오늘 시장의 주도주 Top 5")
    with st.spinner("데이터 연동 중..."):
        df_hot = get_v5_dynamic_screener(live_universe)
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

st.title("👁️‍🗨️ 실전 퀀트 시스템 (V5.5 깐깐한 타점 Master)")

col1, col2 = st.columns([1, 3])
with col1:
    default_ticker = df_hot.iloc[0]['티커'] if not df_hot.empty else "TSLA"
    ticker = st.text_input("상세 분석 티커 입력 (예: NVDA)", value=default_ticker).upper().strip()

tab_radar, tab_detail = st.tabs(["🎯 실시간 4중 매수 레이더망", "👁️‍🗨️ 종목별 세부 X-Ray (엄격 검증)"])

with tab_radar:
    st.markdown("### ⚡ 매수 전용 4중 레이더")
    st.caption(f"안정적인 감시를 위해 총 **{len(live_universe)}개**의 주도주를 **상승(매수) 관점**으로 스캔합니다.")
    
    with st.spinner("매수 타점 레이더망 가동 중..."):
        df_radar = scan_multi_perspective_radar(live_universe)
        if not df_radar.empty:
            st.success(f"🔥 총 **{len(df_radar)}건**의 롱(매수) 유력 동향이 포착되었습니다!")
            st.dataframe(df_radar, use_container_width=True, hide_index=True)
        else:
            st.warning("⏳ 현재 확실한 매수 타점에 진입한 종목이 없습니다.")

if ticker:
    with tab_detail:
        with st.spinner(f"{ticker} 정밀 분석 중 (이중 필터 적용)..."):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period="5d", interval="1m", prepost=False)
                df_15m = stock.history(period="1mo", interval="15m", prepost=False)
                
                if not df.empty and not df_15m.empty:
                    # 15분 매크로 지표 계산 (엄격한 추세 판별용)
                    df_15m['EMA20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
                    df_15m['EMA50'] = df_15m['Close'].ewm(span=50, adjust=False).mean()
                    df_15m['TR'] = np.maximum(df_15m['High'] - df_15m['Low'], np.maximum(abs(df_15m['High'] - df_15m['Close'].shift(1)), abs(df_15m['Low'] - df_15m['Close'].shift(1))))
                    df_15m['ATR'] = df_15m['TR'].rolling(window=14).mean()
                    
                    df_15m_shifted = df_15m.shift(1)[['ATR', 'EMA20', 'EMA50']].rename(
                        columns={'ATR': 'macro_atr', 'EMA20': 'macro_ema20', 'EMA50': 'macro_ema50'})
                    df = pd.merge_asof(df, df_15m_shifted, left_index=True, right_index=True)

                    df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
                    df['Date_NY'] = df['NY_Time'].dt.date
                    df['Time_NY'] = df['NY_Time'].dt.time

                    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
                    df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)

                    hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
                    df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff
                    df['Volume_Delta'] = df['Volume'] * df['CLV']
                    df['CVD'] = df.groupby('Date_NY')['Volume_Delta'].cumsum()
                    df['Vol_SMA20'] = df['Volume'].rolling(20).mean()

                    recent_20_low_1m_val = df['Low'].rolling(20).min().shift(1).iloc[-1]
                    recent_20_high_1m_val = df['High'].rolling(20).max().shift(1).iloc[-1]

                    today_regular = df[df['Date_NY'] == df['Date_NY'].iloc[-1]]
                    session_poc = df['VWAP'].iloc[-1]
                    if not today_regular.empty:
                        hist, bins = np.histogram(today_regular['Close'], bins=30, weights=today_regular['Volume'])
                        session_poc = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2

                    current = df.iloc[-1]
                    c_price, c_vwap = current['Close'], current['VWAP']
                    ny_time = current['Time_NY']
                    
                    is_market_open_noise = ny_time >= pd.to_datetime('09:30').time() and ny_time < pd.to_datetime('09:45').time()

                    position = "관망 ⏳"
                    signal_reason = ""
                    alerts = []

                    if is_market_open_noise:
                        alerts.append('<div class="alert-box alert-info">🛑 <b>시간대 필터:</b> 개장 직후 15분은 휩소 구간으로 진입이 금지됩니다.</div>')

                    # ==========================================
                    # 🎯 엄격한 매수(Long) 타점 로직
                    # ==========================================
                    # 1. 15분 큰 추세 필터 (역추세 매매 방지)
                    macro_uptrend = (current['macro_ema20'] > current['macro_ema50']) or (c_price > current['macro_ema50'])
                    
                    # 2. 강력한 모멘텀 조건 (5분 연속 매수세 및 3배 거래량)
                    vwap_dist_pct = abs(c_price - c_vwap) / c_vwap * 100
                    cvd_strong_trend = current['CVD'] > df['CVD'].rolling(5).mean().iloc[-1] # 최근 5분 평균보다 매수세가 강해야 함
                    vol_mega_burst = current['Volume'] > (current['Vol_SMA20'] * 3.0) # 거래량 3배 이상 폭발만 취급
                    
                    # 1. 완벽한 추세 속 VWAP 눌림목 (거리 0.3% 이내 초근접)
                    if macro_uptrend and (vwap_dist_pct <= 0.3) and (c_price >= c_vwap) and cvd_strong_trend:
                        position = "롱(매수) 진입 🟢"
                        signal_reason = "15분 상승 추세 속 VWAP 완벽 지지 및 강한 수급 유입"
                    
                    # 2. 강력한 거래량 폭발 모멘텀 (역추세라도 거래량이 압도적이면 진입)
                    elif vol_mega_burst and (c_price > recent_20_high_1m_val) and (current['Close'] > current['Open']):
                        position = "롱(매수) 진입 🟢"
                        signal_reason = "3배 이상 거래량 동반한 강력한 단기 고점 돌파"
                    
                    # 3. Liquidity Sweep (저점 깨고 급격한 추세 전환)
                    elif (current['Low'] < recent_20_low_1m_val) and (c_price > recent_20_low_1m_val) and cvd_strong_trend:
                        position = "롱(매수) 진입 🟢"
                        signal_reason = "저점 매물대 소화(Sweep) 후 강력한 매수세(CVD) 동반 추세 전환"
                        
                    if not macro_uptrend and position == "관망 ⏳":
                        alerts.append('<div class="alert-box alert-warning">⚠️ <b>매크로 하락장:</b> 15분봉 큰 추세가 하락 중입니다. 보수적 접근이 필요합니다.</div>')

                    for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                    
                    capital = 1000.0
                    is_active_signal = (position != "관망 ⏳") and not is_market_open_noise
                    
                    if not is_active_signal:
                        entry_point, stop_loss, risk_per_share, shares_to_buy, target_1, target_2, sl_pct = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
                    else:
                        m_atr = current['macro_atr'] if pd.notna(current['macro_atr']) and current['macro_atr'] > 0 else (c_price * 0.005)
                        entry_point = c_price
                        
                        stop_loss = entry_point - (m_atr * 1.5)
                        risk_per_share = abs(entry_point - stop_loss)
                        sl_pct = (risk_per_share / entry_point) * 100 if entry_point > 0 else 0
                        
                        target_1 = entry_point + (risk_per_share * 1.2)
                        target_2 = entry_point + (risk_per_share * 2.0)
                        shares_to_buy = min(int((capital * 0.02) / risk_per_share), int(capital / entry_point)) if risk_per_share > 0 else 0

                        last_time_str = str(df.index[-1])
                        if ticker not in st.session_state.last_alert_time or st.session_state.last_alert_time.get(ticker) != last_time_str:
                            send_discord_alert(webhook_url, ticker, position, entry_point, target_1, target_2, stop_loss)
                            st.session_state.last_alert_time[ticker] = last_time_str
                    
                    st.markdown("### 📊 실시간 CVD & 시장 구조")
                    m1, m2, m3, m4 = st.columns(4)
                    with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if len(df) > 1 and c_price >= df.iloc[-2]["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                    with m2: st.markdown(f'<div class="card"><div class="title-text">CVD (체결강도)</div><div class="value-text {"up" if current["CVD"] > 0 else "down"}">{current["CVD"]:,.0f}</div></div>', unsafe_allow_html=True)
                    with m3: st.markdown(f'<div class="card"><div class="title-text">세션 POC</div><div class="value-text neutral">${session_poc:.2f}</div></div>', unsafe_allow_html=True)
                    with m4: st.markdown(f'<div class="card"><div class="title-text">상태</div><div class="value-text {"up" if "롱" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                    c1, c2, c3 = st.columns(3)
                    with c1: 
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid #26a69a;"><h4 style="color:#26a69a;">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:5px; font-size:12px; color:#8a93a6;">{signal_reason}</p><p style="margin-top:5px; font-size:14px; font-weight:bold;">💡 진입 수량: {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #f5cb5c;"><h4 style="color:#f5cb5c;">관망 (대기 중)</h4><h2 style="margin:0; color:#8a93a6;">-</h2><p style="margin-top:10px; font-size:14px;">엄격한 타점 성립 대기중</p></div>', unsafe_allow_html=True)
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
                    
                    vol_colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
                    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['CVD'], line=dict(color='#00e676', width=2), name="CVD"), row=3, col=1)
                    
                    fig.update_layout(height=750, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', showlegend=False, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"데이터 분석 중 오류가 발생했습니다: {e}")
