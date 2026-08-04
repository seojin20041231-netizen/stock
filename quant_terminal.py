import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time

# --- [1] 기본 설정 및 API 키 ---
FINNHUB_API_KEY = "d9nksmpr01qvumganiogd9nksmpr01qvumganip0"

st.set_page_config(page_title="동전주 몬스터 스캐너 (PRO Version)", layout="wide")

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

# --- [2] 메인 데이터 분석 엔진 ---
@st.cache_data(ttl=60)
def analyze_ticker_ultimate(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        score_details = []
        total_score = 0
        
        # ------------------------------------------------
        # 1. 일봉 데이터 (DNA, 매물대, 전일 고점 돌파)
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
        # 2. 1분봉 데이터 (Finnhub API 적용)
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
        
        # ------------------------------------------------
        # 3. 지표 및 리스크 계산
        # ------------------------------------------------
        float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
        market_cap = info.get('marketCap', 1)
        total_cash = info.get('totalCash', 0)
        cash_ratio = total_cash / market_cap if market_cap > 0 else 0
        has_news = len(ticker.news) > 0
        
        turnover_ratio = today_volume / float_shares if float_shares > 1 else 0
        cap_vs_vol_ratio = dollar_volume / market_cap if market_cap > 1 else 0

        # --- 🎯 [최종 100점 만점 스코어링 로직] ---
        
        # [카테고리 1: 수급 (총 20점)]
        if dollar_volume >= 5_000_000:
            total_score += 10
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "10 / 10", "reason": f"${dollar_volume/1000000:.1f}M 유입. 세력 개입 확인."})
        elif dollar_volume >= 1_000_000:
            total_score += 5
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "5 / 10", "reason": f"${dollar_volume/1000000:.1f}M. 대금 발생 (관찰 요망)."})
        else:
            score_details.append({"cat":"수급 (10점)","item": "실거래 대금", "score": "0 / 10", "reason": "거래대금 100만불 미만. 호가창 가짜 매물."})

        if vol_concentration >= 40:
            total_score += 5
            score_details.append({"cat":"수급 (5점)","item": "거래량 집중도", "score": "5 / 5", "reason": f"최근 1시간 비중 {vol_concentration:.1f}%. 매수세 점화."})
        elif vol_concentration == 0.0 and today_volume > 1:
            total_score += 3
            score_details.append({"cat":"수급 (5점)","item": "거래량 집중도", "score": "3 / 5", "reason": "프리마켓 1분봉 미제공으로 인한 기본 점수 부여."})
        else:
            score_details.append({"cat":"수급 (5점)","item": "거래량 집중도", "score": "0 / 5", "reason": f"비중 {vol_concentration:.1f}%. 현재 매수세 소외 중."})

        if rvol >= 100:
            total_score += 5
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "5 / 5", "reason": "과거 10일 평균 거래량을 돌파."})
        else:
            score_details.append({"cat":"수급 (5점)","item": "상대 거래량(RVOL)", "score": "0 / 5", "reason": "유의미한 거래량 폭발 없음."})

        # [카테고리 2: 차트 (총 30점)]
        if current_price > yest_high:
            total_score += 10
            score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점)", "score": "10 / 10", "reason": f"전일 고점(${yest_high:.2f}) 돌파. 매물대 없음."})
        else:
            score_details.append({"cat":"차트 (10점)","item": "열린 갭 (전일 고점)", "score": "0 / 10", "reason": f"전일 고점 아래 갇힌 갭. 매물 폭탄 주의."})

        if current_price >= fib_382:
            total_score += 10
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "10 / 10", "reason": "38.2% 이내만 내어준 극강의 방어력."})
        elif current_price >= fib_618:
            total_score += 5
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "5 / 10", "reason": "61.8% 방어선 지지 중. 관망 필요."})
        else:
            score_details.append({"cat":"차트 (10점)","item": "피보나치 눌림목", "score": "0 / 10", "reason": "🚨 61.8% 붕괴. 데드캣 바운스 의심."})

        if current_price >= vwap:
            total_score += 5
            score_details.append({"cat":"차트 (5점)","item": "VWAP (생명선)", "score": "5 / 5", "reason": f"당일 평균 단가(${vwap:.2f}) 위에서 지지."})
        else:
            score_details.append({"cat":"차트 (5점)","item": "VWAP (생명선)", "score": "0 / 5", "reason": "VWAP 붕괴. 투매 리스크 고조."})

        if higher_lows:
            total_score += 5
            score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "5 / 5", "reason": "저점을 갱신하며 매물을 소화하는 패턴."})
        else:
            score_details.append({"cat":"차트 (5점)","item": "계단식 저점 방어", "score": "0 / 5", "reason": "저점 하락 중. 지속적인 덤핑 발생."})

        # [카테고리 3: DNA/매물대 (총 20점)]
        if gap_win_rate is None:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": "1년 내 갭상승 이력 없음 (중립 호재)."})
        elif gap_win_rate >= 50 and total_gaps >= 3:
            total_score += 10
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "10 / 10", "reason": f"승률 {gap_win_rate:.1f}%. 신뢰도 높음."})
        elif gap_win_rate < 20 and total_gaps >= 3:
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "0 / 10", "reason": f"🚨 과거 덤핑 확률 {100-gap_win_rate:.1f}%. 상습 설거지."})
        else:
            total_score += 5
            score_details.append({"cat":"DNA (10점)","item": "과거 갭상승 승률", "score": "5 / 10", "reason": f"승률 {gap_win_rate:.1f}%. 본장 수급 확인."})

        if 0 < dist_to_sma200 <= 5.0:
            score_details.append({"cat":"매물대 (10점)","item": "장기 저항선(200일)", "score": "0 / 10", "reason": f"현재가 바로 위 200일선 위치. 매물대 직격."})
        else:
            total_score += 10
            score_details.append({"cat":"매물대 (10점)","item": "장기 저항선(200일)", "score": "10 / 10", "reason": "200일선을 뚫었거나 멀리 있어 안전."})

        # [카테고리 4: 재료 및 함정 방어 (총 30점)]
        if has_news:
            total_score += 10
            score_details.append({"cat":"재료 (10점)","item": "상승 명분 (뉴스)", "score": "10 / 10", "reason": "펌핑을 정당화할 뉴스 존재."})
        else:
            score_details.append({"cat":"재료 (10점)","item": "상승 명분 (뉴스)", "score": "0 / 10", "reason": "아무 뉴스 없음. 숏커버링이나 단순 장난."})

        if total_cash > 5_000_000 or cash_ratio > 0.1:
            total_score += 5
            score_details.append({"cat":"재무 (5점)","item": "오퍼링(유증) 방어", "score": "5 / 5", "reason": "현금 흐름 양호. 기습 유증 확률 낮음."})
        else:
            score_details.append({"cat":"재무 (5점)","item": "오퍼링(유증) 방어", "score": "0 / 5", "reason": "🚨 현금 부족. 장중 기습 유상증자 위험."})

        if gap_pct >= 200 and not has_news:
            score_details.append({"cat":"함정 (5점)","item": "역분할 착시 필터링", "score": "0 / 5", "reason": f"🚨 뉴스 없이 {gap_pct:.0f}% 폭등. 역분할 착시일 확률 99%."})
        else:
            total_score += 5
            score_details.append({"cat":"함정 (5점)","item": "역분할 착시 필터링", "score": "5 / 5", "reason": "역분할 단가 변경 징후 없음."})

        if turnover_ratio > 10:
            score_details.append({"cat":"과열도 (5점)","item": "유통 회전율", "score": "0 / 5", "reason": f"🚨 유통주식 {turnover_ratio:.1f}회전. 극단적 폭탄 돌리기."})
        elif turnover_ratio > 3:
            total_score += 3
            score_details.append({"cat":"과열도 (5점)","item": "유통 회전율", "score": "3 / 5", "reason": f"유통주식 {turnover_ratio:.1f}회전. 주도주 편입."})
        else:
            total_score += 5
            score_details.append({"cat":"과열도 (5점)","item": "유통 회전율", "score": "5 / 5", "reason": f"유통주식 {turnover_ratio:.1f}회전. 매물 소화 양호."})

        if market_cap < 50_000_000 and cap_vs_vol_ratio > 5:
            score_details.append({"cat":"과열도 (5점)","item": "시총 대비 대금 배수", "score": "0 / 5", "reason": f"🚨 초소형 시총에 대금이 {cap_vs_vol_ratio:.1f}배 터짐. 세력 설거지."})
        elif cap_vs_vol_ratio >= 1:
            total_score += 3
            score_details.append({"cat":"과열도 (5점)","item": "시총 대비 대금 배수", "score": "3 / 5", "reason": f"시총의 {cap_vs_vol_ratio:.1f}배 유동성 유입."})
        else:
            total_score += 5
            score_details.append({"cat":"과열도 (5점)","item": "시총 대비 대금 배수", "score": "5 / 5", "reason": "시총 대비 대금 비율 안정적."})

        # 최종 판정
        if total_score >= 85: tier = "👑 찐대장 (수급/차트 최상급)"
        elif total_score >= 70: tier = "🔥 S급 (단타 유효)"
        elif total_score >= 50: tier = "🎯 A급 (눌림목 관망)"
        elif total_score >= 35: tier = "🟡 B급 (주의)"
        else: tier = "☠️ F급 (설거지 위험)"

        # ------------------------------------------------
        # 🚨 [신규] 핵심 결함 (동전주 특성 참고용 표)
        # ------------------------------------------------
        red_flags = []
        country = info.get('country', 'Unknown')
        employees = info.get('fullTimeEmployees', 0)
        rev_growth = info.get('revenueGrowth', None)

        if current_price < 1.0:
            red_flags.append({
                "결함": "나스닥 $1 미달 규정",
                "실체": f"현재가 ${current_price:.2f}. 동전주 단골 손님으로 언제든 역분할 빔 가능성 보유.",
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

        if rev_growth is not None and rev_growth < -0.3:
            red_flags.append({
                "결함": "최근 매출 역성장",
                "실체": f"분기 매출 전년 대비 {rev_growth*100:.1f}% 감소. 기본 재무 상태 불량.",
                "가이드": "🟡 주말/장기 보유 절대 불가"
            })

        return {
            'ticker': ticker_symbol, 'price': current_price, 'gap': gap_pct,
            'dollar_vol': dollar_volume, 'score': total_score, 'tier': tier,
            'details': score_details, 'red_flags': red_flags
        }
    except Exception as e:
        return {"error": f"[{ticker_symbol}] 분석 중 오류 발생: {str(e)}"}

# --- [3] UI 화면 구성 ---
st.title("🛡️ 동전주 정밀 몬스터 스캐너 (PRO Edition)")
st.markdown("수급과 차트로 점수를 매기고, **동전주 고유의 리스크(역분할, 유령회사 등)를 참고용 표로 투명하게 보여줍니다.**")
st.markdown("---")

input_tickers = st.text_input("🔍 종목 입력 (쉼표 구분)", "EZRA, HYFM, WETO")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("Finnhub & yFinance 정밀 스캐닝 중..."):
        results, errors = [], []
        for t in ticker_list:
            res = analyze_ticker_ultimate(t)
            if "error" in res: errors.append(res["error"])
            else: results.append(res)
    
    if errors:
        for err in errors: st.error(err)

    if results:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 수급 & 차트 점수 랭킹")
        st.dataframe(
            df_res[['ticker', 'tier', 'score', 'price', 'gap', 'dollar_vol']].style.format({
                'price': '${:.2f}', 'gap': '{:+.2f}%', 'dollar_vol': '${:,.0f}'
            }), 
            use_container_width=True, hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔬 종목 정밀 리포트")
        selected_ticker = st.selectbox("리포트를 확인할 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([7, 3])
        with c1:
            st.markdown(f"## {data['ticker']} <span style='font-size:18px;'>({data['tier']})</span>", unsafe_allow_html=True)
        with c2:
            score_color = "val-green" if data['score'] >= 70 else ("val-yellow" if data['score'] >= 50 else "val-red")
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 16px; color: #888;'>분석 점수</span><br><span class='{score_color}' style='font-size: 38px;'>{data['score']} / 100</span></div>", unsafe_allow_html=True)
        
        # 1. 스코어 상세 표
        html_table = "<table class='score-table'><thead><tr><th style='width:15%'>카테고리</th><th style='width:20%'>평가 항목</th><th style='width:12%'>점수</th><th style='width:53%'>분석 근거 (Rationale)</th></tr></thead><tbody>"
        
        for item in data['details']:
            if item['score'].startswith('0'): sc_html = f"<span class='val-red'>{item['score']}</span>"
            elif float(item['score'].split('/')[0].strip()) == float(item['score'].split('/')[1].strip()): sc_html = f"<span class='val-green'>{item['score']}</span>"
            else: sc_html = f"<span class='val-blue'>{item['score']}</span>"
                
            html_table += f"<tr><td><b>{item['cat']}</b></td><td>{item['item']}</td><td>{sc_html}</td><td>{item['reason']}</td></tr>"
            
        html_table += "</tbody></table>"
        st.markdown(html_table, unsafe_allow_html=True)

        # 2. 핵심 결함 (참고용 블랙리스트)
        if data.get('red_flags'):
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### ⚠️ 동전주 기업 실체 및 참고 리스크")
            
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
                rf_html += f"<tr><td><b>{rf['결함']}</b></td><td>{rf['실체']}</td><td class='val-yellow'>{rf['가이드']}</td></tr>"
                
            rf_html += "</tbody></table>"
            st.markdown(rf_html, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
