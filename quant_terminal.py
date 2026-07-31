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
        "footer": {"text": "Ultimate Quant Terminal V5.2 (CVD & Screener)"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V5.2", layout="wide", initial_sidebar_state="expanded")

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
# 4번 보완: 동적 시장 스캐너 (Dynamic Screener)
# ==========================================
@st.cache_data(ttl=300)
def get_v5_dynamic_screener():
    # 넓은 유니버스 타겟 (빅테크, 고변동성, 밈, 반도체, 코인주)
    universe = [
        "NVDA", "TSLA", "MSTR", "AMD", "COIN", "SMCI", "MARA", "PLTR", "ARM", "AAPL", 
        "META", "AMZN", "NFLX", "CRWD", "SOFI", "ROKU", "SNOW", "UBER", "INTC", "MU"
    ]
    results = []
    for t in universe:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1mo", interval="1d")
            if len(hist) < 20: continue
            
            # 1. ATR (일일 변동성)
            hist['TR'] = hist['High'] - hist['Low']
            atr = hist['TR'].rolling(14).mean().iloc[-1]
            close_price = hist['Close'].iloc[-1]
            atr_pct = (atr / close_price) * 100
            
            # 2. RVOL (상대 거래량)
            avg_vol = hist['Volume'].iloc[-21:-1].mean()
            today_vol = hist['Volume'].iloc[-1]
            rvol = today_vol / avg_vol if avg_vol > 0 else 0
            
            # 3. Gap %
            yest_close = hist['Close'].iloc[-2]
            today_open = hist['Open'].iloc[-1]
            gap_pct = ((today_open - yest_close) / yest_close) * 100
            
            # 필터링 조건 (RVOL 1.2+ OR ATR% 3%+ OR Gap% 1.5%+)
            if rvol > 1.2 or atr_pct > 3.0 or abs(gap_pct) > 1.5:
                # 세력 점수 = RVOL 가중치(8) + ATR% 가중치(2) + Gap% 절대값
                score = (rvol * 8) + (atr_pct * 2) + abs(gap_pct)
                results.append({
                    "티커": t,
                    "Gap(%)": gap_pct,
                    "RVOL": rvol,
                    "ATR(%)": atr_pct,
                    "세력점수": score
                })
        except:
            continue
            
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values(by="세력점수", ascending=False).reset_index(drop=True)
    return df_res

with st.sidebar:
    st.header("⚙️ V5.2 마스터 설정")
    st.info("🔒 총 자산: **$1,000**\n🤖 CVD 체결강도 + MTF shift(1) 보정\n🌐 동적 전시장 주도주 스캐너 탑재")
    
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
            top_rec = df_hot.iloc[0]['티커']
            st.success(f"💡 추천 타겟: **{top_rec}** (세력 점수 1위)")
        else:
            st.warning("조건에 부합하는 세력 주도주가 없습니다.")

    st.markdown("---")
    st.header("🔔 무료 메신저 알림")
    webhook_url = st.text_input("Discord Webhook URL", placeholder="https://discord.com/api/webhooks/...")
    
    st.markdown("---")
    st.header("🔄 데이터 갱신")
    auto_refresh = st.checkbox("60초 자동 새로고침 켜기", value=False)
    if st.button("즉시 새로고침 (Refresh)"):
        st.rerun()
    if auto_refresh:
        time.sleep(60)
        st.rerun()

st.title("👁️‍🗨️ 기관급 단타 퀀트 시스템 (V5.2 Master)")
st.caption("CVD 체결강도 추적 + Lookahead Bias 완전 제거 + 동적 주도주 스캐너")

col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    default_ticker = df_hot.iloc[0]['티커'] if not df_hot.empty else "TSLA"
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, MSTR)", value=default_ticker).upper().strip()

