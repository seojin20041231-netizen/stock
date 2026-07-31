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
        "footer": {"text": "Ultimate Quant Terminal V3.2"}
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        st.sidebar.error(f"알림 전송 실패: {e}")

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V3.2", layout="wide", initial_sidebar_state="expanded")

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
    st.header("⚙️ 시스템 설정")
    st.info("🔒 총 자산: **$1,000** 고정\n🤖 동적 손익비(R:R) 엔진 활성화\n🔄 Pandas 백테스팅 시뮬레이터 탑재")
    
    st.markdown("---")
    st.header("🔔 무료 메신저 알림 (옵션)")
    webhook_url = st.text_input("Discord Webhook URL", placeholder="https://discord.com/api/webhooks/...")
    
    st.markdown("---")
    st.header("🔄 데이터 갱신")
    auto_refresh = st.checkbox("60초 자동 새로고침 켜기", value=False)
    if st.button("즉시 새로고침 (Refresh)"):
        st.rerun()
        
    if auto_refresh:
        time.sleep(60)
        st.rerun()

st.title("👁️‍🗨️ 세력 추적 & 초정밀 단타 퀀트 시스템 (V3.2)")
st.caption("시간대 필터 + Discord 알림 + 과거 5일 Pandas 백테스트 엔진 내장")

col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, SPY)", value="TSLA").upper().strip()

