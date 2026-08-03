import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- [1] 기본 설정 ---
st.set_page_config(page_title="프리마켓 몬스터 스캐너 (100점 만점 리포트)", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 22px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
    .score-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .score-table th, .score-table td { border: 1px solid #444; padding: 10px; text-align: left; }
    .score-table th { background-color: #2D2D2D; color: #aaa; }
    .val-green { color: #4CAF50; font-weight: bold;}
    .val-red { color: #FF5252; font-weight: bold;}
    .val-blue { color: #2196F3; font-weight: bold;}
    .val-yellow { color: #FFB020; font-weight: bold;}
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

# --- [3] 메인 데이터 분석 엔진 (100점 만점 스코어링) ---
@st.cache_data(ttl=60)
def analyze_ticker_ultimate(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        score_details = []
        total_score = 0
        
        # 1. 일봉 데이터 (DNA 및 매물대 분석)
        df_daily = ticker.history(period="1y", interval="1d")
        
        df_daily['Prev_Close'] = df_daily['Close'].shift(1)
        df_daily['Gap_Pct'] = (df_daily['Open'] - df_daily['Prev_Close']) / df_daily['Prev_Close'] * 100
        gap_days = df_daily[df_daily['Gap_Pct'] >= 10.0]
        
        if len(gap_days) > 0:
            win_days = gap_days[gap_days['Close'] > gap_days['Open']]
            gap_win_rate = (len(win_days) / len(gap_days)) * 100
            total_gaps = len(gap_days)
        else:
            gap_win_rate = None 
            total_gaps = 0

        df_daily['SMA50'] = df_daily['Close'].rolling(window=50, min_periods=10).mean()
        df_daily['SMA200'] = df_daily['Close'].rolling(window=200, min_periods=50).mean()
        
        yest_close = df_daily['Close'].iloc[-1]
        sma200 = df_daily['SMA200'].iloc[-1] if not pd.isna(df_daily['SMA200'].iloc[-1]) else 0
        adv_10 = df_daily['Volume'].tail(10).mean()

        # 2. 1분봉 데이터 (프리마켓)
        df_1m = ticker.history(period="1d", interval="1m", prepost=True)
        if df_1m.empty:
            return {"error": f"[{ticker_symbol}] 당일 분봉 데이터 없음"}

        current_price = df_1m['Close'].iloc[-1]
        today_volume = df_1m['Volume'].sum()
        pm_high = df_1m['High'].max()
        dollar_volume = current_price * today_volume
        
        higher_lows = False
        if len(df_1m) >= 30:
            chunks = np.array_split(df_1m, 3)
            if (chunks[2]['Low'].min() > chunks[1]['Low'].min()) and (chunks[1]['Low'].min() >= chunks[0]['Low'].min()):
                higher_lows = True

        recent_60m_vol = df_1m['Volume'].tail(60).sum()
        vol_concentration = (recent_60m_vol / today_volume * 100) if today_volume > 0 else 0

        df_5m = df_1m.resample('5min').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
        is_above_5m_ema = False
        if len(df_5m) >= 20:
            df_5m['EMA20'] = df_5m['Close'].ewm(span=20, adjust=False).mean()
            is_above_5m_ema = current_price > df_5m['EMA20'].iloc[-1]

        gap_pct = ((current_price - yest_close) / yest_close) * 100
        rvol = (today_volume / adv_10) * 100 if adv_10 > 0 else 0
        dist_to_sma200 = ((sma200 - current_price) / current_price) * 100 if sma200 > 0 else 999
        
        tp = (df_1m['High'] + df_1m['Low'] + df_1m['Close']) / 3
        cum_v = df_1m['Volume'].cumsum()
        vwap = ((tp * df_1m['Volume']).cumsum() / np.where(cum_v == 0, 1, cum_v)).iloc[-1]
        
        float_shares = info.get('floatShares', 0)
        short_pct = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0
        has_news = len(ticker.news) > 0

        # --- 🎯 [100점 만점 스코어링 로직 & 분석 리포트 생성] ---
        
        # [카테고리 1: 수급 및 거래대금 - 최대 30점]
        if dollar_volume >= 5_000_000:
            total_score += 15
            score_details.append({"cat":"수급 (15점)","item": "실거래 대금", "score": "15 / 15", "reason": f"${dollar_volume/1000000:.1f}M 유입. 세력의 '진짜 돈'이 들어온 것으로 판단됨."})
        elif dollar_volume >= 1_000_000:
            total_score += 5
            score_details.append({"cat":"수급 (15점)","item": "실거래 대금", "score": "5 / 15", "reason": f"${dollar_volume/1000000:.1f}M 유입. 거래대금은 발생했으나 S급 돌파를 위해선 부족함."})
        else:
            score_details.append({"cat":"수급 (15점)","item": "실거래 대금", "score": "0 / 15", "reason": "거래대금 100만불 미만. 호가창이 얇아 세력의 틱 장난일 확률이 99%임."})

        if vol_concentration >= 40:
            total_score += 10
            score_details.append({"cat":"수급 (10점)","item": "거래량 집중도", "score": "10 / 10", "reason": f"최근 1시간 내 거래량이 {vol_concentration:.1f}% 집중됨. 본장 직전 매수세가 살아있음."})
        else:
            score_details.append({"cat":"수급 (10점)","item": "거래량 집중도", "score": "0 / 10", "reason": f"최근 1시간 거래 비중이 {vol_concentration:.1f}%에 불과. 새벽 반짝 상승 후 소외되고 있음."})

        if rvol >= 100:
            total_score += 5
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "5 / 5", "reason": "최근 10일 평균 거래량을 이미 돌파하며 시장의 이목이 집중됨."})
        else:
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "0 / 5", "reason": "평소와 비교해 유의미한 거래량 폭발이 관찰되지 않음."})

        # [카테고리 2: 단기 차트 및 추세 - 최대 30점]
        if current_price >= vwap:
            total_score += 10
            score_details.append({"cat":"추세 (10점)","item": "VWAP (생명선) 지지", "score": "10 / 10", "reason": "당일 평균 매수 단가(VWAP) 위에서 가격을 굳건히 방어 중."})
        else:
            score_details.append({"cat":"추세 (10점)","item": "VWAP (생명선) 지지", "score": "0 / 10", "reason": "VWAP 아래로 뚫림. 당일 매수자들 대부분이 손실 구간이라 투매 위험 높음."})

        if is_above_5m_ema:
            total_score += 10
            score_details.append({"cat":"추세 (10점)","item": "5분봉 20EMA 지지", "score": "10 / 10", "reason": "5분봉 기준 단기 이동평균선을 타며 안정적인 상승 추세 유지 중."})
        else:
            score_details.append({"cat":"추세 (10점)","item": "5분봉 20EMA 지지", "score": "0 / 10", "reason": "단기 지지선 이탈. 수급이 꼬이면서 하방 압력이 거세지고 있음."})

        if higher_lows:
            total_score += 10
            score_details.append({"cat":"추세 (10점)","item": "프리마켓 저점 갱신", "score": "10 / 10", "reason": "장전 내내 저점을 계단식으로 높이며 악성 물량을 소화하는 긍정적 패턴."})
        else:
            score_details.append({"cat":"추세 (10점)","item": "프리마켓 저점 갱신", "score": "0 / 10", "reason": "저점이 낮아지거나 횡보 중. 누군가 지속적으로 덤핑(매도)하고 있음."})

        # [카테고리 3: 악질 DNA 및 매물대 - 최대 20점]
        if gap_win_rate is None:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": "최근 1년 내 10% 이상 갭상승 이력 없음 (악성 덤핑 데이터가 없어 중립적 호재)."})
        elif gap_win_rate >= 50 and total_gaps >= 3:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": f"과거 {total_gaps}번 갭 상승 시 {gap_win_rate:.1f}% 확률로 양봉 마감. 상승을 잘 지키는 착한 종목."})
        elif gap_win_rate < 20 and total_gaps >= 3:
            # 치명적 악질 DNA 감점 반영
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "0 / 10", "reason": f"🚨 [경고] 과거 갭 띄우고 내리꽂은 확률 {100-gap_win_rate:.1f}%. 상습 덤핑 종목이라 신뢰도 최악."})
        else:
            total_score += 5
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "5 / 10", "reason": f"과거 승률 {gap_win_rate:.1f}%. 애매한 기록이므로 본장 시작 후 방향성 확인 필수."})

        if 0 < dist_to_sma200 <= 5.0:
            score_details.append({"cat":"매물대 (10점)","item": "장기 이평선(200SMA)", "score": "0 / 10", "reason": f"현재가 바로 위({dist_to_sma200:.1f}%)에 200일선 위치. 과거 물린 개미들의 거대한 매도 폭탄이 대기 중."})
        else:
            total_score += 10
            reason_txt = "이미 200일선을 강하게 돌파했거나, 저항선이 멀리 있어 상방이 열려있음." if dist_to_sma200 < 0 else "장기 저항선과의 간섭이 적은 안전 구간."
            score_details.append({"cat":"매물대 (10점)","item": "장기 이평선(200SMA)", "score": "10 / 10", "reason": reason_txt})

        # [카테고리 4: 재료 및 숏스퀴즈 조건 - 최대 20점]
        if has_news:
            total_score += 10
            score_details.append({"cat":"재료 (10점)","item": "개별 호재(뉴스)", "score": "10 / 10", "reason": "오늘 펌핑을 정당화할 명확한 뉴스가 존재하여 시장의 매수세가 붙기 좋음."})
        else:
            score_details.append({"cat":"재료 (10점)","item": "개별 호재(뉴스)", "score": "0 / 10", "reason": "아무 뉴스 없이 오름. 세력의 장난이나 단순 숏커버링으로, 정규장에서 유지가 힘듦."})

        squeeze_score = 0
        sq_reasons = []
        if 0 < float_shares <= 20_000_000:
            squeeze_score += 5
            sq_reasons.append(f"품절주(Float {float_shares/1_000_000:.1f}M)")
        if short_pct >= 15:
            squeeze_score += 5
            sq_reasons.append(f"공매도 잔고 높음({short_pct:.1f}%)")
        
        total_score += squeeze_score
        sq_reason_text = " + ".join(sq_reasons) + " -> 숏스퀴즈 및 가벼운 슈팅 가능성 높음." if squeeze_score > 0 else "유통 주식이 너무 무겁거나 스퀴즈 모멘텀이 부족함."
        score_details.append({"cat":"가벼움 (10점)","item": "품절주 & 공매도", "score": f"{squeeze_score} / 10", "reason": sq_reason_text})

        # 최종 등급 판정 (0 ~ 100점 만점)
        if total_score >= 85: tier = "👑 찐대장 (상킷 타겟)"
        elif total_score >= 70: tier = "🔥 S급 (수급 양호)"
        elif total_score >= 50: tier = "🎯 A급 (감시망)"
        elif total_score >= 35: tier = "🟡 B급 (관망)"
        else: tier = "☠️ F급 (설거지 주의)"

        return {
            'ticker': ticker_symbol, 'price': current_price, 'gap': gap_pct,
            'dollar_vol': dollar_volume, 'vwap': vwap, 'score': total_score, 'tier': tier,
            'details': score_details
        }
    except Exception as e:
        return {"error": f"[{ticker_symbol}] 분석 중 오류: {str(e)}"}

