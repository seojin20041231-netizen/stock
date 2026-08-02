import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 프리마켓 갭앤고 스캐너", layout="centered")

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
    hist_daily = ticker.history(period="1mo") # RVOL 계산용 30일 데이터
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    if hist_5m.empty or current_price == 0:
        return None

    last_day = hist_5m.index[-1].date()
    today_hist = hist_5m[hist_5m.index.date == last_day].copy()
    
    prev_close = info.get('previousClose', 0.0)
    float_shares = info.get('floatShares', 0)
    short_percent = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0 # 숏 비율
    avg_daily_volume = hist_daily['Volume'].mean() if not hist_daily.empty else 1
    
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
        
        today_hist['Upper_Wick'] = today_hist['High'] - today_hist[['Open', 'Close']].max(axis=1)
        today_hist['Body'] = (today_hist['Open'] - today_hist['Close']).abs()
        recent_5_candles = today_hist.tail(5)
        selling_pressure_wicks = len(recent_5_candles[recent_5_candles['Upper_Wick'] > (recent_5_candles['Body'] * 1.5)])
        
        if len(today_hist) >= 6:
            recent_3_vol = today_hist['Volume'].tail(3).mean()
            prev_3_vol = today_hist['Volume'].iloc[-6:-3].mean()
            if recent_3_vol > prev_3_vol * 1.2:
                vol_acceleration = True
    else:
        today_volume = 0

    # 뉴스 분석
    news_items = ticker.news
    has_today_news = False
    news_sentiment = "NEUTRAL"
    current_time = time.time()
    
    for n in news_items:
        if current_time - n.get('providerPublishTime', 0) < 86400:
            has_today_news = True
            title_lower = n.get('title', '').lower()
            if any(kw in title_lower for kw in BAD_KEYWORDS):
                news_sentiment = "BAD"
            elif any(kw in title_lower for kw in GOOD_KEYWORDS) and news_sentiment != "BAD":
                news_sentiment = "GOOD"

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = today_volume / float_shares if float_shares else 0
    rvol = today_volume / avg_daily_volume if avg_daily_volume else 0

    return {
        'price': current_price, 'change': change_pct,
        'float': float_shares, 'pm_volume': today_volume,
        'turnover': turnover_rate, 'rvol': rvol, 'vwap': vwap, 
        'has_news': has_today_news, 'news_sentiment': news_sentiment,
        'pm_high': pm_high, 'pm_low': pm_low, 'short_pct': short_percent,
        'selling_wicks': selling_pressure_wicks, 'vol_acceleration': vol_acceleration
    }

# --- [3] UI 렌더링 ---
st.title("🚀 정규장 오픈 직전 Gap & Go 판독기")
st.markdown("<span style='font-size: 13px; color: #888;'>목적: 오전 9:30 본장 시작 직후 20~30% 단기 슈팅 포착</span>", unsafe_allow_html=True)
target_ticker = st.text_input("프리마켓 급등 종목 입력 (예: FFIE, GME)", "FFIE").upper()

