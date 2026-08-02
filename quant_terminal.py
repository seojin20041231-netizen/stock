import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 프리마켓 대장주 판독기 Max", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 20px; border-radius: 12px; border: 1px solid #333; }
    .badge-red { background-color: #4A1919; color: #FF5252; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FF5252;}
    .badge-orange { background-color: #4A3519; color: #FFB020; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FFB020;}
    .badge-green { background-color: #193D24; color: #4CAF50; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #4CAF50;}
    
    .pill-gray { background-color: #2D2D2D; color: #A0A0A0; padding: 4px 10px; border-radius: 6px; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-blue { background-color: rgba(33, 150, 243, 0.1); color: #2196F3; padding: 4px 10px; border-radius: 6px; border: 1px solid #2196F3; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-orange { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 4px 10px; border-radius: 6px; border: 1px solid #FFB020; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-green { background-color: rgba(76, 175, 80, 0.1); color: #4CAF50; padding: 4px 10px; border-radius: 6px; border: 1px solid #4CAF50; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-red { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 4px 10px; border-radius: 6px; border: 1px solid #FF5252; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    
    .warning-block { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-top: 6px; border: 1px solid rgba(255, 82, 82, 0.3);}
    .squeeze-block { background-color: rgba(33, 150, 243, 0.1); color: #2196F3; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-top: 6px; border: 1px solid rgba(33, 150, 243, 0.3);}
    
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 14px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
    .news-box { background-color: #263238; padding: 15px; border-radius: 8px; border-left: 4px solid #00BCD4; margin-top: 15px;}
    .bottom-warning { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 10px; border-radius: 8px; font-size: 12px; text-align: center; margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

BAD_KEYWORDS = ['offering', 'direct offering', 'public offering', 'reverse split', 'delist', 'bankruptcy', 'chapter 11', 'lawsuit', 'subpoena']
GOOD_KEYWORDS = ['fda', 'patent', 'earnings', 'partnership', 'agreement', 'approval', 'merger', 'acquisition', 'clinical', 'contract']

# RSI 계산 함수 추가
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    hist_5m = ticker.history(period="5d", interval="5m", prepost=True)
    hist_daily = ticker.history(period="6mo", interval="1d")
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    if hist_5m.empty or current_price == 0:
        return None

    last_day = hist_5m.index[-1].date()
    today_hist = hist_5m[hist_5m.index.date == last_day].copy()
    
    prev_close = info.get('previousClose', 0.0)
    market_cap = info.get('marketCap', 0)
    float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
    high_52w = info.get('fiftyTwoWeekHigh', 0.0)
    short_pct = info.get('shortPercentOfFloat', 0)

    # 1. 강력한 악성 매물대
    past_daily = hist_daily[hist_daily.index.date < last_day]
    if not past_daily.empty:
        max_vol_idx = past_daily['Volume'].idxmax()
        heavy_resistance = past_daily.loc[max_vol_idx, 'High']
        recent_high = past_daily['High'].tail(20).max()
    else:
        heavy_resistance = current_price
        recent_high = current_price

    # 2. 당일 분봉 기반 심층 분석 (VWAP, OBV, 매도 윗꼬리, RSI, PMH)
    is_rising = False
    vwap = current_price
    intra_obv_status = "데이터 부족"
    intra_obv_color = "#A0A0A0"
    selling_pressure_wicks = 0
    current_rsi = 50
    pm_high = current_price
    
    if not today_hist.empty:
        today_volume = today_hist['Volume'].sum()
        v = today_hist['Volume']
        tp = (today_hist['High'] + today_hist['Low'] + today_hist['Close']) / 3
        vwap_series = (tp * v).cumsum() / v.cumsum()
        vwap = vvwap = vwap_series.iloc[-1] if not vwap_series.empty else current_price
        
        # [신규] 프리마켓 최고점 (PMH) 추적
        pm_high = today_hist['High'].max()
        
        # [신규] RSI 계산
        if len(today_hist) > 14:
            today_hist['RSI'] = calculate_rsi(today_hist['Close'])
            current_rsi = today_hist['RSI'].iloc[-1]

        # [신규] 윗꼬리(Wick) 매도 압력 분석
        today_hist['Upper_Wick'] = today_hist['High'] - today_hist[['Open', 'Close']].max(axis=1)
        today_hist['Body'] = (today_hist['Open'] - today_hist['Close']).abs()
        
        # 최근 5개 봉 중 윗꼬리가 몸통보다 1.5배 이상 긴 캔들 개수 파악 (악성 매물 출회 징후)
        recent_5_candles = today_hist.tail(5)
        selling_pressure_wicks = len(recent_5_candles[recent_5_candles['Upper_Wick'] > (recent_5_candles['Body'] * 1.5)])
        
        today_hist['EMA9'] = today_hist['Close'].ewm(span=9, adjust=False).mean()
        today_hist['EMA20'] = today_hist['Close'].ewm(span=20, adjust=False).mean()
        
        if len(today_hist) >= 20:
            last_close = today_hist['Close'].iloc[-1]
            last_ema9 = today_hist['EMA9'].iloc[-1]
            last_ema20 = today_hist['EMA20'].iloc[-1]
            if (last_close > vwap) and (last_ema9 > last_ema20):
                is_rising = True

        change = today_hist['Close'].diff()
        direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
        today_hist['Intra_OBV'] = (today_hist['Volume'] * direction).cumsum()
        
        if len(today_hist) >= 3:
            if today_hist['Intra_OBV'].iloc[-1] > 0:
                intra_obv_status = "매수세 압도(진성 펌핑)"
                intra_obv_color = "#4CAF50"
            else:
                intra_obv_status = "매도세 우위(설거지)"
                intra_obv_color = "#FF5252"
    else:
        today_volume = 0

    # 3. 뉴스 스캐너
    news_items = ticker.news
    has_today_news = False
    news_sentiment = "NEUTRAL"
    recent_news_titles = []
    current_time = time.time()
    
    for n in news_items:
        if current_time - n.get('providerPublishTime', 0) < 86400:
            has_today_news = True
            title = n.get('title', '제목 없음')
            recent_news_titles.append(title)
            title_lower = title.lower()
            if any(kw in title_lower for kw in BAD_KEYWORDS):
                news_sentiment = "BAD"
            elif any(kw in title_lower for kw in GOOD_KEYWORDS) and news_sentiment != "BAD":
                news_sentiment = "GOOD"

    vol_avg_20 = past_daily['Volume'].tail(20).mean() if not past_daily.empty else 1
    vol_avg_20 = vol_avg_20 if vol_avg_20 > 0 else 1
    vol_mult_20d = today_volume / vol_avg_20

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = today_volume / float_shares if float_shares else 0
    drop_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w else 0

    warnings = []
    messages = []
    
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (나스닥 상장유지 요건 위험 / S-3 오퍼링 가능성)")
    if market_cap > 0 and market_cap < 10_000_000: warnings.append(f"⚠️ 초소형 시총 ${(market_cap/1000000):.1f}M (세력 장난질 극대화)")
    if drop_from_high < -80: warnings.append(f"⚠️ 52주 고점 대비 {abs(drop_from_high):.0f}% 폭락 (위로 시체의 산 가득)")
    if change_pct > 150: warnings.append("⚠️ 극단적 갭상승 (150%+): 본장 시작 시 강력한 차익실현(Fade) 위험")
    
    if short_pct is not None and short_pct > 0.10: 
        messages.append(f"🔥 유통주식 내 공매도 비율(Short Float) {(short_pct*100):.1f}%! 숏스퀴즈 연료 장전")

    return {
        'price': current_price, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'pm_volume': today_volume,
        'turnover': turnover_rate, 'warnings': warnings, 'messages': messages,
        'vwap': vwap, 'has_news': has_today_news, 'news_sentiment': news_sentiment,
        'news_titles': recent_news_titles[:2], 'vol_mult_20d': vol_mult_20d,
        'intra_obv_status': intra_obv_status, 'intra_obv_color': intra_obv_color,
        'recent_high': recent_high, 'heavy_resistance': heavy_resistance, 
        'is_rising': is_rising, 'pm_high': pm_high, 'current_rsi': current_rsi,
        'selling_wicks': selling_pressure_wicks
    }

# --- [3] UI 렌더링 ---
st.title("🦅 프리마켓 찐 대장주 감별기 Max")
st.markdown("<span style='font-size: 13px; color: #888;'>*yfinance 데이터 기반 (최종 매매 전 HTS/MTS에서 Float 및 악재 여부 교차검증 필수)</span>", unsafe_allow_html=True)
target_ticker = st.text_input("프리마켓 급등 종목 티커 입력 (예: CISS, FFIE)", "FFIE").upper()

if target_ticker:
    with st.spinner("호가창 수급, 캔들 패턴(매도 꼬리), PMH 돌파 여부 판독 중..."):
        data = get_stock_data(target_ticker)
        
    if data is None:
        st.error("데이터를 불러올 수 없습니다. 티커를 다시 확인해 주세요.")
    else:
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        # [헤더]
        col1, col2 = st.columns([6, 4])
        with col1:
            st.markdown(f"### {target_ticker} <span style='font-size: 14px; color: #888;'>NASDAQ</span>", unsafe_allow_html=True)
        with col2:
            price_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>당일 등락: {data['change']:.2f}%</div>", unsafe_allow_html=True)
        
        # 🏷️ [동적 상태 태그 (Pill)]
        tags_html = ""
        
        if data['has_news']: 
            if data['news_sentiment'] == "BAD": tags_html += '<span class="pill-red">🚨 치명적 악재 감지</span>'
            elif data['news_sentiment'] == "GOOD": tags_html += '<span class="pill-blue">📰 확실한 호재 키워드</span>'
            else: tags_html += '<span class="pill-blue">📰 당일 뉴스/공시 </span>'
        else: 
            tags_html += '<span class="pill-gray">텅 빈 깡통 (무명분 펌핑)</span>'
        
        if data['is_rising']: tags_html += '<span class="pill-green">🔥 정배열 진행중</span>'
        if data['selling_wicks'] >= 2: tags_html += f'<span class="pill-red">📉 매도 윗꼬리 {data["selling_wicks"]}회 포착(세력 이탈중)</span>'
        if data['current_rsi'] > 80: tags_html += '<span class="pill-red">🔥 극단적 과매수(RSI 80+)</span>'
        if data['turnover'] > 2.0: tags_html += f'<span class="pill-orange">⚠️ 유통주식 {data["turnover"]:.1f}회전</span>'
        
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [프리마켓 데스 필터 심화 로직] 
        is_under_vwap = data['price'] < data['vwap']
        is_low_pm_vol = data['pm_volume'] < 1_000_000 
        distance_to_pmh = ((data['pm_high'] - data['price']) / data['price']) * 100

        if data['news_sentiment'] == "BAD":
            verdict_color = "#FF1744"; verdict_bg = "rgba(255, 23, 68, 0.15)"
            verdict_title = "☠️ 절대 접근 금지 (치명적 악재)"
            verdict_desc = "유상증자(Offering), 상폐 경고 등 악재가 있습니다. 절대 하따(하한가 따라잡기) 금지."
            status_badge = '<span class="badge-red">🔴 매매 금지</span>'
        elif is_under_vwap and (is_low_pm_vol or data['selling_wicks'] >= 3):
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"
            verdict_title = "🚨 전형적인 가짜 펌핑 (설거지 진행중)"
            verdict_desc = "VWAP 이탈 + 심한 매도 윗꼬리가 출현했습니다. 이미 세력이 물량을 떠넘기고 있습니다."
            status_badge = '<span class="badge-red">🔴 회피 (데드캣)</span>'
        elif is_under_vwap:
            verdict_color = "#FFB020"; verdict_bg = "rgba(255, 176, 32, 0.15)"
            verdict_title = "⚠️ 관망 (투심 꺾임, 돌파 대기)"
            verdict_desc = "평단가(VWAP) 아래로 밀렸습니다. 거래량을 동반하며 VWAP을 재돌파하기 전까진 진입 금지."
            status_badge = '<span class="badge-orange">🟡 주의 (돌파 대기)</span>'
        elif data['price'] > data['vwap'] and data['current_rsi'] > 85:
            verdict_color = "#FF9800"; verdict_bg = "rgba(255, 152, 0, 0.15)"
            verdict_title = "⚠️ 신규 진입 주의 (극단적 고점)"
            verdict_desc = "추세는 좋으나 단기 RSI가 너무 높습니다. 지금 진입하면 고점에 물릴 확률이 매우 높습니다. 눌림목을 기다리세요."
            status_badge = '<span class="badge-orange">🟡 눌림 대기</span>'
        elif not is_low_pm_vol and data['has_news'] and not is_under_vwap and data['is_rising']:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"
            verdict_title = "🔥 찐 대장주 조건 완벽 충족"
            verdict_desc = "호재 + 거래량 + VWAP 지지 + 매수세 우위. 본장에서도 시세를 줄 확률이 높습니다."
            status_badge = '<span class="badge-green">🔵 찐 대장주 (매수 고려)</span>'
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "차트나 수급 중 하나가 비어있습니다. 확실한 A급 종목이 아니라면 굳이 리스크를 질 필요 없습니다."
            status_badge = '<span class="badge-orange">🟡 주의 (조건 미달)</span>'

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(status_badge, unsafe_allow_html=True)
        
        for msg in data['messages']:
            st.markdown(f"<div class='squeeze-block'>{msg}</div>", unsafe_allow_html=True)
        for warning in data['warnings']:
            st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # 📊 [데이터 그리드 1] 인트라데이 수급 & 모멘텀
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>당일 프리 거래량</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>{int(data['pm_volume']/1000):,} K</div>", unsafe_allow_html=True)
        with g1_c2:
            st.markdown("<div class='metric-label'>단기 과매수(RSI)</div>", unsafe_allow_html=True)
            rsi_color = "val-red" if data['current_rsi'] > 75 else "val-green"
            st.markdown(f"<div class='metric-val {rsi_color}'>{data['current_rsi']:.1f}</div>", unsafe_allow_html=True)
        with g1_c3:
            st.markdown("<div class='metric-label'>PMH(최고점) 거리</div>", unsafe_allow_html=True)
            pmh_color = "val-green" if distance_to_pmh < 5 else "val-orange"
            st.markdown(f"<div class='metric-val {pmh_color}'>-{distance_to_pmh:.1f}%</div>", unsafe_allow_html=True)
        with g1_c4:
            st.markdown("<div class='metric-label'>당일 분봉 수급 (OBV)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color: {data['intra_obv_color']};'>{data['intra_obv_status']}</div>", unsafe_allow_html=True)

        # 📰 [당일 호재(Catalyst) 판독 상자]
        if data['news_sentiment'] == "BAD": news_border = "#FF1744"
        elif data['news_sentiment'] == "GOOD": news_border = "#4CAF50"
        elif data['has_news']: news_border = "#00BCD4"
        else: news_border = "#546E7A"

        news_title_str = "<br>".join([f"- {t}" for t in data['news_titles']]) if data['has_news'] else "24시간 내 올라온 영문 뉴스나 공시(SEC)가 없습니다."
        
        st.markdown(f"""
        <div class="news-box" style="border-left-color: {news_border};">
            <h5 style="margin-top: 0px; margin-bottom: 10px; color: #E0F7FA;">📰 당일 상승 명분 (Catalyst) 체크</h5>
            <div style="font-size: 13px; color: #B0BEC5;">{news_title_str}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 🛠️ [데이터 그리드 2] 당일 매매 레벨 (+ 최대 거래량 시체 매물대 추가)
        st.markdown("**매매 레벨 가이드**")
        entry_price = data['vwap']
        pullback = entry_price * 0.95
        stop_loss = entry_price * 0.90 

        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>당일 지지선 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${entry_price:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>공략 눌림목</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>${pullback:.2f}</div>", unsafe_allow_html=True)
        with g2_c2:
            st.markdown("<div class='metric-label'>돌파 타겟 (프리장 최고점)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${data['pm_high']:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>칼손절가 (투심 이탈)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${stop_loss:.2f}</div>", unsafe_allow_html=True)
        with g2_c3:
            st.markdown("<div class='metric-label'>단기 전고점 (20일)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#E0E0E0;'>${data['recent_high']:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>최대 거래량 악성 매물대</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#FF9800;'>${data['heavy_resistance']:.2f}</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        l_c1, l_c2, l_c3 = st.columns(3)
        with l_c1: st.button("📰 야후 뉴스", use_container_width=True)
        with l_c2: st.button("📄 공시(Edgar)", use_container_width=True)
        with l_c3: st.button("🏢 Finviz(Float 확인)", use_container_width=True)

        st.markdown(f"<div class='bottom-warning'>⏱️ 갱신 시점 = 장중 봉 (본장 오픈 전 8:00 AM 이후의 거래량이 진짜 수급입니다)</div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
