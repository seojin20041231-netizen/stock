import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

st.set_page_config(page_title="급등주 추적기 v3", layout="wide")

st.title("📈 미국 당일 급등주 완벽 분석기 (세력선, 이평선, 갭, 분할)")
st.write("5분봉 세력선, 224선/60분봉 20선, 이전 갭상승/하락 지지저항선, 액면분할 여부를 모두 표시합니다.")

# 티커 입력
ticker = st.text_input("검색할 미국 주식 티커를 입력하세요 (예: TSLA, NVDA, AAPL):", "TSLA").upper()

if ticker:
    # 데이터 로드 (과거 갭과 이평선을 위해 10일치 가져오기)
    stock = yf.Ticker(ticker)
    df = stock.history(period="10d", interval="5m")
    
    # 액면분할 이력 가져오기
    splits = stock.splits

    if not df.empty:
        df = df.copy()
        
        # --- [1. 지표 추가 파트] ---
        # 5분봉 224선 & 60분봉 20선(5분 240선)
        df['MA_224'] = df['Close'].rolling(window=224).mean()
        df['MA_240'] = df['Close'].rolling(window=240).mean()

        # --- [2. 이전 갭상승 / 갭하락 구간 찾기] ---
        # 일자별 첫 시가와 마지막 종가를 구해 갭을 계산합니다.
        df['Date'] = df.index.date
        daily_summary = df.groupby('Date').agg({'Open': 'first', 'Close': 'last'})
        daily_summary['Prev_Close'] = daily_summary['Close'].shift(1)
        
        # 갭 퍼센트 계산: (당일 시가 - 전일 종가) / 전일 종가 * 100
        daily_summary['Gap_Pct'] = (daily_summary['Open'] - daily_summary['Prev_Close']) / daily_summary['Prev_Close'] * 100
        
        gap_up_zones = []
        gap_down_zones = []
        
        for date, row in daily_summary.iterrows():
            if pd.isna(row['Prev_Close']): continue
            # 0.5% 이상 차이나면 의미 있는 갭으로 판단
            if row['Gap_Pct'] >= 0.5:
                gap_up_zones.append((row['Prev_Close'], row['Open'], date))
            elif row['Gap_Pct'] <= -0.5:
                gap_down_zones.append((row['Open'], row['Prev_Close'], date)) # 아래가 Open, 위가 Prev_Close

        # --- [3. 당일 데이터 추출 파트] ---
        last_date = df.index[-1].date()
        df_today = df[df.index.date == last_date].copy()
        
        if not df_today.empty:
            df_today['Body'] = df_today['Close'] - df_today['Open']
            df_today['Surge_Score'] = df_today.apply(lambda x: x['Body'] * x['Volume'] if x['Body'] > 0 else 0, axis=1)
            
            if df_today['Surge_Score'].max() > 0:
                surge_idx = df_today['Surge_Score'].idxmax()
                surge_open = df_today.loc[surge_idx, 'Open']
                
                before_surge = df_today.loc[:surge_idx]
                if len(before_surge) > 1:
                    base_open = before_surge.iloc[0]['Open']
                else:
                    base_open = df_today.iloc[0]['Open']

                # --- [4. 차트 그리기 파트 (Plotly)] ---
                fig = go.Figure()

                # 캔들 추가
                fig.add_trace(go.Candlestick(x=df_today.index,
                                open=df_today['Open'],
                                high=df_today['High'],
                                low=df_today['Low'],
                                close=df_today['Close'],
                                name='5분봉'))

                # 이평선 추가
                fig.add_trace(go.Scatter(x=df_today.index, y=df_today['MA_224'], 
                                         mode='lines', line=dict(color='orange', width=1.5), name='5분봉 224선'))
                fig.add_trace(go.Scatter(x=df_today.index, y=df_today['MA_240'], 
                                         mode='lines', line=dict(color='purple', width=1.5), name='60분봉 20선 (240선)'))

                # 세력선 & 횡보 시가 수평선 추가
                fig.add_hline(y=base_open, line_dash="dash", line_color="blue", 
                              annotation_text="급등 전 횡보 시가", annotation_position="bottom right", annotation_font_color="blue")
                fig.add_hline(y=surge_open, line_dash="solid", line_color="red", 
                              annotation_text="세력선 시가", annotation_position="top right", annotation_font_color="red")

                # 갭상승 구간 표시 (최근 3개까지만 표시하여 차트 깔끔하게 유지)
                for prev_c, open_p, date in gap_up_zones[-3:]:
                    fig.add_hrect(y0=prev_c, y1=open_p, fillcolor="rgba(0, 255, 0, 0.15)", line_width=0, 
                                  annotation_text=f"갭상승 지지구간({date.strftime('%m/%d')})", annotation_position="top left")

                # 갭하락 구간 표시
                for open_p, prev_c, date in gap_down_zones[-3:]:
                    fig.add_hrect(y0=open_p, y1=prev_c, fillcolor="rgba(0, 191, 255, 0.15)", line_width=0, 
                                  annotation_text=f"갭하락 저항구간({date.strftime('%m/%d')})", annotation_position="bottom left")

                # 액면분할 당일일 경우 세로선 표시
                split_msg = "최근 액면분할 이력 없음 (또는 데이터 없음)"
                if not splits.empty:
                    last_split_date = splits.index[-1]
                    last_split_ratio = splits.iloc[-1]
                    
                    # 날짜 텍스트 처리
                    try:
                        ls_date_str = last_split_date.strftime('%Y-%m-%d')
                    except:
                        ls_date_str = str(last_split_date)[:10]
                        
                    split_msg = f"{ls_date_str} (비율 1 : {last_split_ratio})"
                    
                    # 만약 차트 당일(Today)이 액면분할 적용일이라면 수직선 긋기
                    if str(last_date) == ls_date_str:
                        fig.add_vline(x=df_today.index[0], line_dash="dash", line_color="yellow", 
                                      annotation_text="⭐ 액면분할 적용일", annotation_position="top left", annotation_font_color="yellow")

                # 차트 레이아웃
                fig.update_layout(title=f"{ticker} 5분봉 당일 분석 차트",
                                  yaxis_title="가격 (USD)",
                                  xaxis_rangeslider_visible=False,
                                  height=700,
                                  template="plotly_dark",
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

                st.plotly_chart(fig, use_container_width=True)
                
                # --- [5. 하단 데이터 요약 파트] ---
                st.markdown(f"**💡 {ticker} 분석 요약 ({last_date})**")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"- **급등 전 횡보 시가:** ${base_open:.2f}")
                    st.markdown(f"- **세력선 시가:** ${surge_open:.2f} ({surge_idx.strftime('%H:%M')} 발생)")
                    st.markdown(f"- **최근 액면분할:** {split_msg}")
                with col2:
                    st.markdown(f"- **현재 5분봉 224선:** ${df_today['MA_224'].iloc[-1]:.2f}")
                    st.markdown(f"- **현재 60분봉 20선:** ${df_today['MA_240'].iloc[-1]:.2f}")
                
            else:
                st.warning("오늘 의미 있는 상승(양봉) 캔들이 없습니다.")
        else:
            st.error("당일 데이터를 추출할 수 없습니다.")
    else:
        st.error("데이터를 불러올 수 없습니다. 장이 열려있지 않거나 티커가 잘못되었습니다.")
