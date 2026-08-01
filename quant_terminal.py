import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import pytz

warnings.filterwarnings('ignore')

# ==========================================
# 1. 터미널 UI 및 환경 설정
# ==========================================
st.set_page_config(page_title="Ultimate Quant Terminal", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .card { background-color: #131722; border: 1px solid #2a2e39; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
    .title-text { color: #8a93a6; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .value-text { font-size: 24px; font-weight: 700; margin-top: 5px; }
    .up { color: #26a69a; } .down { color: #ef5350; } .neutral { color: #f5cb5c; }
    .whale-alert { background-color: rgba(239, 83, 80, 0.1); border-left: 4px solid #ef5350; padding: 10px; margin-top: 10px; }
    .whale-buy { background-color: rgba(38, 166, 154, 0.1); border-left: 4px solid #26a69a; padding: 10px; margin-top: 10px; }
    hr { border-color: #2a2e39; }
    </style>
""", unsafe_allow_html=True)

st.title("👁️‍🗨️ 세력(주포) 추적 & SMC 기반 무한 단타 시스템 (v2.0)")
st.caption("⚠️ 주의: Yahoo Finance 데이터는 실시간 호가가 아니므로 지연이 발생할 수 있습니다. 보조 지표로만 활용하세요.")

# ==========================================
# 2. 데이터 수집
# ==========================================
col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, SPY)", value="TSLA").upper().strip()

if ticker:
    with st.spinner("최적화된 퀀트 알고리즘으로 데이터를 분석 중입니다..."):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="1m", prepost=True)
            
            if df.empty:
                st.error("데이터가 없습니다. 티커를 확인하거나 장기 휴장일인지 확인하세요.")
                st.stop()

            # 시간대 설정 (뉴욕 시간 기준)
                        # 시간대 설정 (뉴욕 시간 기준 - 서버 호환성 반영)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('America/New_York')
            else:
                df.index = df.index.tz_convert('America/New_York')


            # ==========================================
            # 3. 🧠 최상위 퀀트 알고리즘 (벡터화 연산 최적화)
            # ==========================================
            
            # [A] 기본 가격 및 변동성 (ATR), 거시 추세 (EMA 200)
            df['H-L'] = df['High'] - df['Low']
            df['H-PC'] = np.abs(df['High'] - df['Close'].shift(1))
            df['L-PC'] = np.abs(df['Low'] - df['Close'].shift(1))
            df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            df['ATR'] = df['TR'].rolling(window=14).mean()
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean() # 1분봉 기준 약 3.3시간 장기 추세

            # [B] 세션 분리형 기관 평단가 (VWAP) - 정규장 리셋
            df['Date'] = df.index.date
            df['Time'] = df.index.time
            # 프리마켓(04:00~09:30)과 정규장(09:30~16:00)을 분리하는 세션 ID 생성
            df['Session_Type'] = np.where(df['Time'] >= pd.to_datetime('09:30').time(), 'Reg', 'Pre')
            df['Session_ID'] = df['Date'].astype(str) + "_" + df['Session_Type']
            
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Session_ID').apply(
                lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()
            ).reset_index(level=0, drop=True)
            
            # [C] 🐋 세력 매집/분산 추적 (OBV & MFI 벡터화 최적화)
            # OBV
            obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'], 
                         np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
            df['OBV'] = obv_change.cumsum()
            df['OBV_EMA'] = df['OBV'].ewm(span=20).mean()

            # MFI
            raw_mf = df['Typical_Price'] * df['Volume']
            pos_mf = np.where(df['Typical_Price'] > df['Typical_Price'].shift(1), raw_mf, 0)
            neg_mf = np.where(df['Typical_Price'] < df['Typical_Price'].shift(1), raw_mf, 0)
            pf_sum = pd.Series(pos_mf).rolling(window=14).sum()
            nf_sum = pd.Series(neg_mf).rolling(window=14).sum()
            mfi_ratio = pf_sum / (nf_sum + 1e-10) # 0 나누기 방지
            df['MFI'] = 100 - (100 / (1 + mfi_ratio))
            df['MFI'].fillna(50, inplace=True)

            # [D] 📊 매물대 분석 (Volume Profile - POC) - 캔들 평균가 사용
            recent_df = df.tail(300)
            hist, bins = np.histogram(recent_df['Typical_Price'], bins=30, weights=recent_df['Volume'])
            max_vol_idx = np.argmax(hist)
            poc_price = (bins[max_vol_idx] + bins[max_vol_idx+1]) / 2

            # [E] ⚡ 스마트 머니 콘셉트 (SMC) & FVG 지지선 추출
            df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Close'].shift(1) > df['Open'].shift(1))
            df['FVG_Bear'] = (df['High'] < df['Low'].shift(2)) & (df['Close'].shift(1) < df['Open'].shift(1))
            # 최근 Bull FVG의 하단을 강력한 지지선으로 기록
            df['Last_FVG_Support'] = np.where(df['FVG_Bull'], df['High'].shift(2), np.nan)
            df['Last_FVG_Support'].ffill(inplace=True)

            # [F] 🚨 세력 거래량 스파이크 감지 (장 개시 15분 필터링 적용)
            is_open_rush = (df['Time'] >= pd.to_datetime('09:30').time()) & (df['Time'] <= pd.to_datetime('09:45').time())
            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            # 장 초반은 평소 대비 10배, 평시에는 3.5배를 스파이크로 간주
            spike_threshold = np.where(is_open_rush, df['Vol_SMA20'] * 10, df['Vol_SMA20'] * 3.5)
            
            df['Whale_Spike_Buy'] = (df['Volume'] > spike_threshold) & (df['Close'] > df['Open'])
            df['Whale_Spike_Sell'] = (df['Volume'] > spike_threshold) & (df['Close'] < df['Open'])

            # ==========================================
            # 4. 실시간 상황 및 판독
            # ==========================================
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            c_price = current['Close']
            c_vwap = current['VWAP']
            c_atr = current['ATR']
            trend_200 = current['EMA_200']
            fvg_support = current['Last_FVG_Support']
            
            # 주포 상태 판독
            whale_status = "중립 (관망 중)"
            whale_color = "neutral"
            if current['OBV'] > current['OBV_EMA'] and current['MFI'] > 50:
                whale_status = "매집 진행 중 (세력 유입 🟢)"
                whale_color = "up"
            elif current['OBV'] < current['OBV_EMA'] and current['MFI'] < 50:
                whale_status = "분산 진행 중 (세력 이탈 🔴)"
                whale_color = "down"

            # 스파이크 알림 (최근 5분)
            recent_spikes = df.tail(5)
            if recent_spikes['Whale_Spike_Buy'].sum() > 0:
                whale_alert = f'<div class="whale-buy">🔥 <b>세력 포착:</b> 최근 5분 내 기관급 대량 매수 감지!</div>'
            elif recent_spikes['Whale_Spike_Sell'].sum() > 0:
                whale_alert = f'<div class="whale-alert">⚠️ <b>비상:</b> 최근 5분 내 대량 물량 투하(패닉셀) 감지!</div>'
            else:
                whale_alert = ""

            # ==========================================
            # 5. SMC & 변동성 기반 타점 설계 (안전장치 추가)
            # ==========================================
            
            # [매수 타점] POC, VWAP, FVG 지지선 중 현재가와 가장 가깝고 낮은 가격
            supports = [s for s in [poc_price, c_vwap, fvg_support] if not pd.isna(s) and s < c_price]
            entry_point = max(supports) if supports else c_price - c_atr
            
            # [익절 타점] ATR 기반
            target_1 = c_price + (c_atr * 2.0)
            target_2 = c_price + (c_atr * 3.5)
            
            # [손절 타점] 구조적 저점 붕괴 확인 후, 최대 -2% 강제 컷 방어
            recent_lows = recent_df['Low'].tail(15).min()
            calc_stop_loss = min(c_price - (c_atr * 1.5), recent_lows)
            max_loss_cap = c_price * 0.98 # -2% 하드 스탑
            stop_loss = max(calc_stop_loss, max_loss_cap)

            # [포지션 로직] 거시 추세(EMA200) 필터링 추가
            position = "관망 ⏳"
            if c_price > c_vwap and current['MFI'] < 80 and whale_color == "up":
                if c_price > trend_200:
                    position = "정배열 롱(매수) 🟢"
                else:
                    position = "역추세 단기 반등 (주의) ⚠️"
            elif c_price < c_vwap and current['MFI'] > 20 and whale_color == "down":
                if c_price < trend_200:
                    position = "역배열 숏(매도) 🔴"
                else:
                    position = "조정 중 (관망) ⏳"

            # ==========================================
            # 6. 대시보드 출력
            # ==========================================
            if whale_alert: st.markdown(whale_alert, unsafe_allow_html=True)
            
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= prev["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
            with m2: st.markdown(f'<div class="card"><div class="title-text">세력 매물대 (POC)</div><div class="value-text neutral">${poc_price:.2f}</div><div style="font-size:12px; color:#8a93a6;">최대 거래 밀집 구역</div></div>', unsafe_allow_html=True)
            with m3: st.markdown(f'<div class="card"><div class="title-text">주포 자금흐름 (OBV)</div><div class="value-text {whale_color}">{whale_status}</div></div>', unsafe_allow_html=True)
            with m4: st.markdown(f'<div class="card"><div class="title-text">알고리즘 판독</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

            # ==========================================
            # 7. 차트 렌더링
            # ==========================================
            st.markdown("### 📈 세력 추적 X-Ray 차트 (최근 150분)")
            df_plot = df.tail(150)
            
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2])
            
            # [Row 1] 캔들 + VWAP + EMA200
            fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name='Price'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name='VWAP (세션)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_200'], line=dict(color='#ab47bc', width=1.5, dash='dot'), name='EMA 200 (추세)'), row=1, col=1)
            fig.add_hline(y=poc_price, line_dash="dash", line_color="#b39ddb", annotation_text="POC (매물대)", row=1, col=1)
            if not pd.isna(fvg_support):
                fig.add_hline(y=fvg_support, line_dash="dot", line_color="#4caf50", annotation_text="최근 FVG 지지선", row=1, col=1)
            
            # [Row 2] 거래량
            colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
            fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=colors, name='Volume'), row=2, col=1)
            
            # [Row 3] OBV
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV'], line=dict(color='#2196f3', width=2), name='OBV'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV_EMA'], line=dict(color='#ff9800', width=1, dash='dot'), name='OBV Signal'), row=3, col=1)

            fig.update_layout(height=700, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='#0b0e14', plot_bgcolor='#131722', font=dict(color='#8a93a6'), showlegend=False, xaxis_rangeslider_visible=False)
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            st.plotly_chart(fig, use_container_width=True)

            # ==========================================
            # 8. 실전 퀀트 매매 전략 시트
            # ==========================================
            st.markdown("### 🎯 기관급 동적 매매 시나리오")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #26a69a;">
                    <h4 style="color:#26a69a;">🟢 추천 진입 (Entry)</h4>
                    <p style="font-size:14px; color:#8a93a6;">하단 지지선(POC/VWAP/FVG) 인접 시</p>
                    <h2 style="margin:0;">${entry_point:.2f}</h2>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #42a5f5;">
                    <h4 style="color:#42a5f5;">🔵 동적 익절 (Target)</h4>
                    <p style="font-size:14px; color:#8a93a6;">현재 변동성(ATR) 기반 통계적 도달 범위</p>
                    <p style="margin:0; font-size:18px;">1차: <b>${target_1:.2f}</b> (절반 매도)</p>
                    <p style="margin:5px 0 0 0; font-size:18px;">2차: <b>${target_2:.2f}</b> (전량 매도)</p>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #ef5350;">
                    <h4 style="color:#ef5350;">🔴 기계적 손절 (Stop Loss)</h4>
                    <p style="font-size:14px; color:#8a93a6;">지정가 이탈 또는 최대 -2% 하드스탑</p>
                    <h2 style="margin:0;">${stop_loss:.2f}</h2>
                </div>
                """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")
