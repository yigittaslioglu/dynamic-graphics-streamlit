import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import pandas_ta as ta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed



st.set_page_config(page_title="Raporlar", page_icon=":bar_chart:", layout="wide")  # bulamadım şimdilik

st.sidebar.header("Sayfa Seçin")  # sidebar ana naşlık

page = st.sidebar.radio(                                                         
   "Sayfalar:",                                                               # sidebar alt başlık ve burada oluşturmak istediğim raporları yazıyorum ve sayfarı oluşturuyor. 
  ("CRYPTO ANALYS", "BIST ANALYS", "SINGLE ANALYS")      # radio metodu yuvarlak seçenek seçtirerek ayrı ayrı sayfalar oluşturuyor.  
)

if page == "CRYPTO ANALYS":

    # -------------------------------------------------
    # Rate‑limit dostu session
    # -------------------------------------------------
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Streamlit Kripto App)"
    })

    st.set_page_config(page_title="Kripto Takip", page_icon="Chart", layout="wide")
    st.title("4Crypto Price Chart")

    # -------------------------------------------------
    # Coin listesi (tek istek, cache)
    # -------------------------------------------------
    @st.cache_data(ttl=3600)
    def get_coin_list():
        all_data = []
        base_url = "https://api.coingecko.com/api/v3/coins/markets"
        for page in range(1, 5):
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 250,
                "page": page,
                "sparkline": False,
            }
            try:
                time.sleep(1.4)  # sadece coin listesi için
                r = session.get(base_url, params=params, timeout=15)
                if r.status_code == 429:
                    st.error("Rate limit! 1‑2 dakika bekleyin.")
                    return pd.DataFrame()
                if r.status_code != 200:
                    continue
                data = r.json()
                if not data:
                    break
                all_data.extend(data)
                if len(data) < 250:
                    break
            except:
                continue
        if not all_data:
            st.error("Coin listesi alınamadı.")
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df = df[["id", "symbol", "name", "current_price", "market_cap_rank"]]
        exclude = ["bridged", "wrapped", "vault", "token", "usd", "usdc", "usdt", "tether", "stake", "stable"]
        mask = ~df["id"].str.contains("|".join(exclude), case=False, na=False)
        df = df[mask].sort_values("market_cap_rank").reset_index(drop=True)
        return df

    with st.spinner("Coin listesi yükleniyor…"):
        coin_df = get_coin_list()
    if coin_df.empty:
        st.stop()

    # -------------------------------------------------
    # Zaman aralığı (90 gün varsayılan)
    # -------------------------------------------------
    day_options = {"1 Gün": 1, "7 Gün": 7, "30 Gün": 30, "90 Gün": 90, "180 Gün": 180, "365 Gün": 365}
    selected_day_label = st.selectbox("Zaman Aralığı:", list(day_options.keys()), index=3)
    days = day_options[selected_day_label]

    # -------------------------------------------------
    # 4 kripto seçimi
    # -------------------------------------------------
    col1, col2 = st.columns(2)
    with col1:
        coin_opts = coin_df["name"] + " (" + coin_df["symbol"].str.upper() + ")"
        coin1_label = st.selectbox("1. Kripto Para", coin_opts, index=0)
        coin1_id = coin_df.loc[coin_opts == coin1_label, "id"].values[0]
        coin2_label = st.selectbox("2. Kripto Para", coin_opts, index=1)
        coin2_id = coin_df.loc[coin_opts == coin2_label, "id"].values[0]
    with col2:
        coin3_label = st.selectbox("3. Kripto Para", coin_opts, index=2)
        coin3_id = coin_df.loc[coin_opts == coin3_label, "id"].values[0]
        coin4_label = st.selectbox("4. Kripto Para", coin_opts, index=3)
        coin4_id = coin_df.loc[coin_opts == coin4_label, "id"].values[0]

    # -------------------------------------------------
    # TEK SEFERDE 4 COİN VERİSİ ÇEK (PARALEL)
    # -------------------------------------------------
    @st.cache_data(ttl=300)
    def fetch_price_data(coin_id, days):
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days}
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                return coin_id, None
            data = r.json()
            if "prices" not in data or not data["prices"]:
                return coin_id, None
            return coin_id, data
        except:
            return coin_id, None

    # Tüm verileri aynı anda çek
    coin_ids = [coin1_id, coin2_id, coin3_id, coin4_id]
    labels = [coin1_label, coin2_label, coin3_label, coin4_label]

    with st.spinner("4 coin verisi paralel çekiliyor…"):
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_coin = {executor.submit(fetch_price_data, cid, days): (cid, lbl) for cid, lbl in zip(coin_ids, labels)}
            for future in as_completed(future_to_coin):
                coin_id, data = future.result()
                label = future_to_coin[future][1]
                results[coin_id] = (label, data)

    # -------------------------------------------------
    # Grafik fonksiyonu
    # -------------------------------------------------
    def create_chart(coin_id, label, days):
        _, data = results.get(coin_id, (None, None))
        if not data:
            fig = go.Figure()
            fig.add_annotation(text="Veri alınamadı", xref="paper", yref="paper",
                            x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="red"))
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=30, r=30, t=70, b=30))
            return fig, None

        df = pd.DataFrame(data["prices"], columns=["timestamp", "Close"])
        df["timestamp"] = df["timestamp"].apply(lambda x: datetime.fromtimestamp(x / 1000))
        df.set_index("timestamp", inplace=True)

        try:
            df["SMA20"] = ta.sma(df["Close"], length=20)
            df["SMA50"] = ta.sma(df["Close"], length=50)
            df["SMA100"] = ta.sma(df["Close"], length=100)
            df["SMA200"] = ta.sma(df["Close"], length=200)
        except:
            pass

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Close"],
            mode="lines", name="Fiyat",
            line=dict(color="#00CED1", width=2),
            fill="tozeroy", fillcolor="rgba(0, 206, 209, 0.05)"
        ))

        sma_cfg = [("SMA20", "#ADD8E6", "SMA20"), ("SMA50", "#FFFF99", "SMA50"),
                ("SMA100", "#FFA500", "SMA100"), ("SMA200", "#FF0000", "SMA200")]
        for col, colr, name in sma_cfg:
            if col in df.columns and df[col].notna().any():
                fig.add_trace(go.Scatter(x=df.index, y=df[col], mode="lines", name=name,
                                    line=dict(color=colr, width=1.5)))

        fig.update_layout(
            title=f'{label.split(" (")[0]} – {days} Gün',
            title_font=dict(size=16, family="Arial", color="#FFFFFF"),
            xaxis=dict(tickangle=45, tickfont=dict(size=10, color="#CCCCCC"),
                    gridcolor="rgba(128,128,128,0.2)"),
            yaxis=dict(tickfont=dict(size=10, color="#CCCCCC"),
                    gridcolor="rgba(128,128,128,0.2)"),
            hovermode="x unified", showlegend=True,
            legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0.5)"),
            template="plotly_dark",
            margin=dict(l=20, r=20, t=50, b=20),
            height=380
        )
        return fig, df["Close"].iloc[-1]

    # -------------------------------------------------
    # 2×2 grafik düzeni
    # -------------------------------------------------
    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        fig1, p1 = create_chart(coin1_id, coin1_label, days)
        st.plotly_chart(fig1, use_container_width=True, key="chart_1")
        st.metric(coin1_label.split(" (")[0], f"${p1:,.6f}" if p1 else "N/A")
    with c2:
        fig2, p2 = create_chart(coin2_id, coin2_label, days)
        st.plotly_chart(fig2, use_container_width=True, key="chart_2")
        st.metric(coin2_label.split(" (")[0], f"${p2:,.6f}" if p2 else "N/A")

    c3, c4 = st.columns(2)
    with c3:
        fig3, p3 = create_chart(coin3_id, coin3_label, days)
        st.plotly_chart(fig3, use_container_width=True, key="chart_3")
        st.metric(coin3_label.split(" (")[0], f"${p3:,.6f}" if p3 else "N/A")
    with c4:
        fig4, p4 = create_chart(coin4_id, coin4_label, days)
        st.plotly_chart(fig4, use_container_width=True, key="chart_4")
        st.metric(coin4_label.split(" (")[0], f"${p4:,.6f}" if p4 else "N/A")