if ticker:
    with st.spinner("데이터 분석 및 백테스팅 엔진 구동 중..."):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="1m", prepost=True)
            df_15m = stock.history(period="1mo", interval="15m", prepost=True)
            
            if df.empty or df_15m.empty:
                st.error("데이터가 없습니다. 티커를 확인하거나 휴장일인지 확인하세요.")
                st.stop()

            # ==========================================
            # 2. 지표 연산 (백테스트를 위해 전체 벡터화)
            # ==========================================
            df['TR'] = np.maximum(df['High'] - df['Low'], np.maximum(abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))))
            df['ATR'] = df['TR'].rolling(window=14).mean()
            df['Date'] = df.index.date
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)
            
            df['Direction'] = np.sign(df['Close'].diff())
            df['OBV'] = (df['Direction'] * df['Volume']).fillna(0).cumsum()

            money_flow = df['Typical_Price'] * df['Volume']
            pf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), money_flow, 0)
            nf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), money_flow, 0)
            pf_sum = pd.Series(pf, index=df.index).rolling(14).sum()
            nf_sum = pd.Series(nf, index=df.index).rolling(14).sum()

            with np.errstate(divide='ignore', invalid='ignore'):
                mfi_ratio = pf_sum / nf_sum
                mfi_calc = 100 - (100 / (1 + mfi_ratio))
                df['MFI'] = mfi_calc.fillna(50)
                df.loc[nf_sum == 0, 'MFI'] = 100

            hist, bins = np.histogram(df['Close'].tail(300), bins=30, weights=df['Volume'].tail(300))
            poc_price = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2

            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Close'].shift(1) > df['Open'].shift(1))
            df['Whale_Spike'] = df['Volume'] > (df['Vol_SMA20'] * 3.5)

            df_15m['EMA20'] = df_15m['Close'].ewm(span=20).mean()
            df_15m['EMA50'] = df_15m['Close'].ewm(span=50).mean()
            macro_trend = "상승 (Bullish) 🟢" if df_15m['EMA20'].iloc[-1] > df_15m['EMA50'].iloc[-1] else "하락 (Bearish) 🔴"
            
            sum_tr = df['TR'].rolling(14).sum()
            max_h = df['High'].rolling(14).max()
            min_l = df['Low'].rolling(14).min()
            df['CHOP'] = 100 * np.log10(sum_tr / (max_h - min_l)) / np.log10(14)
            
            # 구조적 매물대 벡터화 (백테스트용)
            df['recent_15_low'] = df['Low'].rolling(15).min().shift(1)
            df['recent_15_high'] = df['High'].rolling(15).max().shift(1)
            recent_20_low = df['Low'].rolling(20).min().shift(1)
            df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low) & (df['Close'] > recent_20_low)
            
            body = abs(df['Close'] - df['Open'])
            upper_wick = df['High'] - df[['Close', 'Open']].max(axis=1)
            lower_wick = df[['Close', 'Open']].min(axis=1) - df['Low']
            df['Bull_Pin'] = (lower_wick > 2 * body) & (upper_wick < body)
            df['Bull_Engulf'] = (df['Close'].shift(1) < df['Open'].shift(1)) & (df['Open'] < df['Close'].shift(1)) & (df['Close'] > df['Open'].shift(1))

            # 탭 구성
            tab1, tab2 = st.tabs(["👁️‍🗨️ 실시간 터미널", "🔄 백테스팅 시뮬레이터 (과거 5일)"])

            with tab1:
                # ==========================================
                # 3. 실시간 터미널 화면
                # ==========================================
                current = df.iloc[-1]
                prev = df.iloc[-2]
                
                c_price, c_vwap, c_atr, c_chop = current['Close'], current['VWAP'], current['ATR'], current['CHOP']

                last_dt = df.index[-1]
                ny_time = last_dt.tz_convert('America/New_York') if last_dt.tzinfo else last_dt
                is_market_open_noise = ny_time.hour == 9 and ny_time.minute < 45

                alerts = []
                market_state = "추세 진행 중 📈"
                position = "관망 ⏳"
                
                if is_market_open_noise:
                    market_state = "개장 직후 노이즈 구간 🛑"
                    alerts.append('<div class="alert-box alert-info">🛑 <b>시간대 필터:</b> 개장 직후 15분은 휩소가 심한 구간으로 신호를 억제합니다.</div>')
                elif c_chop > 61.8:
                    market_state = "박스권 횡보 중 (휩소 주의) ⏳"
                    alerts.append('<div class="alert-box alert-warning">⚠️ <b>노이즈 경고:</b> CHOP 지수가 높습니다. 보수적으로 접근하세요.</div>')
                else:
                    if current['MFI'] < 80 and (c_price > c_vwap or current['Liq_Sweep_Bull']):
                        position = "롱(매수) 진입 🟢"
                    elif current['MFI'] > 20 and c_price < c_vwap:
                        position = "숏(매도) 진입 🔴"

                for alert in alerts: st.markdown(alert, unsafe_allow_html=True)
                
                st.markdown("### 📊 실시간 시장 구조 분석")
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= prev["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="card"><div class="title-text">거시 추세 (15분봉)</div><div class="value-text {"up" if "상승" in macro_trend else "down"}">{macro_trend}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="card"><div class="title-text">시장 노이즈 (CHOP)</div><div class="value-text {"neutral" if is_market_open_noise or c_chop > 61.8 else "up"}">{market_state}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="card"><div class="title-text">단기 포지션 방향</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

                capital = 1000.0
                is_short = "숏" in position
                entry_point = poc_price if is_short and c_price < poc_price else (min(poc_price if c_price > poc_price else c_vwap, c_price) if not is_short else c_vwap)
                
                volatility_pct = (c_atr / c_price) * 100 if c_price > 0 else 1.0
                atr_multiplier = 2.0 if volatility_pct > 1.2 else 1.5

                if is_short:
                    stop_loss = max(current['recent_15_high'], entry_point + (c_atr * atr_multiplier))
                else:
                    stop_loss = min(current['recent_15_low'], entry_point - (c_atr * atr_multiplier))

                risk_per_share = abs(entry_point - stop_loss)
                sl_pct = (risk_per_share / entry_point) * 100 if entry_point > 0 else 0.0

                auto_risk_pct = 1.5
                rr_tp1, rr_tp2 = 1.2, 2.0
                trade_mode = "⚡ 반등/조정 단타 (스캘핑 모드)"
                mode_color = "#ff9800" if is_short else "#03a9f4"

                target_1 = entry_point - (risk_per_share * rr_tp1) if is_short else entry_point + (risk_per_share * rr_tp1)
                target_2 = entry_point - (risk_per_share * rr_tp2) if is_short else entry_point + (risk_per_share * rr_tp2)

                target_1_pct = (abs(target_1 - entry_point) / entry_point) * 100
                target_2_pct = (abs(target_2 - entry_point) / entry_point) * 100
                risk_amount = capital * (auto_risk_pct / 100.0)
                shares_to_buy = min(int(risk_amount / risk_per_share), int(capital / entry_point)) if risk_per_share > 0 else 0

                if position != "관망 ⏳" and not is_market_open_noise:
                    last_time_str = str(df.index[-1])
                    if ticker not in st.session_state.last_alert_time or st.session_state.last_alert_time.get(ticker) != last_time_str:
                        send_discord_alert(webhook_url, ticker, position, entry_point, target_1, target_2, stop_loss)
                        st.session_state.last_alert_time[ticker] = last_time_str

                st.markdown(f"""
                <div class="ai-decision" style="border-left: 5px solid {mode_color};">
                    <h3 style="margin:0; color:{mode_color};">🤖 AI 동적 리스크 엔진: {trade_mode}</h3>
                    <div style="background-color:rgba(255,255,255,0.05); padding:10px; margin-top:10px; border-radius:5px;">
                        <b>🛡️ 포지션 관리 가이드:</b> 1차 익절 도달 시 50% 매도 후, 손절가를 <b>본절가(진입가)</b>로 즉시 상향하세요.
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns(3)
                with c1: st.markdown(f'<div class="card" style="border-top: 3px solid {"#ef5350" if is_short else "#26a69a"};"><h4 style="color:{"#ef5350" if is_short else "#26a69a"};">{position}</h4><h2 style="margin:0;">${entry_point:.2f}</h2><p style="margin-top:10px; font-size:14px; font-weight:bold;">💡 수량: {shares_to_buy} 주</p></div>', unsafe_allow_html=True)
                with c2: st.markdown(f'<div class="card" style="border-top: 3px solid #42a5f5;"><h4 style="color:#42a5f5;">🔵 손익비(R:R) 익절</h4><p style="margin:0; font-size:16px;">1차 (1:{rr_tp1}): <b>${target_1:.2f}</b></p><p style="margin:5px 0 0 0; font-size:16px;">2차 (1:{rr_tp2}): <b>${target_2:.2f}</b></p></div>', unsafe_allow_html=True)
                with c3: st.markdown(f'<div class="card" style="border-top: 3px solid #ff9800;"><h4 style="color:#ff9800;">⚠️ 유동적 손절</h4><h2 style="margin:0;">${stop_loss:.2f}</h2><p style="margin-top:10px; font-size:13px; color:#8a93a6;">리스크 1.5% 한도 내 차단</p></div>', unsafe_allow_html=True)

                st.markdown("### 📈 세력 추적 X-Ray 차트")
                df_plot = df.tail(150)
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2])
                fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close']), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2)), row=1, col=1)
                vol_colors = ['#f48fb1' if row['Whale_Spike'] and row['Close']<row['Open'] else '#80cbc4' if row['Whale_Spike'] and row['Close']>=row['Open'] else '#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
                fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['CHOP'], line=dict(color='#ce93d8', width=2)), row=3, col=1)
                fig.add_hline(y=61.8, line_dash="dash", line_color="#ef5350", row=3, col=1)
                fig.update_layout(height=750, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with tab2:
                # ==========================================
                # 4. 과거 5일 백테스팅 시뮬레이터 (Pandas 연산)
                # ==========================================
                st.markdown("### 🔄 과거 5일 전략 시뮬레이션 결과")
                st.caption(f"자본금 $1,000 기준, 리스크 1.5% 및 TP1(R:R 1.2) 목표 백테스팅. 슬리피지 미포함. ({ticker})")
                
                trades = []
                in_trade = False
                trade_type = ""
                b_entry, b_tp, b_sl = 0, 0, 0
                
                # Pandas iterrows를 활용한 시뮬레이션
                for idx, row in df.iterrows():
                    if pd.isna(row['CHOP']) or pd.isna(row['ATR']): continue
                    
                    if not in_trade:
                        # 1. 시간 필터 (노이즈 구간 패스)
                        nt = idx.tz_convert('America/New_York') if idx.tzinfo else idx
                        if nt.hour == 9 and nt.minute < 45: continue
                        
                        # 2. 진입 로직
                        is_long_sig = row['CHOP'] < 61.8 and row['MFI'] < 80 and (row['Close'] > row['VWAP'] or row['Liq_Sweep_Bull'])
                        is_short_sig = row['CHOP'] < 61.8 and row['MFI'] > 20 and row['Close'] < row['VWAP']
                        
                        if is_long_sig:
                            in_trade = True
                            trade_type = "LONG"
                            b_entry = row['Close']
                            b_sl = min(row['recent_15_low'], b_entry - row['ATR']*1.5) if pd.notna(row['recent_15_low']) else b_entry - row['ATR']*1.5
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry + (risk * 1.2) # R:R 1.2
                            entry_time = idx
                        elif is_short_sig:
                            in_trade = True
                            trade_type = "SHORT"
                            b_entry = row['Close']
                            b_sl = max(row['recent_15_high'], b_entry + row['ATR']*1.5) if pd.notna(row['recent_15_high']) else b_entry + row['ATR']*1.5
                            risk = abs(b_entry - b_sl)
                            b_tp = b_entry - (risk * 1.2)
                            entry_time = idx
                    else:
                        # 3. 청산 로직 (손절가 or 1차 목표가 터치 시)
                        if trade_type == "LONG":
                            if row['Low'] <= b_sl:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "LOSS", "Return(%)": -1.5}) # 리스크 1.5% 손실
                                in_trade = False
                            elif row['High'] >= b_tp:
                                trades.append({"Time": idx, "Type": "LONG", "Result": "WIN", "Return(%)": 1.5 * 1.2}) # 1.8% 수익
                                in_trade = False
                        elif trade_type == "SHORT":
                            if row['High'] >= b_sl:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "LOSS", "Return(%)": -1.5})
                                in_trade = False
                            elif row['Low'] <= b_tp:
                                trades.append({"Time": idx, "Type": "SHORT", "Result": "WIN", "Return(%)": 1.5 * 1.2})
                                in_trade = False

                # 백테스트 통계 계산
                if len(trades) > 0:
                    df_trades = pd.DataFrame(trades)
                    wins = len(df_trades[df_trades['Result'] == 'WIN'])
                    losses = len(df_trades[df_trades['Result'] == 'LOSS'])
                    win_rate = (wins / len(trades)) * 100
                    
                    # 자산 성장 곡선 계산 (단리 합산 기준)
                    df_trades['Equity'] = 1000 + (1000 * (df_trades['Return(%)'].cumsum() / 100))
                    final_equity = df_trades['Equity'].iloc[-1]
                    net_profit = ((final_equity - 1000) / 1000) * 100

                    # 메트릭 표시
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("총 거래 횟수", f"{len(trades)}회")
                    s2.metric("승률 (Win Rate)", f"{win_rate:.1f}%", f"{wins}승 {losses}패")
                    s3.metric("누적 수익률", f"{net_profit:.2f}%", "5일 기준")
                    s4.metric("최종 자산", f"${final_equity:.2f}")

                    # Equity Curve 차트
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(x=df_trades.index, y=df_trades['Equity'], mode='lines+markers', name='자산($)', line=dict(color='#26a69a', width=3)))
                    fig_eq.update_layout(title="📈 시뮬레이션 자산 성장 곡선", height=300, paper_bgcolor='#0b0e14', plot_bgcolor='#131722', font=dict(color='#8a93a6'))
                    st.plotly_chart(fig_eq, use_container_width=True)

                    with st.expander("📝 전체 매매 내역 보기"):
                        st.dataframe(df_trades[['Time', 'Type', 'Result', 'Return(%)', 'Equity']].style.applymap(
                            lambda x: 'color: #26a69a' if x == 'WIN' else ('color: #ef5350' if x == 'LOSS' else ''), subset=['Result']
                        ))
                else:
                    st.info("조건에 맞는 매매 신호가 지난 5일간 발생하지 않았습니다. (보수적 장세)")

        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")
