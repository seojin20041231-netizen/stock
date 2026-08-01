import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 급등주 판독기", layout="centered")

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

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    hist = ticker.history(period="1d", interval="5m")
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    prev_close = info.get('previousClose', 0.0)
    market_cap = info.get('marketCap', 0)
    float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
    volume_today = info.get('regularMarketVolume', 0)
    
    if hist.empty or current_price == 0:
        return None

    # VWAP 계산
    v = hist['Volume']
    tp = (hist['High'] + hist['Low'] + hist['Close']) / 3
    vwap = (tp * v).cumsum() / v.cumsum()
    vwap = vwap.iloc[-1] if not vwap.empty else current_price
    
    # 최근 30분 수급 (거래대금)
    recent_hist = hist.tail(6)
    vol_30m = (recent_hist['Close'] * recent_hist['Volume']).sum()

    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = volume_today / float_shares if float_shares else 0
    
    # 리스크 경고
    warnings = []
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (나스닥 상장유지 요건 위험)")
    if market_cap < 15_000_000: warnings.append(f"⚠️ 초소형 시총 ${(market_cap/1000000):.1f}M (조작·급변동 취약)")
    if float_shares > 20_000_000: warnings.append(f"⚠️ 무거운 유통물량 ({float_shares/1000000:.1f}M) - 탄력 둔화")

    krw_price = current_price * 1350 

    return {
        'price': current_price, 'krw': krw_price, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'volume': volume_today,
        'turnover': turnover_rate, 'warnings': warnings,
        'vwap': vwap, 'vol_30m': vol_30m
    }

# --- [3] UI 렌더링 ---
st.title("🚀 미국 급등주 AI 판독기")
target_ticker = st.text_input("종목 티커 입력 (예: CISS)", "CISS").upper()

if target_ticker:
    with st.spinner("호가 및 수급 데이터 분석 중..."):
        data = get_stock_data(target_ticker)
        
    if data is None:
        st.error("데이터를 불러올 수 없습니다. 티커를 확인하거나 장 개장 여부를 확인하세요.")
    else:
        st.markdown('<div class="card-container">', unsafe_allow_html=True)
        
        # [헤더]
        col1, col2 = st.columns([6, 4])
        with col1:
            st.markdown(f"### {target_ticker} <span style='font-size: 14px; color: #888;'>NASDAQ</span>", unsafe_allow_html=True)
        with col2:
            price_color = "val-green" if data['change'] >= 0 else "val-red"
            st.markdown(f"<div style='text-align: right;'><span style='font-size: 28px; font-weight: bold;' class='{price_color}'>${data['price']:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 14px;'>≈ {int(data['krw']):,}원</div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 🎯 [핵심] ㅈ되는 종목 거르는 '최종 매매 판정' (Death Filter)
        is_under_vwap = data['price'] < data['vwap']
        is_heavy_float = data['float'] > 20_000_000 if data['float'] else False
        is_low_volume = data['vol_30m'] < 1_000_000

        if is_under_vwap and (is_heavy_float or is_low_volume):
            verdict_color = "#FF5252"
            verdict_bg = "rgba(255, 82, 82, 0.15)"
            verdict_title = "🚨 절대 매수 금지 (설거지 위험 99%)"
            verdict_desc = "이미 고점 찍고 세력이 물량 넘기는 중이거나 수급이 말랐습니다. 쳐다보지도 마세요."
            status_badge = '<span class="badge-red">🔴 회피 (설거지)</span>'
        elif is_under_vwap:
            verdict_color = "#FFB020"
            verdict_bg = "rgba(255, 176, 32, 0.15)"
            verdict_title = "⚠️ 관망 (투심 꺾임, 낙폭 과대 단타만)"
            verdict_desc = "평균 단가(VWAP) 아래로 밀렸습니다. 확실하게 VWAP을 다시 뚫기 전까지는 위험합니다."
            status_badge = '<span class="badge-orange">🟡 주의 (단타용)</span>'
        elif not is_heavy_float and not is_low_volume and data['price'] > data['vwap']:
            verdict_color = "#4CAF50"
            verdict_bg = "rgba(76, 175, 80, 0.15)"
            verdict_title = "🔥 매수 고려 (찐 대장주 폼 유지 중)"
            verdict_desc = "물량도 가볍고, 수급도 살아있으며, VWAP 위에서 추세를 타고 있습니다."
            status_badge = '<span class="badge-green">🔵 관심 (대장주)</span>'
        else:
            verdict_color = "#A0A0A0"
            verdict_bg = "rgba(160, 160, 160, 0.15)"
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "조건이 완벽하지 않습니다. 굳이 리스크를 안고 도박할 필요는 없습니다."
            status_badge = '<span class="badge-orange">🟡 주의 (조건 미달)</span>'

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 태그 및 경고 블록
        st.markdown(status_badge, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
            <span class="pill-orange">휴면→각성 ⚡</span>
            <span class="pill-gray">살아있는 유량 ${(data['vol_30m']/1000000):.1f}M / 30분</span>
        """, unsafe_allow_html=True)
        
        for warning in data['warnings']:
            st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # [데이터 그리드 1] 거래 및 수급
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

        # 🛠️ [데이터 그리드 2] 동적 매매 레벨
        st.markdown("**매매 레벨 (규칙형 참고치)**")
        
        if data['price'] >= data['vwap']:
            # 강세 (VWAP 위)
            entry_price = data['vwap']
            pullback = entry_price * 0.95
            res_1 = data['price'] * 1.15
            res_2 = data['price'] * 1.30
            support = entry_price * 0.90
            stop_loss = entry_price * 0.85
        else:
            # 약세 (VWAP 아래)
            entry_price = data['price']
            pullback = entry_price * 0.95
            res_1 = data['vwap']
            res_2 = data['vwap'] * 1.10
            support = entry_price * 0.90
            stop_loss = entry_price * 0.85

        g2_c1, g2_c2, g2_c3 = st.columns(3)
        with g2_c1:
            st.markdown("<div class='metric-label'>진입가</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>${entry_price:.2f}</div>", unsafe_allow_html=True)
            st.markdown("<div class='metric-label' style='margin-top:10px;'>눌림목</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val val-orange'>${pullback:.2f}</div>", unsafe_allow_html=True)
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

        # [하단 버튼 및 주의사항]
        l_c1, l_c2, l_c3 = st.columns(3)
        with l_c1: st.button("📰 야후 뉴스", use_container_width=True)
        with l_c2: st.button("📄 공시·보도자료", use_container_width=True)
        with l_c3: st.button("🏢 기업정보", use_container_width=True)

        st.markdown(f"<div class='bottom-warning'>⏱️ 갱신 시점 = 장중(미완성) 봉 · 거래량은 마감까지 더 늘 수 있음 (현재 {int(data['volume']):,})</div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
