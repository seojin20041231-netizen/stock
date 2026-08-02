import streamlit as st
import pandas as pd
import numpy as np
import time
from tvDatafeed import TvDatafeed, Interval

# --- [1] 기본 설정 및 트레이딩뷰 연결 ---
st.set_page_config(page_title="프리마켓 갭앤고 대장주 스캐너", layout="wide")

# API 키 없이 익명 모드로 접속
@st.cache_resource
def get_tv_client():
    return TvDatafeed()

tv = get_tv_client()

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

# --- [2] 트레이딩뷰 수집 엔진 ---
@st.cache_data(ttl=30)
def analyze_ticker_tv(ticker_symbol):
    try:
        # 거래소 자동 탐색 (NASDAQ -> NYSE -> AMEX)
        exchanges = ['NASDAQ', 'NYSE', 'AMEX']
        df_1m = None
        
        for ex in exchanges:
            try:
                data = tv.get_hist(symbol=ticker_symbol, exchange=ex, interval=Interval.in_1_minute, n_bars=500)
                if data is not None and not data.empty:
                    df_1m = data
                    break
            except Exception:
                continue

        if df_1m is None or df_1m.empty:
            return None

        # 데이터 추출
        current_price = df_1m['close'].iloc[-1]
        
        # 최근 프리마켓/당일 데이터 (마지막 300개 봉 기준)
        df_recent = df_1m.tail(300)
        today_volume = df_recent['volume'].sum()
        pm_high = df_recent['high'].max()
        pm_low = df_recent['low'].min()
        
        # VWAP 계산
        tp = (df_recent['high'] + df_recent['low'] + df_recent['close']) / 3
        cum_v = df_recent['volume'].cumsum()
        vwap_series = (tp * df_recent['volume']).cumsum() / np.where(cum_v == 0, 1, cum_v)
        vwap = vwap_series.iloc[-1]
        
        # 등락률 및 PMH 거리 계산
        first_price = df_recent['open'].iloc[0]
        change_pct = ((current_price - first_price) / first_price * 100) if first_price else 0
        dist_to_pmh = ((pm_high - current_price) / current_price * 100) if current_price else 0

        # 거래량 가속도 (최근 5분 vs 이전 5분)
        recent_vol = df_1m['volume'].tail(5).mean()
        prev_vol = df_1m['volume'].iloc[-10:-5].mean() if len(df_1m) >= 10 else 1
        vol_accel = recent_vol > (prev_vol * 1.3)

        # 정밀 스코어링
        score = 0
        if today_volume >= 500_000: score += 25
        elif today_volume >= 100_000: score += 10
        
        if current_price >= vwap: score += 30      # 생명선(VWAP) 필수 지지
        if dist_to_pmh <= 3.0: score += 25         # PMH 바짝 밀착
        if vol_accel: score += 10                  # 오픈 직전 거래량 솟구침
        if change_pct >= 15: score += 10           # 갭상승 모멘텀

        # 등급 판정
        if score >= 80 and current_price >= vwap:
            tier = "S급 (진대장주)"
        elif score >= 60 and current_price >= vwap:
            tier = "A급 (돌파셋업)"
        elif current_price < vwap:
            tier = "F급 (절대금지)"
        else:
            tier = "B급 (관망권장)"

        return {
            'ticker': ticker_symbol, 'price': current_price, 'change': change_pct,
            'volume': today_volume, 'vwap': vwap, 'pm_high': pm_high, 'pm_low': pm_low,
            'dist_pmh': dist_to_pmh, 'vol_accel': vol_accel, 'score': score, 'tier': tier
        }
    except Exception as e:
        return None

# --- [3] UI 화면 구성 ---
st.title("🚀 미국 프리마켓 대장주 판독기")
st.markdown("<span style='font-size: 13px; color: #888;'>소스: TradingView Real-time | API 키 없음 (100% 무료)</span>", unsafe_allow_html=True)
st.markdown("---")

