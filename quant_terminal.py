import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# --- [1] 페이지 및 기본 설정 ---
st.set_page_config(page_title="미국 급등주 AI 판독기", layout="centered")

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
    .longterm-box { background-color: #262626; padding: 15px; border-radius: 8px; border-left: 4px solid #7B1FA2; margin-top: 15px;}
    .whale-box { background-color: #1A237E; padding: 15px; border-radius: 8px; border-left: 4px solid #5C6BC0; margin-top: 15px; color: #E8EAF6;}
    .whale-check { display: flex; justify-content: space-between; font-size: 13px; margin-top: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px;}
</style>
""", unsafe_allow_html=True)

# --- [2] 데이터 수집 및 분석 ---
@st.cache_data(ttl=60)
def get_stock_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # 단기 5분봉 (오늘) & 장기 일봉 (6개월 - 매집 분석용)
    hist_5m = ticker.history(period="1d", interval="5m")
    hist_daily = ticker.history(period="6mo", interval="1d")
    
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    if hist_5m.empty or hist_daily.empty or current_price == 0:
        return None

    prev_close = info.get('previousClose', 0.0)
    market_cap = info.get('marketCap', 0)
    float_shares = info.get('floatShares', info.get('sharesOutstanding', 1))
    volume_today = info.get('regularMarketVolume', 0)
    high_52w = info.get('fiftyTwoWeekHigh', 0.0)
    ma_200 = info.get('twoHundredDayAverage', 0.0)

    # 1. 단기 분석 (VWAP, 수급)
    v = hist_5m['Volume']
    tp = (hist_5m['High'] + hist_5m['Low'] + hist_5m['Close']) / 3
    vwap = (tp * v).cumsum() / v.cumsum()
    vwap = vwap.iloc[-1] if not vwap.empty else current_price
    recent_hist = hist_5m.tail(6)
    vol_30m = (recent_hist['Close'] * recent_hist['Volume']).sum()

    # 2. 🕵️‍♂️ 세력 매집 분석 (일봉 기반 4가지 지표)
    # 지표 1: OBV 계산 및 다이버전스 확인
    change = hist_daily['Close'].diff()
    direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
    hist_daily['OBV'] = (hist_daily['Volume'] * direction).cumsum()
    
    obv_30d = hist_daily['OBV'].tail(30)
    price_30d = hist_daily['Close'].tail(30)
    # OBV는 상승/유지되는데 주가는 하락/횡보 중인가?
    obv_divergence = obv_30d.iloc[-1] >= obv_30d.iloc[0] and price_30d.iloc[-1] <= price_30d.iloc[0]

    # 지표 2: 매집봉 (윗꼬리) 횟수 (최근 60일)
    hist_daily['Upper_Wick'] = hist_daily['High'] - hist_daily[['Open', 'Close']].max(axis=1)
    hist_daily['Body'] = abs(hist_daily['Open'] - hist_daily['Close'])
    vol_avg_20 = hist_daily['Volume'].rolling(20).mean()
    # 윗꼬리가 몸통보다 2배 이상 길고, 거래량이 평균 이상인 캔들
    hist_daily['Wick_Signal'] = (hist_daily['Upper_Wick'] > hist_daily['Body'] * 2) & (hist_daily['Volume'] > vol_avg_20)
    accumulation_wicks = hist_daily['Wick_Signal'].tail(60).sum()
    has_wicks = accumulation_wicks >= 2

    # 지표 3: 거래량 씨 마름 (최근 5일 vs 60일 평균)
    vol_5d_avg = hist_daily['Volume'].tail(5).mean()
    vol_60d_avg = hist_daily['Volume'].tail(60).mean()
    volume_dry = vol_5d_avg < (vol_60d_avg * 0.4) if vol_60d_avg > 0 else False

    # 지표 4: 수급 폭발(명분 준비) - 최근 10일 내 거래량 5배 이상 터진 날이 있는가?
    vol_spike = (hist_daily['Volume'].tail(10) > (vol_avg_20.tail(10) * 5)).any()

    # 매집 스코어 계산 (100점 만점)
    whale_score = 0
    if obv_divergence: whale_score += 30
    if has_wicks: whale_score += 30
    if volume_dry: whale_score += 20
    if vol_spike: whale_score += 20

    # 3. 기본 리스크 분석
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
    turnover_rate = volume_today / float_shares if float_shares else 0
    drop_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w else 0

    warnings = []
    if current_price < 1.0: warnings.append("⚠️ $1 미만 (나스닥 상장유지 요건 위험)")
    if float_shares > 20_000_000: warnings.append(f"⚠️ 무거운 유통물량 ({float_shares/1000000:.1f}M) - 슈팅 탄력 둔화")
    if drop_from_high < -80: warnings.append(f"⚠️ 전고점 대비 {abs(drop_from_high):.0f}% 폭락 상태 (악성 매물대 주의)")

    return {
        'price': current_price, 'krw': current_price * 1350, 'change': change_pct,
        'market_cap': market_cap, 'float': float_shares, 'volume': volume_today,
        'turnover': turnover_rate, 'warnings': warnings,
        'vwap': vwap, 'vol_30m': vol_30m,
        'high_52w': high_52w, 'ma_200': ma_200, 'drop_from_high': drop_from_high,
        # 세력 분석 데이터
        'whale_score': whale_score, 'obv_div': obv_divergence, 'wicks': int(accumulation_wicks), 
        'has_wicks': has_wicks, 'vol_dry': volume_dry, 'vol_spike': vol_spike
    }

# --- [3] UI 렌더링 ---
st.title("🚀 미국 급등주 AI 판독기 (Pro)")
target_ticker = st.text_input("종목 티커 입력 (예: CISS, FFIE)", "CISS").upper()

if target_ticker:
    with st.spinner("호가, 수급, 장기 추세 및 세력 매집 흔적 분석 중..."):
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
        
        # 🎯 [데스 필터] 매매 판정
        is_under_vwap = data['price'] < data['vwap']
        is_heavy_float = data['float'] > 20_000_000 if data['float'] else False
        is_low_volume = data['vol_30m'] < 1_000_000

        if is_under_vwap and (is_heavy_float or is_low_volume):
            verdict_color = "#FF5252"; verdict_bg = "rgba(255, 82, 82, 0.15)"
            verdict_title = "🚨 절대 매수 금지 (설거지 위험 99%)"
            verdict_desc = "고점 찍고 세력이 넘기는 중이거나 수급이 말랐습니다. 쳐다보지도 마세요."
            status_badge = '<span class="badge-red">🔴 회피 (설거지)</span>'
        elif is_under_vwap:
            verdict_color = "#FFB020"; verdict_bg = "rgba(255, 176, 32, 0.15)"
            verdict_title = "⚠️ 관망 (투심 꺾임, 낙폭 과대 단타만)"
            verdict_desc = "평균 단가(VWAP) 아래로 밀렸습니다. 확실하게 VWAP을 다시 뚫기 전까지는 위험합니다."
            status_badge = '<span class="badge-orange">🟡 주의 (단타용)</span>'
        elif not is_heavy_float and not is_low_volume and data['price'] > data['vwap']:
            verdict_color = "#4CAF50"; verdict_bg = "rgba(76, 175, 80, 0.15)"
            verdict_title = "🔥 매수 고려 (찐 대장주 폼 유지 중)"
            verdict_desc = "물량도 가볍고, 수급도 살아있으며, VWAP 위에서 추세를 타고 있습니다."
            status_badge = '<span class="badge-green">🔵 관심 (대장주)</span>'
        else:
            verdict_color = "#A0A0A0"; verdict_bg = "rgba(160, 160, 160, 0.15)"
            verdict_title = "🤔 애매함 (패스 권장)"
            verdict_desc = "조건이 완벽하지 않습니다. 굳이 리스크를 안고 도박할 필요는 없습니다."
            status_badge = '<span class="badge-orange">🟡 주의 (조건 미달)</span>'

        st.markdown(f"""
        <div style="border: 2px solid {verdict_color}; background-color: {verdict_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {verdict_color}; margin-top: 0px; margin-bottom: 5px;">{verdict_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{verdict_desc}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(status_badge, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
            <span class="pill-orange">휴면→각성 ⚡</span>
            <span class="pill-gray">살아있는 유량 ${(data['vol_30m']/1000000):.1f}M / 30분</span>
        """, unsafe_allow_html=True)
        
        for warning in data['warnings']:
            st.markdown(f"<div class='warning-block'>{warning}</div>", unsafe_allow_html=True)
            
        st.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
        
        # [데이터 그리드 1] 당일 거래 및 수급
        g1_c1, g1_c2, g1_c3, g1_c4 = st.columns(4)
        with g1_c1:
            st.markdown("<div class='metric-label'>당일 등락률</div>", unsafe_allow_html=True)
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

        # 🕵️‍♂️ [신규 기능] 세력 매집 및 D-Day 판독기
        whale_color = "#4CAF50" if data['whale_score'] >= 70 else "#FFB020" if data['whale_score'] >= 40 else "#FF5252"
        st.markdown(f"""
        <div class="whale-box">
            <h5 style="margin-top: 0px; margin-bottom: 5px; color: #C5CAE9;">🕵️‍♂️ 세력 매집 및 슈팅 임박 판독</h5>
            <div style="font-size: 20px; font-weight: bold; margin-bottom: 10px;">매집 스코어: <span style="color: {whale_color};">{data['whale_score']} / 100점</span></div>
            
            <div class="whale-check">
                <span>1. OBV 다이버전스 (주가는 횡보/하락, 수급은 우상향)</span>
                <strong>{"✅ 포착됨" if data['obv_div'] else "❌ 없음"}</strong>
            </div>
            <div class="whale-check">
                <span>2. 바닥권 매집봉 출현 (최근 60일 내 윗꼬리 캔들)</span>
                <strong>{"✅ 포착 ("+str(data['wicks'])+"회)" if data['has_wicks'] else "❌ 없음"}</strong>
            </div>
            <div class="whale-check">
                <span>3. 거래량 씨 마름 (시중에 유통 물량 잠김 현상)</span>
                <strong>{"✅ 잠김 확인" if data['vol_dry'] else "❌ 변동성 큼"}</strong>
            </div>
            <div class="whale-check" style="border-bottom: none;">
                <span>4. 슈팅 전조 현상 (최근 수급 대폭발 이력 유무)</span>
                <strong>{"✅ 포착됨" if data['vol_spike'] else "❌ 없음"}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 🛠️ [데이터 그리드 2] 동적 매매 레벨
        st.markdown("**매매 레벨 (규칙형 참고치)**")
        if data['price'] >= data['vwap']:
            entry_price, pullback = data['vwap'], data['vwap'] * 0.95
            res_1, res_2 = data['price'] * 1.15, data['price'] * 1.30
            support, stop_loss = entry_price * 0.90, entry_price * 0.85
        else:
            entry_price, pullback = data['price'], data['price'] * 0.95
            res_1, res_2 = data['vwap'], data['vwap'] * 1.10
            support, stop_loss = entry_price * 0.90, entry_price * 0.85

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

        # [하단 버튼]
        st.markdown("<br>", unsafe_allow_html=True)
        l_c1, l_c2, l_c3 = st.columns(3)
        with l_c1: st.button("📰 야후 뉴스", use_container_width=True)
        with l_c2: st.button("📄 공시·보도자료", use_container_width=True)
        with l_c3: st.button("🏢 기업정보", use_container_width=True)

        st.markdown(f"<div class='bottom-warning'>⏱️ 갱신 시점 = 장중(미완성) 봉 · 현재 거래량 {int(data['volume']):,}</div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