###################################################################################
###################################################################################
###################################################################################
###################################################################################


if page == "BIST ANALYS":
    
    import streamlit as st
    import yfinance as yf
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta
    import pandas_ta as ta

    st.set_page_config(page_title="BIST 100 Takip", page_icon="Chart", layout="wide")
    st.title("4BIST ANALYS")

    # -------------------------------------------------
    # GÜNCEL BIST 100 LİSTESİ (2025 - 100 Hisse)
    # -------------------------------------------------
    @st.cache_data(ttl=3600)
    def get_bist100_stocks():
        bist100 = [
            "AKBNK.IS", "ASELS.IS", "BIMAS.IS", "EKGYO.IS", "EREGL.IS", "FROTO.IS",
            "GARAN.IS", "ISCTR.IS", "KCHOL.IS", "PETKM.IS", "SAHOL.IS", "SISE.IS",
            "TCELL.IS", "THYAO.IS", "TUPRS.IS", "VAKBN.IS", "YKBNK.IS", "ARCLK.IS",
            "HALKB.IS", "KOZAL.IS", "PGSUS.IS", "SASA.IS", "TAVHL.IS", "TOASO.IS",
            "TTKOM.IS", "VESBE.IS", "YATAS.IS", "ALARK.IS", "BRSAN.IS", "DOHOL.IS",
            "ENJSA.IS", "GUBRF.IS", "HEKTS.IS", "KARSN.IS", "KRDMD.IS", "OTKAR.IS",
            "OYAKC.IS", "QUAGR.IS", "SKBNK.IS", "TTRAK.IS", "ULKER.IS", "VESTL.IS",
            "ZOREN.IS", "AEFES.IS", "AKSA.IS", "AKSGY.IS", "ALGYO.IS", "AYGAZ.IS",
            "BAGFS.IS", "BLCYT.IS", "BRISA.IS", "CEMTS.IS", "CIMSA.IS", "DEVA.IS",
            "DOAS.IS", "ECILC.IS", "EGEEN.IS", "ENKAI.IS", "ERBOS.IS", "FENER.IS",
            "GENIL.IS", "GESAN.IS", "GOLTS.IS", "GOZDE.IS", "GSDHO.IS", "INDES.IS",
            "ISGYO.IS", "ISMEN.IS", "KONTR.IS", "KORDS.IS", "KUTPO.IS", "MAVI.IS",
            "MGROS.IS", "NTHOL.IS", "ODAS.IS", "PRKME.IS", "RALYH.IS", "SOKM.IS",
            "TKFEN.IS", "TRKCM.IS", "TURSG.IS", "ZOREN.IS", "AFYON.IS", "ANHYT.IS",
            "BAGFS.IS", "BLCYT.IS", "BRISA.IS", "CEMTS.IS", "CIMSA.IS", "DEVA.IS"
        ]
        # Tekrarları temizle
        bist100 = sorted(set(bist100))
        df = pd.DataFrame(bist100, columns=["symbol"])
        df["name"] = df["symbol"].str.replace(".IS", "")
        return df

    with st.spinner("BIST 100 listesi yükleniyor…"):
        stock_df = get_bist100_stocks()

    # -------------------------------------------------
    # Zaman aralığı (90 gün varsayılan)
    # -------------------------------------------------
    day_options = {"1 Gün": 1, "7 Gün": 7, "30 Gün": 30, "90 Gün": 90, "180 Gün": 180, "365 Gün": 365}
    selected_day_label = st.selectbox("Zaman Aralığı:", list(day_options.keys()), index=3)
    days = day_options[selected_day_label]

    # -------------------------------------------------
    # 4 hisse seçimi
    # -------------------------------------------------
    col1, col2 = st.columns(2)
    with col1:
        stock_opts = stock_df["name"] + " (" + stock_df["symbol"].str.replace(".IS", "") + ")"
        stock1_label = st.selectbox("1. Hisse", stock_opts, index=0)
        stock1_symbol = stock_df.loc[stock_opts == stock1_label, "symbol"].values[0]
        stock2_label = st.selectbox("2. Hisse", stock_opts, index=1)
        stock2_symbol = stock_df.loc[stock_opts == stock2_label, "symbol"].values[0]
    with col2:
        stock3_label = st.selectbox("3. Hisse", stock_opts, index=2)
        stock3_symbol = stock_df.loc[stock_opts == stock3_label, "symbol"].values[0]
        stock4_label = st.selectbox("4. Hisse", stock_opts, index=3)
        stock4_symbol = stock_df.loc[stock_opts == stock4_label, "symbol"].values[0]

    # -------------------------------------------------
    # yfinance ile veri çek (SMA200 için +200 gün fazladan)
    # -------------------------------------------------
    @st.cache_data(ttl=300)
    def get_stock_data(symbol, display_days):
        try:
            end_date = datetime.now()
            # SMA200 için 200 gün fazladan veri al
            start_date = end_date - timedelta(days=display_days + 210)
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")
            if df.empty:
                return None
            df = df[['Close']].copy()
            df.index = df.index.tz_localize(None)
            # Sadece istenen günleri göster
            df = df.tail(display_days)
            return df
        except Exception as e:
            st.error(f"Veri hatası ({symbol}): {e}")
            return None

    # -------------------------------------------------
    # Grafik fonksiyonu (SMA200 her zaman görünür)
    # -------------------------------------------------
    def create_chart(symbol, label, display_days):
        df = get_stock_data(symbol, display_days)
        if df is None or df.empty:
            fig = go.Figure()
            fig.add_annotation(text="Veri alınamadı", xref="paper", yref="paper",
                            x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="red"))
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=30, r=30, t=70, b=30))
            return fig, None

        # SMA'lar (200 gün geriye veri olduğu için her zaman hesaplanır)
        df_full = get_stock_data(symbol, 400)  # SMA200 için yeterli veri
        if df_full is not None and len(df_full) >= 200:
            df["SMA20"] = ta.sma(df_full["Close"], length=20).tail(display_days)
            df["SMA50"] = ta.sma(df_full["Close"], length=50).tail(display_days)
            df["SMA100"] = ta.sma(df_full["Close"], length=100).tail(display_days)
            df["SMA200"] = ta.sma(df_full["Close"], length=200).tail(display_days)
        else:
            # Yetersiz veri → sadece mevcut olanları hesapla
            df["SMA20"] = ta.sma(df["Close"], length=20)
            df["SMA50"] = ta.sma(df["Close"], length=50)
            df["SMA100"] = ta.sma(df["Close"], length=100)

        fig = go.Figure()

        # Fiyat (turkuaz + dolgu)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Close"],
            mode="lines", name="Fiyat (TL)",
            line=dict(color="#00CED1", width=2),
            fill="tozeroy", fillcolor="rgba(0, 206, 209, 0.05)"
        ))

        # SMA'lar
        sma_cfg = [
            ("SMA20", "#ADD8E6", "SMA20"),
            ("SMA50", "#FFFF99", "SMA50"),
            ("SMA100", "#FFA500", "SMA100"),
            ("SMA200", "#FF0000", "SMA200")
        ]
        for col, colr, name in sma_cfg:
            if col in df.columns and df[col].notna().any():
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[col],
                    mode="lines", name=name,
                    line=dict(color=colr, width=1.5)
                ))

        # Layout (kripto ile %100 aynı)
        fig.update_layout(
            title=f'{label.split(" (")[0]} – {display_days} Gün',
            title_font=dict(size=16, family="Arial", color="#FFFFFF"),
            xaxis=dict(tickangle=45, tickfont=dict(size=10, color="#CCCCCC"),
                    gridcolor="rgba(128,128,128,0.2)"),
            yaxis=dict(tickfont=dict(size=10, color="#CCCCCC"),
                    gridcolor="rgba(128,128,128,0.2)"),
            hovermode="x unified", showlegend=True,
            legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0.5)"),
            template="plotly_dark",
            margin=dict(l=20, r=20, t=50, b=20),
            height=380
        )
        current_price = df["Close"].iloc[-1]
        return fig, current_price

    # -------------------------------------------------
    # 2×2 grafik düzeni
    # -------------------------------------------------
    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        with st.spinner(f"{stock1_label} yükleniyor…"):
            fig1, p1 = create_chart(stock1_symbol, stock1_label, days)
            st.plotly_chart(fig1, use_container_width=True, key="chart_1")
            st.metric(stock1_label.split(" (")[0], f"₺{p1:,.2f}" if p1 else "N/A")

    with c2:
        with st.spinner(f"{stock2_label} yükleniyor…"):
            fig2, p2 = create_chart(stock2_symbol, stock2_label, days)
            st.plotly_chart(fig2, use_container_width=True, key="chart_2")
            st.metric(stock2_label.split(" (")[0], f"₺{p2:,.2f}" if p2 else "N/A")

    c3, c4 = st.columns(2)
    with c3:
        with st.spinner(f"{stock3_label} yükleniyor…"):
            fig3, p3 = create_chart(stock3_symbol, stock3_label, days)
            st.plotly_chart(fig3, use_container_width=True, key="chart_3")
            st.metric(stock3_label.split(" (")[0], f"₺{p3:,.2f}" if p3 else "N/A")

    with c4:
        with st.spinner(f"{stock4_label} yükleniyor…"):
            fig4, p4 = create_chart(stock4_symbol, stock4_label, days)
            st.plotly_chart(fig4, use_container_width=True, key="chart_4")
            st.metric(stock4_label.split(" (")[0], f"₺{p4:,.2f}" if p4 else "N/A")




