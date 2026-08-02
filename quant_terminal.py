import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- [1] 기본 설정 ---
st.set_page_config(page_title="프리마켓 몬스터 스캐너 (덤핑 방어 필터 장착)", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 22px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 15px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-blue { color: #2196F3; }
    .val-orange { color: #FFB020; }
    .val-purple { color: #E040FB; }
</style>
""", unsafe_allow_html=True)

# --- [2] 보조지표 계산 함수 ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(data, window=20, num_std=2):
    rolling_mean = data.rolling(window=window).mean()
    rolling_std = data.rolling(window=window).std()
    return rolling_mean + (rolling_std * num_std), rolling_mean - (rolling_std * num_std)

# --- [3] 메인 데이터 분석 엔진 ---
@st.cache_data(ttl=60)
def analyze_ticker_ultimate(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 과거 1년 일봉 (종목 DNA 검사 용도)
        df_daily = ticker.history(period="1y", interval="1d")
        if len(df_daily) < 2:
            return {"error": f"[{ticker_symbol}] 일봉 데이터 부족"}
        
        # 👑 [필터 1] 악질 덤핑 DNA 검사 (과거 10% 이상 갭 뜬 날의 승률)
        df_daily['Prev_Close'] = df_daily['Close'].shift(1)
        df_daily['Gap_Pct'] = (df_daily['Open'] - df_daily['Prev_Close']) / df_daily['Prev_Close'] * 100
        gap_days = df_daily[df_daily['Gap_Pct'] >= 10.0]
        
        if len(gap_days) > 0:
            # 갭 뜬 날, 시가보다 종가가 높게 끝난(양봉) 확률
            win_days = gap_days[gap_days['Close'] > gap_days['Open']]
            gap_win_rate = (len(win_days) / len(gap_days)) * 100
            total_gaps = len(gap_days)
        else:
            gap_win_rate = 50.0  # 기록이 없으면 중립
            total_gaps = 0

        yest_close = df_daily['Close'].iloc[-1]
        adv_10 = df_daily['Volume'].tail(10).mean()

        # 2. 1분봉 데이터 (프리마켓)
        df_1m = ticker.history(period="1d", interval="1m", prepost=True)
        if df_1m.empty:
            return {"error": f"[{ticker_symbol}] 당일 분봉 데이터 없음"}

        current_price = df_1m['Close'].iloc[-1]
        today_volume = df_1m['Volume'].sum()
        pm_high = df_1m['High'].max()
        pm_low = df_1m['Low'].min()
        
        # 👑 [필터 2] 진짜 꽂힌 돈 (거래 대금)
        dollar_volume = current_price * today_volume
        
        # 👑 [필터 3] 프리마켓 저점 갱신 방어 (Higher Lows) 검사
        higher_lows = False
        if len(df_1m) >= 30:
            chunks = np.array_split(df_1m, 3)
            low_1 = chunks[0]['Low'].min()
            low_2 = chunks[1]['Low'].min()
            low_3 = chunks[2]['Low'].min()
            # 시간이 지날수록 저점이 높아지는가?
            if (low_3 > low_2) and (low_2 >= low_1):
                higher_lows = True

        # 기본 지표 계산
        gap_pct = ((current_price - yest_close) / yest_close) * 100
        rvol = (today_volume / adv_10) * 100 if adv_10 > 0 else 0
        dist_to_pmh = ((pm_high - current_price) / current_price) * 100
        
        # VWAP, RSI, BB 계산
        tp = (df_1m['High'] + df_1m['Low'] + df_1m['Close']) / 3
        cum_v = df_1m['Volume'].cumsum()
        vwap = ((tp * df_1m['Volume']).cumsum() / np.where(cum_v == 0, 1, cum_v)).iloc[-1]
        
        df_1m['RSI'] = calculate_rsi(df_1m['Close'])
        df_1m['BB_Upper'], _ = calculate_bollinger_bands(df_1m['Close'])
        current_rsi = df_1m['RSI'].iloc[-1]
        bb_upper = df_1m['BB_Upper'].iloc[-1]
        
        float_shares = info.get('floatShares', 0)
        short_pct = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0

        # --- 🎯 [스코어링 로직: 덤핑 방어 특화] ---
        score = 0
        
        # 가점 영역
        if current_price >= vwap: score += 20             
        if gap_pct >= 10: score += 15                     
        if rvol >= 100: score += 10                       
        if dist_to_pmh <= 2.5: score += 15                
        if 0 < float_shares <= 20_000_000: score += 15    
        if short_pct >= 15: score += 10                   
        
        # 🔥 추가 가점 (진짜 대장주 요건)
        if dollar_volume >= 5_000_000: score += 20        # 500만불(65억) 이상 찐돈 유입
        if higher_lows: score += 20                       # 장전 내내 저점 높임 (덤핑 방어 패턴)
        if gap_win_rate >= 50 and total_gaps >= 3: score += 15 # 과거 갭 뜰 때마다 날아간 착한 DNA

        # ☠️ 치명적 감점 (가짜 펌핑 거르기)
        if gap_win_rate < 20 and total_gaps >= 3: score -= 40  # 악질 유상증자/덤핑 상습범
        if dollar_volume < 1_000_000: score -= 30              # 100만불도 안 되는 깃털 호가창
        
        # 최종 등급 판정
        if score >= 110 and current_price >= vwap: tier = "👑 찐대장 (상킷 타겟)"
        elif score >= 80 and current_price >= vwap: tier = "🔥 S급 (수급 양호)"
        elif score >= 50: tier = "🎯 A급 (감시망)"
        elif score < 30 or current_price < (vwap * 0.98): tier = "☠️ F급 (설거지 주의)"
        else: tier = "🟡 B급 (관망)"

        return {
            'ticker': ticker_symbol, 'price': current_price, 'gap': gap_pct,
            'volume': today_volume, 'dollar_vol': dollar_volume, 'rvol': rvol, 'vwap': vwap, 
            'pm_high': pm_high, 'pm_low': pm_low, 'dist_pmh': dist_to_pmh, 
            'rsi': current_rsi, 'bb_up': bb_upper, 'higher_lows': higher_lows,
            'gap_win_rate': gap_win_rate, 'total_gaps': total_gaps,
            'float': float_shares, 'short': short_pct, 'score': score, 'tier': tier
        }
    except Exception as e:
        return {"error": f"[{ticker_symbol}] 데이터 수집 에러 (존재하지 않거나 거래 없음)"}

# --- [4] UI 화면 구성 ---
st.title("🛡️ 프리마켓 찐대장 판독기 (DUMP 필터링)")
st.markdown("가짜 펌핑(Pump & Dump)을 걸러내고 상방 서킷(LULD)을 노리는 동전주 특화 스캐너입니다.")
st.markdown("---")

input_tickers = st.text_input("🔍 종목 입력 (쉼표 구분)", "GME, AMC, FFIE, HOLO, CRKN")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("과거 1년 치 악질 DNA와 거래 대금을 정밀 추적 중..."):
        results, errors = [], []
        for t in ticker_list:
            res = analyze_ticker_ultimate(t)
            if "error" in res: errors.append(res["error"])
            else: results.append(res)
    
    if errors:
        for err in errors: st.error(err)

    if results:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 실시간 타점 & 설거지 방어 랭킹")
        st.dataframe(
            df_res[['ticker', 'tier', 'score', 'price', 'gap', 'dollar_vol', 'gap_win_rate']].style.format({
                'price': '${:.2f}', 'gap': '{:+.2f}%', 'dollar_vol': '${:,.0f}', 'gap_win_rate': '{:.1f}%'
            }), 
            use_container_width=True, hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔬 종목 정밀 엑스레이 (X-Ray)")
        selected_ticker = st.selectbox("심층 해부할 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([6, 4])
        with c1:
            st.markdown(f"## {data['ticker']} <span style='font-size:18px;'>({data['tier']})</span>", unsafe_allow_html=True)
        with c2:
            p_color = "val-green" if data['gap'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span class='{p_color}' style='font-size: 32px; font-weight: bold;'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["💰 거래대금 & 수급", "🛡️ 덤핑 방어력 (DNA)", "⚙️ 기준선 & 스퀴즈"])
        
        with tab1:
            st.markdown("### 진짜 돈이 들어왔는가?")
            d_vol_str = f"${data['dollar_vol']/1_000_000:.1f}M (백만 달러)"
            st.markdown(f"**실 거래대금:** <span class='val-green'>{d_vol_str}</span>", unsafe_allow_html=True)
            if data['dollar_vol'] < 1_000_000:
                st.error("🚨 경고: 거래대금이 100만 달러 미만입니다. 세력의 호가창 장난일 확률이 99%입니다.")
            elif data['dollar_vol'] >= 5_000_000:
                st.success("🔥 500만 달러 이상 찐돈 유입! 상방 모멘텀이 매우 강력합니다.")
            
            st.markdown(f"**RVOL (상대 거래량):** {data['rvol']:.1f}%")

        with tab2:
            st.markdown("### 본장에서 내리꽂을 놈인가?")
            
            # DNA 검사 결과
            if data['total_gaps'] > 0:
                dna_color = "val-red" if data['gap_win_rate'] < 30 else ("val-green" if data['gap_win_rate'] > 50 else "")
                st.markdown(f"**과거 갭상승 승률:** <span class='{dna_color}'>{data['gap_win_rate']:.1f}%</span> (총 {data['total_gaps']}번의 갭상승 중 양봉 마감 비율)", unsafe_allow_html=True)
                if data['gap_win_rate'] < 20 and data['total_gaps'] >= 3:
                    st.error("☠️ 악질 DNA: 이 종목은 과거 갭만 띄우고 본장에서 내다 꽂은 전적이 화려합니다. 절대 매수 금지.")
            else:
                st.markdown("**과거 갭상승 승률:** 최근 1년간 10% 이상 갭 뜬 이력이 없습니다.")

            # 계단식 저점 방어
            st.markdown(f"**프리마켓 저점 지지 여부:** {'✅ 강력 (저점 높이는 중)' if data['higher_lows'] else '❌ 취약 (저점이 깨지거나 횡보)'}")
            if data['higher_lows']:
                st.info("장전 내내 누군가 물량을 받으며 저점을 끌어올리는 '덤핑 방어 패턴'이 확인되었습니다.")

        with tab3:
            st.markdown(f"**VWAP (생명선):** <span class='val-blue'>${data['vwap']:.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"**PMH (전고점 거리):** {data['dist_pmh']:.1f}% 남음")
            
            f_str = f"{data['float']/1_000_000:.1f}M" if data['float'] > 0 else "N/A"
            s_str = f"{data['short']:.1f}%" if data['short'] > 0 else "N/A"
            st.markdown(f"**유통주식수 (Float):** {f_str}")
            st.markdown(f"**공매도 잔고 (Short):** {s_str}")

        st.markdown('</div>', unsafe_allow_html=True)
