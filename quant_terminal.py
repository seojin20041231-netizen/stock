import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings

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

st.title("👁️‍🗨️ 세력(주포) 추적 & SMC 기반 무한 단타 시스템")
st.caption("Volume Profile, 매집/분산(OBV/MFI), 스마트머니(FVG), 다중 ATR 변동성을 융합한 최상위 알고리즘")

# ==========================================
# 2. 데이터 수집 및 텐서 연산 준비
# ==========================================
col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    ticker = st.text_input("티커 입력 (예: NVDA, TSLA, SPY)", value="TSLA").upper().strip()

if ticker:
    with st.spinner("주포 움직임 및 초정밀 틱 데이터를 분석 중입니다. 잠시만 기다려주세요..."):
        try:
            stock = yf.Ticker(ticker)
            # 단타를 위한 최근 5일, 1분봉 초정밀 데이터 (프리마켓 포함)
            df = stock.history(period="5d", interval="1m", prepost=True)
            
            if df.empty:
                st.error("데이터가 없습니다. 티커를 확인하거나 장기 휴장일인지 확인하세요.")
                st.stop()

            # ==========================================
            # 3. 🧠 최상위 퀀트 알고리즘 지표 자체 계산
            # ==========================================
            
            # [A] 기본 가격 및 변동성 (ATR)
            df['H-L'] = df['High'] - df['Low']
            df['H-PC'] = np.abs(df['High'] - df['Close'].shift(1))
            df['L-PC'] = np.abs(df['Low'] - df['Close'].shift(1))
            df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            df['ATR'] = df['TR'].rolling(window=14).mean()

            # [B] 기관 평단가 (VWAP)
            df['Date'] = df.index.date
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = df.groupby('Date').apply(lambda x: (x['Typical_Price'] * x['Volume']).cumsum() / x['Volume'].cumsum()).reset_index(level=0, drop=True)
            
            # [C] 🐋 세력(주포) 매집/분산 추적 (OBV & MFI)
            # OBV (On-Balance Volume): 거래량에 가격 방향을 곱해 누적. 주포의 매집/이탈 확인.
            obv = [0]
            for i in range(1, len(df)):
                if df['Close'].iloc[i] > df['Close'].iloc[i-1]: obv.append(obv[-1] + df['Volume'].iloc[i])
                elif df['Close'].iloc[i] < df['Close'].iloc[i-1]: obv.append(obv[-1] - df['Volume'].iloc[i])
                else: obv.append(obv[-1])
            df['OBV'] = obv
            df['OBV_EMA'] = df['OBV'].ewm(span=20).mean() # 주포 방향성 척도

            # MFI (Money Flow Index): 거래량이 실린 RSI. 세력 자금의 유입/유출 과열도 (14주기)
            typical_price = (df['High'] + df['Low'] + df['Close']) / 3
            raw_money_flow = typical_price * df['Volume']
            positive_flow = [0]
            negative_flow = [0]
            for i in range(1, len(typical_price)):
                if typical_price.iloc[i] > typical_price.iloc[i-1]:
                    positive_flow.append(raw_money_flow.iloc[i])
                    negative_flow.append(0)
                elif typical_price.iloc[i] < typical_price.iloc[i-1]:
                    positive_flow.append(0)
                    negative_flow.append(raw_money_flow.iloc[i])
                else:
                    positive_flow.append(0)
                    negative_flow.append(0)
            
            pf_sum = pd.Series(positive_flow).rolling(window=14).sum()
            nf_sum = pd.Series(negative_flow).rolling(window=14).sum()
            mfi_ratio = pf_sum / nf_sum
            df['MFI'] = 100 - (100 / (1 + mfi_ratio))
            df['MFI'].fillna(50, inplace=True)

            # [D] 📊 매물대 분석 (Volume Profile - POC)
            # 가장 거래가 많이 일어난 가격대 (주포의 본전 부근이거나 강력한 지지/저항선)
            recent_df = df.tail(300) # 최근 300분(약 5시간) 기준 매물대
            hist, bins = np.histogram(recent_df['Close'], bins=30, weights=recent_df['Volume'])
            max_vol_idx = np.argmax(hist)
            poc_price = (bins[max_vol_idx] + bins[max_vol_idx+1]) / 2 # Point of Control

            # [E] ⚡ 스마트 머니 콘셉트 (SMC): FVG (공정가치 갭) 감지
            # 주포가 급하게 시장가로 긁어서 발생한 '진공 상태'의 갭. 반드시 채우러 오거나 강력한 지지/저항이 됨.
            df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Close'].shift(1) > df['Open'].shift(1))
            df['FVG_Bear'] = (df['High'] < df['Low'].shift(2)) & (df['Close'].shift(1) < df['Open'].shift(1))

            # [F] 🚨 세력 거래량 스파이크 감지 (평소 대비 3배 이상 폭발)
            df['Vol_SMA20'] = df['Volume'].rolling(20).mean()
            df['Whale_Spike_Buy'] = (df['Volume'] > df['Vol_SMA20'] * 3.5) & (df['Close'] > df['Open'])
            df['Whale_Spike_Sell'] = (df['Volume'] > df['Vol_SMA20'] * 3.5) & (df['Close'] < df['Open'])

            # ==========================================
            # 4. 실시간 상황 및 AI 판독
            # ==========================================
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            c_price = current['Close']
            c_vwap = current['VWAP']
            c_atr = current['ATR']
            
            # 주포 상태 판독기
            whale_status = "중립 (관망 중)"
            whale_color = "neutral"
            if current['OBV'] > current['OBV_EMA'] and current['MFI'] > 50:
                whale_status = "매집 진행 중 (세력 유입 🟢)"
                whale_color = "up"
            elif current['OBV'] < current['OBV_EMA'] and current['MFI'] < 50:
                whale_status = "분산 진행 중 (세력 이탈 🔴)"
                whale_color = "down"

            # 최근 10분 내 세력 스파이크 확인
            recent_spikes = df.tail(10)
            if recent_spikes['Whale_Spike_Buy'].sum() > 0:
                whale_alert = f'<div class="whale-buy">🔥 <b>세력 포착:</b> 최근 10분 내 기관급 대량 매수(시장가 긁기) 감지!</div>'
            elif recent_spikes['Whale_Spike_Sell'].sum() > 0:
                whale_alert = f'<div class="whale-alert">⚠️ <b>비상:</b> 최근 10분 내 세력급 대량 물량 투하(패닉셀) 감지!</div>'
            else:
                whale_alert = ""

            # ==========================================
            # 5. SMC & 변동성 기반 타점 설계 (가장 중요한 부분)
            # ==========================================
            # 단순 퍼센트가 아닙니다. 시장 구조와 세력의 평단가(POC/VWAP)를 기준으로 잡습니다.
            
            # [매수 타점] = 주포의 주요 매물대(POC) 근처 또는 VWAP 지지선
            entry_point = poc_price if c_price > poc_price else c_vwap
            
            # [익절 타점] = 현재가 + (ATR의 2배 ~ 3배). 주가 변동성 폭 안에서 안전하게 먹고 나옴.
            target_1 = c_price + (c_atr * 2.0)
            target_2 = c_price + (c_atr * 3.5)
            
            # [손절 타점] = 최근 캔들의 구조적 붕괴점 (직전 FVG 갭을 깨거나 변동성 한계를 넘을 때)
            recent_lows = recent_df['Low'].tail(15).min()
            stop_loss = min(c_price - (c_atr * 1.5), recent_lows)

            # 포지션 추천 로직
            position = "관망 ⏳"
            if c_price > c_vwap and current['MFI'] < 80 and whale_color == "up":
                position = "롱(매수) 진입 가능 🟢"
            elif c_price < c_vwap and current['MFI'] > 20 and whale_color == "down":
                position = "숏(매도)/관망 🔴"

            # ==========================================
            # 6. UI 대시보드 출력
            # ==========================================
            st.markdown(whale_alert, unsafe_allow_html=True)
            
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f'<div class="card"><div class="title-text">현재가</div><div class="value-text {"up" if c_price >= prev["Close"] else "down"}">${c_price:.2f}</div></div>', unsafe_allow_html=True)
            with m2:
                st.markdown(f'<div class="card"><div class="title-text">세력 매물대 (POC)</div><div class="value-text neutral">${poc_price:.2f}</div><div style="font-size:12px; color:#8a93a6;">주포 평단가 추정치</div></div>', unsafe_allow_html=True)
            with m3:
                st.markdown(f'<div class="card"><div class="title-text">주포 자금흐름 (OBV)</div><div class="value-text {whale_color}">{whale_status}</div></div>', unsafe_allow_html=True)
            with m4:
                st.markdown(f'<div class="card"><div class="title-text">알고리즘 판독</div><div class="value-text {"up" if "롱" in position else "down" if "숏" in position else "neutral"}">{position}</div></div>', unsafe_allow_html=True)

            # ==========================================
            # 7. 인터랙티브 통합 차트 (Plotly)
            # ==========================================
            st.markdown("### 📈 세력 추적 X-Ray 차트 (최근 150분)")
            df_plot = df.tail(150)
            
            # 3단 차트 구성 (가격+VWAP / 거래량+MFI / OBV 주포선)
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2])
            
            # [Row 1] 캔들 + VWAP + POC 선
            fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name='Price'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['VWAP'], line=dict(color='#ffeb3b', width=2), name='VWAP (당일평균)'), row=1, col=1)
            fig.add_hline(y=poc_price, line_dash="dot", line_color="#b39ddb", annotation_text="POC (최대 매물대)", row=1, col=1)
            
            # [Row 2] 거래량 + 세력 스파이크 표시
            colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for idx, row in df_plot.iterrows()]
            fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=colors, name='Volume'), row=2, col=1)
            
            # [Row 3] OBV (누적 자금 흐름)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV'], line=dict(color='#2196f3', width=2), name='OBV (누적매집)'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV_EMA'], line=dict(color='#ff9800', width=1, dash='dot'), name='OBV 시그널'), row=3, col=1)

            fig.update_layout(
                height=700, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor='#0b0e14', plot_bgcolor='#131722',
                font=dict(color='#8a93a6'), showlegend=False, xaxis_rangeslider_visible=False
            )
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            st.plotly_chart(fig, use_container_width=True)

            # ==========================================
            # 8. 실전 퀀트 매매 전략 시트
            # ==========================================
            st.markdown("### 🎯 기관급 동적 매매 시나리오 (Smart Money Concepts)")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #26a69a;">
                    <h4 style="color:#26a69a;">🟢 추천 진입 (Entry)</h4>
                    <p style="font-size:14px; color:#8a93a6;">세력 평단가 및 강력한 지지 구조 기반</p>
                    <h2 style="margin:0;">${entry_point:.2f}</h2>
                    <p style="margin-top:10px; font-size:13px;">이 가격대 근처에서 OBV가 상승 전환할 때가 '찐' 타점입니다.</p>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #42a5f5;">
                    <h4 style="color:#42a5f5;">🔵 동적 익절 (Target)</h4>
                    <p style="font-size:14px; color:#8a93a6;">현재 변동성(ATR) 기반 통계적 도달 범위</p>
                    <p style="margin:0; font-size:18px;">1차: <b>${target_1:.2f}</b> (절반 매도)</p>
                    <p style="margin:5px 0 0 0; font-size:18px;">2차: <b>${target_2:.2f}</b> (전량 매도)</p>
                    <p style="margin-top:10px; font-size:13px;">무지성 %가 아닌 현재 분봉의 파동 폭을 계산한 수치입니다.</p>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="card" style="border-top: 3px solid #ef5350;">
                    <h4 style="color:#ef5350;">🔴 기계적 손절 (Stop Loss)</h4>
                    <p style="font-size:14px; color:#8a93a6;">최근 구조적 저점 및 변동성 한계 붕괴</p>
                    <h2 style="margin:0;">${stop_loss:.2f}</h2>
                    <p style="margin-top:10px; font-size:13px;">이 가격이 뚫리면 세력이 물량을 포기하고 이탈한 것으로 간주합니다. <b>칼손절 필수</b>.</p>
                </div>
                """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"시스템 오류 발생 (티커 점검 또는 데이터 수신 지연): {e}")