if ticker:
    with st.spinner("CVD 체결 강도 및 MTF 구조 분석 중..."):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="1m", prepost=True)
            df_15m = stock.history(period="1mo", interval="15m", prepost=True)
            
            if df.empty or df_15m.empty:
                st.error("데이터가 없습니다. 티커 및 휴장일 여부를 확인하세요.")
                st.stop()

            # ==========================================
            # 2. 매크로 (15분봉) 연산 & Lookahead Bias 제거 (shift(1))
            # ==========================================
            df_15m['EMA20'] = df_15m['Close'].ewm(span=20).mean()
            df_15m['EMA50'] = df_15m['Close'].ewm(span=50).mean()
            macro_trend = "상승 (Bullish) 🟢" if df_15m['EMA20'].iloc[-1] > df_15m['EMA50'].iloc[-1] else "하락 (Bearish) 🔴"
            
            df_15m['TR'] = np.maximum(df_15m['High'] - df_15m['Low'], np.maximum(abs(df_15m['High'] - df_15m['Close'].shift(1)), abs(df_15m['Low'] - df_15m['Close'].shift(1))))
            df_15m['ATR'] = df_15m['TR'].rolling(window=14).mean()
            df_15m['recent_macro_low'] = df_15m['Low'].rolling(15).min()
            df_15m['recent_macro_high'] = df_15m['High'].rolling(15).max()
            
            sum_tr_15m = df_15m['TR'].rolling(14).sum()
            max_h_15m = df_15m['High'].rolling(14).max()
            min_l_15m = df_15m['Low'].rolling(14).min()
            df_15m['macro_CHOP'] = 100 * np.log10(sum_tr_15m / (max_h_15m - min_l_15m)) / np.log10(14)

            # 🚨 1번 오류 보완: 15분봉 데이터를 1분봉에 병합할 때 shift(1)을 걸어 미래 참조 배제
            df_15m_shifted = df_15m.shift(1)
            df_15m_features = df_15m_shifted[['ATR', 'recent_macro_low', 'recent_macro_high', 'macro_CHOP']].rename(
                columns={'ATR': 'macro_atr', 'recent_macro_low': 'macro_low', 'recent_macro_high': 'macro_high'}
            )
            df = pd.merge_asof(df, df_15m_features, left_index=True, right_index=True)

            # ==========================================
            # 3. 마이크로 (1분봉) 지표 & 5번 보완: CVD 체결강도
            # ==========================================
            df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
            df['Date_NY'] = df['NY_Time'].dt.date
            df['Time_NY'] = df['NY_Time'].dt.time
            
            is_regular = (df['Time_NY'] >= pd.to_datetime('09:30').time()) & (df['Time_NY'] < pd.to_datetime('16:00').time())
            is_premarket = (df['Time_NY'] >= pd.to_datetime('04:00').time()) & (df['Time_NY'] < pd.to_datetime('09:30').time())

            # 전일/장전 핵심 가격대 (PDH/PDL/PMH/PML)
            daily_data = df[is_regular].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'}).shift(1)
            df = df.merge(daily_data.rename(columns={'High': 'PDH', 'Low': 'PDL'}), left_on='Date_NY', right_index=True, how='left')
            pm_data = df[is_premarket].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'})
            df = df.merge(pm_data.rename(columns={'High': 'PMH', 'Low': 'PML'}), left_on='Date_NY', right_index=True, how='left')

            # 유동성 스위핑
            df['Sweep_PDL'] = (df['Low'] < df['PDL']) & (df['Close'] > df['PDL'])
            df['Sweep_PDH'] = (df['High'] > df['PDH']) & (df['Close'] < df['PDH'])

            # VWAP
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)

            # 🚨 5번 보완: CVD (Cumulative Volume Delta) 연산
            hl_diff = np.where((df['High'] - df['Low']) == 0, 1e-5, df['High'] - df['Low'])
            df['CLV'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / hl_diff # Close Location Value
            df['Volume_Delta'] = df['Volume'] * df['CLV']
            df['CVD'] = df.groupby('Date_NY')['Volume_Delta'].cumsum()

            # MFI
            money_flow = df['Typical_Price'] * df['Volume']
            pf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), money_flow, 0)
            nf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), money_flow, 0)
            pf_sum = pd.Series(pf, index=df.index).rolling(14).sum()
            nf_sum = pd.Series(nf, index=df.index).rolling(14).sum()
            with np.errstate(divide='ignore', invalid='ignore'):
                mfi_ratio = pf_sum / nf_sum
                df['MFI'] = (100 - (100 / (1 + mfi_ratio))).fillna(50)

            # CVD & Price 다이버전스 (진짜 매수/매도 세력 확인)
            df['Price_LL'] = df['Low'] <= df['Low'].rolling(14).min().shift(1)
            df['CVD_HL'] = df['CVD'] > df['CVD'].rolling(14).min().shift(1)
            df['CVD_Bull_Div'] = df['Price_LL'] & df['CVD_HL'] # 주가는 저점 갱신, CVD는 상승 -> 롱 다이버전스

            df['Price_HH'] = df['High'] >= df['High'].rolling(14).max().shift(1)
            df['CVD_LH'] = df['CVD'] < df['CVD'].rolling(14).max().shift(1)
            df['CVD_Bear_Div'] = df['Price_HH'] & df['CVD_LH'] # 주가는 고점 갱신, CVD는 하락 -> 숏 다이버전스

            # 세션 POC
            today_regular = df[(df['Date_NY'] == df['Date_NY'].iloc[-1]) & is_regular]
            if not today_regular.empty:
                hist, bins = np.histogram(today_regular['Close'], bins=30, weights=today_regular['Volume'])
                session_poc = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2
            else:
                session_poc = df['VWAP'].iloc[-1]

            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            df['Whale_Spike'] = df['Volume'] > (df['Vol_SMA20'] * 3.5)

            recent_20_low_1m = df['Low'].rolling(20).min().shift(1)
            recent_20_high_1m = df['High'].rolling(20).max().shift(1)
            df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low_1m) & (df['Close'] > recent_20_low_1m)
            df['Liq_Sweep_Bear'] = (df['High'] > recent_20_high_1m) & (df['Close'] < recent_20_high_1m)

            # ==========================================
            # 4. 화면 출력부
            # ==========================================
            tab1, tab2 = st.tabs(["👁️‍🗨️ 실시간 CVD 터미널", "🔄 백테스팅 시뮬레이터 (Shift 적용)"])

            with tab1:
                current = df.iloc[-1]
                c_price, c_vwap, m_chop = current['Close'], current['VWAP'], current['macro_CHOP']
                ny_time = current['Time_NY']
                is_market_open_noise = ny_time >= pd.to_datetime('09:30').time() and ny_time < pd.to_datetime('09:45').time()

                alerts = []
                position = "관망 ⏳"
                
                if is_market_open_noise:
                    alerts.append('<div class="alert-box alert-info">🛑 <b>시간대 필터:</b> 개장 직후 15분은 휩소 구간으로 진입이 금지됩니다.</div>')
                elif m_chop > 61.8:
                    alerts.append('<div class="alert-box alert-warning">⚠️ <b>매크로 횡보 경고:</b> 15분봉 CHOP 지수가 높습니다.</div>')
                else:
                    # CVD 필터가 통합된 정밀 진입 시그널
                    is_long = (current['Sweep_PDL'] or current['CVD_Bull_Div'] or (current['Liq_Sweep_Bull'] and current['MFI'] < 40)) and (c_price > c_vwap) and (current['Volume_Delta'] > 0)
                    is_short = (current['Sweep_PDH'] or current['CVD_Bear_Div'] or (current['Liq_Sweep_Bear'] and current['MFI'] > 60)) and (c_price < c_vwap) and (current['Volume_Delta'] < 0)
                    
                    if is_long: position = "롱(매수) 진입 🟢"
                    elif is_short: position = "숏(매도) 진입 🔴"

                for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                
                st.markdown("### 📊 실시간 CVD & 시장 구조")
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= df.iloc[-2]["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="card"><div class="title-text">당일 누적 체결강도 (CVD)</div><div class="value-text {"up" if current["CVD"] > 0 else "down"}">{current["CVD"]:,.0f}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="card"><div class="title-text">세션 진짜 평단가(POC)</div><div class="value-text neutral">${session_poc:.2f}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="card"><div class="title-text">포지션 방향 (V5.2)</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                capital = 1000.0
                is_short_pos = "숏" in position
                entry_point = session_poc if is_short_pos and c_price < session_poc else (min(session_poc if c_price > session_poc else c_vwap, c_price) if not is_short_pos else c_vwap)
                
                m_atr = current['macro_atr'] if pd.notna(current['macro_atr']) else 1.0
                if is_short_pos:
                    stop_loss = max(current['macro_high'], entry_point + (m_atr * 1.5)) if pd.notna(current['macro_high']) else entry_point + (m_atr * 1.5)
                else:
                    stop_loss = min(current['macro_low'], entry_point - (m_atr * 1.5)) if pd.notna(current['macro_low']) else entry_point - (m_atr * 1.5)

                risk_per_share = abs(entry_point - stop_loss)
                sl_pct = (risk_per_share / entry_point) * 100 if entry_point > 0 else 0.0

                auto_risk_pct = 2.0 
                rr_tp1, rr_tp2 = 1.2, 2.0
                mode_color = "#e91e63" if is_short_pos else "#9c27b0"

                target_1 = entry_point - (risk_per_share * rr_tp1) if is_short_pos else entry_point + (risk_per_share * rr_tp1)
                target_2 = entry_point - (risk_per_share * rr_tp2) if is_short_pos else entry_point + (risk_per_share * rr_tp2)

                risk_amount = capital * (auto_risk_pct / 100.0)
                shares_to_buy = min(int(risk_amount / risk_per_share), int(capital / entry_point)) if risk_per_share > 0 else 0

                if position != "관망 ⏳" and not is_market_open_noise:
                    last_time_str = str(df.index[-1])
                    if ticker not in st.session_state.last_alert_time or st.session_state.last_alert_time.get(ticker) != last_time_str:
                        send_discord_alert(webhook_url, ticker, position, entry_point, target_1, target_2, stop_loss)
                        st.session_state.last_alert_time[ticker] = last_time_str

                st.markdown(f"""
                <div class="ai-decision" style="border-left: 5px solid {mode_color};">
                    <h3 style="margin:0; color:{mode_color};">🤖 V5.2 리스크 엔진: {position}</h3>
                    <p style="margin:5px 0 0 0; font-size: 14px;">Lookahead Bias 제거완료. CVD 체결 강도 동의 및 15m 지지/저항 구조적 스톱로스가 설정되었습니다.</p>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns(3)
                with c1: st.markdown(f'<div class="card" style="border-top: 3px solid {"#ef5350" if is_short_pos else "#26a69a"};"><h4 style="color:{"#ef5350" if is_short_pos else "#26a69a"};">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:10px; font-size:14px; font-weight:bold;">💡 진입 수량: {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                with c2: st.markdown(f'<div class="card" style="border-top: 3px solid #42a5f5;"><h4 style="color:#42a5f5;">🔵 익절 목표가</h4><p style="margin:0; font-size:16px;">1차 (1:{rr_tp1}): <b>${target_1:.2f}</b></p><p style="margin:5px 0 0 0; font-size:16px;">2차 (1:{rr_tp2}): <b>${target_2:.2f}</b></p></div>', unsafe_allow_html=True)
                with c3: st.markdown(f'<div class="card" style="border-top: 3px solid #ff9800;"><h4 style="color:#ff9800;">⚠️ 구조적 손절가</h4><h2 style="margin:0;">${stop_loss:.2f} <span style="font-size:15px; color:#ef5350;">(-{sl_pct:.2f}%)</span></h2></div>', unsafe_allow_html=True)

                st.markdown("### 📈 차트 X-Ray (CVD 체결강도 서브차트 포함)")
                df_plot = df.tail(150)
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.55, 0.2, 0.25])
                
                # 캔들스틱 & 핵심 매물대
                fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close']), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name="VWAP"), row=1, col=1)
                if pd.notna(current['PDH']): fig.add_hline(y=current['PDH'], line_dash="dot", line_color="#ff5252", row=1, col=1)
                if pd.notna(current['PDL']): fig.add_hline(y=current['PDL'], line_dash="dot", line_color="#448aff", row=1, col=1)
                
                # 거래량
                vol_colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
                fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors), row=2, col=1)
                
                # 5번 보완: CVD 차트
                cvd_colors = ['#26a69a' if val >= 0 else '#ef5350' for val in df_plot['CVD']]
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['CVD'], line=dict(color='#00e676', width=2), name="CVD"), row=3, col=1)
                
                fig.update_layout(height=750, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with tab2:
                st.markdown("### 🔄 백테스팅 시뮬레이터 (Lookahead Bias 제거 검증)")
                st.caption("15분봉 지표 shift(1) 보정 및 CVD 체결강도 적용 시뮬레이션")
                
                trades = []
                in_trade = False
                trade_type = ""
                b_entry, b_tp, b_sl = 0, 0, 0
                
                for idx, row in df.iterrows():
                    if pd.isna(row['macro_CHOP']) or pd.isna(row['macro_atr']): continue
                    
                    if not in_trade:
                        ny_t = row['Time_NY']
                        if ny_t >= pd.to_datetime('09:30').time() and ny_t < pd.to_datetime('09:45').time(): continue
                        if row['macro_CHOP'] > 61.8: continue
                        
                        is_long_sig = (row['Sweep_PDL'] or row['CVD_Bull_Div'] or (row['Liq_Sweep_Bull'] and row['MFI'] < 40)) and (row['Close'] > row['VWAP']) and (row['Volume_Delta'] > 0)
                        is_short_sig = (row['Sweep_PDH'] or row['CVD_Bear_Div'] or (row['Liq_Sweep_Bear'] and row['MFI'] > 60)) and (row['Close'] < row['VWAP']) and (row['Volume_Delta'] < 0)
                        
                        m_atr = row['macro_atr']
                        
                        if is_long_sig:
                            in_trade = True
                            trade_type = "LONG"
                            b_entry = row['Close']
                            b_sl = min(row['macro_low'], b_entry - (m_atr * 1.5)) if pd.notna(row['macro_low']) else b_entry - (m_atr * 1.5)
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry + (risk * 1.2)
                        elif is_short_sig:
                            in_trade = True
                            trade_type = "SHORT"
                            b_entry = row['Close']
                            b_sl = max(row['macro_high'], b_entry + (m_atr * 1.5)) if pd.notna(row['macro_high']) else b_entry + (m_atr * 1.5)
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry - (risk * 1.2)
                    else:
                        if trade_type == "LONG":
                            if row['Low'] <= b_sl:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "LOSS", "Return(%)": -2.0})
                                in_trade = False
                            elif row['High'] >= b_tp:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "WIN", "Return(%)": 2.4})
                                in_trade = False
                        elif trade_type == "SHORT":
                            if row['High'] >= b_sl:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "LOSS", "Return(%)": -2.0})
                                in_trade = False
                            elif row['Low'] <= b_tp:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "WIN", "Return(%)": 2.4})
                                in_trade = False

                if len(trades) > 0:
                    df_trades = pd.DataFrame(trades)
                    wins = len(df_trades[df_trades['Result'] == 'WIN'])
                    losses = len(df_trades[df_trades['Result'] == 'LOSS'])
                    win_rate = (wins / len(trades)) * 100
                    
                    df_trades['Equity'] = 1000 + (1000 * (df_trades['Return(%)'].cumsum() / 100))
                    final_equity = df_trades['Equity'].iloc[-1]
                    net_profit = ((final_equity - 1000) / 1000) * 100

                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("총 거래 횟수", f"{len(trades)}회")
                    s2.metric("승률 (Win Rate)", f"{win_rate:.1f}%", f"{wins}승 {losses}패")
                    s3.metric("누적 수익률", f"{net_profit:.2f}%", "5일 기준")
                    s4.metric("최종 자산", f"${final_equity:.2f}")

                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(x=df_trades.index, y=df_trades['Equity'], mode='lines+markers', line=dict(color='#26a69a', width=3)))
                    fig_eq.update_layout(title="📈 자산 성장 곡선 (V5.2)", height=300, paper_bgcolor='#0b0e14', plot_bgcolor='#131722', font=dict(color='#8a93a6'))
                    st.plotly_chart(fig_eq, use_container_width=True)
                else:
                    st.info("V5.2의 강화된 조건(CVD + CHOP)을 만족하는 신호가 발생하지 않았습니다.")

        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")
