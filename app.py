"""DWC26 Reservoir Intelligence Suite - Streamlit prototype of the 3-page Power BI dashboard.

Run:   pip install streamlit plotly pandas numpy
       streamlit run app.py

Data:  the CSVs in ./data (copied from outputs/deliverable, outputs/results, outputs/explore).
       Three optional files unlock the history-dependent charts; create them with
       `python export_powerbi_data.py` from the repo root after `python src/run_pipeline.py`:
         observed_quarterly.csv  - 1998-2008 observed rates, cumulatives, water injection
         cases.csv               - the 4 uncertain parameters for all 100 cases
         pca_variance.csv        - cumulative explained variance per PCA component
       Without them the app still runs; affected charts fall back to what the core CSVs support
       and say so on the chart.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------------------------------
SLATE, SLATE2, CRIMSON, CANVAS = "#1E2229", "#2A2F3A", "#ED1B2D", "#F4F6F9"
OIL, WATER, GAS, LIQUID = "#2E7D32", "#0288D1", "#D32F2F", "#6D4C41"
INK, MUTED, GRID = "#1E2229", "#5F6673", "#E3E7ED"
PHASE_COLOR = {"Oil": OIL, "Water": WATER, "Gas": GAS}

# Facts from the pipeline's grid check (explore.py -> grid_check on '03 Train Cases 1.xlsx').
# Confirm these against your own run before presenting; they are not in the CSV outputs.
GRID_FACTS = {"active_cells": 42512}

st.set_page_config(page_title="DWC26 Reservoir Intelligence Suite", page_icon="🛢️", layout="wide")

st.markdown(f"""
<style>
  .stApp {{ background:{CANVAS}; }}
  header[data-testid="stHeader"] {{ background:{SLATE}; }}
  .block-container {{ padding-top:3.2rem; padding-bottom:2rem; max-width:1500px; }}
  .banner {{ background:linear-gradient(90deg,{SLATE} 0%,{SLATE2} 100%); color:#fff; border-radius:10px;
            padding:14px 22px; margin-bottom:10px; border-left:6px solid {CRIMSON}; }}
  .banner h1 {{ font-size:1.35rem; margin:0; color:#fff; letter-spacing:.3px; }}
  .banner p {{ margin:2px 0 0 0; color:#C9CED8; font-size:.86rem; }}
  .kpi {{ background:#fff; border-radius:10px; padding:12px 14px; border-top:4px solid {CRIMSON};
          box-shadow:0 1px 3px rgba(30,34,41,.08); height:100%; }}
  .kpi .lbl {{ color:{MUTED}; font-size:.74rem; text-transform:uppercase; letter-spacing:.6px; }}
  .kpi .val {{ color:{INK}; font-size:1.55rem; font-weight:700; line-height:1.25; }}
  .kpi .sub {{ color:{MUTED}; font-size:.76rem; }}
  .qa {{ background:#fff; border:1px solid #D5DAE2; border-radius:22px; padding:6px 14px; }}
  .qa-ans {{ background:{SLATE2}; color:#EEF1F5; border-radius:8px; padding:10px 14px; font-size:.88rem;
             margin-top:6px; }}
  .ai {{ background:{SLATE}; color:#E8EBF0; border-radius:10px; padding:16px 20px; border-left:6px solid {CRIMSON};
         margin-top:8px; font-size:.92rem; line-height:1.55; }}
  .ai h4 {{ color:#fff; margin:0 0 6px 0; font-size:1rem; }}
  .ai b {{ color:#fff; }}
  .note {{ color:{MUTED}; font-size:.78rem; margin-top:-6px; }}
  div[data-testid="stSegmentedControl"] button {{ font-weight:600; }}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
SEARCH = [Path(os.environ["DWC_DATA"])] if "DWC_DATA" in os.environ else []
SEARCH += [APP_DIR / "data", APP_DIR, APP_DIR.parent / "outputs" / "powerbi",
           APP_DIR.parent / "outputs" / "deliverable", APP_DIR.parent / "outputs" / "results",
           APP_DIR.parent / "outputs" / "explore"]


def find(name: str) -> Path | None:
    return next((d / name for d in SEARCH if (d / name).exists()), None)


def read(name: str, **kw) -> pd.DataFrame | None:
    p = find(name)
    return pd.read_csv(p, **kw) if p else None


@st.cache_data
def load():
    d = {n: read(f"{n}.csv") for n in [
        "selected_cases", "original_cases_ranking", "method_sensitivity", "model_comparison",
        "proxy_optimised_sets", "pca_check", "backtest_methods"]}
    d["sensitivity"] = read("sensitivity.csv", index_col=0)
    d["after_porosity"] = read("after_porosity.csv", index_col=0)
    d["forecast"] = read("forecast_2008_2028.csv", parse_dates=["date"])
    d["observed"] = read("observed_quarterly.csv", parse_dates=["date"])      # optional
    d["cases"] = read("cases.csv")                                             # optional
    d["pca_variance"] = read("pca_variance.csv")                               # optional
    missing = [k for k in ("selected_cases", "forecast", "original_cases_ranking") if d[k] is None]
    if missing:
        st.error(f"Required files not found: {missing}. Put the pipeline CSVs in {APP_DIR / 'data'}.")
        st.stop()

    f = d["forecast"].rename(columns={"oil_cum_stb": "oil_cum", "water_cum_stb": "water_cum",
                                      "gas_cum_mscf": "gas_cum", "oil_rate_stbd": "oil_rate",
                                      "water_rate_stbd": "water_rate", "gas_rate_mscfd": "gas_rate"})
    f["label"] = "Case " + f["rank"].astype(str)
    f["liquid_rate"] = f.oil_rate + f.water_rate
    f["gor"] = f.gas_rate / f.oil_rate * 1000            # scf/STB
    d["forecast"] = f

    # Start-of-forecast (2008-01-01) cumulative: observed if available, else back-calculated
    # from the first forecast quarter (cum at 2008-04 minus 91 days at the 2008-04 rate).
    obs = d["observed"]
    first = f[f.date == f.date.min()].set_index("case")
    if obs is not None:
        o = obs.sort_values("date").iloc[-1]
        base = {p: pd.Series(o[f"{p}_cum"], index=first.index) for p in ("oil", "gas", "water")}
        d["base_source"] = f"observed {o.date:%b %Y}"
    else:
        base = {p: first[f"{p}_cum"] - first[f"{p}_rate"] * 91 for p in ("oil", "gas", "water")}
        d["base_source"] = "estimated from first forecast quarter (add observed_quarterly.csv for exact)"
    d["base"] = base
    return d


D = load()
F, SEL, RANK, OBS, CASES = D["forecast"], D["selected_cases"], D["original_cases_ranking"], D["observed"], D["cases"]
LAST = F[F.date == F.date.max()].set_index("case")
SEL = SEL.set_index("case")
if CASES is not None:
    SEL = SEL.join(CASES.set_index("case")[["fault_trans", "poro_mult", "perm_mult", "aquifer_pv"]])
    RANK = RANK.merge(CASES, on="case", how="left", suffixes=("", "_p"))


# ----------------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------------
def style(fig: go.Figure, title: str, h: int = 340, legend: bool = True) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=14, color=INK), x=0.01, y=0.97),
        height=h, margin=dict(l=10, r=10, t=52, b=10), paper_bgcolor="#fff", plot_bgcolor="#fff",
        font=dict(family="Segoe UI, Arial", size=11, color=INK), showlegend=legend,
        legend=dict(orientation="h", y=-0.24, x=0, font=dict(size=10)), hoverlabel=dict(font_size=11))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor="#C5CBD3")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor="#C5CBD3")
    return fig


def show(fig, note: str | None = None):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    if note:
        st.markdown(f"<div class='note'>{note}</div>", unsafe_allow_html=True)


def kpi(col, label, value, sub=""):
    col.markdown(f"<div class='kpi'><div class='lbl'>{label}</div><div class='val'>{value}</div>"
                 f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)


def banner(title, sub):
    st.markdown(f"<div class='banner'><h1>{title}</h1><p>{sub}</p></div>", unsafe_allow_html=True)


def ai_box(title, html):
    st.markdown(f"<div class='ai'><h4>✦ {title}</h4>{html}</div>", unsafe_allow_html=True)


def mm(x):
    return f"{x / 1e6:,.2f}"


def with_history(case: int) -> pd.DataFrame:
    """Observed 1998-2008 + forecast 2008-2028 for one case, one continuous frame."""
    fc = F[F.case == case][["date", "oil_cum", "gas_cum", "water_cum", "oil_rate", "gas_rate",
                            "water_rate", "liquid_rate", "water_cut", "gor"]].assign(src="Forecast")
    if OBS is None:
        return fc
    h = OBS.copy()
    h["liquid_rate"] = h.oil_rate + h.water_rate
    h["water_cut"] = h.water_rate / h.liquid_rate
    h["gor"] = h.gas_rate / h.oil_rate * 1000
    h["src"] = "Observed"
    return pd.concat([h[fc.columns], fc], ignore_index=True)


# Q&A stand-in: in Power BI this is the native Q&A visual. Here a small keyword router answers
# the questions stakeholders typically type, from the same numbers the charts use.
def qa(q: str, ctx: dict) -> str:
    q = q.lower()
    if not q.strip():
        return ""
    o = LAST.oil_cum
    rules = [
        (("best", "lowest j", "mismatch", "top case"),
         lambda: f"Best history match is template Case 1 (simulation #{SEL.index[0]}), "
                 f"J = {SEL.history_mismatch_J.iloc[0]:.4f}; the 10th pick has J = {SEL.history_mismatch_J.iloc[-1]:.4f}."),
        (("eur", "oil 2028", "reserves", "ultimate"),
         lambda: f"2028 cumulative oil ranges {mm(o.min())}–{mm(o.max())} MMSTB across the 10 cases "
                 f"(P50 {mm(o.median())} MMSTB)."),
        (("water cut", "watercut", "wct"),
         lambda: f"2028 water cut ranges {LAST.water_cut.min():.1%}–{LAST.water_cut.max():.1%}; "
                 f"it is {F[F.date == F.date.min()].water_cut.median():.1%} at the start of the forecast."),
        (("gas", "gor"),
         lambda: f"2028 gas cumulative P50 = {LAST.gas_cum.median() / 1e6:,.2f} Bcf; producing GOR is "
                 f"{F.gor.median():.0f} scf/STB throughout the forecast."),
        (("price", "cash", "npv", "revenue", "economic"),
         lambda: f"At ${ctx.get('price', 80)}/bbl the simplified 2008–2028 net cash flow is "
                 f"${ctx.get('ncf', 0) / 1e9:,.2f} B (NPV@{ctx.get('disc', 10)}% ${ctx.get('npv', 0) / 1e9:,.2f} B)."),
        (("model", "proxy", "gaussian", "surrogate", "ml"),
         lambda: "The Matérn-2.5 Gaussian Process is the proxy: 0.04% oil / 0.09% water error on 2008 totals "
                 "for the 15 unseen test cases, ~3x better than the next model (MLP)."),
        (("poro", "sensitiv", "parameter"),
         lambda: "Porosity multiplier alone explains 98.5% of the oil-2008 variation between cases; "
                 "permeability and aquifer size only appear in what is left over."),
        (("method", "extrapolat", "arps", "uncertain"),
         lambda: f"Across back-tested extrapolation methods 2028 oil spans "
                 f"{D['method_sensitivity'].oil_2028_mmstb_median.min():.1f}–{D['method_sensitivity'].oil_2028_mmstb_median.max():.1f} MMSTB."),
    ]
    for keys, fn in rules:
        if any(k in q for k in keys):
            return fn()
    return "Try: 'best case', 'oil EUR', 'water cut 2028', 'cash flow at this price', 'proxy accuracy', 'which parameter matters'."


def qa_bar(key: str, ctx: dict | None = None):
    c1, c2 = st.columns([0.04, 0.96])
    c1.markdown("<div style='font-size:1.6rem;margin-top:2px'>💬</div>", unsafe_allow_html=True)
    q = c2.text_input("Ask a question about your data", key=key, label_visibility="collapsed",
                      placeholder="Ask a question about your data — e.g. 'what is the oil EUR range?'")
    ans = qa(q, ctx or {})
    if ans:
        st.markdown(f"<div class='qa-ans'>{ans}</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------------------------
# Economics (simplified: revenue less lifting and produced-water handling; no capex, tax, royalty)
# ----------------------------------------------------------------------------------------------
def economics(price, gas_price, lift, water_cost, disc):
    rows = []
    for case, g in F.sort_values("date").groupby("case"):
        inc = {p: np.diff(np.r_[D["base"][p][case], g[f"{p}_cum"].values]) for p in ("oil", "gas", "water")}
        t = (g.date - pd.Timestamp("2008-01-01")).dt.days.values / 365.25 - 0.125   # mid-quarter
        dfac = 1 / (1 + disc / 100) ** t
        oil_rev, gas_rev = inc["oil"] * price, inc["gas"] * gas_price
        lift_c, wat_c = inc["oil"] * lift, inc["water"] * water_cost
        cf = oil_rev + gas_rev - lift_c - wat_c
        rows.append(dict(case=case, oil_rev=oil_rev.sum(), gas_rev=gas_rev.sum(), lift=lift_c.sum(),
                         water=wat_c.sum(), ncf=cf.sum(), npv=(cf * dfac).sum(),
                         inc_oil=inc["oil"].sum(), inc_gas=inc["gas"].sum(), inc_water=inc["water"].sum()))
    return pd.DataFrame(rows).set_index("case")


# ----------------------------------------------------------------------------------------------
# Header + page navigator
# ----------------------------------------------------------------------------------------------
PAGES = ["① Business & Commercial", "② Reservoir & Facilities", "③ Subsurface & ML Governance"]
nav = st.segmented_control("Page navigator", PAGES, default=PAGES[0], key="nav", label_visibility="collapsed")
page = nav or PAGES[0]
if OBS is None or CASES is None:
    st.caption("ℹ️ Running on core CSVs only. Add observed_quarterly.csv / cases.csv / pca_variance.csv "
               "(export_powerbi_data.py) to unlock 1998–2008 history, injection and parameter-sized charts.")


# ==============================================================================================
# PAGE 1 - Business & Commercial
# ==============================================================================================
def page1():
    banner("Component A — Business & Commercial Portal",
           "Upstream Asset Managers & Commercial Planners · 10 history-matched cases · forecast Apr 2008 – Jan 2028")

    c = st.columns([1.2, 1, 1.4])
    price = c[0].slider("Oil price ($/bbl)", 50, 110, 80, 5)
    phase = c[1].segmented_control("Phase", ["Oil", "Gas", "Water"], default="Oil") or "Oil"
    with c[2].expander("Economic assumptions", expanded=False):
        gas_price = st.slider("Gas price ($/MSCF)", 1.0, 8.0, 3.0, 0.5)
        lift = st.slider("Oil lifting cost ($/bbl)", 0.0, 30.0, 12.0, 1.0)
        water_cost = st.slider("Produced-water handling ($/bbl)", 0.0, 5.0, 1.5, 0.25)
        disc = st.slider("Discount rate (%)", 0, 15, 10, 1)

    econ = economics(price, gas_price, lift, water_cost, disc)
    p50_case = (LAST.oil_cum - LAST.oil_cum.median()).abs().idxmin()
    e50 = econ.loc[p50_case]
    ctx = dict(price=price, ncf=e50.ncf, npv=e50.npv, disc=disc)
    qa_bar("qa1", ctx)

    k = st.columns(5)
    o = LAST.oil_cum
    kpi(k[0], "2028 P50 Oil EUR", f"{mm(o.median())} MMSTB", f"range {mm(o.min())}–{mm(o.max())}")
    kpi(k[1], "Incremental Oil 2008–28", f"{mm(econ.inc_oil.median())} MMSTB",
        f"{econ.inc_oil.median() / o.median():.1%} of EUR still to produce")
    kpi(k[2], "2028 Gas EUR", f"{LAST.gas_cum.median() / 1e6:,.2f} Bcf", f"GOR {F.gor.median():.0f} scf/STB")
    kpi(k[3], "2028 Water EUR", f"{mm(LAST.water_cum.median())} MMSTB",
        f"water cut → {LAST.water_cut.median():.1%}")
    kpi(k[4], f"Net Cash Flow @ ${price}", f"${e50.ncf / 1e9:,.2f} B",
        f"NPV{disc} ${e50.npv / 1e9:,.2f} B · P50 case")
    st.write("")

    # --- G1 fan chart ---------------------------------------------------------------------------
    col = f"{phase.lower()}_cum"
    unit, scale = ("Bcf", 1e6) if phase == "Gas" else ("MMSTB", 1e6)
    g1 = go.Figure()
    piv = F.pivot(index="date", columns="case", values=col) / scale
    g1.add_trace(go.Scatter(x=piv.index, y=piv.max(axis=1), line=dict(width=0), showlegend=False, hoverinfo="skip"))
    g1.add_trace(go.Scatter(x=piv.index, y=piv.min(axis=1), fill="tonexty", line=dict(width=0),
                            fillcolor="rgba(237,27,45,.15)", name="10-case envelope"))
    for case in piv.columns:
        g1.add_trace(go.Scatter(x=piv.index, y=piv[case], mode="lines", line=dict(width=1, color=PHASE_COLOR[phase]),
                                opacity=.45, name=f"sim #{case}", showlegend=False))
    g1.add_trace(go.Scatter(x=piv.index, y=piv.median(axis=1), line=dict(width=3, color=PHASE_COLOR[phase]),
                            name="P50 forecast"))
    if OBS is not None:
        g1.add_trace(go.Scatter(x=OBS.date, y=OBS[col] / scale, mode="lines+markers", marker=dict(size=4),
                                line=dict(color=INK, width=2), name="Observed 1998–2008"))
    if phase == "Oil":
        ms = D["method_sensitivity"].oil_2028_mmstb_median
        g1.add_trace(go.Scatter(x=[F.date.max()], y=[ms.median()], mode="markers", marker=dict(color=CRIMSON, size=9),
                                error_y=dict(type="data", symmetric=False, array=[ms.max() - ms.median()],
                                             arrayminus=[ms.median() - ms.min()], color=CRIMSON, width=8),
                                name=f"Decline-method envelope 2028 ({ms.min():.1f}–{ms.max():.1f})"))
    g1.add_vline(x=F.date.min(), line=dict(dash="dot", color=MUTED))
    g1.update_yaxes(title=f"Cumulative {phase.lower()} ({unit})")
    hist_lbl = "Observed History → " if OBS is not None else ""
    show(style(g1, f"G1 · Cumulative {phase} — {hist_lbl}10-Case Forecast Fan to 2028", 380))

    a, b = st.columns(2)
    # --- G2 historical vs incremental -----------------------------------------------------------
    with a:
        rows = []
        for p, lab in (("oil", "Oil"), ("gas", "Gas"), ("water", "Water")):
            hist = D["base"][p].median()
            tot = LAST[f"{p}_cum"].median()
            rows.append((lab, hist / tot, 1 - hist / tot))
        df2 = pd.DataFrame(rows, columns=["phase", "hist_share", "inc_share"])
        g2 = go.Figure([
            go.Bar(y=df2.phase, x=df2.hist_share, orientation="h", name="Historical 1998–2008", marker_color=SLATE2,
                   text=[f"{v:.1%}" for v in df2.hist_share], textposition="inside"),
            go.Bar(y=df2.phase, x=df2.inc_share, orientation="h", name="Incremental 2008–2028",
                   marker_color=[OIL, GAS, WATER], text=[f"{v:.1%}" for v in df2.inc_share], textposition="inside")])
        g2.update_layout(barmode="stack")
        g2.update_yaxes(categoryorder="array", categoryarray=["Water", "Gas", "Oil"])
        g2.update_xaxes(tickformat=".0%", range=[0, 1])
        show(style(g2, "G2 · Historical vs Incremental Reserves (share of 2028 EUR)"),
             f"Oil is a mature, mostly-produced asset; water is mostly ahead. 2008 base: {D['base_source']}.")

    # --- G3 10-case EUR spread ------------------------------------------------------------------
    with b:
        v = LAST[col].reindex(SEL.index) / scale
        labels = [f"C{r}<br>#{c}" for r, c in zip(SEL["rank"], SEL.index)]
        spread = (v.max() - v.min()) / v.median()
        g3 = go.Figure(go.Bar(x=labels, y=v, marker_color=[CRIMSON if x == v.idxmax() or x == v.idxmin() else PHASE_COLOR[phase]
                                                          for x in v.index],
                              text=[f"{x:,.2f}" for x in v], textposition="outside"))
        g3.add_hline(y=v.median(), line=dict(dash="dash", color=INK), annotation_text=f"P50 {v.median():,.2f}", annotation_position="top left")
        pad = (v.max() - v.min()) * 0.6 + 1e-9
        g3.update_yaxes(range=[v.min() - pad, v.max() + pad], title=unit)
        show(style(g3, f"G3 · 2028 {phase} EUR by Case — spread {spread:.2%} of P50", legend=False),
             "Truncated axis to expose differences. Cases are ranked by history mismatch J (template order). "
             f"Spread excluding Case 2 (#73): {(v.drop(73).max() - v.drop(73).min()) / v.median():.2%}.")

    a, b = st.columns(2)
    # --- G4 waterfall ---------------------------------------------------------------------------
    with a:
        g4 = go.Figure(go.Waterfall(
            x=["Oil revenue", "Gas revenue", "Lifting OPEX", "Water handling", "Net cash flow"],
            measure=["relative", "relative", "relative", "relative", "total"],
            y=np.array([e50.oil_rev, e50.gas_rev, -e50.lift, -e50.water, 0]) / 1e6,
            text=[("−" if x < 0 else "") + f"${abs(x) / 1e6:,.0f}M" for x in (e50.oil_rev, e50.gas_rev, -e50.lift, -e50.water, e50.ncf)],
            increasing=dict(marker_color=OIL), decreasing=dict(marker_color=CRIMSON),
            totals=dict(marker_color=SLATE2), connector=dict(line=dict(color="#9AA1AC"))))
        g4.update_yaxes(title="US$ million (undiscounted)")
        show(style(g4, f"G4 · 20-Year Cash-Flow Bridge @ ${price}/bbl (P50 case)", legend=False),
             "Simplified: excludes capex, royalties and tax. Water handling is the cost that grows as water cut rises.")

    # --- G5 price sensitivity -------------------------------------------------------------------
    with b:
        prices = np.arange(50, 111, 5)
        g5 = go.Figure()
        for wc, dash, name in ((water_cost * 0.5, "dot", "Water cost −50%"), (water_cost, "solid", "Base"),
                               (water_cost * 2, "dash", "Water cost ×2")):
            y = [economics(p, gas_price, lift, wc, disc).loc[p50_case, "ncf"] / 1e9 for p in prices]
            g5.add_trace(go.Scatter(x=prices, y=y, mode="lines", line=dict(dash=dash, width=2.5 if dash == "solid" else 1.6,
                                                                         color=CRIMSON if dash == "solid" else SLATE2), name=name))
        g5.add_vline(x=price, line=dict(color=OIL, dash="dot"), annotation_text=f"${price}")
        g5.add_hline(y=0, line=dict(color=MUTED, width=1))
        g5.update_xaxes(title="Oil price ($/bbl)")
        g5.update_yaxes(title="Net cash flow (US$ B)")
        show(style(g5, "G5 · Net Cash-Flow Sensitivity to Oil Price & Water Cost"),
             f"Each $10/bbl adds ≈ ${econ.loc[p50_case, 'inc_oil'] * 10 / 1e6:,.0f}M; doubling water cost removes "
             f"≈ ${econ.loc[p50_case, 'inc_water'] * water_cost / 1e6:,.0f}M.")

    # --- G6 EUR vs water cut --------------------------------------------------------------------
    sz = SEL["aquifer_pv"] if "aquifer_pv" in SEL else pd.Series(1.0, index=SEL.index)
    g6 = go.Figure(go.Scatter(
        x=LAST.water_cut.reindex(SEL.index), y=LAST.oil_cum.reindex(SEL.index) / 1e6, mode="markers+text",
        text=[f"C{r}" for r in SEL["rank"]], textposition="top center",
        marker=dict(size=14 + 26 * (sz - sz.min()) / (sz.max() - sz.min() + 1e-12), color=SEL.history_mismatch_J,
                    colorscale=[[0, OIL], [0.5, "#F9A825"], [1, CRIMSON]], showscale=True,
                    colorbar=dict(title="J", thickness=10), line=dict(color=INK, width=1)),
        customdata=np.c_[SEL.index, sz], hovertemplate="sim #%{customdata[0]}<br>WCT %{x:.2%}<br>EUR %{y:.3f} MMSTB"
                                                       "<br>aquifer PV %{customdata[1]:.1f}<extra></extra>"))
    g6.update_xaxes(title="2028 water cut", tickformat=".2%")
    g6.update_yaxes(title="2028 oil EUR (MMSTB)")
    corr = np.corrcoef(LAST.water_cut.reindex(SEL.index), LAST.oil_cum.reindex(SEL.index))[0, 1]
    show(style(g6, f"G6 · Case EUR vs 2028 Water Cut — bubble = aquifer PV, colour = mismatch J (r = {corr:+.2f})", 360, legend=False),
         None if "aquifer_pv" in SEL else "Bubble size needs cases.csv (aquifer PV per case); sizes are uniform until it is added.")

    # --- AI commentary --------------------------------------------------------------------------
    be = (e50.water + e50.lift - e50.gas_rev) / e50.inc_oil   # oil price where NCF = 0
    ai_box("AI Commercial Commentary", f"""
      At <b>${price}/bbl</b> the P50 case (simulation #{p50_case}) returns a simplified 20-year net cash flow of
      <b>${e50.ncf / 1e9:,.2f} B</b> (NPV{disc} <b>${e50.npv / 1e9:,.2f} B</b>). Oil revenue is
      {e50.oil_rev / (e50.oil_rev + e50.gas_rev):.0%} of gross; water handling consumes
      <b>{e50.water / (e50.oil_rev + e50.gas_rev):.1%}</b> of gross revenue, rising as water cut climbs from
      {F[F.date == F.date.min()].water_cut.median():.0%} to {LAST.water_cut.median():.0%}.
      The cash-flow break-even oil price is <b>${be:,.1f}/bbl</b> under these assumptions.<br>
      Reserves risk is <b>low between cases</b>: 2028 oil spans only {mm(o.min())}–{mm(o.max())} MMSTB
      ({(o.max() - o.min()) / o.median():.2%}), but <b>method risk dominates</b> — decline-curve alternatives span
      {D['method_sensitivity'].oil_2028_mmstb_median.min():.1f}–{D['method_sensitivity'].oil_2028_mmstb_median.max():.1f} MMSTB,
      roughly {(D['method_sensitivity'].oil_2028_mmstb_median.max() - D['method_sensitivity'].oil_2028_mmstb_median.min()) / ((o.max() - o.min()) / 1e6):.0f}×
      the case spread. Plan facilities and budgets on the P50 profile; carry the method envelope as the reserves range.""")


# ==============================================================================================
# PAGE 2 - Reservoir & Facilities
# ==============================================================================================
def page2():
    banner("Component B1 — Reservoir Engineering & Facilities",
           "Production & Facility Engineers · per-case rates, liquid handling, water cut and GOR control")
    opts = {f"Case {r}  (sim #{c})": c for r, c in zip(SEL["rank"], SEL.index)}
    t = st.columns([1.4, 1, 1, 1, 1])
    case = opts[t[0].selectbox("History-matched case", list(opts))]
    s, last = SEL.loc[case], LAST.loc[case]
    kpi(t[1], "History mismatch J", f"{s.history_mismatch_J:.4f}",
        f"rank {int(s['rank'])} of 100 · {s.split} set")
    kpi(t[2], "2028 water cut", f"{last.water_cut:.1%}", f"{F[(F.case == case)].water_cut.iloc[0]:.1%} at Apr 2008")
    kpi(t[3], "Final oil rate (Jan 2028)", f"{last.oil_rate:,.0f} STB/d",
        f"from {F[(F.case == case)].oil_rate.iloc[0]:,.0f} in Apr 2008")
    kpi(t[4], "Final liquid rate", f"{last.liquid_rate:,.0f} STB/d", "oil + water at surface")
    qa_bar("qa2")
    st.write("")

    h = with_history(case)
    fc = h[h.src == "Forecast"]

    a, b = st.columns(2)
    with a:   # G1 rates
        g = go.Figure()
        for c, col, name in (("oil_rate", OIL, "Oil (STB/d)"), ("water_rate", WATER, "Water (STB/d)"),
                             ("gas_rate", GAS, "Gas (MSCF/d)"), ("liquid_rate", LIQUID, "Liquid (STB/d)")):
            for src, dash in (("Observed", "solid"), ("Forecast", "solid")):
                part = h[h.src == src]
                if len(part):
                    g.add_trace(go.Scatter(x=part.date, y=part[c], line=dict(color=col, width=2 if src == "Forecast" else 1.4,
                                                                             dash="dot" if c == "liquid_rate" else dash),
                                           name=name if src == "Forecast" else None, showlegend=src == "Forecast",
                                           opacity=1 if src == "Forecast" else .75))
        g.add_vline(x=fc.date.min(), line=dict(dash="dot", color=CRIMSON), annotation_text="forecast start")
        g.update_yaxes(title="Rate")
        show(style(g, "G1 · Daily Fluid Rates — Observed 1998–2008 → Forecast to 2028", 360),
             None if OBS is not None else "History segment needs observed_quarterly.csv; forecast shown.")
    with b:   # G2 facility combo
        yr = fc[fc.date.dt.month == 1]
        g = go.Figure()
        g.add_trace(go.Bar(x=yr.date.dt.year, y=yr.oil_rate, name="Oil", marker_color=OIL))
        g.add_trace(go.Bar(x=yr.date.dt.year, y=yr.water_rate, name="Water", marker_color=WATER))
        g.add_trace(go.Scatter(x=yr.date.dt.year, y=yr.water_cut, yaxis="y2", name="Water cut",
                               line=dict(color=CRIMSON, width=3), mode="lines+markers"))
        g.update_layout(barmode="stack", yaxis2=dict(overlaying="y", side="right", tickformat=".0%", range=[0.5, 1],
                                                     showgrid=False, title="Water cut"))
        g.update_layout(yaxis=dict(title="Liquid rate (STB/d)"))
        show(style(g, f"G2 · Surface Liquid Handling — {fc.liquid_rate.iloc[0]:,.0f} → {fc.liquid_rate.iloc[-1]:,.0f} STB/d", 360),
             f"Total liquid falls {1 - fc.liquid_rate.iloc[-1] / fc.liquid_rate.iloc[0]:.0%}, but water's share rises to "
             f"{fc.water_cut.iloc[-1]:.0%}: the separator and water-treatment train, not oil, set the facility load.")

    a, b = st.columns(2)
    with a:   # G3 injection
        g = go.Figure()
        if OBS is not None and "water_inj_rate" in OBS:
            liq = OBS.oil_rate + OBS.water_rate
            g.add_trace(go.Scatter(x=OBS.date, y=OBS.water_inj_rate, name="Water injection", line=dict(color=WATER, width=3),
                                   fill="tozeroy", fillcolor="rgba(2,136,209,.10)"))
            g.add_trace(go.Scatter(x=OBS.date, y=liq, name="Liquid produced", line=dict(color=LIQUID, dash="dash")))
            g.add_trace(go.Scatter(x=OBS.date, y=OBS.water_inj_rate / liq, name="Injection / liquid (rhs)", yaxis="y2",
                                   line=dict(color=CRIMSON, width=1.5)))
            g.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, title="ratio"))
            inj = OBS.water_inj_rate[OBS.water_inj_rate > 0]
            title = f"G3 · Water Injection Throttling — {inj.iloc[0] / 1e3:.1f}k → {inj.iloc[-1] / 1e3:.1f}k STB/d"
            note = "Surface-volume ratio only (no formation volume factors); a falling ratio signals reduced pressure support."
        else:
            g.add_annotation(text="Needs observed_quarterly.csv with water_inj_rate<br>(run export_powerbi_data.py)",
                             showarrow=False, font=dict(size=13, color=MUTED), x=0.5, y=0.5, xref="paper", yref="paper")
            g.update_xaxes(visible=False); g.update_yaxes(visible=False)
            title, note = "G3 · Historical Water Injection Throttling", None
        g.update_yaxes(title="STB/d")
        show(style(g, title, 340), note)
    with b:   # G4 cumulative
        g = go.Figure()
        g.add_trace(go.Scatter(x=h.date, y=h.oil_cum / 1e6, stackgroup="liq", name="Oil (MMSTB)", line=dict(color=OIL)))
        g.add_trace(go.Scatter(x=h.date, y=h.water_cum / 1e6, stackgroup="liq", name="Water (MMSTB)", line=dict(color=WATER)))
        g.add_trace(go.Scatter(x=h.date, y=h.gas_cum / 1e6, yaxis="y2", name="Gas (Bcf, rhs)", line=dict(color=GAS, width=3)))
        g.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Bcf", rangemode="tozero"))
        g.update_layout(yaxis=dict(title="MMSTB (stacked = gross liquid)"))
        cross = fc[fc.water_cum > fc.oil_cum].date.min()
        if pd.notna(cross):
            g.add_vline(x=cross, line=dict(dash="dot", color=MUTED), annotation_text=f"water > oil {cross:%Y}")
        show(style(g, "G4 · Multi-Phase Cumulative Growth", 340),
             "Oil and water stacked (same unit, STB); gas on its own axis because MSCF cannot be stacked with barrels.")

    a, b = st.columns(2)
    with a:   # G5 water cut all cases, shown as deviation from the 10-case median (curves overlap otherwise)
        g = go.Figure()
        piv = F.pivot(index="date", columns="case", values="water_cut")
        dev = piv.sub(piv.median(axis=1), axis=0) * 100
        for c_ in dev.columns:
            sel = c_ == case
            g.add_trace(go.Scatter(x=dev.index, y=dev[c_], line=dict(color=CRIMSON if sel else "#A9B0BB", width=3 if sel else 1),
                                   name=f"C{int(SEL.loc[c_, 'rank'])} #{c_}", showlegend=sel, opacity=1 if sel else .8))
        g.add_hline(y=0, line=dict(color=INK, dash="dash"), annotation_text="10-case median")
        wc = LAST.water_cut
        g.update_yaxes(title="Water cut − median (percentage points)")
        show(style(g, f"G5 · Water-Cut Progression vs 10-Case Median — 2028 range {wc.min():.2%}–{wc.max():.2%}", 340),
             f"Absolute curves overlap (all rise ~61% → ~87%), so the chart shows each case's offset. Selected case ends "
             f"{(wc[case] - wc.median()) * 100:+.2f} pp from the median.")
    with b:   # G6 GOR control chart
        g = go.Figure()
        ref = h[h.src == "Observed"].gor if OBS is not None else fc.gor
        mu, sd = ref.mean(), ref.std(ddof=1) if len(ref) > 1 else 0
        if sd < 0.01:          # flat by construction (forecast only): avoid float-noise limits
            sd = 0.0
            g.update_yaxes(range=[mu - 25, mu + 25])
        for src, col in (("Observed", INK), ("Forecast", GAS)):
            part = h[h.src == src]
            if len(part):
                g.add_trace(go.Scatter(x=part.date, y=part.gor, mode="lines+markers", marker=dict(size=3),
                                       line=dict(color=col), name=f"{src} GOR"))
        for k_, dash in (((0, "solid"), (3, "dash"), (-3, "dash")) if sd > 0 else ((0, "solid"),)):
            g.add_hline(y=mu + k_ * max(sd, 1e-6), line=dict(color=MUTED if k_ else OIL, dash=dash, width=1),
                        annotation_text="mean" if k_ == 0 else f"{k_:+d}σ", annotation_position="right")
        g.update_yaxes(title="Producing GOR (scf/STB)")
        out = int(((ref - mu).abs() > 3 * sd).sum()) if sd > 0 else 0
        show(style(g, f"G6 · GOR Control Chart — mean {mu:.0f} scf/STB, {out} points beyond ±3σ", 340),
             "Forecast gas = GOR × oil by construction, so the forecast line is flat by design; the observed history is "
             "the real test. A flat producing GOR is consistent with pressure above bubble point (no PVT data to confirm).")

    # AI diagnosis
    params = ""
    if "poro_mult" in s:
        params = (f"Rock/aquifer multipliers: porosity <b>{s.poro_mult:.3f}</b>, permeability <b>{s.perm_mult:.3f}</b>, "
                  f"aquifer PV <b>{s.aquifer_pv:.1f}</b>, fault transmissibility <b>{s.fault_trans:.3f}</b>. ")
    r = RANK.set_index("case").loc[case]
    worst = max(("oil_cum", "oil_rate", "water_cum", "water_rate"), key=lambda k_: r[k_])
    ai_box("AI Engineering Diagnosis", f"""
      <b>Case {int(s['rank'])} (simulation #{case}, {s.split} set)</b> ranks {int(s['rank'])} of 100 with J = <b>{s.history_mismatch_J:.4f}</b>
      ({(s.history_mismatch_J / SEL.history_mismatch_J.min() - 1):+.1%} vs the best match). {params}
      Its largest mismatch term is <b>{worst.replace('_', ' ')}</b> ({r[worst]:.4f}); water-rate misfit is
      {r.water_rate / r.oil_rate:.1f}× the oil-rate misfit, so water timing is the weakest-constrained output.<br>
      Facilities: liquid falls from <b>{fc.liquid_rate.iloc[0]:,.0f}</b> to <b>{fc.liquid_rate.iloc[-1]:,.0f} STB/d</b> while water cut climbs to
      <b>{last.water_cut:.1%}</b>; by 2028 the plant handles {last.water_rate / last.oil_rate:.1f} bbl of water per bbl of oil.
      Oil rate declines {1 - last.oil_rate / fc.oil_rate.iloc[0]:.0%} over 20 years
      ({(1 - (last.oil_rate / fc.oil_rate.iloc[0]) ** (1 / 19.75)):.1%}/yr effective). Prioritise water-handling debottlenecking
      over oil-train capacity.""")


# ==============================================================================================
# PAGE 3 - Subsurface & ML Governance
# ==============================================================================================
def page3():
    banner("Component B2 — Subsurface Physics & ML Governance",
           "Subsurface Geomodellers & Data Scientists · parameter identifiability, proxy accuracy, forecast-method risk")
    qa_bar("qa3")
    st.write("")
    P, MC, MS = D["proxy_optimised_sets"], D["model_comparison"], D["method_sensitivity"]

    a, b = st.columns(2)
    with a:   # G1 trust-region scatter
        g = go.Figure(go.Scatter(
            x=P.poro_mult, y=P.perm_mult, mode="markers+text", text=[f"k{int(c)}" for c in P.cluster],
            textposition="top center",
            marker=dict(size=12 + 28 * (P.aquifer_pv - P.aquifer_pv.min()) / (P.aquifer_pv.max() - P.aquifer_pv.min()),
                        color=P.J, colorscale=[[0, OIL], [0.5, "#F9A825"], [1, CRIMSON]], showscale=True,
                        colorbar=dict(title="J", thickness=10), line=dict(color=INK, width=1)),
            customdata=np.c_[P.aquifer_pv, P.fault_trans, P.J],
            hovertemplate="poro %{x:.4f}<br>perm %{y:.3f}<br>aquifer PV %{customdata[0]:.1f}<br>fault T %{customdata[1]:.3f}"
                          "<br>J %{customdata[2]:.5f}<extra></extra>"))
        if CASES is not None:
            top = RANK.nsmallest(10, "J")
            g.add_trace(go.Scatter(x=top.poro_mult, y=top.perm_mult, mode="markers", name="Top-10 simulated cases",
                                   marker=dict(symbol="diamond-open", size=11, color=SLATE2, line=dict(width=2))))
        g.update_xaxes(title="Porosity multiplier")
        g.update_yaxes(title="Permeability multiplier")
        show(style(g, "G1 · K-Means Trust-Region Picks — porosity pinned, permeability free", 360),
             f"10 GP-optimised sets, one per K-Means cluster, all flagged trusted. Porosity spans only "
             f"{P.poro_mult.min():.3f}–{P.poro_mult.max():.3f} ({(P.poro_mult.max() / P.poro_mult.min() - 1):.1%}); permeability "
             f"spans {P.perm_mult.min():.2f}–{P.perm_mult.max():.2f} ({P.perm_mult.max() / P.perm_mult.min():.1f}×) at near-identical J.")
    with b:   # G2 tornado
        S, A = D["sensitivity"], D["after_porosity"]
        labels = ["Porosity mult.", "Permeability mult.", "Aquifer PV", "Fault transmissibility"]
        first_oil = [S.loc[p, "oil_2008"] for p in ("poro_mult", "perm_mult", "aquifer_pv", "fault_trans")]
        second_oil = [np.nan, A.loc["oil_2008", "left_over_vs_perm_mult"], A.loc["oil_2008", "left_over_vs_aquifer_pv"],
                      A.loc["oil_2008", "left_over_vs_fault_trans"]]
        second_wat = [np.nan, A.loc["water_2008", "left_over_vs_perm_mult"], A.loc["water_2008", "left_over_vs_aquifer_pv"],
                      A.loc["water_2008", "left_over_vs_fault_trans"]]
        g = go.Figure()
        g.add_trace(go.Bar(y=labels, x=first_oil, orientation="h", name="1st-order ρ vs oil 2008", marker_color=SLATE2))
        g.add_trace(go.Bar(y=labels, x=second_oil, orientation="h", name="2nd-order ρ, oil residual", marker_color=OIL))
        g.add_trace(go.Bar(y=labels, x=second_wat, orientation="h", name="2nd-order ρ, water residual", marker_color=WATER))
        g.update_layout(barmode="group")
        g.update_yaxes(autorange="reversed")
        g.update_xaxes(range=[-1, 1], title="Spearman rank correlation")
        show(style(g, f"G2 · Parameter Sensitivity — porosity alone explains {A.loc['oil_2008', 'r2_porosity_only']:.1%} of oil 2008", 360),
             f"After removing porosity: permeability drives the oil residual (ρ = {A.loc['oil_2008', 'left_over_vs_perm_mult']:.2f}), "
             f"aquifer PV drives the water residual (ρ = {A.loc['water_2008', 'left_over_vs_aquifer_pv']:.2f}); fault "
             f"transmissibility stays noise (|ρ| < 0.05). The GP agrees: its fault-T length scale hits the 1000 bound.")

    a, b = st.columns(2)
    with a:   # G3 model comparison
        t = MC[MC.split == "test"].copy()
        t = t.sort_values("oil_2008_err_%")
        g = go.Figure()
        for c, col, name in (("oil_2008_err_%", OIL, "Oil 2008 error %"), ("water_2008_err_%", WATER, "Water 2008 error %"),
                             ("oil_worst_case_%", "#81C784", "Oil worst-case %"), ("water_worst_case_%", "#4FC3F7", "Water worst-case %")):
            g.add_trace(go.Bar(x=t.family, y=t[c], name=name, marker_color=col,
                               text=[f"{v:.2f}" for v in t[c]], textposition="outside", textfont=dict(size=9)))
        g.update_layout(barmode="group")
        g.update_yaxes(type="log", title="Error on 15 unseen test cases (%, log)", dtick=1, tickformat="~g")
        gp, mlp = t[t.family.str.startswith("Gaussian")].iloc[0], t[t.family.str.startswith("MLP")].iloc[0]
        show(style(g, "G3 · ML Surrogate Test-Set Error — GP vs 4 challengers", 380),
             f"GP oil-2008 error {gp['oil_2008_err_%']:.3f}% vs MLP {mlp['oil_2008_err_%']:.3f}% "
             f"({mlp['oil_2008_err_%'] / gp['oil_2008_err_%']:.1f}× lower); GP 2nd-order R² {gp.oil_2nd_order_R2:.3f}/"
             f"{gp.water_2nd_order_R2:.3f} — it alone resolves the small perm/aquifer signal. kNN and LightGBM have negative 2nd-order R².")
    with b:   # G4 method range
        g = go.Figure()
        for tie, col in (("rate_ratio", CRIMSON), ("wor_shift", SLATE2)):
            m = MS[MS.tie_in == tie]
            g.add_trace(go.Bar(y=m.method + " · " + m.window.astype(str) + "q", x=m.oil_2028_mmstb_median, orientation="h",
                               name=f"tie-in: {tie}", marker_color=col, text=[f"{v:.1f}" for v in m.oil_2028_mmstb_median],
                               textposition="outside"))
        g.add_vline(x=LAST.oil_cum.median() / 1e6, line=dict(color=OIL, dash="dash"),
                    annotation_text=f"Simulator P50 {LAST.oil_cum.median() / 1e6:.1f}")
        g.update_layout(barmode="group")
        g.update_xaxes(range=[50, 62], title="2028 oil, MMSTB (median of 10 cases)")
        show(style(g, f"G4 · Extrapolation-Method Uncertainty — {MS.oil_2028_mmstb_median.min():.1f} to "
                      f"{MS.oil_2028_mmstb_median.max():.1f} MMSTB", 380),
             "Longer fitting windows lower liquid-WOR forecasts sharply (59.1 → 53.8); Arps is less window-sensitive. "
             "liquid_wor·16q had the lowest 2005 back-test score (3.29) and matches the simulator P50.")

    a, b = st.columns(2)
    with a:   # G5 poro vs J
        g = go.Figure()
        if CASES is not None:
            for split, col in (("train", "#90A4AE"), ("validation", "#F9A825"), ("test", WATER)):
                r = RANK[RANK.split == split]
                g.add_trace(go.Scatter(x=r.poro_mult, y=r.J, mode="markers", name=split, marker=dict(color=col, size=8,
                                                                                                         line=dict(color=INK, width=.5))))
            top = RANK.nsmallest(10, "J")
            g.add_trace(go.Scatter(x=top.poro_mult, y=top.J, mode="markers", name="selected 10",
                                   marker=dict(symbol="circle-open", size=14, color=CRIMSON, line=dict(width=2))))
            note = f"Spearman ρ(|poro − best|, J) = {RANK.assign(d=(RANK.poro_mult - top.poro_mult.median()).abs())[['d', 'J']].corr('spearman').iloc[0, 1]:.2f}."
        else:
            note = "100-case cloud needs cases.csv; showing the 10 GP-optimised proxy sets only."
        g.add_trace(go.Scatter(x=P.poro_mult, y=P.J, mode="markers", name="GP-optimised sets",
                               marker=dict(symbol="star", size=12, color=OIL, line=dict(color=INK, width=1))))
        g.update_xaxes(title="Porosity multiplier")
        g.update_yaxes(title="History mismatch J", type="log")
        show(style(g, "G5 · Porosity Multiplier vs History Mismatch J", 360), note)
    with b:   # G6 PCA
        g = go.Figure()
        PV = D["pca_variance"]
        if PV is not None:
            for ph, col in (("oil_cum", OIL), ("water_cum", WATER)):
                v = PV[PV.phase == ph]
                g.add_trace(go.Scatter(x=v.k, y=v.cum_explained_var * 100, mode="lines+markers", name=ph.split("_")[0],
                                       line=dict(color=col, width=2.5)))
            g.add_vline(x=5, line=dict(color=OIL, dash="dot"), annotation_text="oil k=5")
            g.add_vline(x=6, line=dict(color=WATER, dash="dot"), annotation_text="water k=6", annotation_position="bottom right")
            g.update_yaxes(title="Cumulative variance explained (%)")
            g.update_xaxes(title="Principal components", dtick=1)
            title = "G6 · PCA Compression — Cumulative Variance Explained (5 oil + 6 water = 11 PCs)"
        else:
            pc = D["pca_check"]
            for split, col in (("train", SLATE2), ("validation", "#F9A825"), ("test", CRIMSON)):
                v = pc[pc.split == split]
                g.add_trace(go.Bar(x=v.phase.str.replace("_cum", "") + " (k=" + v.components.astype(str) + ")",
                                   y=v["max_curve_err_%"], name=f"{split} curve err", marker_color=col))
            g.add_hline(y=0.1, line=dict(color=CRIMSON, dash="dash"), annotation_text="0.1% tolerance")
            g.update_layout(barmode="group")
            g.update_yaxes(title="Max reconstruction error (%)")
            title = "G6 · PCA Compression Fidelity — 11 PCs (5 oil + 6 water)"
        show(style(g, title, 360), None if PV is not None else
             "Explained-variance curve needs pca_variance.csv; showing worst-curve reconstruction error vs the 0.1% tolerance.")

    gp = MC[(MC.split == "test") & MC.family.str.startswith("Gaussian")].iloc[0]
    ai_box("AI Subsurface Governance & Physics Takeaway", f"""
      <b>Grid:</b> {GRID_FACTS['active_cells']:,} active cells; most grid properties are identical across realizations and the rest are
      scaled by the four multipliers, so the 4-parameter proxy loses no geological information.
      <b>Identifiability:</b> porosity (pore volume) is tightly pinned by history — the 10 trusted GP optima sit within
      {(P.poro_mult.max() / P.poro_mult.min() - 1):.1%} of each other — while permeability varies {P.perm_mult.max() / P.perm_mult.min():.1f}× at
      equal J: history alone cannot resolve permeability, so it remains the key uncertainty to carry forward.
      Fault transmissibility is not identifiable (GP length scale at the 1000 bound).<br>
      <b>ML governance:</b> PCA (11 components, ≤0.075% curve error) feeds a Matérn-2.5 GP that holds
      {gp['oil_2008_err_%']:.3f}% / {gp['water_2008_err_%']:.3f}% error on 15 untouched test cases; the split was fixed by the organisers,
      the model was chosen on validation and tested once. Optima are only accepted inside the trust region (GP std
      ≤0.073% oil, ≤0.167% water). <b>Residual risk</b> sits in forecast method choice
      ({MS.oil_2028_mmstb_median.min():.1f}–{MS.oil_2028_mmstb_median.max():.1f} MMSTB), not in the proxy.""")


{PAGES[0]: page1, PAGES[1]: page2, PAGES[2]: page3}[page]()
st.markdown("<div class='note' style='margin-top:14px;text-align:center'>DWC26 · ExxonMobil DataWorks Challenge 2026 · "
            "Streamlit prototype of the Power BI build</div>", unsafe_allow_html=True)
