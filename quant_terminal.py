import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- [1] 기본 설정 ---
st.set_page_config(page_title="프리마켓 몬스터 스캐너 (최종 종결판)", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 22px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
    .score-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .score-table th, .score-table td { border: 1px solid #444; padding: 10px; text-align: left; font-size: 14px; }
    .score-table th { background-color: #2D2D2D; color: #aaa; font-weight: bold;}
    .val-green { color: #4CAF50; font-weight: bold;}
    .val-red { color: #FF5252; font-weight: bold;}
    .val-blue { color: #2196F3; font-weight: bold;}
    .val-yellow { color: #FFB020; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- [2] 메인 데이터 분석 엔진 (최종 100점 만점) ---
@st.cache_data(ttl=60)
def analyze_ticker_ultimate(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        score_details = []
        total_score = 0
        
        # ------------------------------------------------
        # 1. 일봉 데이터 (DNA, 매물대, 전일 고점 돌파 확인)
        # ------------------------------------------------
        df_daily = ticker.history(period="1y", interval="1d")
        if len(df_daily) < 2:
            return {"error": f"[{ticker_symbol}] 일봉 데이터 부족"}

        # 👑 [신규 디테일 1] 갇힌 갭 vs 열린 갭 (YDT High 돌파 여부)
        # 마지막 행은 현재(오늘) 데이터일 수 있으므로 shift(1)을 통해 정확한 전일 종가/고점 추출
        df_daily['Prev_Close'] = df_daily['Close'].shift(1)
        df_daily['Prev_High'] = df_daily['High'].shift(1)
        
        yest_close = df_daily['Prev_Close'].iloc[-1]
        yest_high = df_daily['Prev_High'].iloc[-1]

        # 갭 DNA 계산
        df_daily['Gap_Pct'] = (df_daily['Open'] - df_daily['Prev_Close']) / df_daily['Prev_Close'] * 100
        gap_days = df_daily[df_daily['Gap_Pct'] >= 10.0]
        if len(gap_days) > 0:
            win_days = gap_days[gap_days['Close'] > gap_days['Open']]
            gap_win_rate = (len(win_days) / len(gap_days)) * 100
            total_gaps = len(gap_days)
        else:
            gap_win_rate = None 
            total_gaps = 0

        # 장기 매물대
        df_daily['SMA200'] = df_daily['Close'].rolling(window=200, min_periods=50).mean()
        sma200 = df_daily['SMA200'].iloc[-1] if not pd.isna(df_daily['SMA200'].iloc[-1]) else 0
        adv_10 = df_daily['Volume'].tail(10).mean()

        # ------------------------------------------------
        # 2. 1분봉 데이터 (피보나치, VWAP, 수급 디테일)
        # ------------------------------------------------
        df_1m = ticker.history(period="1d", interval="1m", prepost=True)
        if df_1m.empty:
            return {"error": f"[{ticker_symbol}] 당일 분봉 데이터 없음"}

        current_price = df_1m['Close'].iloc[-1]
        today_volume = df_1m['Volume'].sum()
        dollar_volume = current_price * today_volume
        pm_high = df_1m['High'].max()
        pm_low = df_1m['Low'].min()

        # 👑 [신규 디테일 2] 피보나치 0.618 방어선 계산 (Dead Cat 필터)
        fib_range = pm_high - pm_low
        fib_382 = pm_high - (fib_range * 0.382)
        fib_618 = pm_high - (fib_range * 0.618)

        # 저점 갱신 방어
        higher_lows = False
        if len(df_1m) >= 30:
            chunks = np.array_split(df_1m, 3)
            if (chunks[2]['Low'].min() > chunks[1]['Low'].min()) and (chunks[1]['Low'].min() >= chunks[0]['Low'].min()):
                higher_lows = True

        # 거래량 집중도 & VWAP
        recent_60m_vol = df_1m['Volume'].tail(60).sum()
        vol_concentration = (recent_60m_vol / today_volume * 100) if today_volume > 0 else 0
        tp = (df_1m['High'] + df_1m['Low'] + df_1m['Close']) / 3
        cum_v = df_1m['Volume'].cumsum()
        vwap = ((tp * df_1m['Volume']).cumsum() / np.where(cum_v == 0, 1, cum_v)).iloc[-1]
        
        gap_pct = ((current_price - yest_close) / yest_close) * 100
        rvol = (today_volume / adv_10) * 100 if adv_10 > 0 else 0
        dist_to_sma200 = ((sma200 - current_price) / current_price) * 100 if sma200 > 0 else 999
        
        # ------------------------------------------------
        # 3. 펀더멘털 & 재료 (뉴스, 유상증자 폭탄 리스크)
        # ------------------------------------------------
        float_shares = info.get('floatShares', 0)
        short_pct = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0
        has_news = len(ticker.news) > 0
        
        # 👑 [신규 디테일 3] 보유 현금 기반 유증 리스크 (Cash Runway)
        total_cash = info.get('totalCash', 0)
        market_cap = info.get('marketCap', 1)
        cash_ratio = total_cash / market_cap if market_cap > 0 else 0

        # --- 🎯 [최종 100점 만점 스코어링 로직] ---
        
        # [카테고리 1: 수급 및 거래대금 (총 25점)]
        if dollar_volume >= 5_000_000:
            total_score += 10
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "10 / 10", "reason": f"${dollar_volume/1000000:.1f}M 유입. 기관/세력의 강력한 개입 확인."})
        elif dollar_volume >= 1_000_000:
            total_score += 5
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "5 / 10", "reason": f"${dollar_volume/1000000:.1f}M. 대금은 발생했으나 S급 슈팅엔 약간 부족."})
        else:
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "0 / 10", "reason": "거래대금 100만불 미만. 호가창 장난일 확률 99%."})

        if vol_concentration >= 40:
            total_score += 10
            score_details.append({"cat":"수급 (10점)","item": "거래량 집중도", "score": "10 / 10", "reason": f"최근 1시간 거래 비중 {vol_concentration:.1f}%. 본장 직전 매수세 점화 됨."})
        else:
            score_details.append({"cat":"수급 (10점)","item": "거래량 집중도", "score": "0 / 10", "reason": f"최근 1시간 비중 {vol_concentration:.1f}%. 새벽에만 띄워놓고 현재 소외 중."})

        if rvol >= 100:
            total_score += 5
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "5 / 5", "reason": "과거 10일 평균 거래량을 프리장부터 이미 뚫었음."})
        else:
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "0 / 5", "reason": "평소 대비 유의미한 거래량 폭발이 없음."})

        # [카테고리 2: 단기 차트 및 추세 (총 35점)]
        if current_price > yest_high:
            total_score += 10
            score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점 돌파)", "score": "10 / 10", "reason": f"전일 고점(${yest_high:.2f}) 돌파. 위에 갇힌 매물대가 없는 'Clear Sky' 구간!"})
        else:
            score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점 돌파)", "score": "0 / 10", "reason": f"전일 고점(${yest_high:.2f}) 아래의 갇힌 갭. 본전 탈출 매물 폭탄 주의."})

        if current_price >= fib_382:
            total_score += 10
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "10 / 10", "reason": "상승분의 38.2% 이내만 내어준 건강한 눌림. 극강의 방어력."})
        elif current_price >= fib_618:
            total_score += 5
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "5 / 10", "reason": "마지노선인 61.8% 방어선 지지 중. 방향성 관망 필요."})
        else:
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "0 / 10", "reason": "🚨 상승분의 61.8% 이상 반납. 수급이 붕괴된 데드캣 바운스."})

        if current_price >= vwap:
            total_score += 10
            score_details.append({"cat":"차트 (10점)","item": "VWAP (생명선)", "score": "10 / 10", "reason": f"당일 평균 단가(${vwap:.2f}) 위에서 안정적으로 지지 중."})
        else:
            score_details.append({"cat":"차트 (10점)","item": "VWAP (생명선)", "score": "0 / 10", "reason": "VWAP 아래로 뚫림. 당일 매수자 투매 리스크 고조."})

        if higher_lows:
            total_score += 5
            score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "5 / 5", "reason": "장전 내내 저점을 갱신하며 매물을 소화하는 긍정적 패턴."})
        else:
            score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "0 / 5", "reason": "저점이 지속 하락 중. 지속적인 덤핑(매도) 발생 중."})

        # [카테고리 3: 악질 DNA 및 장기 매물대 (총 20점)]
        if gap_win_rate is None:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": "1년 내 갭상승 이력 없음. 덤핑 데이터가 없어 중립 호재."})
        elif gap_win_rate >= 50 and total_gaps >= 3:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": f"과거 {total_gaps}번 중 {gap_win_rate:.1f}% 양봉 마감. 신뢰도 높음."})
        elif gap_win_rate < 20 and total_gaps >= 3:
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "0 / 10", "reason": f"🚨 과거 덤핑 확률 {100-gap_win_rate:.1f}%. 상습 설거지 종목!"})
        else:
            total_score += 5
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "5 / 10", "reason": f"승률 {gap_win_rate:.1f}%. 본장 시작 후 수급 확인 필수."})

        if 0 < dist_to_sma200 <= 5.0:
            score_details.append({"cat":"매물대 (10점)","item": "장기 저항선 (200 SMA)", "score": "0 / 10", "reason": f"현재가 바로 위({dist_to_sma200:.1f}%) 200일선 위치. 악성 매물대 직격 위험."})
        else:
            total_score += 10
            score_details.append({"cat":"매물대 (10점)","item": "장기 저항선 (200 SMA)", "score": "10 / 10", "reason": "200일선을 완벽히 뚫어냈거나, 매물대가 멀리 있어 안전함."})

        # [카테고리 4: 펀더멘털 및 스퀴즈 재료 (총 25점)] -> 오타 수정. 총점 맞추기 위해 20점으로 조정.
        if has_news:
            total_score += 10
            score_details.append({"cat":"재료 (10점)","item": "상승 명분 (뉴스)", "score": "10 / 10", "reason": "오늘 펌핑을 정당화할 뉴스가 존재. 묻지마 펌핑 아님."})
        else:
            score_details.append({"cat":"재료 (10점)","item": "상승 명분 (뉴스)", "score": "0 / 10", "reason": "아무 뉴스 없음. 단순 숏커버링이나 장난일 확률 높아 본장 유지 힘듦."})

        if total_cash > 5_000_000 or cash_ratio > 0.1:
            total_score += 5
            score_details.append({"cat":"재무 (5점)","item": "유상증자 리스크 방어", "score": "5 / 5", "reason": "금고에 500만불 이상 있거나 시총대비 현금 양호. 장중 ATM 유증 직격탄 확률 낮음."})
        else:
            score_details.append({"cat":"재무 (5점)","item": "유상증자 리스크 방어", "score": "0 / 5", "reason": "🚨 현금 바닥 상태. 주가 띄워놓고 기습 유상증자(Offering) 때릴 확률 극히 높음."})

        squeeze_score = 0
        if 0 < float_shares <= 20_000_000: squeeze_score += 3
        if short_pct >= 15: squeeze_score += 2
        
        total_score += squeeze_score
        score_details.append({"cat":"가벼움 (5점)","item": "품절주 & 공매도", "score": f"{squeeze_score} / 5", "reason": "숏스퀴즈 모멘텀과 유통주식수 가벼움 정도 평가."})

        # 최종 판정
        if total_score >= 85: tier = "👑 찐대장 (풀베팅 타겟)"
        elif total_score >= 70: tier = "🔥 S급 (수급 양호)"
        elif total_score >= 50: tier = "🎯 A급 (감시망)"
        elif total_score >= 35: tier = "🟡 B급 (관망)"
        else: tier = "☠️ F급 (설거지 확정)"

        return {
            'ticker': ticker_symbol, 'price': current_price, 'gap': gap_pct,
            'dollar_vol': dollar_volume, 'score': total_score, 'tier': tier,
            'details': score_details
        }
    except Exception as e:
        return {"error": f"[{ticker_symbol}] 분석 중 오류: {str(e)}"}