# --- [4] UI 화면 구성 ---
st.title("🛡️ 100점 만점 프리마켓 정밀 판독기")
st.markdown("수급, 추세, DNA, 재료를 100점 만점으로 환산하여 오를 수밖에 없는 이유와 덤핑 징후를 정확히 짚어줍니다.")
st.markdown("---")

input_tickers = st.text_input("🔍 종목 입력 (쉼표 구분)", "GME, AMC, FFIE, HOLO, CRKN")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("종목별 100점 만점 채점 및 이유 분석 중..."):
        results, errors = [], []
        for t in ticker_list:
            res = analyze_ticker_ultimate(t)
            if "error" in res: errors.append(res["error"])
            else: results.append(res)
    
    if errors:
        for err in errors: st.error(err)

    if results:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 종합 점수 랭킹")
        st.dataframe(
            df_res[['ticker', 'tier', 'score', 'price', 'gap', 'dollar_vol']].style.format({
                'price': '${:.2f}', 'gap': '{:+.2f}%', 'dollar_vol': '${:,.0f}'
            }), 
            use_container_width=True, hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔬 100점 만점 상세 채점표 (X-Ray Report)")
        selected_ticker = st.selectbox("분석 리포트를 볼 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([7, 3])
        with c1:
            st.markdown(f"## {data['ticker']} <span style='font-size:18px;'>({data['tier']})</span>", unsafe_allow_html=True)
        with c2:
            score_color = "val-green" if data['score'] >= 70 else ("val-yellow" if data['score'] >= 50 else "val-red")
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 16px; color: #888;'>종합 점수</span><br><span class='{score_color}' style='font-size: 38px;'>{data['score']} / 100</span></div>", unsafe_allow_html=True)
        
        # 상세 채점표 HTML 렌더링
        html_table = "<table class='score-table'><thead><tr><th style='width:15%'>카테고리</th><th style='width:20%'>평가 항목</th><th style='width:10%'>획득 점수</th><th style='width:55%'>분석 이유 (Rationale)</th></tr></thead><tbody>"
        
        for item in data['details']:
            # 점수에 따른 색상 하이라이트
            if item['score'].startswith('0'):
                sc_html = f"<span class='val-red'>{item['score']}</span>"
            elif float(item['score'].split('/')[0].strip()) == float(item['score'].split('/')[1].strip()):
                sc_html = f"<span class='val-green'>{item['score']}</span>"
            else:
                sc_html = f"<span class='val-blue'>{item['score']}</span>"
                
            html_table += f"<tr><td><b>{item['cat']}</b></td><td>{item['item']}</td><td>{sc_html}</td><td>{item['reason']}</td></tr>"
            
        html_table += "</tbody></table>"
        
        st.markdown(html_table, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
