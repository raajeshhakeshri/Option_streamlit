import time
from datetime import datetime, timedelta, date

import altair as alt
import pandas as pd
import pyotp
import requests
import streamlit as st
from SmartApi import SmartConnect

# ============================ PAGE CONFIG ============================
st.set_page_config(
    page_title="Option Candle & Pair Analyzer",
    page_icon="馃搱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================== STYLING ==============================
st.markdown(
    """
<style>
.block-container {padding-top: 1.3rem; padding-bottom: 3rem; max-width: 1400px;}
#MainMenu, footer {visibility: hidden;}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.25);}
[data-testid="stSidebar"] .stButton > button {width: 100%;}

.hero {background: linear-gradient(120deg,#0b1f4d 0%,#1e3a8a 55%,#2563eb 100%); color:#fff;
       border-radius: 18px; padding: 22px 28px; margin-bottom: 18px;
       display:flex; justify-content:space-between; align-items:center; gap:16px;
       box-shadow: 0 10px 28px rgba(15,32,77,.28);}
.hero h1 {font-size: 1.6rem; margin: 0; padding: 0; color:#fff; font-weight: 700; letter-spacing:-.01em;}
.hero p  {margin: 5px 0 0 0; color:#c7d6fe; font-size:.92rem;}
.hero .chip {background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.28);
             padding:6px 14px; border-radius:999px; font-size:.74rem; font-weight:600;
             letter-spacing:.07em; white-space:nowrap;}

.kpi {border:1px solid rgba(128,128,128,.28); background: rgba(128,128,128,.07);
      border-radius:14px; padding:14px 16px; height:100%;}
.kpi-l {font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; opacity:.62; font-weight:600;}
.kpi-v {font-size:1.45rem; font-weight:700; margin-top:3px; line-height:1.15;}
.kpi-s {font-size:.78rem; opacity:.6; margin-top:3px;}
.kpi.good {border-color: rgba(22,163,74,.55); background: rgba(22,163,74,.09);}
.kpi.warn {border-color: rgba(217,119,6,.55); background: rgba(217,119,6,.09);}

.verdict {border-radius:14px; padding:16px 20px; margin: 4px 0 16px 0; display:flex; gap:16px; align-items:center;}
.verdict.hit  {background: rgba(22,163,74,.10); border:1px solid rgba(22,163,74,.5);}
.verdict.miss {background: rgba(217,119,6,.10); border:1px solid rgba(217,119,6,.5);}
.verdict .big {font-size:2rem; font-weight:800; line-height:1;}
.verdict .txt b {font-size:1rem;}
.verdict .txt span {opacity:.7; font-size:.86rem;}

.pairs {display:grid; grid-template-columns: repeat(auto-fill,minmax(290px,1fr)); gap:14px;}
.pair {border:1px solid rgba(128,128,128,.3); background: rgba(128,128,128,.06);
       border-radius:16px; padding:16px; border-left:5px solid #16a34a;}
.pair-top {display:flex; align-items:center; gap:8px;}
.tag {font-weight:700; font-size:.8rem; padding:4px 10px; border-radius:999px;}
.tag.ce {color:#15803d; background: rgba(22,163,74,.14);}
.tag.pe {color:#be185d; background: rgba(219,39,119,.14);}
.score {margin-left:auto; font-size:1.6rem; font-weight:800; color:#15803d;}
.score small {font-size:.8rem; opacity:.6; font-weight:600;}
.pair-sub {font-size:.8rem; opacity:.65; margin:8px 0 10px 0;}
.pair-grid {display:grid; grid-template-columns:1fr 1fr; gap:10px;}
.pair-grid div {border:1px solid rgba(128,128,128,.25); border-radius:12px; padding:9px 12px; background: rgba(128,128,128,.05);}
.pair-grid span {display:block; font-size:.66rem; text-transform:uppercase; letter-spacing:.08em; opacity:.6;}
.pair-grid b {font-size:1.12rem;}

.welcome {border:1px dashed rgba(128,128,128,.45); border-radius:16px; padding:34px 30px; text-align:center; margin-top:8px;}
.welcome h3 {margin:0 0 8px 0;}
.welcome p {opacity:.7; margin:0;}
.section-title {font-size:.78rem; text-transform:uppercase; letter-spacing:.1em; opacity:.6; font-weight:700; margin: 18px 0 8px 0;}
.stTabs [data-baseweb="tab"] {font-weight:600; padding: 10px 18px;}
.small-note {font-size:.78rem; opacity:.6;}
</style>
""",
    unsafe_allow_html=True,
)

# ============================== SECRETS ==============================
API_KEY = st.secrets["angel"]["API_KEY"]
CLIENT_CODE = st.secrets["angel"]["CLIENT_CODE"]
PIN = st.secrets["angel"]["PIN"]
TOTP_SECRET = st.secrets["angel"]["TOTP_SECRET"]

# ============================== CONFIG ===============================
INDICES = {
    "NIFTY": dict(label="Nifty 50", venue="NSE 路 NFO", opt_exch="NFO", step=50,
                  hours=("09:15", "15:30"), session_open=(9, 15), default_strike=25000,
                  spot_exch="NSE", spot_token="99926000", spot_symbol="NIFTY"),
    "SENSEX": dict(label="Sensex", venue="BSE 路 BFO", opt_exch="BFO", step=100,
                   hours=("09:15", "15:30"), session_open=(9, 15), default_strike=82000,
                   spot_exch="BSE", spot_token="99919000", spot_symbol="SENSEX"),
    # MCX crude oil options (underlying = crude futures, so no spot index)
    "CRUDEOILM": dict(label="Crude Oil Mini", venue="MCX 路 10 bbl", opt_exch="MCX", step=50,
                      itype="OPTFUT", hours=("09:00", "23:50"), session_open=(9, 0),
                      default_strike=8000, strike_floor=1000),
    "CRUDEOIL": dict(label="Crude Oil", venue="MCX 路 100 bbl", opt_exch="MCX", step=50,
                     itype="OPTFUT", hours=("09:00", "23:50"), session_open=(9, 0),
                     default_strike=8000, strike_floor=1000),
}
N_AROUND = 3                 # strikes on each side
CALL_DELAY = 1.2             # seconds between API calls (Angel rate-limits aggressively)
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


# ============================ CORE FUNCTIONS =========================
def login():
    smart = SmartConnect(api_key=API_KEY)
    res = smart.generateSession(CLIENT_CODE, PIN, pyotp.TOTP(TOTP_SECRET).now())
    if not res or not res.get("status"):
        raise RuntimeError(f"Login failed: {res}")
    return smart


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_master():
    """Download Angel's instrument list once (cached 6 h) and keep only what we need."""
    df = pd.DataFrame(requests.get(SCRIP_URL, timeout=120).json())
    df = df[df["name"].isin(list(INDICES.keys())) & df["instrumenttype"].isin(["OPTIDX", "OPTFUT"])]
    return df[["token", "symbol", "name", "expiry", "strike", "exch_seg", "instrumenttype"]].copy()


def load_option_map(index_name, expiry_selection):
    """Return (expiry_date, {(strike, 'CE'/'PE'): (token, symbol)})."""
    df = load_master()
    cfg = INDICES[index_name]
    df = df[(df["instrumenttype"] == cfg.get("itype", "OPTIDX")) & (df["name"] == index_name)
            & (df["exch_seg"] == cfg["opt_exch"])].copy()
    df["expiry_d"] = pd.to_datetime(df["expiry"], format="%d%b%Y").dt.date
    df = df[df["expiry_d"] >= date.today()]
    expiries = sorted(df["expiry_d"].unique())
    if not expiries:
        raise RuntimeError(f"No running expiries found for {index_name}")

    if expiry_selection == "Next" and len(expiries) > 1:
        expiry = expiries[1]
    else:
        expiry = expiries[0]

    df = df[df["expiry_d"] == expiry]
    df["strike_f"] = df["strike"].astype(float) / 100.0
    if cfg.get("strike_floor"):                       # some MCX rows are not scaled by 100
        df["strike_f"] = df["strike_f"].where(df["strike_f"] >= cfg["strike_floor"],
                                              df["strike"].astype(float))
    df["otype"] = df["symbol"].str[-2:]
    cmap = {(r.strike_f, r.otype): (r.token, r.symbol) for r in df.itertuples()}
    return expiry, cmap


def fetch_candle(smart, exch, token, candle_start, session_open=(9, 15)):
    """Return dict of the 5-min candle starting at candle_start, else None."""
    frm = max(candle_start - timedelta(minutes=10),
              candle_start.replace(hour=session_open[0], minute=session_open[1]))
    params = {
        "exchange": exch,
        "symboltoken": token,
        "interval": "FIVE_MINUTE",
        "fromdate": frm.strftime("%Y-%m-%d %H:%M"),
        "todate": (candle_start + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M"),
    }
    for wait in (2, 4, 8):                            # retry with growing back-off
        try:
            res = smart.getCandleData(params)
        except Exception:
            time.sleep(wait)
            continue
        finally:
            time.sleep(CALL_DELAY)
        if res and res.get("status") and res.get("data") is not None:
            for ts, o, h, l, c, v in res["data"]:
                if datetime.fromisoformat(ts).replace(tzinfo=None) == candle_start:
                    return dict(open=o, high=h, low=l, close=c, volume=v)
            return None                               # no trade in that candle
        time.sleep(wait)
    return None


def compute_pairs(df):
    """
    Compare EVERY CE strike with EVERY PE strike in df (same candle).
     ce_count = number of PE {O,H,L,C} lying inside [CE low, CE high]
     pe_count = number of CE {O,H,L,C} lying inside [PE low, PE high]
     total    = ce_count + pe_count   (max 8)
    """
    cols = ["open", "high", "low", "close"]
    ce_df = df[df["type"] == "CE"].dropna(subset=cols)
    pe_df = df[df["type"] == "PE"].dropna(subset=cols)

    results = []
    for c in ce_df.itertuples(index=False):
        c_vals = [c.open, c.high, c.low, c.close]
        for p in pe_df.itertuples(index=False):
            p_vals = [p.open, p.high, p.low, p.close]
            ce_cnt = sum(c.low <= v <= c.high for v in p_vals)   # PE values inside CE range
            pe_cnt = sum(p.low <= v <= p.high for v in c_vals)   # CE values inside PE range
            results.append(dict(
                ce_strike=c.strike, pe_strike=p.strike,
                ce_count=ce_cnt, pe_count=pe_cnt, total=ce_cnt + pe_cnt,
                higher_high=max(c.high, p.high), lower_low=min(c.low, p.low)))
    return pd.DataFrame(results)


def matches_of(res, min_total):
    if res.empty:
        return res
    return res[res["total"] >= min_total].sort_values(
        ["total", "ce_strike", "pe_strike"], ascending=[False, True, True]).reset_index(drop=True)


# ============================== UI HELPERS ===========================
def show_df(obj, **kw):
    try:
        st.dataframe(obj, width="stretch", **kw)
    except Exception:
        st.dataframe(obj, use_container_width=True, **kw)


def show_chart(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except Exception:
        st.altair_chart(chart, use_container_width=True)


def kpi(label, value, sub="", tone=""):
    return (f'<div class="kpi {tone}"><div class="kpi-l">{label}</div>'
            f'<div class="kpi-v">{value}</div><div class="kpi-s">{sub}</div></div>')


def pair_card(r):
    return (
        '<div class="pair"><div class="pair-top">'
        f'<span class="tag ce">CE {int(r.ce_strike)}</span><span class="tag pe">PE {int(r.pe_strike)}</span>'
        f'<span class="score">{int(r.total)}<small>/8</small></span></div>'
        f'<div class="pair-sub">CE count {int(r.ce_count)} &nbsp;路&nbsp; PE count {int(r.pe_count)}</div>'
        '<div class="pair-grid">'
        f'<div><span>Higher high</span><b>{r.higher_high:,.2f}</b></div>'
        f'<div><span>Lower low</span><b>{r.lower_low:,.2f}</b></div>'
        '</div></div>'
    )


def wide_table(df):
    out = pd.DataFrame({"Strike": sorted(df["strike"].unique())}).set_index("Strike")
    for t in ("CE", "PE"):
        sub = df[df["type"] == t].set_index("strike")
        for v in ("open", "high", "low", "close"):
            out[f"{t} {v.title()}"] = sub[v]
    return out


def heatmap(res, min_total):
    base = alt.Chart(res).encode(
        x=alt.X("pe_strike:O", title="PE strike"),
        y=alt.Y("ce_strike:O", title="CE strike"),
    )
    rect = base.mark_rect().encode(
        color=alt.Color("total:Q", scale=alt.Scale(scheme="blues", domain=[0, 8]), title="Total"),
        tooltip=[alt.Tooltip("ce_strike:O", title="CE strike"), alt.Tooltip("pe_strike:O", title="PE strike"),
                 alt.Tooltip("ce_count:Q", title="CE count"), alt.Tooltip("pe_count:Q", title="PE count"),
                 alt.Tooltip("total:Q", title="Total"),
                 alt.Tooltip("higher_high:Q", title="Higher high", format=",.2f"),
                 alt.Tooltip("lower_low:Q", title="Lower low", format=",.2f")],
    )
    ring = base.mark_rect(fillOpacity=0, strokeWidth=3).encode(
        stroke=alt.condition(alt.datum.total >= min_total, alt.value("#16a34a"), alt.value("transparent")))
    text = base.mark_text(fontWeight="bold", fontSize=14).encode(
        text="total:Q",
        color=alt.condition(alt.datum.total >= 4, alt.value("white"), alt.value("#0f172a")))
    return (rect + ring + text).properties(height=400)


def range_chart(df):
    d = df.dropna(subset=["high", "low"]).copy()
    d["strike"] = d["strike"].astype(int)
    return alt.Chart(d).mark_bar(size=14).encode(
        x=alt.X("strike:O", title="Strike"),
        y=alt.Y("low:Q", title="Candle range (鈧?", scale=alt.Scale(zero=False)),
        y2="high:Q",
        xOffset="type:N",
        color=alt.Color("type:N", title="Type",
                        scale=alt.Scale(domain=["CE", "PE"], range=["#16a34a", "#db2777"])),
        tooltip=["type:N", "strike:O", "open:Q", "high:Q", "low:Q", "close:Q"],
    ).properties(height=320)


# =============================== HEADER ==============================
st.markdown(
    """
<div class="hero">
  <div>
    <h1>Option Candle &amp; Pair Analyzer</h1>
    <p>Angel One SmartAPI &nbsp;路&nbsp; Nifty 50 &nbsp;路&nbsp; Sensex &nbsp;路&nbsp; Crude Oil &nbsp;路&nbsp; Crude Oil Mini</p>
  </div>
  <div class="chip">5-MIN CANDLES 路 CE 脳 PE OVERLAP</div>
</div>
""",
    unsafe_allow_html=True,
)

# ============================== SIDEBAR ==============================
st.sidebar.markdown("### 鈿欙笍 Parameters")
index_name = st.sidebar.selectbox(
    "Market / Instrument", list(INDICES.keys()),
    format_func=lambda k: f"{INDICES[k]['label']}  路  {INDICES[k]['venue']}")
cfg = INDICES[index_name]
step = cfg["step"]


def make_times(start, end):
    t, e, out = datetime.strptime(start, "%H:%M"), datetime.strptime(end, "%H:%M"), []
    while t <= e:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=5)
    return out


time_options = make_times(*cfg["hours"])
is_mcx = cfg["opt_exch"] == "MCX"
t_text = st.sidebar.selectbox("Candle start time", options=time_options,
                              index=0 if is_mcx else 1, key=f"time_{index_name}")
_h, _m = map(int, t_text.split(":"))
_end = datetime(2000, 1, 1, _h, _m) + timedelta(minutes=5)
st.sidebar.caption(f"Candle window: {t_text} 鈥?{_end.strftime('%H:%M')}")

d_text = st.sidebar.date_input("Date", value=date.today(), max_value=date.today())
centre = st.sidebar.number_input(f"Centre strike (multiple of {step})", min_value=0,
                                 value=cfg["default_strike"], step=step, key=f"strike_{index_name}")
expiry_option = st.sidebar.radio("Expiry", ["Current", "Next"], horizontal=True)
if is_mcx:
    st.sidebar.caption("Crude oil options expire monthly: Current = nearest expiry, Next = the one after.")
min_total = st.sidebar.slider("Minimum total for a pair match", min_value=1, max_value=8, value=6)
run_button = st.sidebar.button("鈻? Run lookup & analysis", type="primary")
st.sidebar.markdown(
    '<div class="small-note">Strikes covered: centre 鈭? to +3 (7 strikes 脳 CE/PE = 14 contracts).</div>',
    unsafe_allow_html=True)

# ============================ EXECUTION FLOW =========================
if run_button:
    if centre % step != 0:
        st.error(f"{cfg['label']} strikes move in steps of {step}. Centre strike must be a multiple of {step}.")
    else:
        try:
            candle_start = datetime.combine(d_text, datetime.min.time()).replace(hour=_h, minute=_m)
            with st.status("Connecting to Angel One", expanded=True) as status:
                smart = login()
                st.write("鉁?Logged in")
                status.update(label="Loading option contracts鈥?)
                expiry, cmap = load_option_map(index_name, expiry_option)
                st.write(f"鉁?{cfg['label']} expiry ({expiry_option}): **{expiry}**")

                strikes = [centre + i * step for i in range(-N_AROUND, N_AROUND + 1)]
                rows, total_steps, current_step = [], len(strikes) * 2, 0
                bar = st.progress(0.0)
                for strike in strikes:
                    for otype in ("CE", "PE"):
                        current_step += 1
                        info = cmap.get((strike, otype))
                        if not info:
                            bar.progress(current_step / total_steps)
                            continue
                        token, symbol = info
                        status.update(label=f"Fetching {symbol}  ({current_step}/{total_steps})")
                        c = fetch_candle(smart, cfg["opt_exch"], token, candle_start, cfg["session_open"])
                        rows.append(dict(
                            candle_time=candle_start.strftime("%Y-%m-%d %H:%M"),
                            index=index_name, expiry=str(expiry), strike=int(strike), type=otype,
                            symbol=symbol,
                            open=c["open"] if c else None, high=c["high"] if c else None,
                            low=c["low"] if c else None, close=c["close"] if c else None,
                            volume=c["volume"] if c else None))
                        bar.progress(current_step / total_steps)

                df = pd.DataFrame(rows)
                if df.empty:
                    status.update(label="No contracts found for those inputs", state="error")
                    st.session_state.pop("result", None)
                    st.warning("No contracts were found for that strike / expiry. Check the strike level.")
                else:
                    df = df.sort_values(["strike", "type"]).reset_index(drop=True)
                    res = compute_pairs(df)
                    st.session_state["result"] = dict(
                        df=df, res=res, label=cfg["label"], index=index_name, expiry=expiry,
                        pick=expiry_option, day=d_text, start=t_text, end=_end.strftime("%H:%M"),
                        centre=int(centre), step=step)
                    status.update(label="Done", state="complete", expanded=False)
        except Exception as e:
            st.error(f"An error occurred: {e}")

# ============================== RESULTS ==============================
R = st.session_state.get("result")
tab_match, tab_data, tab_matrix, tab_track = st.tabs(
    ["馃幆  Matches", "馃搵  Candle data", "馃М  Pair matrix", "馃摗  Index tracker"])

if not R:
    for tab in (tab_match, tab_data, tab_matrix):
        with tab:
            st.markdown(
                '<div class="welcome"><h3>Ready when you are</h3>'
                '<p>Pick a market, candle time and centre strike in the sidebar, then click '
                '<b>Run lookup &amp; analysis</b>.</p></div>', unsafe_allow_html=True)
else:
    df, res = R["df"], R["res"]
    matched = matches_of(res, min_total)
    got = int(df["open"].notna().sum())
    best = int(res["total"].max()) if not res.empty else 0

    with tab_match:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(kpi("Market", R["label"], f"Expiry {R['expiry']} ({R['pick']})"), unsafe_allow_html=True)
        c2.markdown(kpi("Candle", f"{R['start']}鈥搟R['end']}", R["day"].strftime("%d %b %Y")), unsafe_allow_html=True)
        c3.markdown(kpi("Centre strike", f"{R['centre']:,}", f"鈭? 鈥?+3 路 step {R['step']}"), unsafe_allow_html=True)
        c4.markdown(kpi("Candles received", f"{got}/{len(df)}", "CE + PE contracts"), unsafe_allow_html=True)
        c5.markdown(kpi("Matched pairs", f"{len(matched)}", f"threshold 鈮?{min_total} 路 best {best}/8",
                        "good" if len(matched) else "warn"), unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        if res.empty:
            st.warning("No complete CE/PE candle data to compare. Some contracts returned no candle "
                       "(no trade, or Angel rate-limited the request). Try again in a minute.")
        elif matched.empty:
            st.markdown(
                f'<div class="verdict miss"><div class="big">{best}</div><div class="txt">'
                f'<b>No pair reached {min_total}</b><br><span>Best total found: {best} of 8 across '
                f'{len(res)} CE 脳 PE pairs. Try lowering the threshold in the sidebar.</span></div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="verdict hit"><div class="big">{len(matched)}</div><div class="txt">'
                f'<b>pair{"s" if len(matched) != 1 else ""} reached a total of {min_total} or more</b><br>'
                f'<span>Highest total {best}/8 路 {len(res)} CE 脳 PE pairs compared</span></div></div>',
                unsafe_allow_html=True)
            st.markdown('<div class="section-title">Top matching pairs</div>', unsafe_allow_html=True)
            st.markdown('<div class="pairs">' + "".join(pair_card(r) for r in matched.head(12).itertuples())
                        + "</div>", unsafe_allow_html=True)
            if len(matched) > 12:
                st.caption(f"Showing 12 of {len(matched)} pairs. See the Pair matrix tab for the full list.")

    with tab_data:
        st.markdown('<div class="section-title">OHLC by strike 路 CE and PE side by side</div>',
                    unsafe_allow_html=True)
        wide = wide_table(df)

        def hl(row):
            on = row.name == R["centre"]
            return ["background-color: rgba(30,58,138,.12); font-weight: 600" if on else "" for _ in row]

        show_df(wide.style.format("{:,.2f}", na_rep="鈥?).apply(hl, axis=1))
        st.caption("Highlighted row = centre strike. 鈥溾€撯€?means no candle was returned for that contract.")

        st.markdown('<div class="section-title">Candle range by strike</div>', unsafe_allow_html=True)
        try:
            show_chart(range_chart(df))
        except Exception:
            st.info("Range chart needs a newer Altair version. The table above has the same numbers.")

        with st.expander("Raw rows (symbols, volume)"):
            show_df(df, hide_index=True)
        st.download_button("猬?Download candle data (CSV)", df.to_csv(index=False).encode(),
                           file_name=f"candles_{R['index']}_{R['day']}_{R['start'].replace(':', '')}.csv",
                           mime="text/csv")

    with tab_matrix:
        if res.empty:
            st.warning("No complete CE/PE candle data to compare.")
        else:
            st.markdown('<div class="section-title">Total count per CE 脳 PE pair</div>', unsafe_allow_html=True)
            show_chart(heatmap(res, min_total))
            st.caption("Rows = CE strike, columns = PE strike. Each cell = CE count + PE count (max 8). "
                       "Green outline = reached your threshold.")
            st.markdown('<div class="section-title">All pairs</div>', unsafe_allow_html=True)
            full = res.sort_values(["total", "ce_strike", "pe_strike"], ascending=[False, True, True]).rename(columns={
                "ce_strike": "CE strike", "pe_strike": "PE strike", "ce_count": "CE count",
                "pe_count": "PE count", "total": "Total", "higher_high": "Higher high", "lower_low": "Lower low"})
            show_df(full, hide_index=True)
            st.download_button("猬?Download all pairs (CSV)", full.to_csv(index=False).encode(),
                               file_name=f"pairs_{R['index']}_{R['day']}_{R['start'].replace(':', '')}.csv",
                               mime="text/csv")

# ============================ INDEX TRACKER ==========================
with tab_track:
    st.markdown('<div class="section-title">Spot index 路 CMP and 9:15 open (selected date)</div>',
                unsafe_allow_html=True)
    st.caption("Available for Nifty 50 and Sensex. Crude oil options trade on futures, so they have no spot index.")
    if st.button("馃攧  Get latest CMP & 9:15 open"):
        try:
            with st.spinner("Fetching index data鈥?):
                smart_temp = SmartConnect(api_key=API_KEY)
                res_temp = smart_temp.generateSession(CLIENT_CODE, PIN, pyotp.TOTP(TOTP_SECRET).now())
                if res_temp and res_temp.get("status"):
                    selected_date_str = d_text.strftime("%Y-%m-%d")
                    out = {}
                    for idx_key, idx_cfg in INDICES.items():
                        if "spot_token" not in idx_cfg:
                            continue
                        try:
                            ltp_res = smart_temp.ltpData(idx_cfg["spot_exch"], idx_cfg["spot_symbol"],
                                                         idx_cfg["spot_token"])
                            cmp_val = ltp_res["data"]["ltp"] if ltp_res and "data" in ltp_res else "N/A"
                            candle_params = {
                                "exchange": idx_cfg["spot_exch"],
                                "symboltoken": idx_cfg["spot_token"],
                                "interval": "ONE_MINUTE",
                                "fromdate": f"{selected_date_str} 09:15",
                                "todate": f"{selected_date_str} 09:16",
                            }
                            candle_res = smart_temp.getCandleData(candle_params)
                            open_val = "N/A"
                            if candle_res and "data" in candle_res and candle_res["data"]:
                                open_val = candle_res["data"][0][1]        # index 1 is open price
                            out[idx_key] = (cmp_val, open_val, selected_date_str)
                        except Exception as e_inner:
                            out[idx_key] = ("error", str(e_inner), selected_date_str)
                    st.session_state["tracker"] = out
                else:
                    st.error("Failed to login to Angel One API.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    T = st.session_state.get("tracker")
    if T:
        cols = st.columns(len(T))
        for col, (k, (cmp_val, open_val, dstr)) in zip(cols, T.items()):
            if cmp_val == "error":
                col.error(f"{INDICES[k]['label']}: {open_val}")
                continue
            chg = ""
            try:
                chg = f"{float(cmp_val) - float(open_val):+,.2f} vs open"
            except Exception:
                pass
            col.markdown(kpi(INDICES[k]["label"], f"{cmp_val}", f"9:15 open ({dstr}): {open_val} 路 {chg}"),
                         unsafe_allow_html=True)

st.markdown("<div class='small-note' style='margin-top:30px;text-align:center'>"
            "Data from Angel One SmartAPI 路 For analysis only, not investment advice.</div>",
            unsafe_allow_html=True)