input_tickers = st.text_input("🔍 프리마켓 급등 종목들을 입력하세요 (쉼표 구분)", "TGHL, FFIE, HOLO, GME")
ticker_list = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

if ticker_list:
    with st.spinner("트레이딩뷰 실시간 1분봉 수급 분석 중..."):
        results = []
        for t in ticker_list:
            res = analyze_ticker_tv(t)
            if res:
                results.append(res)
    
    if not results:
        st.error("종목 데이터를 불러올 수 없습니다. 입력한 티커가 미국 상장 종목인지 확인하세요.")
    else:
        df_res = pd.DataFrame(results).sort_values(by="score", ascending=False).reset_index(drop=True)

        st.subheader("🏆 대장주 실시간 순위 리더보드")
        display_df = pd.DataFrame({
            '순위': [f"#{i+1}" for i in range(len(df_res))],
            '티커': df_res['ticker'],
            '판정 등급': df_res['tier'],
            '점수': df_res['score'].apply(lambda x: f"{x}점"),
            '현재가': df_res['price'].apply(lambda x: f"${x:.2f}"),
            '모멘텀': df_res['change'].apply(lambda x: f"{x:+.1f}%"),
            'Pre 거래량': df_res['volume'].apply(lambda x: f"{int(x/1000):,}K" if x < 1000000 else f"{x/1000000:.2f}M"),
            'PMH 거리': df_res['dist_pmh'].apply(lambda x: f"{x:.1f}%"),
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
        
        if data['volume'] >= 500_000: tags_html += '<span class="pill pill-green">🌊 거래량 50만주 이상</span>'
        if data['dist_pmh'] <= 3.0: tags_html += '<span class="pill pill-green">⚔️ PMH 3% 이내 바짝 밀착</span>'
        if data['vol_accel']: tags_html += '<span class="pill pill-purple">⚡ 최근 5분 거래량 가속중</span>'

        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if data['price'] < data['vwap']:
            v_color, v_bg = "#FF5252", "rgba(255, 82, 82, 0.15)"
            v_title, v_desc = "🚨 세력 이탈 (VWAP 하방)", "가격이 생명선(VWAP) 아래에 있습니다. 장 열리고 폭락할 위험이 매우 높습니다."
        elif data['tier'] in ["S급 (진대장주)", "A급 (돌파셋업)"]:
            v_color, v_bg = "#00E676", "rgba(0, 230, 118, 0.15)"
            v_title, v_desc = f"🔥 {data['tier']} - 슈팅 돌파 셋업", "PMH(고점) 근처에서 VWAP 위를 지지하고 있습니다. 본장 시작과 동시에 20~30% 슈팅 타겟입니다."
        else:
            v_color, v_bg = "#FFB020", "rgba(255, 176, 32, 0.15)"
            v_title, v_desc = "🤔 수급 미달 (관망)", "상승 탄력이나 거래량이 부족합니다. 굳이 매수하지 마세요."

        st.markdown(f"""
        <div style="border: 2px solid {v_color}; background-color: {v_bg}; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <h4 style="color: {v_color}; margin-top: 0px; margin-bottom: 5px;">{v_title}</h4>
            <span style="font-size: 14px; color: #E0E0E0;">{v_desc}</span>
        </div>
        """, unsafe_allow_html=True)

        vol_str = f"{data['volume']/1_000_000:.2f}M" if data['volume'] >= 1_000_000 else f"{int(data['volume']/1000):,}K"
        
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("<div class='metric-label'>Pre 누적 거래량</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{vol_str}</div>", unsafe_allow_html=True)
        with g2:
            st.markdown("<div class='metric-label'>PMH(전고점)까지 거리</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-val'>{data['dist_pmh']:.1f}%</div>", unsafe_allow_html=True)

        st.markdown("<br>**🎯 초단타 대응 기준 가격**", unsafe_allow_html=True)
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
