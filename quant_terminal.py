import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 프리마켓 대장주 판독기", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    .card-container { background-color: #1E1E1E; padding: 20px; border-radius: 12px; border: 1px solid #333; }
    .badge-red { background-color: #4A1919; color: #FF5252; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FF5252;}
    .badge-orange { background-color: #4A3519; color: #FFB020; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #FFB020;}
    .badge-green { background-color: #193D24; color: #4CAF50; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: bold; border: 1px solid #4CAF50;}
    .pill-orange { background-color: rgba(255, 176, 32, 0.1); color: #FFB020; padding: 4px 10px; border-radius: 6px; border: 1px solid #FFB020; font-size: 12px; margin-right: 8px;}
    .pill-blue { background-color: rgba(33, 150, 243, 0.1); color: #2196F3; padding: 4px 10px; border-radius: 6px; border: 1px solid #2196F3; font-size: 12px; margin-right: 8px;}
    .warning-block { background-color: rgba(255, 82, 82, 0.1); color: #FF5252; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-top: 6px; border: 1px solid rgba(255, 82, 82, 0.3);}
    .metric-label { font-size: 12px; color: #888888; margin-bottom: 2px;}
    .metric-val { font-size: 14px; font-weight: bold; }
    .val-green { color: #4CAF50; }
    .val-red { color: #FF5252; }
    .val-orange { color: #FFB020; }
    .news-box { background-color: #263238; padding: 15px; border-radius: 8px; border-left: 4px solid #00BCD4; margin-top: 15px;}
    .whale-box { background-color: #1A237E; padding: 15px; border-radius: 8px; border-left: 4px solid #5C6BC0; margin-top: 15px; color: #E8EAF6;}
</style>
""", unsafe_allow_html=True)

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # 🚨 핵심 수정 1: prepost=True로 프리마켓 데이터 포함하여 수집
    hist_5m = ticker.history(period="3d", interval="5m", prepost=True)
    hist_daily = ticker.history(period="6mo", interval="1d")
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    if hist_5m.empty or current_price == 0:
        return None

    # 당일 데이터만 필터링 (프리마켓 시작점부터 리셋을 위함)
    last_day = hist_5m.index[-1].date()
    today_hist = hist_5m[hist_5m.index.date == last_day]
    
    prev_close = info.get('previousClose', 0.0)
    market_cap = info.get('marketCap', 0)
    float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
    high_52w = info.get('fiftyTwoWeekHigh', 0.0)

    # 🚨 핵심 수정 2 & 3: 당일 프리마켓 전용 거래량 및 VWAP 계산
    if not today_hist.empty:
        today_volume = today_hist['Volume'].sum()
        v = today_hist['Volume']
        tp = (today_hist['High'] + today_hist['Low'] + today_hist['Close']) / 3
        vwap_series = (tp * v).cumsum() / v.cumsum()
        vwap = vwap_series.iloc[-1] if not vwap_series.empty else current_price
        
        recent_hist = today_hist.tail(6) # 최근 30분(5분봉 x 6)
        vol_30m = (recent_hist['Close'] * recent_hist['Volume']).sum()
    else:
        today_volume = 0
        vwap = current_price
        vol_30m = 0

    # 🚨 핵심 수정 4: 당일 호재(뉴스/공시) 유무 확인
    news_items = ticker.news
    has_today_news = False
    current_time = time.time()
    recent_news_titles = []
    
    for n in news_items:
        # 최근 24시간(86400초) 이내의 뉴스가 있는지 판별
        if current_time - n.get('providerPublishTime', 0) < 86400:
            has_today_news = True
            recent_news_titles.append(n.get('title', '제목 없음'))

    # 스윙 관점의 세력 매집 흔적 (보조 지표로 강등)
    whale_score = 0
    obv_div, has_wicks, volume_dry, vol_spike = False, False, False, False
    wicks = 0
    if not hist_daily.empty:
        change = hist_daily['Close'].diff()
        direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
        hist_daily['OBV'] = (hist_daily['Volume'] * direction).cumsum()
        
        obv_30d = hist_daily['OBV'].tail(30)
        price_30d = hist_daily['Close'].tail(30)
        if len(obv_30d) > 0 and len(price_30d) > 0:
            obv_div = obv_30d.iloc[-1] >= obv_30d.iloc[0] and price_30d.iloc[-1] <= price_30d.iloc[0]

        hist_daily['Upper_Wick'] = hist_daily['High'] - hist_daily[['Open', 'Close']].max(axis=1)
        hist_daily['Body'] = abs(hist_daily['Open'] - hist_daily['Close'])
        vol_avg_20 = hist_daily['Volume'].rolling(20).mean()
        
        hist_daily['Wick_Signal'] = (hist_daily['Upper_Wick'] > hist_daily['Body'] * 2) & (hist_daily['Volume'] > vol_avg_20)
        wicks = hist_daily['Wick_Signal'].tail(60).sum()
        has_wicks = wicks >= 2

        vol_5d_avg = hist_daily['Volume'].tail(5).mean()
        vol_60d_avg = hist_daily['Volume'].tail(60).mean()
        volume_dry = vol_5d_avg < (vol_60d_avg * 0.4) if vol_60d_avg > 0 else False
        vol_spike = (hist_daily['Volume'].tail(10) > (vol_avg_20.tail(10) * 5)).any()

        if obv_div: whale_score += 30
        if has_wicks: whale_score += 30
        if volume_dry: whale_score += 20
        if vol_spike: whale_score += 20

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = today_volume / float_shares if float_shares else 0
    drop_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w else 0

    warnings = []
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (상장유지 요건 위험/동전주 변동성 극대화)")
    if float_shares > 20_000_000: warnings.append(f"⚠️ 유통물량 무거움 ({float_shares/1000000:.1f}M) - 찐 대장 되기 힘듦")
    if drop_from_high < -80: warnings.append(f"⚠️ 전고점 대비 {abs(drop_from_high):.0f}% 폭락 상태 (위로 악성 매물대 가득)")

    return {
        'price': current_price, 'krw': current_price * 1350, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'pm_volume': today_volume,
        'turnover': turnover_rate, 'warnings': warnings,
        'vwap': vwap, 'vol_30m': vol_30m,
        'has_news': has_today_news, 'news_titles': recent_news_titles[:2], # 최대 2개만
        'whale_score': whale_score, 'obv_div': obv_div, 'has_wicks': has_wicks, 'wicks': int(wicks)
    }

# --- [3] UI 렌더링 ---
st.title("🦅 프리마켓 대장주 감별기")
target_ticker = st.text_input("프리마켓 급등 종목 티커 입력 (예: CISS)", "CISS").upper()

if target_ticker:
    with st.spinner("당일 프리마켓 데이터 및 호재 수집 중..."):
        data = get_stock_data(target_ticker)
        
    if data is None:
        st.error("데이터를 불러올 수 없습니다. 티커를 확인하세요.")
    else:
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        # [헤더]
        col1, col2 = st.columns([6, 4])
        with col1:
            st.markdown(f"### {target_ticker} <span style='font-size: 14px; color: #888;'>NASDAQ</span>", unsafe_allow_html=True)
        with col2:
            price_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>당일 변동: {data['change']:.2f}%</div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [프리마켓 데스 필터] 
        is_under_vwap = data['price'] < data['vwap']
        is_heavy_float = data['float'] > 20_000_000 if data['float'] else False
        is_low_pm_vol = data['pm_volume'] < 500_000 # 프리마켓 50만주 이하는 가짜
        no_news = not data['has_news']

        if is_under_vwap and (is_low_pm_vol or no_news):
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"
            verdict_title = "🚨 가짜 반등 (설거지 위험)"
            verdict_desc = "당일 호재도 없고, 프리마켓 평단가(VWAP) 아래로 쳐박혔습니다. 본장 열리면 나락갑니다."
            status_badge = '<span class="badge-red">🔴 회피 (데드캣)</span>'
        elif is_under_vwap:
            verdict_color = "#FFB020"; verdict_bg = "rgba(255, 176, 32, 0.15)"
            verdict_title = "⚠️ 관망 (투심 꺾임, 추세 전환 대기)"
            verdict_desc = "호재/수급은 있으나 현재 프리장 평단가 아래로 밀렸습니다. VWAP 돌파 전까진 건들지 마세요."
            status_badge = '<span class="badge-orange">🟡 주의 (돌파 대기)</span>'
        elif not is_heavy_float and not is_low_pm_vol and data['has_news'] and data['price'] > data['vwap']:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"
            verdict_title = "🔥 프리마켓 찐 대장주 조건 충족"
            verdict_desc = "당일 확실한 호재 + 가벼운 물량 + 터지는 거래량 + VWAP 위 안착. 오늘 밤 주도주입니다."
            status_badge = '<span class="badge-green">🔵 찐 대장주 (매수 고려)</span>'
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "명분이나 수급 중 하나가 빠져있습니다. 굳이 리스크를 안고 도박할 필요는 없습니다."
            status_badge = '<span class="badge-orange">🟡 주의 (조건 미달)</span>'

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(status_badge, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        if data['has_news']:
            st.markdown('<span class="pill-blue">📰 당일 뉴스/공시 존재</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="pill-gray">텅 빈 깡통 (이유없는 펌핑)</span>', unsafe_allow_html=True)
            
        for warning in data['warnings']:
            st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # [데이터 그리드 1] 당일 수급 집중 분석
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>당일 누적 거래량</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{int(data['pm_volume']):,}</div>", unsafe_allow_html=True)
        with g1_c2:
            st.markdown("<div class='metric-label'>당일 평단가(VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val' style='color:#2196F3;'>${data['vwap']:.2f}</div>", unsafe_allow_html=True)
        with g1_c3:
            st.markdown("<div class='metric-label'>시가총액</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>${(data['market_cap']/1000000):.1f}M</div>", unsafe_allow_html=True)
        with g1_c4:
            st.markdown("<div class='metric-label'>당일 유통 회전율</div>", unsafe_allow_html=True)
            turnover_color = "val-green" if data['turnover'] > 0.5 else "val-orange"
            st.markdown(f"<div class='metric-val {turnover_color}'>x{data['turnover']:.2f}</div>", unsafe_allow_html=True)

        # 📰 [신규 기능] 당일 호재(Catalyst) 판독
        news_border = "#00BCD4" if data['has_news'] else "#546E7A"
        news_title_str = "<br>".join([f"- {t}" for t in data['news_titles']]) if data['has_news'] else "24시간 내 올라온 영문 뉴스나 공시(SEC)가 없습니다. 전형적인 세력의 가짜 펌핑일 확률이 높습니다."
        
        st.markdown(f"""
        <div class="news-box" style="border-left-color: {news_border};">
            <h5 style="margin-top: 0px; margin-bottom: 10px; color: #E0F7FA;">📰 당일 상승 명분 (Catalyst) 체크</h5>
            <div style="font-size: 13px; color: #B0BEC5;">{news_title_str}</div>
        </div>
        """, unsafe_allow_html=True)

        # 🕵️‍♂️ 과거 매집 스코어 (참고용으로 축소)
        st.markdown(f"""
        <div class="whale-box" style="padding: 10px 15px; margin-top: 10px;">
            <div style="display:flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px;">🕵️‍♂️ <b>사전 매집 스코어 (참고용):</b> {data['whale_score']} / 100점</span>
                <span style="font-size: 11px; color:#9FA8DA;">OBV 다이버전스: {'✅' if data['obv_div'] else '❌'} | 매집봉: {'✅' if data['has_wicks'] else '❌'}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 🛠️ [데이터 그리드 2] 당일 VWAP 기준 매매 레벨
        st.markdown("**프리마켓/본장 초반 매매 레벨**")
        entry_price = data['vwap']
        pullback = entry_price * 0.95
        res_1 = entry_price * 1.15
        stop_loss = entry_price * 0.88 # VWAP 이탈 시 칼손절

        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>돌파/지지 (VWAP)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>${entry_price:.2f}</div>", unsafe_allow_html=True)
        with g2_c2:
            st.markdown("<div class='metric-label'>저항 (목표가)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-green'>${res_1:.2f}</div>", unsafe_allow_html=True)
        with g2_c3:
            st.markdown("<div class='metric-label'>칼손절가 (투심 이탈)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-red'>${stop_loss:.2f}</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
