import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import time

warnings.filterwarnings('ignore')

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal V2.5", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .card { background-color: #131722; border: 1px solid #2a2e39; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
    .title-text { color: #8a93a6; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .value-text { font-size: 24px; font-weight: 700; margin-top: 5px; }
    .up { color: #26a69a; } .down { color: #ef5350; } .neutral { color: #f5cb5c; }
    .alert-box { padding: 12px; border-radius: 6px; margin-top: 10px; margin-bottom: 15px; font-weight: bold; }
    .alert-danger { background-color: rgba(239, 83, 80, 0.1); border-left: 4px solid #ef5350; color: #ef5350; }
    .alert-success { background-color: rgba(38, 166, 154, 0.1); border-left: 4px solid #26a69a; color: #26a69a; }
    .alert-warning { background-color: rgba(245, 203, 92, 0.1); border-left: 4px solid #f5cb5c; color: #f5cb5c; }
    hr { border-color: #2a2e39; margin: 20px 0; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# [신규] 사이드바: 트레이딩 설정 및 리스크 관리
# ==========================================
with st.sidebar:
    st.header("⚙️ 트레이딩 설정")
    capital = st.number_input("총 자산 (Capital $)", min_value=100, value=10000, step=1000)
    risk_pct = st.slider("1회 최대 감수 리스크 (%)", 1.0, 5.0, 2.0, 0.5)
    
    st.markdown("---")
    st.header("🔄 데이터 갱신")
    auto_refresh = st.checkbox("60초 자동 새로고침 켜기", value=False)
    if st.button("즉시 새로고침 (Refresh)"):
        st.rerun()
        
    if auto_refresh:
        time.sleep(60)
        st.rerun()

st.title("👁️‍🗨️ 세력 추적 & 초정밀 단타 퀀트 시스템 (V2.5)")
st.caption("기존 로직 + 버그 픽스 + 리스크 관리(포지션 사이징) 및 차트 시각화 강화")

# ==========================================
# 2. 데이터 수집
# ==========================================
col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, SPY)", value="TSLA").upper().strip()

if ticker:
    with st.spinner("초정밀 틱 데이터 및 다중 시간대 프랙탈 구조 분석 중..."):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="1m", prepost=True)
            df_15m = stock.history(period="1mo", interval="15m", prepost=True)
            
            if df.empty or df_15m.empty:
                st.error("데이터가 없습니다. 티커를 확인하거나 휴장일인지 확인하세요.")
                st.stop()

            # ==========================================
            # 3. 기본 지표 연산
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
            df['MFI'] = 100 - (100 / (1 + pf_sum / nf_sum))
            df['MFI'].fillna(50, inplace=True)

            recent_df = df.tail(300)
            hist, bins = np.histogram(recent_df['Close'], bins=30, weights=recent_df['Volume'])
            poc_price = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2

            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Close'].shift(1) > df['Open'].shift(1))
            df['Whale_Spike'] = df['Volume'] > (df['Vol_SMA20'] * 3.5)

            # ==========================================
            # 4. 단타의 신 로직 (MTF, CHOP, Sweep)
            # ==========================================
            df_15m['EMA20'] = df_15m['Close'].ewm(span=20).mean()
            df_15m['EMA50'] = df_15m['Close'].ewm(span=50).mean()
            macro_trend = "상승 (Bullish) 🟢" if df_15m['EMA20'].iloc[-1] > df_15m['EMA50'].iloc[-1] else "하락 (Bearish) 🔴"
            
            sum_tr = df['TR'].rolling(14).sum()
            max_h = df['High'].rolling(14).max()
            min_l = df['Low'].rolling(14).min()
            df['CHOP'] = 100 * np.log10(sum_tr / (max_h - min_l)) / np.log10(14)
            
            body = abs(df['Close'] - df['Open'])
            upper_wick = df['High'] - df[['Close', 'Open']].max(axis=1)
            lower_wick = df[['Close', 'Open']].min(axis=1) - df['Low']
            
            df['Bull_Pin'] = (lower_wick > 2 * body) & (upper_wick < body)
            df['Bull_Engulf'] = (df['Close'].shift(1) < df['Open'].shift(1)) & (df['Open'] < df['Close'].shift(1)) & (df['Close'] > df['Open'].shift(1))
            
            recent_20_low = df['Low'].rolling(20).min().shift(1)
            df['Liq_Sweep_Bull'] = (df['Low'] < recent_20_low) & (df['Close'] > recent_20_low)

            # ==========================================
            # 5. 실시간 상황 및 판독기
            # ==========================================
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            c_price = current['Close']
            c_vwap = current['VWAP']
            c_atr = current['ATR']
            c_chop = current['CHOP']

            alerts = []
            market_state = "추세 진행 중 📈"
            if c_chop > 61.8:
                market_state = "박스권 횡보 중 (휩소 주의) ⏳"
                alerts.append('<div class="alert-box alert-warning">⚠️ <b>노이즈 경고:</b> CHOP 지수가 높습니다. 세력이 방향을 정하지 않은 횡보장이니 진입을 보류하세요.</div>')

            near_support = abs(c_price - c_vwap) < c_atr or abs(c_price - poc_price) < c_atr
            if current['Liq_Sweep_Bull']:
                alerts.append('<div class="alert-box alert-success">🔥 <b>유동성 사냥 포착:</b> 개미들의 손절 물량을 뺏고 말아올리는 세력의 Stop-Hunt(휩소) 패턴이 발생했습니다!</div>')
            if (current['Bull_Pin'] or current['Bull_Engulf']) and near_support:
                alerts.append('<div class="alert-box alert-success">🎯 <b>핵심 캔들 출현:</b> 주포 평단가(VWAP/POC) 부근에서 강력한 지지 캔들(핀바/장악형)이 포착되었습니다.</div>')

            position = "관망 ⏳"
            if c_chop < 61.8 and current['MFI'] < 80 and (c_price > c_vwap or current['Liq_Sweep_Bull']):
                if "하락" in macro_trend:
                    position = "단기 반등 (역추세 단타) 🟡"
                else:
                    position = "강력한 롱(매수) 진입 🟢"
            elif c_chop < 61.8 and current['MFI'] > 20 and c_price < c_vwap:
                position = "숏(매도) 진입 🔴"

            # UI 대시보드 출력
            for alert in alerts:
                st.markdown(alert, unsafe_allow_html=True)
            
            st.markdown("### 📊 V2 엔진: 실시간 시장 구조 분석")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= prev["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
            with m2:
                st.markdown(f'<div class="card"><div class="title-text">거시 추세 (15분봉)</div><div class="value-text {"up" if "상승" in macro_trend else "down"}">{macro_trend}</div></div>', unsafe_allow_html=True)
            with m3:
                st.markdown(f'<div class="card"><div class="title-text">시장 노이즈 (CHOP)</div><div class="value-text {"neutral" if c_chop > 61.8 else "up"}">{market_state}</div></div>', unsafe_allow_html=True)
            with m4:
                st.markdown(f'<div class="card"><div class="title-text">AI 시스템 최종 판독</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

            # ==========================================
            # 6. [신규/버그픽스] 실전 퀀트 매매 전략 시트 (포지션 분리 및 수량 계산)
            # ==========================================
            st.markdown("### 🎯 동적 타점 & 리스크 관리 시나리오")
            
            recent_15_low = df['Low'].tail(15).min()
            recent_15_high = df['High'].tail(15).max()
            
            is_short = "숏" in position
            
            if is_short:
                # 숏(매도) 포지션
                entry_point = poc_price if c_price < poc_price else c_vwap
                target_1 = entry_point - (c_atr * 1.5)
                target_2 = entry_point - (c_atr * 3.0)
                stop_loss = max(entry_point + (c_atr * 1.2), recent_15_high) # 진입가보다 높게
            else:
                # 롱(매수) 또는 관망 포지션
                base_entry = poc_price if c_price > poc_price else c_vwap
                entry_point = min(base_entry, c_price)
                target_1 = entry_point + (c_atr * 1.5)
                target_2 = entry_point + (c_atr * 3.0)
                stop_loss = min(entry_point - (c_atr * 1.2), recent_15_low) # 진입가보다 낮게
                
            # [신규] 리스크 기반 포지션 사이징 계산
            risk_amount = capital * (risk_pct / 100)
            price_diff = abs(entry_point - stop_loss)
            shares_to_buy = int(risk_amount / price_diff) if price_diff > 0 else 0
            
            theme_color = "#ef5350" if is_short else "#26a69a"
            position_text = "🔴 숏(매도) 진입" if is_short else "🟢 롱(매수) 진입"
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid {theme_color};">
                    <h4 style="color:{theme_color};">{position_text}</h4>
                    <h2 style="margin:0;">${entry_point:.2f}</h2>
                    <p style="margin-top:10px; font-size:14px; font-weight:bold; color:#e0e0e0;">💡 권장 진입 수량: {shares_to_buy} 주</p>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #42a5f5;">
                    <h4 style="color:#42a5f5;">🔵 파동 익절 (Target)</h4>
                    <p style="margin:0; font-size:18px;">1차: <b>${target_1:.2f}</b></p>
                    <p style="margin:5px 0 0 0; font-size:18px;">2차: <b>${target_2:.2f}</b></p>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #ff9800;">
                    <h4 style="color:#ff9800;">⚠️ 구조적 손절 (Stop Loss)</h4>
                    <h2 style="margin:0;">${stop_loss:.2f}</h2>
                    <p style="margin-top:10px; font-size:13px; color:#8a93a6;">최대 손실액: ${risk_amount:.0f}</p>
                </div>
                """, unsafe_allow_html=True)

            # ==========================================
            # 7. 인터랙티브 통합 차트 (Plotly 시각화 강화)
            # ==========================================
            st.markdown("### 📈 세력 추적 X-Ray 차트 (최근 150분)")
            df_plot = df.tail(150)
            
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2])
            
            fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name='Price'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name='VWAP (당일평균)'), row=1, col=1)
            fig.add_hline(y=poc_price, line_dash="dot", line_color="#b39ddb", annotation_text="POC (최대 매물대)", row=1, col=1)
            
            # [신규] 유동성 사냥(Sweep) 마커 표시
            sweep_points = df_plot[df_plot['Liq_Sweep_Bull']]
            fig.add_trace(go.Scatter(x=sweep_points.index, y=sweep_points['Low'], mode='markers',
                                     marker=dict(symbol='triangle-up', size=12, color='#ff9800'),
                                     name='유동성 사냥(Sweep)'), row=1, col=1)
            
            # [신규] FVG(공정가치갭) 마커 표시
            fvg_points = df_plot[df_plot['FVG_Bull']]
            fig.add_trace(go.Scatter(x=fvg_points.index, y=fvg_points['Low'], mode='markers+text',
                                     marker=dict(symbol='star', size=10, color='#26a69a'),
                                     text='FVG', textposition='bottom center', name='FVG Bull'), row=1, col=1)
            
            vol_colors = ['#f48fb1' if row['Whale_Spike'] and row['Close']<row['Open'] else '#80cbc4' if row['Whale_Spike'] and row['Close']>=row['Open'] else '#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
            fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors, name='Volume'), row=2, col=1)
            
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['CHOP'], line=dict(color='#ce93d8', width=2), name='CHOP'), row=3, col=1)
            fig.add_hline(y=61.8, line_dash="dash", line_color="#ef5350", annotation_text="횡보장 한계선", row=3, col=1)
            fig.add_hline(y=38.2, line_dash="dash", line_color="#26a69a", annotation_text="추세장 한계선", row=3, col=1)

            fig.update_layout(
                height=750, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor='#0b0e14', plot_bgcolor='#131722',
                font=dict(color='#8a93a6'), showlegend=False, xaxis_rangeslider_visible=False
            )
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")
