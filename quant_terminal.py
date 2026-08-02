import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 프리마켓 갭앤고(Gap & Go) 스캐너", layout="centered")

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
    
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 14px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
    .news-box { background-color: #263238; padding: 15px; border-radius: 8px; border-left: 4px solid #00BCD4; margin-top: 15px;}
</style>
""", unsafe_allow_html=True)

BAD_KEYWORDS = ['offering', 'direct offering', 'public offering', 'reverse split', 'delist', 'bankruptcy', 'chapter 11', 'warrant']
GOOD_KEYWORDS = ['fda', 'patent', 'earnings', 'partnership', 'agreement', 'approval', 'merger', 'acquisition', 'clinical', 'contract']

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    hist_5m = ticker.history(period="2d", interval="5m", prepost=True)
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    if hist_5m.empty or current_price == 0:
        return None

    last_day = hist_5m.index[-1].date()
    today_hist = hist_5m[hist_5m.index.date == last_day].copy()
    
    prev_close = info.get('previousClose', 0.0)
    float_shares = info.get('floatShares', 0)
    
    # 지표 초기화
    vwap = current_price
    pm_high = current_price
    pm_low = current_price
    selling_pressure_wicks = 0
    vol_acceleration = False
    
    if not today_hist.empty:
        today_volume = today_hist['Volume'].sum()
        v = today_hist['Volume']
        tp = (today_hist['High'] + today_hist['Low'] + today_hist['Close']) / 3
        vwap_series = (tp * v).cumsum() / v.cumsum()
        vwap = vwap_series.iloc[-1] if not vwap_series.empty else current_price
        
        pm_high = today_hist['High'].max()
        pm_low = today_hist['Low'].min()
        
        # 윗꼬리(Wick) 매도 압력 분석 (최근 5봉)
        today_hist['Upper_Wick'] = today_hist['High'] - today_hist[['Open', 'Close']].max(axis=1)
        today_hist['Body'] = (today_hist['Open'] - today_hist['Close']).abs()
        recent_5_candles = today_hist.tail(5)
        selling_pressure_wicks = len(recent_5_candles[recent_5_candles['Upper_Wick'] > (recent_5_candles['Body'] * 1.5)])
        
        # [신규] 거래량 가속도 (Volume Acceleration) 분석
        # 본장 시작 전, 최근 3개봉(15분) 평균 거래량이 그 직전 3개봉(15분)보다 증가했는가?
        if len(today_hist) >= 6:
            recent_3_vol = today_hist['Volume'].tail(3).mean()
            prev_3_vol = today_hist['Volume'].iloc[-6:-3].mean()
            if recent_3_vol > prev_3_vol * 1.2:  # 20% 이상 거래량 증가 추세
                vol_acceleration = True
    else:
        today_volume = 0

    # 뉴스 스캐너
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

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = today_volume / float_shares if float_shares else 0

    return {
        'price': current_price, 'change': change_pct,
        'float': float_shares, 'pm_volume': today_volume,
        'turnover': turnover_rate, 'vwap': vwap, 
        'has_news': has_today_news, 'news_sentiment': news_sentiment,
        'news_titles': recent_news_titles[:2], 'pm_high': pm_high, 'pm_low': pm_low,
        'selling_wicks': selling_pressure_wicks, 'vol_acceleration': vol_acceleration
    }

# --- [3] UI 렌더링 ---
st.title("🚀 Gap & Go 스캘핑 타겟 판독기")
st.markdown("<span style='font-size: 13px; color: #888;'>목적: 정규장 오픈 직후(9:30 AM) 20~30% 급등 모멘텀 포착</span>", unsafe_allow_html=True)
target_ticker = st.text_input("프리마켓 급등 종목 입력 (예: FFIE, GME)", "FFIE").upper()

if target_ticker:
    with st.spinner("호가창 수급, 거래량 가속도, 유통주식수(Float) 교차 검증 중..."):
        data = get_stock_data(target_ticker)
        
    if data is None:
        st.error("데이터를 불러올 수 없습니다.")
    else:
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        # [헤더]
        col1, col2 = st.columns([6, 4])
        with col1:
            st.markdown(f"### {target_ticker}")
        with col2:
            price_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>당일 등락: {data['change']:.2f}%</div>", unsafe_allow_html=True)
        
        # 🏷️ [동적 상태 태그 (Pill)]
        tags_html = ""
        
        if data['has_news']: 
            if data['news_sentiment'] == "BAD": tags_html += '<span class="pill-red">🚨 악재(오퍼링 등) 감지</span>'
            elif data['news_sentiment'] == "GOOD": tags_html += '<span class="pill-blue">📰 확실한 호재(FDA/계약 등)</span>'
            else: tags_html += '<span class="pill-blue">📰 뉴스/공시 존재</span>'
        else: 
            tags_html += '<span class="pill-gray">무명분 펌핑 (위험)</span>'
            
        # Float 태그 (매우 중요)
        if 0 < data['float'] <= 10_000_000:
            tags_html += '<span class="pill-green">🚀 Micro-Float (품절주 펌핑 최적)</span>'
        elif data['float'] > 30_000_000:
            tags_html += '<span class="pill-orange">⚠️ 무거운 Float (탄력 저하)</span>'
            
        if data['vol_acceleration']: tags_html += '<span class="pill-green">🔥 오픈 임박 거래량 솟구침</span>'
        if data['selling_wicks'] >= 2: tags_html += f'<span class="pill-red">📉 매도 윗꼬리 {data["selling_wicks"]}회 (물량 떠넘기기)</span>'
        
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [모멘텀 스캘핑 데스 필터] 
        is_under_vwap = data['price'] < data['vwap']
        is_low_pm_vol = data['pm_volume'] < 1_000_000 
        ideal_gap = 20 <= data['change'] <= 80

        if data['news_sentiment'] == "BAD":
            verdict_color = "#FF1744"; verdict_bg = "rgba(255, 23, 68, 0.15)"; status_badge = '<span class="badge-red">🔴 매매 절대 금지</span>'
            verdict_title = "☠️ 악재 펌핑 (오퍼링/상폐 위험)"
            verdict_desc = "본장 시작하자마자 패닉셀이 나올 확률이 99%입니다. 건드리지 마세요."
        elif is_under_vwap and data['selling_wicks'] >= 2:
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"; status_badge = '<span class="badge-red">🔴 설거지 진행중</span>'
            verdict_title = "🚨 가짜 펌핑 (Fade 주의)"
            verdict_desc = "이미 세력이 물량을 털고 VWAP 아래로 밀렸습니다. 시가에 갭하락으로 시작할 수 있습니다."
        elif data['change'] > 150:
            verdict_color = "#FFB020"; verdict_bg = "rgba(255, 176, 32, 0.15)"; status_badge = '<span class="badge-orange">🟡 차익실현 빔 주의</span>'
            verdict_title = "⚠️ 극단적 갭상승 (Fade 리스크)"
            verdict_desc = "이미 150% 이상 상승했습니다. 본장 오픈 직후 거대한 차익실현 물량이 쏟아질 수 있으니 초반 5분은 관망하세요."
        elif data['price'] >= data['vwap'] and data['vol_acceleration'] and ideal_gap:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"; status_badge = '<span class="badge-green">🔵 최적의 갭앤고 타겟</span>'
            verdict_title = "🔥 A급 스캘핑 셋업 충족"
            verdict_desc = "적당한 갭상승, VWAP 지지, 본장 임박 거래량 증가까지 완벽합니다. PMH 돌파 시 즉각적인 20% 수익이 가능합니다."
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"; status_badge = '<span class="badge-orange">🟡 조건 미달 (관망)</span>'
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "수급 가속도가 부족하거나 너무 무겁습니다. 확실한 셋업이 아니면 본장 초반 도박을 피하세요."

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(status_badge, unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # 📊 [데이터 그리드 1] 급등 모멘텀 지표
        float_display = f"{int(data['float']/1000000):,} M" if data['float'] > 0 else "N/A"
        
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>프리마켓 거래량</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>{int(data['pm_volume']/1000):,} K</div>", unsafe_allow_html=True)
        with g1_c2:
            st.markdown("<div class='metric-label'>Float (유통주식)</div>", unsafe_allow_html=True)
            f_color = "val-green" if (data['float'] > 0 and data['float'] <= 10000000) else "val-red"
            st.markdown(f"<div class='metric-val {f_color}'>{float_display}</div>", unsafe_allow_html=True)
        with g1_c3:
            st.markdown("<div class='metric-label'>당일 갭(Gap) 상승률</div>", unsafe_allow_html=True)
            gap_color = "val-green" if ideal_gap else "val-orange"
            st.markdown(f"<div class='metric-val {gap_color}'>{data['change']:.1f}%</div>", unsafe_allow_html=True)
        with g1_c4:
            st.markdown("<div class='metric-label'>Float 회전율</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{'%.1f' % data['turnover'] if data['turnover'] else 'N/A'} 회</div>", unsafe_allow_html=True)

        # 🛠️ [데이터 그리드 2] 모멘텀 트레이딩 실전 레벨
        st.markdown("**스캘핑 기준 레벨 (본장 시작 후 즉각 대응용)**")

        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>생명선 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${data['vwap']:.2f}</div>", unsafe_allow_html=True)
        with g2_c2:
            st.markdown("<div class='metric-label'>돌파 시 급등타겟 (PMH)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${data['pm_high']:.2f}</div>", unsafe_allow_html=True)
        with g2_c3:
            st.markdown("<div class='metric-label'>최종 칼손절가 (PML)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${data['pm_low']:.2f}</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
