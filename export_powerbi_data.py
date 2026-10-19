"""Export everything the dashboard needs into one folder: outputs/powerbi/

Run from the repo root AFTER the pipeline:
    python src/run_pipeline.py
    python dashboard/export_powerbi_data.py          (or: python export_powerbi_data.py --repo <path>)

Writes (all CSV, UTF-8, ISO dates):
  observed_quarterly.csv   1998-2008 observed rates, cumulatives and water injection      (Streamlit + Power BI)
  cases.csv                4 uncertain parameters for all 100 cases + split               (Streamlit + Power BI)
  pca_variance.csv         cumulative explained variance, k = 1..12, oil and water        (Streamlit + Power BI)
  fact_profile.csv         observed history + forecast in ONE table, one row per case/date (Power BI)
  dim_case.csv             the 10 selected cases: rank, sim #, J and its 4 terms, params, 2028 totals
  all_cases.csv            all 100 cases: J terms + params (Page 3 scatter)
  sensitivity_long.csv     1st/2nd-order rank correlations in long form (tornado)
  model_test_long.csv      surrogate errors by model/metric/split in long form
  ...plus copies of the pipeline CSVs the dashboard reads directly.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--repo", default=None, help="repo root (default: parent of this file's folder, or cwd)")
args = ap.parse_args()

here = Path(__file__).resolve().parent
candidates = [Path(args.repo)] if args.repo else [here.parent, Path.cwd(), here]
ROOT = next((p for p in candidates if (p / "outputs").exists()), None)
if ROOT is None:
    raise SystemExit("Could not find the repo (a folder containing outputs/). Pass --repo <path>.")

OUT = ROOT / "outputs" / "powerbi"
OUT.mkdir(parents=True, exist_ok=True)
PROC = ROOT / "data" / "processed"


def src(name: str) -> Path | None:
    for d in ("deliverable", "results", "explore", "powerbi"):
        p = ROOT / "outputs" / d / name
        if p.exists():
            return p
    return None


def done(name, df):
    df.to_csv(OUT / name, index=False)
    print(f"  ✓ {name:<26} {len(df):>6} rows")


print(f"Repo: {ROOT}\nOutput: {OUT}")

# 1. copy the pipeline CSVs the dashboard reads as-is --------------------------------------------
for n in ["forecast_2008_2028.csv", "selected_cases.csv", "original_cases_ranking.csv", "method_sensitivity.csv",
          "model_comparison.csv", "proxy_optimised_sets.csv", "pca_check.csv", "backtest_methods.csv",
          "backtest_tiein.csv", "sensitivity.csv", "after_porosity.csv", "gp_lengthscales.csv"]:
    p = src(n)
    if p and p.parent != OUT:
        shutil.copy(p, OUT / n)
        print(f"  ✓ copied {n}")
    elif not p:
        print(f"  – {n} not found (skipped)")

# 2. observed history and case parameters (from step 1 parquet) -----------------------------------
obs = cases = None
if (PROC / "observed_quarterly.parquet").exists():
    obs = pd.read_parquet(PROC / "observed_quarterly.parquet").sort_values("date")
    obs = obs[[c for c in ["date", "oil_rate", "gas_rate", "water_rate", "water_inj_rate",
                           "oil_cum", "gas_cum", "water_cum"] if c in obs]]
    done("observed_quarterly.csv", obs)
else:
    print("  – data/processed/observed_quarterly.parquet missing: run src/step1_data.py")

if (PROC / "cases.parquet").exists():
    cases = pd.read_parquet(PROC / "cases.parquet")
    cases = cases[["case", "split", "fault_trans", "poro_mult", "perm_mult", "aquifer_pv"]]
    done("cases.csv", cases)
else:
    print("  – data/processed/cases.parquet missing: run src/step1_data.py")

# 3. PCA explained variance (re-fit exactly as step 2 does: train cases only) ----------------------
feat = PROC / "features"
if (feat / "X.parquet").exists():
    from sklearn.decomposition import PCA
    X = pd.read_parquet(feat / "X.parquet")
    rows = []
    for ph in ("oil_cum", "water_cum"):
        Y = pd.read_parquet(feat / f"Y_{ph}.parquet")
        pca = PCA(n_components=12).fit(Y[X.split == "train"].values)
        cum = np.cumsum(pca.explained_variance_ratio_)
        rows += [{"phase": ph, "k": k + 1, "explained_var": float(pca.explained_variance_ratio_[k]),
                  "cum_explained_var": float(cum[k]), "selected": (k + 1) <= (5 if ph == "oil_cum" else 6)}
                 for k in range(12)]
    done("pca_variance.csv", pd.DataFrame(rows))
else:
    print("  – PCA features missing: run src/step2_features.py")

# 4. Power BI star schema -------------------------------------------------------------------------
fc = pd.read_csv(OUT / "forecast_2008_2028.csv", parse_dates=["date"]).rename(columns={
    "oil_cum_stb": "oil_cum", "water_cum_stb": "water_cum", "gas_cum_mscf": "gas_cum",
    "oil_rate_stbd": "oil_rate", "water_rate_stbd": "water_rate", "gas_rate_mscfd": "gas_rate"})
fc["source"] = "Forecast"
sel = pd.read_csv(OUT / "selected_cases.csv")

# History is replicated under every selected case so a case slicer still draws one continuous line.
parts = [fc]
if obs is not None:
    for _, r in sel.iterrows():
        h = obs.copy()
        h["rank"], h["case"], h["source"] = r["rank"], r["case"], "Observed"
        h["water_cut"] = h.water_rate / (h.oil_rate + h.water_rate)
        parts.append(h)
prof = pd.concat(parts, ignore_index=True)
prof["case_label"] = "Case " + prof["rank"].astype(int).astype(str)
prof["liquid_rate"] = prof.oil_rate + prof.water_rate
prof["gor_scf_stb"] = prof.gas_rate / prof.oil_rate * 1000
# per-quarter incremental volumes and mid-quarter time (years from 2008-01-01) for cash flow / NPV in DAX
first = fc[fc.date == fc.date.min()].set_index("case")
base = {p: ({c: float(obs[f"{p}_cum"].iloc[-1]) for c in first.index} if obs is not None
            else (first[f"{p}_cum"] - first[f"{p}_rate"] * 91).to_dict()) for p in ("oil", "gas", "water")}
prof = prof.sort_values(["rank", "source", "date"]).reset_index(drop=True)
isf = prof.source == "Forecast"
for p in ("oil", "gas", "water"):
    prev = prof[isf].groupby("case")[f"{p}_cum"].shift(1)
    prev = prev.fillna(prof.loc[isf, "case"].map(base[p]))
    prof.loc[isf, f"d_{p}"] = prof.loc[isf, f"{p}_cum"] - prev
prof.loc[isf, "t_years"] = (prof.loc[isf, "date"] - pd.Timestamp("2008-01-01")).dt.days / 365.25 - 0.125
prof["date"] = prof.date.dt.date
cols = ["case_label", "rank", "case", "date", "source", "oil_cum", "gas_cum", "water_cum", "oil_rate", "gas_rate",
        "water_rate", "liquid_rate", "water_cut", "gor_scf_stb", "d_oil", "d_gas", "d_water", "t_years"] + (["water_inj_rate"] if "water_inj_rate" in prof else [])
done("fact_profile.csv", prof[cols].sort_values(["rank", "date"]))

rank = pd.read_csv(OUT / "original_cases_ranking.csv")
dim = sel.merge(rank[["case", "oil_cum", "oil_rate", "water_cum", "water_rate"]].add_prefix("J_").rename(
    columns={"J_case": "case"}), on="case")
if cases is not None:
    dim = dim.merge(cases.drop(columns="split"), on="case", how="left")
    rank = rank.merge(cases.drop(columns="split"), on="case", how="left")
# 2008-01 starting cumulatives: observed if available, else back-calculated from the first forecast quarter
first = fc[fc.date == fc.date.min()].set_index("case")
for p in ("oil", "gas", "water"):
    dim[f"{p}_cum_2008"] = (float(obs[f"{p}_cum"].iloc[-1]) if obs is not None
                            else dim.case.map(first[f"{p}_cum"] - first[f"{p}_rate"] * 91))
dim["case_label"] = "Case " + dim["rank"].astype(str)
eur = dim.oil_cum_stb_2028
dim["is_p50"] = (eur - eur.median()).abs() == (eur - eur.median()).abs().min()   # case nearest the P50 EUR
done("dim_case.csv", dim)
done("all_cases.csv", rank)

s1 = pd.read_csv(OUT / "sensitivity.csv", index_col=0)
s2 = pd.read_csv(OUT / "after_porosity.csv", index_col=0)
long = [{"parameter": p, "outcome": o, "order": "1st order", "rho": float(s1.loc[p, o])}
        for p in s1.index for o in s1.columns]
long += [{"parameter": c.replace("left_over_vs_", ""), "outcome": o, "order": "2nd order (after porosity)",
          "rho": float(s2.loc[o, c])} for o in s2.index for c in s2.columns if c.startswith("left_over")]
long += [{"parameter": "poro_mult", "outcome": o, "order": "R² porosity only", "rho": float(s2.loc[o, "r2_porosity_only"])}
         for o in s2.index]
done("sensitivity_long.csv", pd.DataFrame(long))

mc = pd.read_csv(OUT / "model_comparison.csv")
mlong = mc.melt(id_vars=["family", "setting", "split"], var_name="metric", value_name="value")
mlong["phase"] = np.where(mlong.metric.str.startswith("oil"), "Oil", np.where(mlong.metric.str.startswith("water"), "Water", "Both"))
done("model_test_long.csv", mlong)
print("Done. Point Power BI (Get data > Folder) or the Streamlit app (DWC_DATA env var) at", OUT)
