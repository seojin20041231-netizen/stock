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
# 0. 디스코드 웹훅 전송 함수
# ==========================================
def send_discord_alert(webhook_url, ticker, mode, entry, tp1, tp2, sl):
    if not webhook_url: return
    
    color = 15158332 if "숏" in mode or "덤핑" in mode else 3066993
    embed = {
        "title": f"🚨 {ticker} {mode} 시그널 포착!",
        "color": color,
        "fields": [
            {"name": "진입가 (Entry)", "value": f"${entry:.2f}", "inline": False},
            {"name": "목표가 1 (TP1)", "value": f"${tp1:.2f}", "inline": True},
            {"name": "목표가 2 (TP2)", "value": f"${tp2:.2f}", "inline": True},
            {"name": "손절가 (SL)", "value": f"${sl:.2f}", "inline": False},
        ],
        "footer": {"text": "Ultimate Momentum Terminal (US 급등주 전용)"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 감시 종목 세팅 (급등주, 밈주식, Top Gainers 스크래핑)
# ==========================================
@st.cache_data(ttl=300)
def get_dynamic_market_leaders():
    momentum_runners = ["MSTR", "SMCI", "CVNA", "COIN", "MARA", "RIOT", "GME", "AMC", "HOOD", "UPST", "AFRM", "RIVN", "LCID", "PLTR", "SOFI", "NIO"]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = 'https://finance.yahoo.com/gainers'
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        scraped_tickers = []
        for a in soup.find_all('a', {'data-test': 'quoteLink'}):
            ticker = a.text.strip()
            if ticker.isalpha() and len(ticker) <= 5:
                scraped_tickers.append(ticker)
                
        combined = scraped_tickers + momentum_runners
        return list(dict.fromkeys(combined))[:60]
    except Exception:
        return momentum_runners[:60]

# ==========================================
# 2. 급등주 전용 스캐너 (RVOL 및 프리마켓 갭 중심)
# ==========================================
@st.cache_data(ttl=300)
def get_momentum_screener(universe):
    results = []
    for t in universe[:20]:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1mo", interval="1d", prepost=True)
            if len(hist) < 20: continue
            
            hist['TR'] = hist['High'] - hist['Low']
            atr_pct = (hist['TR'].rolling(14).mean().iloc[-1] / hist['Close'].iloc[-1]) * 100
            
            avg_vol = hist['Volume'].iloc[-11:-1].mean()
            rvol = hist['Volume'].iloc[-1] / avg_vol if avg_vol > 0 else 0
            gap_pct = ((hist['Open'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
            
            if rvol > 2.5 or atr_pct > 5.0 or abs(gap_pct) > 3.0:
                score = (rvol * 15) + (atr_pct * 3) + abs(gap_pct) * 2
                results.append({"티커": t, "Gap(%)": gap_pct, "RVOL": rvol, "ATR(%)": atr_pct, "폭발점수": score})
        except: continue
            
    df_res = pd.DataFrame(results)
    if not df_res.empty: df_res = df_res.sort_values(by="폭발점수", ascending=False).reset_index(drop=True)
    return df_res

# ==========================================
# 3. [일봉] 폭발 임박 스윙 셋업 스캐너 (VCP / Squeeze)
# ==========================================
@st.cache_data(ttl=3600)
def scan_daily_primed_setups(universe):
    primed_results = []
    for t in universe:
        try:
            stock = yf.Ticker(t)
            df_daily = stock.history(period="1mo", interval="1d")
            if df_daily.empty or len(df_daily) < 15: continue
            
            recent_10d = df_daily.tail(10)
            max_daily_gain = ((recent_10d['High'] - recent_10d['Open']) / recent_10d['Open'] * 100).max()
            surge_volume = recent_10d['Volume'].max()
            
            last_3d = df_daily.tail(3)
            current_vol = df_daily['Volume'].iloc[-1]
            
            volume_dried = current_vol < (surge_volume * 0.3)
            last_3d_tr = (last_3d['High'] - last_3d['Low']) / last_3d['Close'] * 100
            tight_range = last_3d_tr.mean() < 4.0
            
            df_daily['SMA10'] = df_daily['Close'].rolling(10).mean()
            c_price = df_daily['Close'].iloc[-1]
            sma10 = df_daily['SMA10'].iloc[-1]
            above_sma10 = c_price > sma10 and (abs(c_price - sma10) / sma10 * 100) < 5.0
            
            if max_daily_gain >= 15.0 and volume_dried and tight_range and above_sma10:
                primed_results.append({
                    "상태": "🗜️ 스프링 압축 (폭발 임박)",
                    "티커": t,
                    "현재가": f"${c_price:.2f}",
                    "최고 변동": f"+{max_daily_gain:.1f}%",
                    "특이사항": "급등 후 거래량 급감, 10일선 지지 횡보 중"
                })
        except: continue
            
    return pd.DataFrame(primed_results)

# ==========================================
# 4. [1분봉] 급등 직전 & 2차 재급등 고급 레이더
# ==========================================
@st.cache_data(ttl=60)
def scan_advanced_momentum_radar(universe):
    radar_results = []
    for t in universe:
        try:
            stock = yf.Ticker(t)
            df = stock.history(period="2d", interval="1m", prepost=True)
            if df.empty or len(df) < 30: continue
            
            df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
            df['Date_NY'] = df['NY_Time'].dt.date
            
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date_NY').apply(
                lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / (x['Volume'].cumsum() + 1e-5)
            ).reset_index(level=0, drop=True)
            
            df['MA20'] = df['Close'].rolling(20).mean()
            df['STD20'] = df['Close'].rolling(20).std()
            df['Band_Width'] = ((df['MA20'] + 2 * df['STD20']) - (df['MA20'] - 2 * df['STD20'])) / df['MA20'] * 100
            df['Vol_SMA15'] = df['Volume'].rolling(15).mean()
            
            curr, prev = df.iloc[-1], df.iloc[-2]
            c_price, c_vwap = curr['Close'], curr['VWAP']
            is_green = curr['Close'] > curr['Open']
            
            # Pattern 1: 1차 급등 직전 (Pre-Surge Squeeze)
            is_squeezed = df['Band_Width'].tail(10).mean() < 1.2
            volume_ignite = curr['Volume'] > (curr['Vol_SMA15'] * 2.5)
            if is_squeezed and volume_ignite and is_green:
                radar_results.append({
                    "포착 유형": "💣 [1차 폭발 직전] 에너지 응축 후 점화",
                    "티커": t, "현재가": f"${c_price:.2f}",
                    "특이사항": f"차트 수축 상태에서 거래량 {curr['Volume']/curr['Vol_SMA15']:.1f}배 폭발"
                })

            # Pattern 2: 2차 재급등 (2nd Leg Up)
            today_df = df[df['Date_NY'] == curr['Date_NY']]
            if not today_df.empty:
                open_p = today_df['Open'].iloc[0]
                high_p = today_df['High'].max()
                day_gain_pct = ((high_p - open_p) / open_p) * 100
                
                if day_gain_pct >= 8.0:
                    vwap_dist = (c_price - c_vwap) / c_vwap * 100
                    vwap_supported = (0.0 <= vwap_dist <= 1.2)
                    volume_rebound = (curr['Volume'] > prev['Volume'] * 1.8) and is_green
                    if vwap_supported and volume_rebound:
                        radar_results.append({
                            "포착 유형": "🔥 [2차 재급등] VWAP 눌림목 반등",
                            "티커": t, "현재가": f"${c_price:.2f}",
                            "특이사항": f"당일 +{day_gain_pct:.1f}% 기록 후 VWAP 지지 반등"
                        })
        except: continue
            
    df_radar = pd.DataFrame(radar_results)
    if not df_radar.empty:
        df_radar['Rank'] = df_radar['포착 유형'].map(lambda x: 1 if "2차" in x else 2)
        df_radar = df_radar.sort_values(by=['Rank', '티커']).drop(columns=['Rank']).reset_index(drop=True)
    return df_radar

# ==========================================
# 5. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="US Momentum Terminal V2", layout="wide", initial_sidebar_state="expanded")

if 'last_alert_time' not in st.session_state: st.session_state.last_alert_time = {}

st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #f0f0f0; font-family: 'Inter', sans-serif; }
    .card { background-color: #111111; border: 1px solid #333333; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
    .title-text { color: #aaaaaa; font-size: 13px; font-weight: 600; text-transform: uppercase; }
    .value-text { font-size: 24px; font-weight: 700; margin-top: 5px; }
    .up { color: #00ff88; } .down { color: #ff3366; } .neutral { color: #ffcc00; }
    .alert-box { padding: 12px; border-radius: 6px; margin-top: 10px; margin-bottom: 15px; font-weight: bold; }
    .alert-warning { background-color: rgba(255, 204, 0, 0.1); border-left: 4px solid #ffcc00; color: #ffcc00; }
    .alert-success { background-color: rgba(0, 255, 136, 0.1); border-left: 4px solid #00ff88; color: #00ff88; }
    </style>
""", unsafe_allow_html=True)

live_universe = get_dynamic_market_leaders()

with st.sidebar:
    st.header("⚙️ 급등주 터미널 설정")
    st.info(f"🚀 Top Gainers 실시간 크롤링 (현재 감시: {len(live_universe)}개)\n🔥 모멘텀 돌파, 프리마켓 갭 특화")
    
    st.markdown("---")
    st.header("🔥 당일 폭발 주도주 Top 5")
    with st.spinner("급등주 데이터 스캔 중..."):
        df_hot = get_momentum_screener(live_universe)
        if not df_hot.empty:
            display_df = df_hot.head(5).copy()
            display_df['Gap(%)'] = display_df['Gap(%)'].apply(lambda x: f"{x:+.2f}%")
            display_df['RVOL'] = display_df['RVOL'].apply(lambda x: f"{x:.1f}x")
            display_df['폭발점수'] = display_df['폭발점수'].apply(lambda x: f"{x:.0f}")
            st.dataframe(display_df[['티커', 'Gap(%)', 'RVOL', '폭발점수']], use_container_width=True, hide_index=True)
        else:
            st.warning("조건에 부합하는 급등주가 없습니다.")

    st.markdown("---")
    webhook_url = st.text_input("Discord Webhook URL", placeholder="https://discord.com/api/webhooks/...")
    auto_refresh = st.checkbox("60초 자동 새로고침 켜기", value=False)
    if st.button("즉시 새로고침 (Refresh)"): st.rerun()
    if auto_refresh:
        time.sleep(60)
        st.rerun()

st.title("🚀 미국 급등주 스나이퍼 (Momentum Sniper V2)")

# --- [상단] 일봉 관심종목 스캐너 ---
st.markdown("### 📅 [0순위 관심종목] 일봉 수축 및 폭발 준비 셋업 (VCP)")
st.caption("며칠간 뜸을 들이며 에너지를 응축한 종목입니다. 장중에 1분봉 레이더에 이 종목이 포착되면 **강력한 진입 신호**입니다.")
with st.spinner("일봉 셋업 분석 중... (최초 1회 약 10초 소요)"):
    df_primed = scan_daily_primed_setups(live_universe)
    if not df_primed.empty:
        st.dataframe(df_primed, use_container_width=True, hide_index=True)
    else:
        st.info("현재 완벽하게 수축된 일봉 셋업을 가진 종목이 없습니다.")

st.markdown("---")

col1, col2 = st.columns([1, 3])
with col1:
    default_ticker = df_primed.iloc[0]['티커'] if not df_primed.empty else (df_hot.iloc[0]['티커'] if not df_hot.empty else "MSTR")
    ticker = st.text_input("상세 타점 분석 티커 입력", value=default_ticker).upper().strip()

tab_radar, tab_detail = st.tabs(["🎯 급등주 레이더망", "👁️‍🗨️ 정밀 타점 X-Ray"])

with tab_radar:
    st.markdown("### ⚡ 당일 1분봉 특이동향 (Pre-Surge & 2nd Leg)")
    
    with st.spinner("전체 유니버스 모멘텀 스캔 중..."):
        df_radar = scan_advanced_momentum_radar(live_universe)
        if not df_radar.empty:
            st.success(f"🔥 총 **{len(df_radar)}건**의 폭발적 수급이 포착되었습니다!")
            st.dataframe(df_radar, use_container_width=True, hide_index=True)
        else:
            st.warning("⏳ 현재 돌파 또는 수급 유입 중인 종목이 없습니다.")

if ticker:
    with tab_detail:
        with st.spinner(f"{ticker}의 프라미켓 및 정규장 모멘텀 분석 중..."):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period="3d", interval="1m", prepost=True)
                
                if not df.empty:
                    df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
                    df['Date_NY'] = df['NY_Time'].dt.date
                    df['Time_NY'] = df['NY_Time'].dt.time
                    
                    is_premarket = (df['Time_NY'] >= pd.to_datetime('04:00').time()) & (df['Time_NY'] < pd.to_datetime('09:30').time())
                    pm_data = df[is_premarket].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'}).rename(columns={'High': 'PMH', 'Low': 'PML'})
                    df = df.merge(pm_data, left_on='Date_NY', right_index=True, how='left')

                    is_regular = df['Time_NY'] >= pd.to_datetime('09:30').time()
                    
                    def calc_vwap(group):
                        reg_group = group[group['Time_NY'] >= pd.to_datetime('09:30').time()]
                        if reg_group.empty: return pd.Series(index=group.index, dtype=float)
                        tp = (reg_group['High'] + reg_group['Low'] + reg_group['Close']) / 3
                        vwap = (tp * reg_group['Volume']).cumsum() / (reg_group['Volume'].cumsum() + 1e-5)
                        res = pd.Series(index=group.index, dtype=float)
                        res.loc[reg_group.index] = vwap
                        return res

                    df['VWAP'] = df.groupby('Date_NY', group_keys=False).apply(calc_vwap)
                    
                    hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
                    df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff
                    df['CVD'] = (df['Volume'] * df['CLV']).groupby(df['Date_NY']).cumsum()

                    df['TR'] = df['High'] - df['Low']
                    df['ATR'] = df['TR'].rolling(14).mean()
                    df['Vol_SMA10'] = df['Volume'].rolling(10).mean()

                    current = df.iloc[-1]
                    c_price, c_vwap, pmh, pml = current['Close'], current['VWAP'], current['PMH'], current['PML']
                    is_market_open = current['Time_NY'] >= pd.to_datetime('09:30').time()
                    
                    recent_high_20m = df['High'].rolling(20).max().iloc[-2]

                    position = "관망 ⏳"
                    alerts = []
                    
                    vol_spike = current['Volume'] > (current['Vol_SMA10'] * 2.0)
                    
                    if not is_market_open:
                        alerts.append('<div class="alert-box alert-warning">⏳ <b>장전(Pre-Market) 대기 중:</b> 정규장 개장 후 타점 분석이 활성화됩니다.</div>')
                    else:
                        if pd.notna(pmh) and (c_price > pmh) and df.iloc[-2]['Close'] <= pmh:
                            position = "🚀 프리마켓 고점(PMH) 폭발 🟢"
                            alerts.append(f'<div class="alert-box alert-success">🔥 강력한 매수세: 프리마켓 고점(${pmh:.2f})을 돌파했습니다!</div>')
                        elif (c_price > recent_high_20m) and (c_price > c_vwap) and vol_spike:
                            position = "💥 당일 고점(HOD) 돌파 🟢"
                        elif pd.notna(pml) and (c_price < pml):
                            position = "🩸 덤핑 경고 (숏) 🔴"
                            alerts.append(f'<div class="alert-box alert-warning">⚠️ 프리마켓 저점(${pml:.2f}) 이탈. 투매 주의.</div>')

                    for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                    
                    capital = 1000.0
                    is_active_signal = position != "관망 ⏳" and is_market_open
                    
                    if not is_active_signal:
                        entry_point, stop_loss, risk_per_share, shares_to_buy, target_1, target_2, sl_pct = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
                    else:
                        atr = current['ATR'] if pd.notna(current['ATR']) and current['ATR'] > 0 else (c_price * 0.005)
                        
                        if "숏" in position or "경고" in position:
                            entry_point = c_price
                            stop_loss = c_price + (atr * 2.0)
                        else:
                            entry_point = c_price
                            stop_loss = min(c_price - (atr * 2.0), df['Low'].iloc[-2])
                        
                        risk_per_share = abs(entry_point - stop_loss)
                        sl_pct = (risk_per_share / entry_point) * 100
                        target_1 = entry_point + (risk_per_share * 2.0) if "폭발" in position or "돌파" in position else entry_point - (risk_per_share * 2.0)
                        target_2 = entry_point + (risk_per_share * 4.0) if "폭발" in position or "돌파" in position else entry_point - (risk_per_share * 4.0)
                        shares_to_buy = int(capital / entry_point) if entry_point > 0 else 0

                        last_time_str = str(df.index[-1])
                        if ticker not in st.session_state.last_alert_time or st.session_state.last_alert_time.get(ticker) != last_time_str:
                            send_discord_alert(webhook_url, ticker, position, entry_point, target_1, target_2, stop_loss)
                            st.session_state.last_alert_time[ticker] = last_time_str
                    
                    st.markdown("### 📊 실시간 모멘텀 & 핵심 지지저항")
                    m1, m2, m3, m4 = st.columns(4)
                    with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= df.iloc[-2]["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                    with m2: st.markdown(f'<div class="card"><div class="title-text">VWAP (정규장)</div><div class="value-text neutral">${c_vwap:.2f}</div></div>', unsafe_allow_html=True)
                    with m3: st.markdown(f'<div class="card"><div class="title-text">프리마켓 고점(PMH)</div><div class="value-text {"up" if c_price > pmh else "neutral"}">${pmh:.2f}</div></div>', unsafe_allow_html=True)
                    with m4: st.markdown(f'<div class="card"><div class="title-text">상태 (시그널)</div><div class="value-text {"up" if "🟢" in position else "down" if "🔴" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                    c1, c2, c3 = st.columns(3)
                    with c1: 
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid {"#ff3366" if "숏" in position else "#00ff88"};"><h4 style="color:{"#ff3366" if "숏" in position else "#00ff88"};">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:10px; font-size:14px; font-weight:bold;">💡 진입 수량 (풀시드): {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #ffcc00;"><h4 style="color:#ffcc00;">돌파 대기 중</h4><h2 style="margin:0; color:#aaaaaa;">-</h2><p style="margin-top:10px; font-size:14px;">돌파(Breakout) 조건 성립 대기</p></div>', unsafe_allow_html=True)
                    with c2:
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid #00d4ff;"><h4 style="color:#00d4ff;">🔵 홈런 목표가 (RR 1:2 / 1:4)</h4><p style="margin:0; font-size:16px;">절반 매도: <b>${target_1:.2f}</b></p><p style="margin:5px 0 0 0; font-size:16px;">트레일링: <b>${target_2:.2f}</b></p></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #ffcc00;"><h4 style="color:#ffcc00;">🔵 익절 목표가</h4><h2 style="margin:0; color:#aaaaaa;">-</h2></div>', unsafe_allow_html=True)
                    with c3:
                        if entry_point > 0: st.markdown(f'<div class="card" style="border-top: 3px solid #ff3366;"><h4 style="color:#ff3366;">⚠️ 빠른 손절가 (Cut)</h4><h2 style="margin:0;">${stop_loss:.2f} <span style="font-size:15px; color:#ff3366;">(-{sl_pct:.2f}%)</span></h2></div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="card" style="border-top: 3px solid #ffcc00;"><h4 style="color:#ffcc00;">⚠️ 손절가</h4><h2 style="margin:0; color:#aaaaaa;">-</h2></div>', unsafe_allow_html=True)

                    st.markdown("### 📈 모멘텀 전용 X-Ray 차트")
                    df_plot = df.tail(120) 
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                    
                    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="Price"), row=1, col=1)
                    if not df_plot['VWAP'].isna().all():
                        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffcc00', width=2), name="VWAP"), row=1, col=1)
                    if pd.notna(pmh): fig.add_hline(y=pmh, line_dash="dash", line_color="#00ff88", annotation_text="PMH (프리마켓 고점)", row=1, col=1)
                    if pd.notna(pml): fig.add_hline(y=pml, line_dash="dash", line_color="#ff3366", annotation_text="PML (프리마켓 저점)", row=1, col=1)
                    
                    vol_colors = ['#00ff88' if row['Close'] >= row['Open'] else '#ff3366' for idx, row in df_plot.iterrows()]
                    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors, name="Volume"), row=2, col=1)
                    
                    fig.update_layout(height=650, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#050505', plot_bgcolor='#111111', showlegend=False, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