#########################################################################
#########################################################################
#########################################################################
#########################################################################


if page == "SINGLE ANALYS":

    import streamlit as st
    import yfinance as yf
    import requests
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta
    import pandas_ta as ta
    import time

    # -------------------------------------------------
    # Session (CoinGecko için)
    # -------------------------------------------------
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Streamlit App)"})

    st.set_page_config(page_title="Hisse & Kripto Takip", page_icon="Chart", layout="wide")
    st.title("1SINGLE ANALYS")

    # -------------------------------------------------
    # 1. Hisse mi, Kripto mu?
    # -------------------------------------------------
    analysis_type = st.selectbox("Analiz Türü:", ["Kripto Para", "BIST 100 Hisse"], index=0)

    # -------------------------------------------------
    # 2. Zaman aralığı (90 gün varsayılan)
    # -------------------------------------------------
    day_options = {"1 Gün": 1, "7 Gün": 7, "30 Gün": 30, "90 Gün": 90, "180 Gün": 180, "365 Gün": 365}
    selected_day_label = st.selectbox("Zaman Aralığı:", list(day_options.keys()), index=3)
    days = day_options[selected_day_label]

    # -------------------------------------------------
    # 3. Veri Kaynağı: KRİPTO (CoinGecko)
    # -------------------------------------------------
    @st.cache_data(ttl=3600)
    def get_crypto_list():
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1}
        try:
            time.sleep(1.2)
            r = session.get(url, params=params, timeout=10)
            if r.status_code != 200:
                return pd.DataFrame()
            data = r.json()
            df = pd.DataFrame(data)
            df = df[["id", "symbol", "name"]]
            exclude = ["bridged", "wrapped", "vault", "token", "usd", "usdc", "usdt", "tether", "stake", "stable"]
            mask = ~df["id"].str.contains("|".join(exclude), case=False, na=False)
            df = df[mask].sort_values("name")
            return df
        except:
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_crypto_data(coin_id, days):
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days + 210}  # SMA200 için fazladan
        try:
            time.sleep(1.2)
            r = session.get(url, params=params, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            if "prices" not in data or len(data["prices"]) == 0:
                return None
            return data
        except:
            return None

    # -------------------------------------------------
    # 4. Veri Kaynağı: HİSSE (yfinance + BIST 100)
    # -------------------------------------------------
    @st.cache_data(ttl=3600)
    def get_bist100_stocks():
        bist100 = [
            "AKBNK.IS", "ASELS.IS", "BIMAS.IS", "EKGYO.IS", "EREGL.IS", "FROTO.IS",
            "GARAN.IS", "ISCTR.IS", "KCHOL.IS", "PETKM.IS", "SAHOL.IS", "SISE.IS",
            "TCELL.IS", "THYAO.IS", "TUPRS.IS", "VAKBN.IS", "YKBNK.IS", "ARCLK.IS",
            "HALKB.IS", "KOZAL.IS", "PGSUS.IS", "SASA.IS", "TAVHL.IS", "TOASO.IS",
            "TTKOM.IS", "VESBE.IS", "YATAS.IS", "ALARK.IS", "BRSAN.IS", "DOHOL.IS",
            "ENJSA.IS", "GUBRF.IS", "HEKTS.IS", "KARSN.IS", "KRDMD.IS", "OTKAR.IS",
            "OYAKC.IS", "QUAGR.IS", "SKBNK.IS", "TTRAK.IS", "ULKER.IS", "VESTL.IS",
            "ZOREN.IS", "AEFES.IS", "AKSA.IS", "AKSGY.IS", "ALGYO.IS", "AYGAZ.IS",
            "BAGFS.IS", "BRISA.IS", "CEMTS.IS", "CIMSA.IS", "DEVA.IS", "DOAS.IS",
            "ECILC.IS", "EGEEN.IS", "ENKAI.IS", "ERBOS.IS", "FENER.IS", "GENIL.IS",
            "GESAN.IS", "GOLTS.IS", "GOZDE.IS", "GSDHO.IS", "INDES.IS", "ISGYO.IS",
            "ISMEN.IS", "KONTR.IS", "KORDS.IS", "KUTPO.IS", "MAVI.IS", "MGROS.IS",
            "NTHOL.IS", "ODAS.IS", "PRKME.IS", "RALYH.IS", "SOKM.IS", "TKFEN.IS",
            "TRKCM.IS", "TURSG.IS"
        ]
        df = pd.DataFrame(sorted(set(bist100)), columns=["symbol"])
        df["name"] = df["symbol"].str.replace(".IS", "")
        return df

    @st.cache_data(ttl=300)
    def get_stock_data(symbol, display_days):
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=display_days + 210)
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")
            if df.empty:
                return None
            df = df[['Close']].copy()
            df.index = df.index.tz_localize(None)
            return df.tail(display_days)
        except:
            return None

    # -------------------------------------------------
    # 5. Seçim: Kripto mu, Hisse mi?
    # -------------------------------------------------
    if analysis_type == "Kripto Para":
        crypto_df = get_crypto_list()
        if crypto_df.empty:
            st.error("Kripto listesi alınamadı.")
            st.stop()
        crypto_opts = crypto_df["name"] + " (" + crypto_df["symbol"].str.upper() + ")"
        selected_crypto_label = st.selectbox("Kripto Para Seç:", crypto_opts)
        selected_id = crypto_df.loc[crypto_opts == selected_crypto_label, "id"].values[0]

        with st.spinner(f"{selected_crypto_label} verisi çekiliyor…"):
            raw_data = get_crypto_data(selected_id, days)
        if not raw_data:
            st.error("Veri alınamadı.")
            st.stop()

        df = pd.DataFrame(raw_data["prices"], columns=["timestamp", "Close"])
        df["timestamp"] = df["timestamp"].apply(lambda x: datetime.fromtimestamp(x / 1000))
        df.set_index("timestamp", inplace=True)
        currency = "USD"
        price_label = f"${df['Close'].iloc[-1]:,.6f}"

    else:  # BIST 100 Hisse
        stock_df = get_bist100_stocks()
        stock_opts = stock_df["name"] + " (" + stock_df["symbol"].str.replace(".IS", "") + ")"
        selected_stock_label = st.selectbox("Hisse Seç:", stock_opts)
        selected_symbol = stock_df.loc[stock_opts == selected_stock_label, "symbol"].values[0]

        with st.spinner(f"{selected_stock_label} verisi çekiliyor…"):
            df = get_stock_data(selected_symbol, days)
        if df is None or df.empty:
            st.error("Veri alınamadı.")
            st.stop()
        currency = "TL"
        price_label = f"₺{df['Close'].iloc[-1]:,.2f}"

    # -------------------------------------------------
    # 6. SMA'lar (her zaman 200 gün veri ile)
    # -------------------------------------------------
    try:
        # Kripto: +210 gün veri alındı
        # Hisse: get_stock_data zaten +210 gün aldı
        full_df = df.copy()
        if analysis_type == "Kripto Para":
            full_raw = get_crypto_data(selected_id, 400)
            if full_raw:
                full_df = pd.DataFrame(full_raw["prices"], columns=["timestamp", "Close"])
                full_df["timestamp"] = full_df["timestamp"].apply(lambda x: datetime.fromtimestamp(x / 1000))
                full_df.set_index("timestamp", inplace=True)

        df["SMA20"] = ta.sma(full_df["Close"], length=20).tail(days)
        df["SMA50"] = ta.sma(full_df["Close"], length=50).tail(days)
        df["SMA100"] = ta.sma(full_df["Close"], length=100).tail(days)
        df["SMA200"] = ta.sma(full_df["Close"], length=200).tail(days)
    except:
        pass

    # -------------------------------------------------
    # 7. Grafik (Tüm ekranı kaplar)
    # -------------------------------------------------
    fig = go.Figure()

    # Fiyat (turkuaz + dolgu)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"],
        mode="lines", name=f"Fiyat ({currency})",
        line=dict(color="#00CED1", width=2),
        fill="tozeroy", fillcolor="rgba(0, 206, 209, 0.05)"
    ))

    # SMA'lar
    sma_cfg = [
        ("SMA20", "#ADD8E6", "SMA20"),
        ("SMA50", "#FFFF99", "SMA50"),
        ("SMA100", "#FFA500", "SMA100"),
        ("SMA200", "#FF0000", "SMA200")
    ]
    for col, colr, name in sma_cfg:
        if col in df.columns and df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col],
                mode="lines", name=name,
                line=dict(color=colr, width=1.5)
            ))

    # Layout (tam ekran, karanlık tema)
    fig.update_layout(
        title=f"{selected_crypto_label if analysis_type == 'Kripto Para' else selected_stock_label} – Son {days} Gün",
        title_font=dict(size=24, family="Arial", color="#FFFFFF"),
        xaxis_title="Tarih", xaxis_title_font=dict(size=16, color="#CCCCCC"),
        yaxis_title=f"Fiyat ({currency})", yaxis_title_font=dict(size=16, color="#CCCCCC"),
        xaxis=dict(tickangle=45, tickfont=dict(size=12, color="#CCCCCC"),
                gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(tickfont=dict(size=12, color="#CCCCCC"),
                gridcolor="rgba(128,128,128,0.2)"),
        hovermode="x unified", showlegend=True,
        legend=dict(font=dict(size=12), bgcolor="rgba(0,0,0,0.5)"),
        template="plotly_dark",
        height=700,
        margin=dict(l=60, r=60, t=100, b=60)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Güncel Fiyat
    st.metric("Güncel Fiyat", price_label)