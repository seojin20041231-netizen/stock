import streamlit as st
import finnhub
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# --- [1] 기본 설정 및 API 키 세팅 ---
st.set_page_config(page_title="프리마켓 갭앤고 대장주 스캐너", layout="wide")

# 발급받은 Finnhub API Key 
FINNHUB_API_KEY = "d9nkph1r01qvumgan3egd9nkph1r01qvumgan3f0"
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 22px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
    
    .badge-s { background-color: #1A3A2A; color: #00E676; padding: 6px 14px; border-radius: 20px; font-size: 15px; font-weight: bold; border: 1px solid #00E676;}
    .badge-a { background-color: #193D24; color: #4CAF50; padding: 6px 14px; border-radius: 20px; font-size: 15px; font-weight: bold; border: 1px solid #4CAF50;}
    .badge-b { background-color: #4A3519; color: #FFB020; padding: 6px 14px; border-radius: 20px; font-size: 15px; font-weight: bold; border: 1px solid #FFB020;}
    .badge-f { background-color: #4A1919; color: #FF5252; padding: 6px 14px; border-radius: 20px; font-size: 15px; font-weight: bold; border: 1px solid #FF5252;}
    
    .pill { padding: 4px 10px; border-radius: 6px; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px; font-weight: 500; }
    .pill-blue { background-color: rgba(33, 150, 243, 0.15); color: #2196F3; border: 1px solid #2196F3; }
    .pill-green { background-color: rgba(76, 175, 80, 0.15); color: #4CAF50; border: 1px solid #4CAF50; }
    .pill-orange { background-color: rgba(255, 176, 32, 0.15); color: #FFB020; border: 1px solid #FFB020; }
    .pill-red { background-color: rgba(255, 82, 82, 0.15); color: #FF5252; border: 1px solid #FF5252; }
    .pill-purple { background-color: rgba(156, 39, 176, 0.15); color: #E040FB; border: 1px solid #E040FB; }

    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 15px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
</style>
""", unsafe_allow_html=True)

# --- [2] 악재/호재 키워드 필터 ---
BAD_KEYWORDS = [
    'offering', 'direct offering', 'public offering', 'reverse split', 
    'delist', 'bankruptcy', 'chapter 11', 'warrant', 's-1', 's-3', 
    '424b5', 'atm', 'at-the-market', 'dilution', 'shelf', 'sell'
]
GOOD_KEYWORDS = [
    'fda', 'patent', 'earnings', 'partnership', 'agreement', 
    'approval', 'merger', 'acquisition', 'clinical', 'contract', 'buyback'
]

# --- [3] Finnhub 데이터 수집 및 분석 엔진 ---
@st.cache_data(ttl=60)
def analyze_ticker_finnhub(ticker_symbol):
    try:
        end_ts = int(time.time())
        start_ts_1m = end_ts - (24 * 3600)  # 최근 24시간
        start_ts_daily = end_ts - (365 * 24 * 3600) # 최근 1년 (이평선용)
        
        # 1. 현재가 및 전일종가 (Quote)
        quote = finnhub_client.quote(ticker_symbol)
        if quote['c'] == 0:
            return None
            
        current_price = quote['c']
        prev_close = quote['pc']
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0

        # 2. 기업 정보 (유통주식수 및 Float 추정)
        # Finnhub는 기본적으로 발행주식수(shareOutstanding)를 제공합니다 (단위: 백만 주)
        profile = finnhub_client.company_profile2(symbol=ticker_symbol)
        float_shares = profile.get('shareOutstanding', 0) * 1_000_000
        
        # 3. 1분봉 데이터 긁어오기 (PMH, PML, 당일 거래량, VWAP)
        res_1m = finnhub_client.stock_candles(ticker_symbol, '1', start_ts_1m, end_ts)
        
        today_volume = 0
        vwap, pm_high, pm_low, dist_to_pmh = current_price, current_price, current_price, 0
        
        if res_1m.get('s') == 'ok':
            df_1m = pd.DataFrame({
                'Open': res_1m['o'], 'High': res_1m['h'], 'Low': res_1m['l'], 
                'Close': res_1m['c'], 'Volume': res_1m['v'], 'Time': res_1m['t']
            })
            # 장 시작 전 대략 12시간 내의 데이터를 오늘 프리마켓 데이터로 간주
            cutoff_time = df_1m['Time'].max() - (12 * 3600)
            df_today = df_1m[df_1m['Time'] >= cutoff_time].copy()
            
            if not df_today.empty:
                today_volume = df_today['Volume'].sum()
                pm_high = df_today['High'].max()
                pm_low = df_today['Low'].min()
                dist_to_pmh = ((pm_high - current_price) / current_price * 100) if current_price else 0
                
                # VWAP 계산
                tp = (df_today['High'] + df_today['Low'] + df_today['Close']) / 3
                cum_v = df_today['Volume'].cumsum()
                vwap_series = (tp * df_today['Volume']).cumsum() / np.where(cum_v == 0, 1, cum_v)
                vwap = vwap_series.iloc[-1]
                
        # 4. 일봉 데이터 (SMA50, SMA200, 평소 거래량)
        res_daily = finnhub_client.stock_candles(ticker_symbol, 'D', start_ts_daily, end_ts)
        is_above_smas = False
        rvol = 0
        
        if res_daily.get('s') == 'ok':
            df_daily = pd.DataFrame({'Close': res_daily['c'], 'Volume': res_daily['v']})
            if len(df_daily) >= 50:
                sma50 = df_daily['Close'].rolling(50).mean().iloc[-1]
                sma200 = df_daily['Close'].rolling(200).mean().iloc[-1] if len(df_daily) >= 200 else 0
                is_above_smas = (current_price > sma50) and (current_price > sma200 or sma200 == 0)
                
            if len(df_daily) >= 2:
                avg_daily_volume = df_daily['Volume'].iloc[:-1].tail(20).mean() # 최근 20일 평균
                rvol = (today_volume / avg_daily_volume) if avg_daily_volume else 0

        # 회전율 계산
        turnover_ratio = (today_volume / float_shares) if float_shares > 0 else 0

        # 5. 뉴스 센티멘트 분석 (최근 2일)
        start_date_news = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        end_date_news = datetime.now().strftime('%Y-%m-%d')
        news_items = finnhub_client.company_news(ticker_symbol, _from=start_date_news, to=end_date_news)
        
        has_today_news = len(news_items) > 0
        news_sentiment = "NEUTRAL"
        
        if has_today_news:
            for n in news_items:
                title_lower = n.get('headline', '').lower()
                if any(kw in title_lower for kw in BAD_KEYWORDS):
                    news_sentiment = "BAD"
                    break
                elif any(kw in title_lower for kw in GOOD_KEYWORDS):
                    news_sentiment = "GOOD"

        # --- 🎯 [정밀 스코어링 시스템] ---
        score = 0
        if news_sentiment == "BAD":
            score = 0
        else:
            if news_sentiment == "GOOD": score += 15
            
            if today_volume >= 1_000_000: score += 15
            elif today_volume >= 500_000: score += 5
            
            if turnover_ratio >= 1.0: score += 20
            elif turnover_ratio >= 0.5: score += 10
            
            if rvol >= 2.0: score += 10
            
            if current_price >= vwap: score += 15
            if dist_to_pmh <= 3.0: score += 15
            if is_above_smas: score += 10
            if 10 <= change_pct <= 150: score += 5

        # 등급 판정
        if news_sentiment == "BAD" or score < 40 or current_price < (vwap * 0.98): # vwap보다 확 밀리면 탈락
            tier = "F급 (절대금지)"
        elif score >= 80:
            tier = "S급 (진대장주)"
        elif score >= 60:
            tier = "A급 (돌파셋업)"
        else:
            tier = "B급 (관망권장)"

        return {
            'ticker': ticker_symbol, 'price': current_price, 'change': change_pct,
            'float': float_shares, 'volume': today_volume, 'turnover': turnover_ratio,
            'rvol': rvol, 'vwap': vwap, 'pm_high': pm_high, 'pm_low': pm_low,
            'dist_pmh': dist_to_pmh, 'news_sentiment': news_sentiment,
            'has_news': has_today_news, 'is_above_smas': is_above_smas, 'score': score, 'tier': tier
        }
    except Exception as e:
        return None

# --- [4] UI 렌더링 ---
st.title("🚀 미국 프리마켓 대장주 판독기 (Finnhub 실시간)")
st.markdown("<span style='font-size: 13px; color: #888;'>목적: 9:30 AM 본장 슛팅 타겟 서치 | 소스: Finnhub Real-time API</span>", unsafe_allow_html=True)
st.markdown("---")

input_tickers = st.text_input("🔍 프리마켓 급등 종목들을 입력하세요 (쉼표로 구분)", "FFIE, BBAI, HOLO, GME, AMC")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("Finnhub 1분봉 및 뉴스 공시 실시간 분석 중..."):
        results = []
        for t in ticker_list:
            res = analyze_ticker_finnhub(t)
            if res:
                results.append(res)
    
    if not results:
        st.error("종목 데이터를 불러올 수 없습니다. 티커를 확인하세요.")
    else:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 대장주 실시간 순위 리더보드")
        display_df = pd.DataFrame({
            '순위': [f"#{i+1}" for i in range(len(df_res))],
            '티커': df_res['ticker'],
            '판정 등급': df_res['tier'],
            '점수': df_res['score'].apply(lambda x: f"{x}점"),
            '현재가': df_res['price'].apply(lambda x: f"${x:.2f}"),
            'Gap 상승률': df_res['change'].apply(lambda x: f"{x:+.1f}%"),
            'Pre 거래량': df_res['volume'].apply(lambda x: f"{int(x/1000):,}K" if x < 1000000 else f"{x/1000000:.2f}M"),
            'Float 회전율': df_res['turnover'].apply(lambda x: f"{x*100:.1f}%"),
            'VWAP 위': df_res.apply(lambda r: "✅" if r['price'] >= r['vwap'] else "❌", axis=1)
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown("<br>", unsafe_allow_html=True)

        st.subheader("🎯 선택 종목 심층 디테일 분석")
        selected_ticker = st.selectbox("상세 분석할 종목 선택", df_res['ticker'].tolist())
        data = next(item for item in results if item['ticker'] == selected_ticker)
        
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([6, 4])
        with c1:
            st.markdown(f"### {data['ticker']}")
        with c2:
            p_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{p_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
        
        tags_html = ""
        if data['tier'] == "S급 (진대장주)": tags_html += '<span class="badge-s">🔥 S급 진대장주 Target</span> '
        elif data['tier'] == "A급 (돌파셋업)": tags_html += '<span class="badge-a">🚀 A급 돌파 셋업</span> '
        elif data['tier'] == "B급 (관망권장)": tags_html += '<span class="badge-b">🟡 B급 관망 권장</span> '
        else: tags_html += '<span class="badge-f">☠️ F급 매매 금지</span> '
        
        if data['turnover'] >= 1.0: tags_html += '<span class="pill pill-purple">⚡ 유통물량 100%+ 회전</span>'
        if data['volume'] >= 1_000_000: tags_html += '<span class="pill pill-green">🌊 거래량 100만주 달성</span>'
        if data['dist_pmh'] <= 3.0: tags_html += '<span class="pill pill-green">⚔️ PMH 3% 이내 밀착</span>'
        if data['is_above_smas']: tags_html += '<span class="pill pill-blue">📈 매물대 상방 돌파 (Clean Chart)</span>'
        
        if data['has_news']:
            if data['news_sentiment'] == "BAD": tags_html += '<span class="pill pill-red">🚨 악재/유상증자 공시 감지</span>'
            elif data['news_sentiment'] == "GOOD": tags_html += '<span class="pill pill-blue">📰 호재 료 장착</span>'

        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if data['news_sentiment'] == "BAD":
            v_color, v_bg = "#FF1744", "rgba(255, 23, 68, 0.15)"
            v_title, v_desc = "☠️ 악재 펌핑 / 오퍼링 위험", "장 열리자마자 덤핑 나옵니다. 매수 절대 금지."
        elif data['price'] < data['vwap']:
            v_color, v_bg = "#FF5252", "rgba(255, 82, 82, 0.15)"
            v_title, v_desc = "🚨 세력 이탈 (VWAP 하방)", "생명선(VWAP) 아래입니다. 본장 패닉셀 조심하세요."
        elif data['tier'] in ["S급 (진대장주)", "A급 (돌파셋업)"]:
            v_color, v_bg = "#00E676", "rgba(0, 230, 118, 0.15)"
            v_title, v_desc = f"🔥 {data['tier']} - 돌파 셋업 완료", "PMH와 거래량이 받쳐줍니다. 오픈 즉시 전고점(PMH) 돌파시 슈팅 나옵니다."
        else:
            v_color, v_bg = "#FFB020", "rgba(255, 176, 32, 0.15)"
            v_title, v_desc = "🤔 조건 미달 (관망)", "수급이 애매합니다. 무리한 진입을 피하세요."

        st.markdown(f"""
        <div style="border: 2px solid {v_color}; background-color: {v_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {v_color}; margin-top: 0px; margin-bottom: 5px;">{v_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{v_desc}</span>
        </div>
        """, unsafe_allow_html=True)

        float_str = f"{int(data['float']/1_000_000):,}M" if data['float'] > 0 else "N/A"
        vol_str = f"{data['volume']/1_000_000:.2f}M" if data['volume'] >= 1_000_000 else f"{int(data['volume']/1000):,}K"
        
        g1, g2, g3 = st.columns(3)
        with g1:
            st.markdown("<div class='metric-label'>Float 회전율 / RVOL</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{data['turnover']*100:.1f}% / {data['rvol']:.1f}x</div>", unsafe_allow_html=True)
        with g2:
            st.markdown("<div class='metric-label'>PM 누적 거래량 / 발행주식수</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{vol_str} / {float_str}</div>", unsafe_allow_html=True)
        with g3:
            st.markdown("<div class='metric-label'>PMH까지 거리</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{data['dist_pmh']:.1f}%</div>", unsafe_allow_html=True)

        st.markdown("<br>**🎯 초단타 핵심 대응 레벨**", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown("<div class='metric-label'>생명선 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${data['vwap']:.2f}</div>", unsafe_allow_html=True)
        with m2:
            st.markdown("<div class='metric-label'>1차 돌파 타겟 (PMH)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${data['pm_high']:.2f}</div>", unsafe_allow_html=True)
        with m3:
            st.markdown("<div class='metric-label'>손절 기준선 (PML)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${data['pm_low']:.2f}</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
