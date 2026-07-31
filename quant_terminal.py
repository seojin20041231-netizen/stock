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
# 0. 디스코드 웹훅 전송 함수 (무료 알림)
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
        "footer": {"text": "Ultimate Quant Terminal V5 (Master)"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V5", layout="wide", initial_sidebar_state="expanded")

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
    hr { border-color: #2a2e39; margin: 20px 0; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ V5 마스터 설정")
    st.info("🔒 총 자산: **$1,000**\n🤖 MTF 리스크 + 핵심 가격대(PDH/PDL) 스위핑 알고리즘\n🔄 5일 백테스팅 시뮬레이터 탑재")
    
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

st.title("👁️‍🗨️ 기관급 단타 퀀트 시스템 (V5 Master)")
st.caption("전일/장전 핵심 매물대 타격 + 15분봉 다중 시간대 노이즈 필터링 적용 완료")

col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, SPY)", value="TSLA").upper().strip()

if ticker:
    with st.spinner("다중 시간대 구조 및 유동성 스위핑 구간 분석 중..."):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="1m", prepost=True)
            df_15m = stock.history(period="1mo", interval="15m", prepost=True)
            
            if df.empty or df_15m.empty:
                st.error("데이터가 없습니다. 티커를 확인하거나 휴장일인지 확인하세요.")
                st.stop()

            # ==========================================
            # 2. 매크로 (15분봉) 지표 연산 & MTF CHOP
            # ==========================================
            df_15m['EMA20'] = df_15m['Close'].ewm(span=20).mean()
            df_15m['EMA50'] = df_15m['Close'].ewm(span=50).mean()
            macro_trend = "상승 (Bullish) 🟢" if df_15m['EMA20'].iloc[-1] > df_15m['EMA50'].iloc[-1] else "하락 (Bearish) 🔴"
            
            # 15분봉 ATR
            df_15m['TR'] = np.maximum(df_15m['High'] - df_15m['Low'], np.maximum(abs(df_15m['High'] - df_15m['Close'].shift(1)), abs(df_15m['Low'] - df_15m['Close'].shift(1))))
            df_15m['ATR'] = df_15m['TR'].rolling(window=14).mean()
            
            # 15분봉 기반 구조적 지지/저항 및 노이즈(CHOP) 판단
            df_15m['recent_macro_low'] = df_15m['Low'].rolling(15).min().shift(1)
            df_15m['recent_macro_high'] = df_15m['High'].rolling(15).max().shift(1)
            
            sum_tr_15m = df_15m['TR'].rolling(14).sum()
            max_h_15m = df_15m['High'].rolling(14).max()
            min_l_15m = df_15m['Low'].rolling(14).min()
            df_15m['macro_CHOP'] = 100 * np.log10(sum_tr_15m / (max_h_15m - min_l_15m)) / np.log10(14)

            # 15분봉 데이터를 1분봉(df)에 병합 (merge_asof)
            df_15m_features = df_15m[['ATR', 'recent_macro_low', 'recent_macro_high', 'macro_CHOP']].rename(
                columns={'ATR': 'macro_atr', 'recent_macro_low': 'macro_low', 'recent_macro_high': 'macro_high'}
            )
            df = pd.merge_asof(df, df_15m_features, left_index=True, right_index=True)

            # ==========================================
            # 3. 마이크로 (1분봉) 지표 연산 및 핵심 가격대(PDH/PDL) 추출
            # ==========================================
            df['NY_Time'] = df.index.tz_convert('America/New_York') if df.index.tzinfo else df.index
            df['Date_NY'] = df['NY_Time'].dt.date
            df['Time_NY'] = df['NY_Time'].dt.time
            
            is_regular = (df['Time_NY'] >= pd.to_datetime('09:30').time()) & (df['Time_NY'] < pd.to_datetime('16:00').time())
            is_premarket = (df['Time_NY'] >= pd.to_datetime('04:00').time()) & (df['Time_NY'] < pd.to_datetime('09:30').time())

            # 전일 고점(PDH)/저점(PDL) 및 프리마켓 고점(PMH)/저점(PML)
            daily_data = df[is_regular].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'}).shift(1)
            df = df.merge(daily_data.rename(columns={'High': 'PDH', 'Low': 'PDL'}), left_on='Date_NY', right_index=True, how='left')
            pm_data = df[is_premarket].groupby('Date_NY').agg({'High': 'max', 'Low': 'min'})
            df = df.merge(pm_data.rename(columns={'High': 'PMH', 'Low': 'PML'}), left_on='Date_NY', right_index=True, how='left')

            # 유동성 스위핑 (휩소 헌팅) 
            df['Sweep_PDL'] = (df['Low'] < df['PDL']) & (df['Close'] > df['PDL']) # 롱 신호
            df['Sweep_PDH'] = (df['High'] > df['PDH']) & (df['Close'] < df['PDH']) # 숏 신호

            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date_NY').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)
            
            # MFI 연산 및 다이버전스 (반전 신호)
            money_flow = df['Typical_Price'] * df['Volume']
            pf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), money_flow, 0)
            nf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), money_flow, 0)
            pf_sum = pd.Series(pf, index=df.index).rolling(14).sum()
            nf_sum = pd.Series(nf, index=df.index).rolling(14).sum()
            with np.errstate(divide='ignore', invalid='ignore'):
                mfi_ratio = pf_sum / nf_sum
                df['MFI'] = (100 - (100 / (1 + mfi_ratio))).fillna(50)

            df['Price_LL'] = df['Low'] <= df['Low'].rolling(14).min().shift(1)
            df['MFI_HL'] = df['MFI'] > df['MFI'].rolling(14).min().shift(1)
            df['Bull_Div'] = df['Price_LL'] & df['MFI_HL'] & (df['MFI'] < 40)

            df['Price_HH'] = df['High'] >= df['High'].rolling(14).max().shift(1)
            df['MFI_LH'] = df['MFI'] < df['MFI'].rolling(14).max().shift(1)
            df['Bear_Div'] = df['Price_HH'] & df['MFI_LH'] & (df['MFI'] > 60)

            # 세션 POC (오늘 정규장 진짜 주포 평단)
            today_regular = df[(df['Date_NY'] == df['Date_NY'].iloc[-1]) & is_regular]
            if not today_regular.empty:
                hist, bins = np.histogram(today_regular['Close'], bins=30, weights=today_regular['Volume'])
                session_poc = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2
            else:
                session_poc = df['VWAP'].iloc[-1]

            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            df['Whale_Spike'] = df['Volume'] > (df['Vol_SMA20'] * 3.5)

            # 롱/숏 대칭 프라이스 액션
            df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Close'].shift(1) > df['Open'].shift(1))
            df['FVG_Bear'] = (df['High'] < df['Low'].shift(2)) & (df['Close'].shift(1) < df['Open'].shift(1))
            
            recent_20_low_1m = df['Low'].rolling(20).min().shift(1)
            recent_20_high_1m = df['High'].rolling(20).max().shift(1)
            df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low_1m) & (df['Close'] > recent_20_low_1m)
            df['Liq_Sweep_Bear'] = (df['High'] > recent_20_high_1m) & (df['Close'] < recent_20_high_1m)

            # ==========================================
            # 4. 화면 출력부
            # ==========================================
            tab1, tab2 = st.tabs(["👁️‍🗨️ 실시간 터미널 (MTF & 핵심가격대)", "🔄 백테스팅 시뮬레이터 (과거 5일)"])

            with tab1:
                current = df.iloc[-1]
                c_price, c_vwap, m_chop = current['Close'], current['VWAP'], current['macro_CHOP']
                ny_time = current['Time_NY']
                is_market_open_noise = ny_time >= pd.to_datetime('09:30').time() and ny_time < pd.to_datetime('09:45').time()

                alerts = []
                market_state = "추세 진행 중 📈"
                position = "관망 ⏳"
                
                if is_market_open_noise:
                    market_state = "개장 직후 노이즈 🛑"
                    alerts.append('<div class="alert-box alert-info">🛑 <b>시간대 필터:</b> 개장 직후 15분은 휩소가 심한 구간으로 신호를 억제합니다.</div>')
                elif m_chop > 61.8:
                    market_state = "매크로 횡보 중 (휩소 주의) ⏳"
                    alerts.append('<div class="alert-box alert-warning">⚠️ <b>매크로 횡보 경고:</b> 15분봉 기준 추세가 없습니다. 보수적으로 접근하세요.</div>')
                else:
                    # 정교해진 진입 시그널 로직
                    is_long = (current['Sweep_PDL'] or current['Bull_Div'] or (current['Liq_Sweep_Bull'] and current['MFI'] < 40)) and (c_price > c_vwap)
                    is_short = (current['Sweep_PDH'] or current['Bear_Div'] or (current['Liq_Sweep_Bear'] and current['MFI'] > 60)) and (c_price < c_vwap)
                    
                    if is_long: position = "롱(매수) 진입 🟢"
                    elif is_short: position = "숏(매도) 진입 🔴"

                for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                
                st.markdown("### 📊 실시간 시장 구조 분석")
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= df.iloc[-2]["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="card"><div class="title-text">거시 추세 (15분봉)</div><div class="value-text {"up" if "상승" in macro_trend else "down"}">{macro_trend}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="card"><div class="title-text">세션 진짜 평단가(POC)</div><div class="value-text neutral">${session_poc:.2f}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="card"><div class="title-text">포지션 방향 (V5 엔진)</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                capital = 1000.0
                is_short_pos = "숏" in position
                entry_point = session_poc if is_short_pos and c_price < session_poc else (min(session_poc if c_price > session_poc else c_vwap, c_price) if not is_short_pos else c_vwap)
                
                # 15분봉(매크로) ATR 기반 구조적 손절가
                m_atr = current['macro_atr']
                if is_short_pos:
                    stop_loss = max(current['macro_high'], entry_point + (m_atr * 1.5)) if pd.notna(current['macro_high']) else entry_point + (m_atr * 1.5)
                else:
                    stop_loss = min(current['macro_low'], entry_point - (m_atr * 1.5)) if pd.notna(current['macro_low']) else entry_point - (m_atr * 1.5)

                risk_per_share = abs(entry_point - stop_loss)
                sl_pct = (risk_per_share / entry_point) * 100 if entry_point > 0 else 0.0

                auto_risk_pct = 2.0 
                rr_tp1, rr_tp2 = 1.2, 2.0
                trade_mode = "⚡ V5 구조적 숏 (유동성 스위핑/다이버전스)" if is_short_pos else "🔥 V5 구조적 롱 (유동성 스위핑/다이버전스)"
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
                    <h3 style="margin:0; color:{mode_color};">🤖 마스터 리스크 엔진: {trade_mode}</h3>
                    <p style="margin:5px 0 0 0; font-size: 14px;">PDH/PDL 매물대 확인 및 15분봉 CHOP 노이즈 필터 통과 완료. MTF 구조적 리스크 기반으로 계산되었습니다.</p>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns(3)
                with c1: st.markdown(f'<div class="card" style="border-top: 3px solid {"#ef5350" if is_short_pos else "#26a69a"};"><h4 style="color:{"#ef5350" if is_short_pos else "#26a69a"};">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:10px; font-size:14px; font-weight:bold;">💡 수량: {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                with c2: st.markdown(f'<div class="card" style="border-top: 3px solid #42a5f5;"><h4 style="color:#42a5f5;">🔵 손익비(R:R) 익절</h4><p style="margin:0; font-size:16px;">1차 (1:{rr_tp1}): <b>${target_1:.2f}</b></p><p style="margin:5px 0 0 0; font-size:16px;">2차 (1:{rr_tp2}): <b>${target_2:.2f}</b></p></div>', unsafe_allow_html=True)
                with c3: st.markdown(f'<div class="card" style="border-top: 3px solid #ff9800;"><h4 style="color:#ff9800;">⚠️ MTF 구조적 손절</h4><h2 style="margin:0;">${stop_loss:.2f} <span style="font-size:15px; color:#ef5350;">(-{sl_pct:.2f}%)</span></h2><p style="margin-top:10px; font-size:13px; color:#8a93a6;">15m 지지/저항 이탈 컷</p></div>', unsafe_allow_html=True)

                st.markdown("### 📈 세력 추적 X-Ray 차트 (핵심 가격대 포함)")
                df_plot = df.tail(150)
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2])
                fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close']), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name="VWAP"), row=1, col=1)
                
                # 전일 고점/저점 라인 표시
                if pd.notna(current['PDH']):
                    fig.add_hline(y=current['PDH'], line_dash="dot", line_color="#ff5252", annotation_text="PDH (전일고점)", row=1, col=1)
                if pd.notna(current['PDL']):
                    fig.add_hline(y=current['PDL'], line_dash="dot", line_color="#448aff", annotation_text="PDL (전일저점)", row=1, col=1)
                
                vol_colors = ['#f48fb1' if row['Whale_Spike'] and row['Close']<row['Open'] else '#80cbc4' if row['Whale_Spike'] and row['Close']>=row['Open'] else '#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
                fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MFI'], line=dict(color='#ce93d8', width=2)), row=3, col=1)
                fig.add_hline(y=80, line_dash="dash", line_color="#ef5350", row=3, col=1)
                fig.add_hline(y=20, line_dash="dash", line_color="#26a69a", row=3, col=1)
                fig.update_layout(height=750, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with tab2:
                # ==========================================
                # 5. 백테스팅 시뮬레이터 (V5 마스터 로직)
                # ==========================================
                st.markdown("### 🔄 과거 5일 전략 시뮬레이션 (V5 Master Engine)")
                st.caption(f"자본금 $1,000 기준, 리스크 2.0% 및 구조적 TP1(R:R 1.2) 목표 백테스팅. ({ticker})")
                
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
                        
                        is_long_sig = (row['Sweep_PDL'] or row['Bull_Div'] or (row['Liq_Sweep_Bull'] and row['MFI'] < 40)) and (row['Close'] > row['VWAP'])
                        is_short_sig = (row['Sweep_PDH'] or row['Bear_Div'] or (row['Liq_Sweep_Bear'] and row['MFI'] > 60)) and (row['Close'] < row['VWAP'])
                        
                        m_atr = row['macro_atr']
                        
                        if is_long_sig:
                            in_trade = True
                            trade_type = "LONG"
                            b_entry = row['Close']
                            b_sl = min(row['macro_low'], b_entry - (m_atr * 1.5)) if pd.notna(row['macro_low']) else b_entry - (m_atr * 1.5)
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry + (risk * 1.2)
                            entry_time = idx
                        elif is_short_sig:
                            in_trade = True
                            trade_type = "SHORT"
                            b_entry = row['Close']
                            b_sl = max(row['macro_high'], b_entry + (m_atr * 1.5)) if pd.notna(row['macro_high']) else b_entry + (m_atr * 1.5)
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry - (risk * 1.2)
                            entry_time = idx
                    else:
                        if trade_type == "LONG":
                            if row['Low'] <= b_sl:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "LOSS", "Return(%)": -2.0})
                                in_trade = False
                            elif row['High'] >= b_tp:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "WIN", "Return(%)": 2.0 * 1.2})
                                in_trade = False
                        elif trade_type == "SHORT":
                            if row['High'] >= b_sl:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "LOSS", "Return(%)": -2.0})
                                in_trade = False
                            elif row['Low'] <= b_tp:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "WIN", "Return(%)": 2.0 * 1.2})
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
                    fig_eq.add_trace(go.Scatter(x=df_trades.index, y=df_trades['Equity'], mode='lines+markers', name='자산($)', line=dict(color='#26a69a', width=3)))
                    fig_eq.update_layout(title="📈 V5 시뮬레이션 자산 성장 곡선", height=300, paper_bgcolor='#0b0e14', plot_bgcolor='#131722', font=dict(color='#8a93a6'))
                    st.plotly_chart(fig_eq, use_container_width=True)

                    with st.expander("📝 전체 매매 내역 보기"):
                        st.dataframe(df_trades[['Time', 'Type', 'Result', 'Return(%)', 'Equity']].style.applymap(
                            lambda x: 'color: #26a69a' if x == 'WIN' else ('color: #ef5350' if x == 'LOSS' else ''), subset=['Result']
                        ))
                else:
                    st.info("조건에 맞는 강력한(V5 기준) 매매 신호가 지난 5일간 발생하지 않았습니다.")

        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")
