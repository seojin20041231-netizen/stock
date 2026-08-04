import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import re

# --- [1] 기본 설정 및 API 키 ---
FINNHUB_API_KEY = "d9nksmpr01qvumganiogd9nksmpr01qvumganip0"

st.set_page_config(page_title="동전주 몬스터 스캐너 (ULTIMATE Version)", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 22px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
    .score-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .score-table th, .score-table td { border: 1px solid #444; padding: 10px; text-align: left; font-size: 14px; }
    .score-table th { background-color: #2D2D2D; color: #aaa; font-weight: bold;}
    .rf-table { width: 100%; border-collapse: collapse; margin-top: 10px; background-color: #181818; color: #d4d4d4;}
    .rf-table th, .rf-table td { border: 1px solid #333; padding: 10px; text-align: left; font-size: 13px; }
    .rf-table th { background-color: #252525; color: #fff; font-weight: bold; text-align: center;}
    .val-green { color: #4CAF50; font-weight: bold;}
    .val-red { color: #FF5252; font-weight: bold;}
    .val-blue { color: #2196F3; font-weight: bold;}
    .val-yellow { color: #FFB020; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# 섹터별 대표 ETF 매핑 (동반 상승 테마 확인용)
SECTOR_ETF_MAP = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF', 
    'Energy': 'XLE', 'Consumer Cyclical': 'XLY', 'Industrials': 'XLI'
}

# --- [2] 메인 데이터 분석 엔진 ---
@st.cache_data(ttl=60)
def analyze_ticker_ultimate(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        score_details = []
        total_score = 0
        
        # ------------------------------------------------
        # 1. 일봉 데이터 (기존 로직)
        # ------------------------------------------------
        df_daily = ticker.history(period="1y", interval="1d")
        if len(df_daily) < 2:
            return {"error": f"[{ticker_symbol}] 일봉 데이터가 부족합니다."}

        df_daily['Prev_Close'] = df_daily['Close'].shift(1)
        df_daily['Prev_High'] = df_daily['High'].shift(1)
        
        yest_close = df_daily['Prev_Close'].iloc[-1]
        yest_high = df_daily['Prev_High'].iloc[-1]

        df_daily['Gap_Pct'] = (df_daily['Open'] - df_daily['Prev_Close']) / df_daily['Prev_Close'] * 100
        gap_days = df_daily[df_daily['Gap_Pct'] >= 10.0]
        if len(gap_days) > 0:
            win_days = gap_days[gap_days['Close'] > gap_days['Open']]
            gap_win_rate = (len(win_days) / len(gap_days)) * 100
            total_gaps = len(gap_days)
        else:
            gap_win_rate = None 
            total_gaps = 0

        df_daily['SMA200'] = df_daily['Close'].rolling(window=200, min_periods=50).mean()
        sma200 = df_daily['SMA200'].iloc[-1] if not pd.isna(df_daily['SMA200'].iloc[-1]) else 0
        adv_10 = df_daily['Volume'].tail(10).mean()

        # ------------------------------------------------
        # 2. 1분봉 데이터 (Finnhub + 기존 로직)
        # ------------------------------------------------
        df_1m = pd.DataFrame()
        end_time = int(time.time())
        start_time = end_time - (86400 * 3) 
        
        fh_url = f"https://finnhub.io/api/v1/stock/candle?symbol={ticker_symbol}&resolution=1&from={start_time}&to={end_time}&token={FINNHUB_API_KEY}"
        try:
            r = requests.get(fh_url, timeout=5)
            fh_data = r.json()
            if fh_data.get('s') == 'ok':
                df_1m = pd.DataFrame({
                    'Close': fh_data['c'], 'High': fh_data['h'],
                    'Low': fh_data['l'], 'Open': fh_data['o'], 'Volume': fh_data['v']
                })
        except Exception:
            pass 

        if df_1m.empty:
            df_1m = ticker.history(period="1d", interval="1m", prepost=True)
            if df_1m.empty:
                return {"error": f"[{ticker_symbol}] 당일 1분봉 데이터가 없습니다."}

        current_price = df_1m['Close'].iloc[-1]
        pm_high = df_1m['High'].max()
        pm_low = df_1m['Low'].min()

        vol_1m_sum = df_1m['Volume'].sum()
        vol_daily = df_daily['Volume'].iloc[-1] if not pd.isna(df_daily['Volume'].iloc[-1]) else 0
        vol_info = info.get('volume', 0)
        
        today_volume = max(vol_1m_sum, vol_daily, vol_info)
        if today_volume <= 0: today_volume = 1 
            
        dollar_volume = current_price * today_volume

        fib_range = pm_high - pm_low
        fib_382 = pm_high - (fib_range * 0.382)
        fib_618 = pm_high - (fib_range * 0.618)

        higher_lows = False
        if len(df_1m) >= 30:
            chunk_size = len(df_1m) // 3
            c1_low = df_1m['Low'].iloc[:chunk_size].min()
            c2_low = df_1m['Low'].iloc[chunk_size:chunk_size*2].min()
            c3_low = df_1m['Low'].iloc[chunk_size*2:].min()
            if (c3_low > c2_low) and (c2_low >= c1_low):
                higher_lows = True

        recent_60m_vol = df_1m['Volume'].tail(60).sum()
        vol_concentration = (recent_60m_vol / today_volume * 100) if today_volume > 0 else 0
        
        tp = (df_1m['High'] + df_1m['Low'] + df_1m['Close']) / 3
        cum_v = df_1m['Volume'].cumsum()
        vwap = ((tp * df_1m['Volume']).cumsum() / cum_v.replace(0, 1)).iloc[-1]
        
        gap_pct = ((current_price - yest_close) / yest_close) * 100
        rvol = (today_volume / adv_10) * 100 if adv_10 > 0 else 0
        dist_to_sma200 = ((sma200 - current_price) / current_price) * 100 if sma200 > 0 else 999
        
        float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
        market_cap = info.get('marketCap', 1)
        total_cash = info.get('totalCash', 0)
        cash_ratio = total_cash / market_cap if market_cap > 0 else 0
        
        turnover_ratio = today_volume / float_shares if float_shares > 1 else 0
        cap_vs_vol_ratio = dollar_volume / market_cap if market_cap > 1 else 0

        # ================================================================
        # 🌟 [신규 추가] 6대 심층 분석 엔진 데이터 수집
        # ================================================================

        # 1. SEC 공시 (유상증자 / 오퍼링 리스크 판별)
        offering_risk = False
        filings_url = f"https://finnhub.io/api/v1/stock/filings?symbol={ticker_symbol}&token={FINNHUB_API_KEY}"
        try:
            r_filings = requests.get(filings_url, timeout=3).json()
            if isinstance(r_filings, list):
                for f in r_filings[:10]: # 최근 10개 공시
                    form = f.get('form', '').upper()
                    if form in ['S-1', 'S-3', '424B3', '424B4', '424B5']:
                        offering_risk = True
                        break
        except: pass

        # 2. 거래량 가속도 (Volume Velocity - 최근 30분 집중도)
        recent_30m_vol = df_1m['Volume'].tail(30).sum()
        vol_velocity_ratio = (recent_30m_vol / today_volume * 100) if today_volume > 0 else 0

        # 3. PM High 수렴 및 Bull Flag
        dist_to_pm_high = ((pm_high - current_price) / pm_high) * 100 if pm_high > 0 else 999
        bull_flag_formed = (0 <= dist_to_pm_high <= 5.0) and (current_price >= vwap)

        # 4. 숏 스퀴즈 데이터 (공매도 잔고 비율)
        short_pct_float = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0

        # 5. 뉴스 NLP 키워드 질적 분석
        raw_news = ticker.news
        has_news = len(raw_news) > 0
        news_score_added = 0
        news_nlp_reason = "뉴스 없음 또는 의미 없는 찌라시."
        
        if has_news:
            s_keywords = r"fda|approv|contract|acquisit|buyback|patent|dod|clear|merger"
            a_keywords = r"earn|beat|partner|positiv|trial|phase"
            f_keywords = r"conferenc|incentiv|complianc|notic|offer|direct|pric|public offering"
            
            headline = raw_news[0]['title'].lower() if 'title' in raw_news[0] else ""
            if re.search(f_keywords, headline):
                news_score_added = -10
                news_nlp_reason = "🚨 [F급 재료] 오퍼링, 유증, 상폐경고 등 악재 키워드 감지."
            elif re.search(s_keywords, headline):
                news_score_added = 15
                news_nlp_reason = "🔥 [S급 재료] FDA, 계약, 인수합병 등 초강력 호재 감지."
            elif re.search(a_keywords, headline):
                news_score_added = 5
                news_nlp_reason = "📈 [A급 재료] 실적 호조, 파트너십 등 긍정적 모멘텀."
            else:
                news_score_added = 2
                news_nlp_reason = "단순 기업 소식 (일반 뉴스)."

        # 6. 테마 동반 상승 (섹터 모멘텀 확인)
        sector = info.get('sector', 'Unknown')
        sympathy_score = 0
        sympathy_reason = "섹터 정보 부재로 테마성 확인 불가."
        if sector in SECTOR_ETF_MAP:
            etf = SECTOR_ETF_MAP[sector]
            try:
                etf_df = yf.Ticker(etf).history(period="2d")
                if len(etf_df) >= 2:
                    etf_gap = (etf_df['Open'].iloc[-1] - etf_df['Close'].iloc[-2]) / etf_df['Close'].iloc[-2] * 100
                    if etf_gap > 0.5:
                        sympathy_score = 5
                        sympathy_reason = f"소속 섹터({sector}/{etf}) 전체 갭상승 중. 테마 동반 상승 징후."
                    else:
                        sympathy_reason = f"소속 섹터({sector}) 수급 평이. 개별주 독단적 움직임."
            except: pass

        # ================================================================
        # 🎯 [최종 스코어링 로직] (기존 100점 + 신규 PRO 가감점)
        # ================================================================

        # [기존: 수급 20 / 차트 30 / 매물대 20 / 재무 20] -> 베이스 스코어
        if dollar_volume >= 5_000_000: total_score += 10; score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "10 / 10", "reason": f"${dollar_volume/1000000:.1f}M 유입. 세력 개입 확인."})
        elif dollar_volume >= 1_000_000: total_score += 5; score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "5 / 10", "reason": f"${dollar_volume/1000000:.1f}M. 대금 발생."})
        else: score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "0 / 10", "reason": "거래대금 100만불 미만. 호가창 가짜 매물."})

        if vol_concentration >= 40: total_score += 5; score_details.append({"cat":"수급 (5점)","item": "거래량 집중도", "score": "5 / 5", "reason": f"최근 1시간 비중 {vol_concentration:.1f}%. 매수세 점화."})
        else: score_details.append({"cat":"수급 (5점)","item": "거래량 집중도", "score": "0 / 5", "reason": f"비중 {vol_concentration:.1f}%. 현재 매수세 소외 중."})

        if rvol >= 100: total_score += 5; score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "5 / 5", "reason": "과거 10일 평균 거래량을 돌파."})
        else: score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "0 / 5", "reason": "유의미한 거래량 폭발 없음."})

        if current_price > yest_high: total_score += 10; score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점)", "score": "10 / 10", "reason": f"전일 고점(${yest_high:.2f}) 돌파. 매물대 없음."})
        else: score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점)", "score": "0 / 10", "reason": f"전일 고점 아래 갇힌 갭. 매물 폭탄 주의."})

        if current_price >= fib_382: total_score += 10; score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "10 / 10", "reason": "38.2% 이내만 내어준 극강의 방어력."})
        elif current_price >= fib_618: total_score += 5; score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "5 / 10", "reason": "61.8% 방어선 지지 중. 관망 필요."})
        else: score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "0 / 10", "reason": "🚨 61.8% 붕괴. 데드캣 바운스 의심."})

        if current_price >= vwap: total_score += 5; score_details.append({"cat":"차트 (5점)","item": "VWAP (생명선)", "score": "5 / 5", "reason": f"당일 평균 단가(${vwap:.2f}) 위에서 지지."})
        else: score_details.append({"cat":"차트 (5점)","item": "VWAP (생명선)", "score": "0 / 5", "reason": "VWAP 붕괴. 투매 리스크 고조."})

        if higher_lows: total_score += 5; score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "5 / 5", "reason": "저점을 갱신하며 매물을 소화하는 패턴."})
        else: score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "0 / 5", "reason": "저점 하락 중. 지속적인 덤핑 발생."})

        if gap_win_rate is None: total_score += 10; score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": "1년 내 갭상승 이력 없음 (중립)."})
        elif gap_win_rate >= 50 and total_gaps >= 3: total_score += 10; score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": f"승률 {gap_win_rate:.1f}%. 신뢰도 높음."})
        else: score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "0 / 10", "reason": f"🚨 과거 덤핑 확률 {100-(gap_win_rate or 0):.1f}%. 상습 설거지."})

        if 0 < dist_to_sma200 <= 5.0: score_details.append({"cat":"매물대 (10점)","item": "장기 저항선(200일)", "score": "0 / 10", "reason": f"현재가 바로 위 200일선 위치. 매물대 직격."})
        else: total_score += 10; score_details.append({"cat":"매물대 (10점)","item": "장기 저항선(200일)", "score": "10 / 10", "reason": "200일선을 뚫었거나 멀리 있어 안전."})

        if total_cash > 5_000_000 or cash_ratio > 0.1: total_score += 5; score_details.append({"cat":"재무 (5점)","item": "기본 현금 흐름", "score": "5 / 5", "reason": "장부상 현금 흐름 양호."})
        else: score_details.append({"cat":"재무 (5점)","item": "기본 현금 흐름", "score": "0 / 5", "reason": "🚨 장부상 현금 부족 위험."})

        if turnover_ratio > 10: score_details.append({"cat":"과열도 (5점)","item": "유통 회전율", "score": "0 / 5", "reason": f"🚨 유통주식 {turnover_ratio:.1f}회전. 극단적 폭탄 돌리기."})
        elif turnover_ratio <= 3: total_score += 5; score_details.append({"cat":"과열도 (5점)","item": "유통 회전율", "score": "5 / 5", "reason": f"회전율 {turnover_ratio:.1f}회전. 매물 소화 양호."})

        # --- 🚀 [PRO 버전 신규 기법 스코어 가감점 반영] ---
        
        # 1. SEC 공시 리스크
        if offering_risk:
            total_score -= 30
            score_details.append({"cat":"🚨 PRO 리스크","item": "SEC S-3/424B 공시", "score": "-30 / 0", "reason": "최근 유상증자/오퍼링 폼 등록됨. 개장 직후 덤핑 확률 극강."})
        else:
            total_score += 5
            score_details.append({"cat":"🛡️ PRO 방어력","item": "SEC 악재 공시", "score": "+5 / 0", "reason": "최근 S-1/S-3 등 기습 신주 발행 등록 폼 없음."})

        # 2. 거래량 가속도 (Velocity)
        if vol_velocity_ratio >= 40:
            total_score += 10
            score_details.append({"cat":"🔥 PRO 수급","item": "개장 직전 가속도", "score": "+10 / 0", "reason": f"최근 30분에 거래량 {vol_velocity_ratio:.1f}% 집중. 개장 돌파 가능성 최상."})
        elif vol_velocity_ratio < 10 and today_volume > 1:
            total_score -= 10
            score_details.append({"cat":"🥶 PRO 수급","item": "개장 직전 가속도", "score": "-10 / 0", "reason": f"초반에만 터지고 최근 30분 비중 {vol_velocity_ratio:.1f}%. 개미 꼬시기 의심."})

        # 3. PM High & Bull Flag
        if bull_flag_formed:
            total_score += 10
            score_details.append({"cat":"🎯 PRO 차트","item": "PM High 수렴", "score": "+10 / 0", "reason": f"고점 대비 {-dist_to_pm_high:.1f}%. VWAP 위에서 에너지 응축 완료."})
        
        # 4. 공매도 숏스퀴즈 (CTB Proxy)
        if short_pct_float > 20:
            total_score += 15
            score_details.append({"cat":"🚀 PRO 스퀴즈","item": "숏 잔고 비율", "score": "+15 / 0", "reason": f"유통주 대비 공매도 {short_pct_float:.1f}%. 본장 개장 시 거대한 숏커버 빔 예상."})

        # 5. 뉴스 NLP 분석
        if news_score_added != 0:
            total_score += news_score_added
            prefix = "+" if news_score_added > 0 else ""
            score_details.append({"cat":"📰 PRO 재료","item": "뉴스 키워드 NLP", "score": f"{prefix}{news_score_added} / 0", "reason": news_nlp_reason})

        # 6. 테마/섹터 동반 상승
        if sympathy_score > 0:
            total_score += sympathy_score
            score_details.append({"cat":"👯 PRO 테마","item": "섹터 모멘텀", "score": f"+{sympathy_score} / 0", "reason": sympathy_reason})

        # 최종 등급 판정 (가점 포함 최대 150점 이상 가능)
        if total_score >= 110: tier = "🚀 우주 돌파 (SS급 대장)"
        elif total_score >= 85: tier = "👑 찐대장 (S급, 본장 돌파 유력)"
        elif total_score >= 65: tier = "🔥 A급 (단타/눌림목 유효)"
        elif total_score >= 45: tier = "🎯 B급 (관망/수급 확인)"
        elif total_score >= 30: tier = "🟡 C급 (주의 요망)"
        else: tier = "☠️ F급 (개미 무덤/설거지 확정)"

        # ------------------------------------------------
        # 🚨 핵심 결함 (레드 플래그 갱신)
        # ------------------------------------------------
        red_flags = []
        country = info.get('country', 'Unknown')
        employees = info.get('fullTimeEmployees', 0)
        rev_growth = info.get('revenueGrowth', None)

        if offering_risk:
            red_flags.append({
                "결함": "SEC 오퍼링 등록",
                "실체": "최근 S-3/424B 공시 존재. 세력이 프리마켓에서 띄워놓고 본장 개장과 동시에 회사 물량을 쏟아낼 수 있음.",
                "가이드": "🔴 절대 매수 금지 (또는 단타 시 칼손절)"
            })
        if current_price < 1.0:
            red_flags.append({
                "결함": "나스닥 $1 미달 규정",
                "실체": f"현재가 ${current_price:.2f}. 동전주 단골로 언제든 역분할 빔 가능성 보유.",
                "가이드": "🟡 당일 단타만 허용 (오버나잇 금지)"
            })
        if country in ['China', 'Hong Kong', 'Macau']:
            red_flags.append({
                "결함": "중국계/홍콩 기업",
                "실체": f"본사 위치: {country}. 잦은 테마 변경 및 기습 덤핑(무지성 세력주) 리스크.",
                "가이드": "🟡 급등 시 즉시 차익실현"
            })
        if 0 < employees < 20:
            red_flags.append({
                "결함": "소규모/유령회사 의심",
                "실체": f"정규직 직원 수 단 {employees}명. 실적보다는 순수 세력 수급으로만 움직임.",
                "가이드": "🟡 수급 깨지면 미련 없이 손절"
            })

        return {
            'ticker': ticker_symbol, 'price': current_price, 'gap': gap_pct,
            'dollar_vol': dollar_volume, 'score': total_score, 'tier': tier,
            'details': score_details, 'red_flags': red_flags
        }
    except Exception as e:
        return {"error": f"[{ticker_symbol}] 분석 중 오류 발생: {str(e)}"}

