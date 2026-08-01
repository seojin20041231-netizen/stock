import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 프리마켓 대장주 판독기 Pro", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 20px; border-radius: 12px; border: 1px solid #333; }
    .badge-red { background-color: #4A1919; color: #FF5252; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FF5252;}
    .badge-orange { background-color: #4A3519; color: #FFB020; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FFB020;}
    .badge-green { background-color: #193D24; color: #4CAF50; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #4CAF50;}
    
    /* 동적 태그용 Pill 스타일 추가 */
    .pill-gray { background-color: #2D2D2D; color: #A0A0A0; padding: 4px 10px; border-radius: 6px; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-blue { background-color: rgba(33, 150, 243, 0.1); color: #2196F3; padding: 4px 10px; border-radius: 6px; border: 1px solid #2196F3; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-orange { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 4px 10px; border-radius: 6px; border: 1px solid #FFB020; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-green { background-color: rgba(76, 175, 80, 0.1); color: #4CAF50; padding: 4px 10px; border-radius: 6px; border: 1px solid #4CAF50; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    .pill-red { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 4px 10px; border-radius: 6px; border: 1px solid #FF5252; font-size: 12px; margin-right: 6px; display: inline-block; margin-bottom: 6px;}
    
    .warning-block { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-top: 6px; border: 1px solid rgba(255, 82, 82, 0.3);}
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 14px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
    .news-box { background-color: #263238; padding: 15px; border-radius: 8px; border-left: 4px solid #00BCD4; margin-top: 15px;}
    .bottom-warning { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 10px; border-radius: 8px; font-size: 12px; text-align: center; margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

# 악재/호재 판별을 위한 키워드 리스트
BAD_KEYWORDS = ['offering', 'direct offering', 'public offering', 'reverse split', 'delist', 'bankruptcy', 'chapter 11', 'lawsuit']
GOOD_KEYWORDS = ['fda', 'patent', 'earnings', 'partnership', 'agreement', 'approval', 'merger', 'acquisition', 'clinical']

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # 당일 프리마켓 포함 5분봉 & 분석용 일봉 데이터
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

    # 1. 강력한 악성 매물대 (최근 6개월 중 최대 거래량이 터진 날의 고점)
    past_daily = hist_daily[hist_daily.index.date < last_day]
    if not past_daily.empty:
        max_vol_idx = past_daily['Volume'].idxmax()
        heavy_resistance = past_daily.loc[max_vol_idx, 'High']
        recent_high = past_daily['High'].tail(20).max()
    else:
        heavy_resistance = current_price
        recent_high = current_price

    # 2. 당일 프리마켓 분봉 데이터 기반 정밀 수급 분석
    is_rising = False
    vwap = current_price
    intra_obv_status = "데이터 부족"
    intra_obv_color = "#A0A0A0"
    
    if not today_hist.empty:
        today_volume = today_hist['Volume'].sum()
        v = today_hist['Volume']
        tp = (today_hist['High'] + today_hist['Low'] + today_hist['Close']) / 3
        # VWAP 산출 (프리마켓 시작점 기준 누적)
        vwap_series = (tp * v).cumsum() / v.cumsum()
        vwap = vwap_series.iloc[-1] if not vwap_series.empty else current_price
        
        # [핵심 로직 개선] 5분봉 기준 EMA 9 / EMA 20 및 골든크로스/정배열 확인
        today_hist['EMA9'] = today_hist['Close'].ewm(span=9, adjust=False).mean()
        today_hist['EMA20'] = today_hist['Close'].ewm(span=20, adjust=False).mean()
        
        if len(today_hist) >= 20:
            last_close = today_hist['Close'].iloc[-1]
            last_ema9 = today_hist['EMA9'].iloc[-1]
            last_ema20 = today_hist['EMA20'].iloc[-1]
            
            # 주가가 VWAP 위이고, EMA9가 EMA20 위에 있으면 완벽한 상승 추세로 판단
            if (last_close > vwap) and (last_ema9 > last_ema20):
                is_rising = True

        # [핵심 로직 개선] 당일 프리마켓 인트라데이 OBV (매집/분산 파악)
        change = today_hist['Close'].diff()
        direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
        today_hist['Intra_OBV'] = (today_hist['Volume'] * direction).cumsum()
        
        if len(today_hist) >= 3:
            # 첫 봉 대비 현재 OBV가 높으면 당일 매수세(주포 진입) 우위로 판단
            if today_hist['Intra_OBV'].iloc[-1] > 0:
                intra_obv_status = "매수세 압도(진성 펌핑)"
                intra_obv_color = "#4CAF50" # 초록
            else:
                intra_obv_status = "매도세 우위(설거지)"
                intra_obv_color = "#FF5252" # 빨강
    else:
        today_volume = 0

    # 3. 뉴스 키워드 기반 악재/호재 스캐너
    news_items = ticker.news
    has_today_news = False
    news_sentiment = "NEUTRAL"
    current_time = time.time()
    recent_news_titles = []
    
    for n in news_items:
        if current_time - n.get('providerPublishTime', 0) < 86400: # 24시간 이내
            has_today_news = True
            title = n.get('title', '제목 없음')
            recent_news_titles.append(title)
            
            # 소문자 변환 후 키워드 검사
            title_lower = title.lower()
            if any(kw in title_lower for kw in BAD_KEYWORDS):
                news_sentiment = "BAD"
            elif any(kw in title_lower for kw in GOOD_KEYWORDS) and news_sentiment != "BAD":
                news_sentiment = "GOOD"

    # 일평균 거래량 산출 (분모 0 방지)
    vol_avg_20 = past_daily['Volume'].tail(20).mean() if not past_daily.empty else 1
    vol_avg_20 = vol_avg_20 if vol_avg_20 > 0 else 1

    # RVOL (프리마켓 거래량만으로 일평균 대비 몇 배 터졌는지)
    vol_mult_20d = today_volume / vol_avg_20

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = today_volume / float_shares if float_shares else 0
    drop_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w else 0

    warnings = []
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (나스닥 상장유지 요건 위험 / 상폐 압박)")
    if market_cap > 0 and market_cap < 10_000_000: warnings.append(f"⚠️ 초소형 시총 ${(market_cap/1000000):.1f}M (세력 장난질 극대화)")
    if drop_from_high < -80: warnings.append(f"⚠️ 52주 최고점 대비 {abs(drop_from_high):.0f}% 폭락 상태 (위로 시체의 산 가득)")

    return {
        'price': current_price, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'pm_volume': today_volume,
        'turnover': turnover_rate, 'warnings': warnings,
        'vwap': vwap, 'has_news': has_today_news, 'news_sentiment': news_sentiment,
        'news_titles': recent_news_titles[:2], 'vol_mult_20d': vol_mult_20d,
        'intra_obv_status': intra_obv_status, 'intra_obv_color': intra_obv_color,
        'recent_high': recent_high, 'heavy_resistance': heavy_resistance, 
        'is_rising': is_rising, 'vol_avg_20': vol_avg_20
    }

# --- [3] UI 렌더링 ---
st.title("🦅 프리마켓 찐 대장주 감별기 Pro")
st.markdown("<span style='font-size: 13px; color: #888;'>*yfinance 데이터 기반 (최종 매매 전 HTS/MTS에서 Float 및 악재 여부 교차검증 필수)</span>", unsafe_allow_html=True)
target_ticker = st.text_input("프리마켓 급등 종목 티커 입력 (예: CISS, FFIE)", "CISS").upper()

if target_ticker:
    with st.spinner("당일 인트라데이 수급(OBV), 추세선, 뉴스 센티먼트 판독 중..."):
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
        
        # 뉴스 센티먼트 태그
        if data['has_news']: 
            if data['news_sentiment'] == "BAD": tags_html += '<span class="pill-red">🚨 치명적 악재(Offering 등) 감지</span>'
            elif data['news_sentiment'] == "GOOD": tags_html += '<span class="pill-blue">📰 확실한 호재 키워드</span>'
            else: tags_html += '<span class="pill-blue">📰 당일 뉴스/공시 </span>'
        else: 
            tags_html += '<span class="pill-gray">텅 빈 깡통 (무명분 펌핑)</span>'
        
        # 거래량 및 추세 태그
        if data['vol_mult_20d'] > 1.0: tags_html += '<span class="pill-orange">📈 프리장 거래량 > 평소 하루치 초과</span>'
        if data['is_rising']: tags_html += '<span class="pill-green">🔥 상승 정배열 (EMA9 > EMA20)</span>'
        if data['turnover'] > 2.0: tags_html += f'<span class="pill-red">⚠️ 유통주식 {data["turnover"]:.1f}회전 (투기과열)</span>'
        
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [프리마켓 데스 필터 심화] 
        is_under_vwap = data['price'] < data['vwap']
        is_low_pm_vol = data['pm_volume'] < 1_000_000 # 동전주는 프리마켓 최소 100만주는 터져야 함

        if data['news_sentiment'] == "BAD":
            verdict_color = "#FF1744"; verdict_bg = "rgba(255, 23, 68, 0.15)"
            verdict_title = "☠️ 절대 접근 금지 (치명적 악재)"
            verdict_desc = "유상증자(Offering), 상폐 경고 등 강력한 악재 키워드가 포함된 뉴스가 있습니다. 하따도 금지입니다."
            status_badge = '<span class="badge-red">🔴 매매 금지</span>'
        elif is_under_vwap and (is_low_pm_vol or not data['has_news']):
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"
            verdict_title = "🚨 전형적인 가짜 반등 (설거지)"
            verdict_desc = "명분도 없고, 수급도 부족한데 프리마켓 평단가(VWAP) 아래로 쳐박혔습니다. 본장 열리면 나락갑니다."
            status_badge = '<span class="badge-red">🔴 회피 (데드캣)</span>'
        elif is_under_vwap:
            verdict_color = "#FFB020"; verdict_bg = "rgba(255, 176, 32, 0.15)"
            verdict_title = "⚠️ 관망 (투심 꺾임, 돌파 대기)"
            verdict_desc = "호재나 수급은 있으나 현재 프리장 평단가(VWAP) 아래로 밀렸습니다. VWAP 재돌파 전까진 건들지 마세요."
            status_badge = '<span class="badge-orange">🟡 주의 (돌파 대기)</span>'
        elif not is_low_pm_vol and data['has_news'] and data['price'] > data['vwap'] and data['is_rising']:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"
            verdict_title = "🔥 찐 대장주 조건 완벽 충족"
            verdict_desc = "호재 + 거래량 폭발 + VWAP 지지 + 분봉 정배열. 오늘 데이트레이딩 주도주입니다. 눌림목을 공략하세요."
            status_badge = '<span class="badge-green">🔵 찐 대장주 (매수 고려)</span>'
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "추세가 불안정하거나 수급이 2% 부족합니다. 굳이 리스크를 안고 도박할 필요는 없습니다."
            status_badge = '<span class="badge-orange">🟡 주의 (조건 미달)</span>'

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(status_badge, unsafe_allow_html=True)
        
        for warning in data['warnings']:
            st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # 📊 [데이터 그리드 1] 인트라데이 수급 중심
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>당일 프리 누적 거래량</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>{int(data['pm_volume']/1000):,} K</div>", unsafe_allow_html=True)
        with g1_c2:
            st.markdown("<div class='metric-label'>20일 일평균 대비(배)</div>", unsafe_allow_html=True)
            vol_color = "val-green" if data['vol_mult_20d'] >= 1 else "val-orange"
            st.markdown(f"<div class='metric-val {vol_color}'>x{data['vol_mult_20d']:.2f}</div>", unsafe_allow_html=True)
        with g1_c3:
            st.markdown("<div class='metric-label'>당일 유통 회전율</div>", unsafe_allow_html=True)
            turnover_color = "val-green" if data['turnover'] < 1 else "val-red"
            st.markdown(f"<div class='metric-val {turnover_color}'>x{data['turnover']:.2f}</div>", unsafe_allow_html=True)
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
        res_1 = entry_price * 1.15
        stop_loss = entry_price * 0.90 # 손절선을 더 타이트하게 변경

        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>당일 지지선 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${entry_price:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>공략 눌림목</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>${pullback:.2f}</div>", unsafe_allow_html=True)
        with g2_c2:
            st.markdown("<div class='metric-label'>1차 단기 저항</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${res_1:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>칼손절가 (투심 이탈)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${stop_loss:.2f}</div>", unsafe_allow_html=True)
        with g2_c3:
            st.markdown("<div class='metric-label'>단기 전고점 (20일)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#E0E0E0;'>${data['recent_high']:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>최대 거래량 악성 매물대</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#FF9800;'>${data['heavy_resistance']:.2f}</div>", unsafe_allow_html=True)

        # [하단 버튼 및 갱신 시간]
        st.markdown("<br>", unsafe_allow_html=True)
        l_c1, l_c2, l_c3 = st.columns(3)
        with l_c1: st.button("📰 야후 뉴스", use_container_width=True)
        with l_c2: st.button("📄 공시(Edgar)", use_container_width=True)
        with l_c3: st.button("🏢 Finviz(Float 확인)", use_container_width=True)

        st.markdown(f"<div class='bottom-warning'>⏱️ 갱신 시점 = 장중 봉 (거래량은 마감까지 더 늘 수 있음)</div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