# --- [3] UI 화면 구성 ---
st.title("🛡️ 100점 만점 프리마켓 정밀 판독기 (Final Edition)")
st.markdown("차트 갭, 피보나치 방어선, 그리고 현금 고갈(유상증자) 리스크까지 모두 통과한 진짜 몬스터만 선별합니다.")
st.markdown("---")

input_tickers = st.text_input("🔍 종목 입력 (쉼표 구분)", "GME, AMC, FFIE, HOLO, CRKN")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("알고리즘 봇 수준의 정밀 스캐닝 중 (매물대/피보나치/유증 리스크 체크)..."):
        results, errors = [], []
        for t in ticker_list:
            res = analyze_ticker_ultimate(t)
            if "error" in res: errors.append(res["error"])
            else: results.append(res)
    
    if errors:
        for err in errors: st.error(err)

    if results:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 최종 종합 점수 랭킹")
        st.dataframe(
            df_res[['ticker', 'tier', 'score', 'price', 'gap', 'dollar_vol']].style.format({
                'price': '${:.2f}', 'gap': '{:+.2f}%', 'dollar_vol': '${:,.0f}'
            }), 
            use_container_width=True, hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔬 100점 만점 엑스레이 채점표")
        selected_ticker = st.selectbox("정밀 리포트를 볼 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([7, 3])
        with c1:
            st.markdown(f"## {data['ticker']} <span style='font-size:18px;'>({data['tier']})</span>", unsafe_allow_html=True)
        with c2:
            score_color = "val-green" if data['score'] >= 70 else ("val-yellow" if data['score'] >= 50 else "val-red")
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 16px; color: #888;'>완벽 분석 점수</span><br><span class='{score_color}' style='font-size: 38px;'>{data['score']} / 100</span></div>", unsafe_allow_html=True)
        
        # 상세 채점표 HTML 렌더링
        html_table = "<table class='score-table'><thead><tr><th style='width:15%'>카테고리</th><th style='width:20%'>평가 항목</th><th style='width:12%'>점수</th><th style='width:53%'>분석 근거 (Rationale)</th></tr></thead><tbody>"
        
        for item in data['details']:
            if item['score'].startswith('0'): sc_html = f"<span class='val-red'>{item['score']}</span>"
            elif float(item['score'].split('/')[0].strip()) == float(item['score'].split('/')[1].strip()): sc_html = f"<span class='val-green'>{item['score']}</span>"
            else: sc_html = f"<span class='val-blue'>{item['score']}</span>"
                
            html_table += f"<tr><td><b>{item['cat']}</b></td><td>{item['item']}</td><td>{sc_html}</td><td>{item['reason']}</td></tr>"
            
        html_table += "</tbody></table>"
        
        st.markdown(html_table, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