if target_ticker:
    with st.spinner("호가창 제외(yfinance 딜레이 주의), 거래량 가속도 및 숏비율 교차 검증 중..."):
        data = get_stock_data(target_ticker)
        
    if data is None:
        st.error("데이터를 불러올 수 없습니다.")
    else:
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        col1, col2 = st.columns([6, 4])
        with col1:
            st.markdown(f"### {target_ticker}")
        with col2:
            price_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>당일 등락: {data['change']:.2f}%</div>", unsafe_allow_html=True)
        
        # 🏷️ [동적 상태 태그]
        tags_html = ""
        
        # 가격대 필터
        if not (1 <= data['price'] <= 15):
            tags_html += '<span class="pill-orange">⚠️ 스캘핑 권장 가격대 이탈 ($1~$15 밖)</span>'

        if data['has_news']: 
            if data['news_sentiment'] == "BAD": tags_html += '<span class="pill-red">🚨 악재(오퍼링 등) 감지</span>'
            elif data['news_sentiment'] == "GOOD": tags_html += '<span class="pill-blue">📰 확실한 호재</span>'
        
        if 0 < data['float'] <= 10_000_000: tags_html += '<span class="pill-green">🚀 Micro-Float (품절주)</span>'
        
        # 신규 지표 태그
        if data['rvol'] > 2: tags_html += f'<span class="pill-green">🔥 폭발적 상대거래량 ({data["rvol"]:.1f}x)</span>'
        if data['short_pct'] > 15: tags_html += f'<span class="pill-orange">🎯 숏스퀴즈 가능성 (Short {data["short_pct"]:.1f}%)</span>'
        if data['vol_acceleration']: tags_html += '<span class="pill-blue">📈 오픈 임박 거래량 솟구침</span>'
        
        dist_to_pmh = ((data['pm_high'] - data['price']) / data['price']) * 100
        if dist_to_pmh <= 3: tags_html += '<span class="pill-green">⚔️ PMH(최고점) 돌파 직전</span>'
        
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [모멘텀 스캘핑 데스 필터] 
        is_under_vwap = data['price'] < data['vwap']
        ideal_gap = 20 <= data['change'] <= 80

        if data['news_sentiment'] == "BAD":
            verdict_color = "#FF1744"; verdict_bg = "rgba(255, 23, 68, 0.15)"; status_badge = '<span class="badge-red">🔴 매매 절대 금지</span>'
            verdict_title, verdict_desc = "☠️ 악재 펌핑", "오픈하자마자 패닉셀이 나옵니다. 건드리지 마세요."
        elif is_under_vwap and dist_to_pmh > 10:
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"; status_badge = '<span class="badge-red">🔴 추세 꺾임 (Fade)</span>'
            verdict_title, verdict_desc = "🚨 세력 이탈 진행중", "PMH를 찍고 흘러내려 VWAP 아래에 있습니다. 장 시작 시 쏟아질 확률이 높습니다."
        elif data['price'] >= data['vwap'] and dist_to_pmh <= 5 and ideal_gap and data['rvol'] > 1:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"; status_badge = '<span class="badge-green">🔵 최적의 타겟</span>'
            verdict_title, verdict_desc = "🔥 A급 돌파 셋업", "PMH와 가깝고 거래량이 받쳐줍니다. 장 시작과 동시에 PMH 돌파 시 20% 상승 탄력이 붙습니다."
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"; status_badge = '<span class="badge-orange">🟡 애매함 (관망)</span>'
            verdict_title, verdict_desc = "🤔 조건 미달", "수급이나 위치가 애매합니다. 9:30 직후 흔들기에 당할 수 있으니 패스하세요."

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(status_badge, unsafe_allow_html=True)
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # 📊 [데이터 그리드]
        float_display = f"{int(data['float']/1000000):,}M" if data['float'] > 0 else "N/A"
        
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>RVOL (평소대비)</div>", unsafe_allow_html=True)
            rvol_color = "val-green" if data['rvol'] >= 2 else "val-orange"
            st.markdown(f"<div class='metric-val {rvol_color}'>{data['rvol']:.1f}x</div>", unsafe_allow_html=True)
        with g1_c2:
            st.markdown("<div class='metric-label'>Float / 숏비율</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{float_display} / {data['short_pct']:.1f}%</div>", unsafe_allow_html=True)
        with g1_c3:
            st.markdown("<div class='metric-label'>현재 Gap 상승률</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>{data['change']:.1f}%</div>", unsafe_allow_html=True)
        with g1_c4:
            st.markdown("<div class='metric-label'>PMH까지 거리</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{dist_to_pmh:.1f}%</div>", unsafe_allow_html=True)

        st.markdown("<br>**스캘핑 기준 레벨 (초단타 대응용)**", unsafe_allow_html=True)
        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>생명선 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${data['vwap']:.2f}</div>", unsafe_allow_html=True)
        with g2_c2:
            st.markdown("<div class='metric-label'>돌파 타겟 (PMH)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${data['pm_high']:.2f}</div>", unsafe_allow_html=True)
        with g2_c3:
            st.markdown("<div class='metric-label'>칼손절가 (PML)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${data['pm_low']:.2f}</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
