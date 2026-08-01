import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 급등주 검색기", layout="centered")

# CSS 스타일링 (다크 테마 및 커스텀 배지/블록)
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 20px; border-radius: 12px; border: 1px solid #333; }
    .badge-red { background-color: #4A1919; color: #FF5252; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FF5252;}
    .badge-orange { background-color: #4A3519; color: #FFB020; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FFB020;}
    .badge-green { background-color: #193D24; color: #4CAF50; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #4CAF50;}
    .pill-orange { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 4px 10px; border-radius: 6px; border: 1px solid #FFB020; font-size: 12px; margin-right: 8px;}
    .pill-gray { background-color: #2D2D2D; color: #A0A0A0; padding: 4px 10px; border-radius: 6px; font-size: 12px;}
    .warning-block { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-top: 6px; border: 1px solid rgba(255, 82, 82, 0.3);}
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 14px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
    .bottom-warning { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 10px; border-radius: 8px; font-size: 12px; text-align: center; margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

# --- [2] 데이터 수집 및 분석 알고리즘 ---
@st.cache_data(ttl=60) # 1분마다 캐시 갱신
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # 당일 5분봉 데이터 가져오기 (VWAP 및 거래량 계산용)
    hist = ticker.history(period="1d", interval="5m")
    
    # 기본 변수 추출 및 예외 처리 (yfinance 누락 대비)
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    prev_close = info.get('previousClose', 0.0)
    market_cap = info.get('marketCap', 0)
    float_shares = info.get('floatShares', info.get('sharesOutstanding', 1)) # float 없으면 총발행주식 대체
    volume_today = info.get('regularMarketVolume', 0)
    
    if hist.empty:
        vwap = current_price
        vol_30m = 0
    else:
        # VWAP 계산: (고가+저가+종가)/3 * 거래량 누적 / 거래량 누적
        v = hist['Volume']
        tp = (hist['High'] + hist['Low'] + hist['Close']) / 3
        vwap = (tp * v).cumsum() / v.cumsum()
        vwap = vwap.iloc[-1]
        
        # 최근 30분 수급 (거래대금)
        recent_hist = hist.tail(6) # 5분봉 * 6 = 30분
        vol_30m = (recent_hist['Close'] * recent_hist['Volume']).sum()

    # 지표 계산
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = volume_today / float_shares if float_shares else 0
    
    # 🎯 대장주 판별 알고리즘 스코어링
    score = 0
    warnings = []
    
    if float_shares < 10_000_000: score += 30
    elif float_shares < 20_000_000: score += 10
    else: warnings.append(f"⚠️ 무거운 유통물량 ({float_shares/1000000:.1f}M)")

    if turnover_rate >= 1.0: score += 30
    elif turnover_rate >= 0.5: score += 10
    
    if current_price > vwap: score += 20
    if vol_30m >= 2_000_000: score += 20
    
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (나스닥 상장유지 요건 위험)")
    if market_cap < 10_000_000: warnings.append(f"⚠️ 초소형 시총 ${(market_cap/1000000):.1f}M (조작·급변동 취약)")

    # 스코어에 따른 상태 결정
    if score >= 70:
        status_html = '<span class="badge-green">🔵 관심 (대장주)</span>'
    elif score >= 40:
        status_html = '<span class="badge-orange">🟡 주의 (단타용)</span>'
    else:
        status_html = '<span class="badge-red">🔴 회피 (설거지)</span>'

    # 원화 환산 (단순 계산용 상수)
    krw_price = current_price * 1350 

    return {
        'price': current_price, 'krw': krw_price, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'volume': volume_today,
        'turnover': turnover_rate, 'status': status_html, 'warnings': warnings,
        'vwap': vwap, 'vol_30m': vol_30m
    }

# --- [3] UI 렌더링 ---
st.title("🚀 동전주 프리마켓 추적기")
target_ticker = st.text_input("종목 티커 입력 (예: CISS, STAK, XRX)", "CISS").upper()

if target_ticker:
    with st.spinner("데이터 분석 중..."):
        data = get_stock_data(target_ticker)
        
    st.markdown('<div class="card-container">', unsafe_allow_html=True)
    
    # 상단 헤더
    col1, col2 = st.columns([6, 4])
    with col1:
        st.markdown(f"### {target_ticker} <span style='font-size: 14px; color: #888;'>NASDAQ</span>", unsafe_allow_html=True)
        st.markdown(data['status'], unsafe_allow_html=True)
    with col2:
        price_color = "val-green" if data['change'] >= 0 else "val-red"
        st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>≈ {int(data['krw']):,}원</div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 태그 및 경고 블록
    st.markdown(f"""
        <span class="pill-orange">휴면→각성 ⚡</span>
        <span class="pill-gray">살아있는 유량 ${(data['vol_30m']/1000000):.1f}M / 30분</span>
    """, unsafe_allow_html=True)
    
    for warning in data['warnings']:
        st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
        
    st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
    
    # 데이터 그리드 1 (거래 및 수급 정보)
    g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
    with g1_c1:
        st.markdown("<div class='metric-label'>등락률</div>", unsafe_allow_html=True)
        sign = "+" if data['change'] > 0 else ""
        st.markdown(f"<div class='metric-val {price_color}'>{sign}{data['change']:.2f}%</div>", unsafe_allow_html=True)
    with g1_c2:
        st.markdown("<div class='metric-label'>당일 거래량</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val'>{int(data['volume']):,}</div>", unsafe_allow_html=True)
    with g1_c3:
        st.markdown("<div class='metric-label'>시가총액</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val'>${(data['market_cap']/1000000):.1f}M</div>", unsafe_allow_html=True)
    with g1_c4:
        st.markdown("<div class='metric-label'>유통 회전율</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-orange'>x{data['turnover']:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 데이터 그리드 2 (매매 레벨 - VWAP 기반 러프한 계산)
    st.markdown("**매매 레벨 (규칙형 참고치)**")
    entry_price = data['vwap']
    res_1 = entry_price * 1.15
    res_2 = entry_price * 1.30
    support = entry_price * 0.90
    stop_loss = entry_price * 0.85
    
    g2_c1, g2_c2, g2_c3 = st.columns(3)
    with g2_c1:
        st.markdown("<div class='metric-label'>VWAP 진입가</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val'>${entry_price:.2f}</div>", unsafe_allow_html=True)
        st.markdown("<div class='metric-label' style='margin-top:10px;'>눌림목</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-orange'>${(entry_price*0.95):.2f}</div>", unsafe_allow_html=True)
    with g2_c2:
        st.markdown("<div class='metric-label'>1차 매도가</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-green'>${res_1:.2f}</div>", unsafe_allow_html=True)
        st.markdown("<div class='metric-label' style='margin-top:10px;'>지지선</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-red'>${support:.2f}</div>", unsafe_allow_html=True)
    with g2_c3:
        st.markdown("<div class='metric-label'>2차 매도가</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-green'>${res_2:.2f}</div>", unsafe_allow_html=True)
        st.markdown("<div class='metric-label' style='margin-top:10px;'>손절가</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val val-red'>${stop_loss:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 하단 링크 버튼
    l_c1, l_c2, l_c3 = st.columns(3)
    with l_c1: st.button("📰 야후 뉴스", use_container_width=True)
    with l_c2: st.button("📄 공시·보도자료", use_container_width=True)
    with l_c3: st.button("🏢 기업정보", use_container_width=True)

    # 하단 주의사항
    st.markdown(f"<div class='bottom-warning'>⏱️ 갱신 시점 = 장중(미완성) 봉 · 거래량은 마감까지 더 늘 수 있음 (현재 {int(data['volume']):,})</div>", unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