# --- [3] UI 화면 구성 (기존 유지) ---
st.title("🛡️ 동전주 정밀 몬스터 스캐너 (ULTIMATE Edition)")
st.markdown("수급, 차트, **SEC공시, NLP뉴스, 숏스퀴즈, 테마 모멘텀 등 6대 핵심 기법이 모두 추가된 완전체입니다.**")
st.markdown("---")

input_tickers = st.text_input("🔍 종목 입력 (쉼표 구분)", "EZRA, HYFM, WETO")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("Finnhub & yFinance 6단계 정밀 심층 스캐닝 중..."):
        results, errors = [], []
        for t in ticker_list:
            res = analyze_ticker_ultimate(t)
            if "error" in res: errors.append(res["error"])
            else: results.append(res)
    
    if errors:
        for err in errors: st.error(err)

    if results:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 궁극의 AI 스캐너 종합 랭킹")
        st.dataframe(
            df_res[['ticker', 'tier', 'score', 'price', 'gap', 'dollar_vol']].style.format({
                'price': '${:.2f}', 'gap': '{:+.2f}%', 'dollar_vol': '${:,.0f}'
            }), 
            use_container_width=True, hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔬 종목 심층 리포트")
        selected_ticker = st.selectbox("리포트를 확인할 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([7, 3])
        with c1:
            st.markdown(f"## {data['ticker']} <span style='font-size:18px;'>({data['tier']})</span>", unsafe_allow_html=True)
        with c2:
            score_color = "val-green" if data['score'] >= 85 else ("val-yellow" if data['score'] >= 45 else "val-red")
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 16px; color: #888;'>분석 총점</span><br><span class='{score_color}' style='font-size: 38px;'>{data['score']}</span></div>", unsafe_allow_html=True)
        
        # 1. 스코어 상세 표
        html_table = "<table class='score-table'><thead><tr><th style='width:15%'>카테고리</th><th style='width:20%'>평가 항목</th><th style='width:15%'>가/감점</th><th style='width:50%'>분석 근거 (Rationale)</th></tr></thead><tbody>"
        
        for item in data['details']:
            if "PRO" in item['cat']:
                if item['score'].startswith('-'): sc_html = f"<span class='val-red'>{item['score']}</span>"
                else: sc_html = f"<span class='val-blue'>{item['score']}</span>"
            else:
                if item['score'].startswith('0'): sc_html = f"<span class='val-red'>{item['score']}</span>"
                elif float(item['score'].split('/')[0].strip()) == float(item['score'].split('/')[1].strip()): sc_html = f"<span class='val-green'>{item['score']}</span>"
                else: sc_html = f"<span style='color:#ccc;'>{item['score']}</span>"
                
            html_table += f"<tr><td><b>{item['cat']}</b></td><td>{item['item']}</td><td>{sc_html}</td><td>{item['reason']}</td></tr>"
            
        html_table += "</tbody></table>"
        st.markdown(html_table, unsafe_allow_html=True)

        # 2. 핵심 결함 (참고용 블랙리스트)
        if data.get('red_flags'):
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### ⚠️ 동전주 기업 실체 및 치명적 리스크")
            
            rf_html = """
            <table class='rf-table'>
                <thead>
                    <tr>
                        <th style='width:20%'>특이 사항</th>
                        <th style='width:55%'>기업 실체 (Reality)</th>
                        <th style='width:25%'>매매 가이드</th>
                    </tr>
                </thead>
                <tbody>
            """
            for rf in data['red_flags']:
                # 오퍼링 등 심각한 악재는 빨간색 강조
                guide_color = "val-red" if "금지" in rf['가이드'] else "val-yellow"
                rf_html += f"<tr><td><b>{rf['결함']}</b></td><td>{rf['실체']}</td><td class='{guide_color}'>{rf['가이드']}</td></tr>"
                
            rf_html += "</tbody></table>"
            st.markdown(rf_html, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
