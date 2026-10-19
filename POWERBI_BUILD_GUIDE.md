# DWC26 Reservoir Intelligence Suite — Power BI Build Guide

Production build of the 3-page dashboard prototyped in `app.py`. Every number the Power BI file shows should match the
Streamlit prototype; Section 11 lists the values to check against.

**Files in this folder**

| File | Purpose |
|---|---|
| `app.py` | Streamlit prototype (run `streamlit run app.py`) |
| `export_powerbi_data.py` | Builds the Power BI dataset in `outputs/powerbi/` from the pipeline outputs |
| `exxon_theme.json` | Power BI report theme (colours, fonts, card accents, navigator styling) |
| `data/` | The pipeline CSVs the prototype runs on |

---

## 0. Read first — where the brief and the data disagree

The dashboard text and titles below use what the data says. Where it differs from the original brief:

| Brief said | Data says | Source |
|---|---|---|
| "10-case EUR spread 0.5% across K-Means picks" | The 10 forecast cases are the **10 lowest-J simulated cases**, not K-Means picks. Their 2028 oil spread is **1.03%** of P50 (53.27–53.82 MMSTB); **0.44%** if Case 2 (sim #73) is excluded. | `selected_cases.csv` |
| K-Means picks | K-Means clusters belong to the **10 GP-optimised parameter sets** (one per cluster, all trusted) — that is Page 3 G1. | `proxy_optimised_sets.csv` |
| Method range "53.1 (liquid_wor) – 63.3 (arps_wor) MMSTB" | **53.2 – 60.1 MMSTB** (liquid_wor 16q wor_shift → arps_wor 8q rate_ratio) | `method_sensitivity.csv` |
| "71.6% of oil historical, 80.2% of water ahead" | Needs the observed Jan-2008 cumulative. Back-calculated from the first forecast quarter it is 71.3% / 80.4%; the exported `observed_quarterly.csv` gives the exact figure. | `forecast_2008_2028.csv` |
| "Jul 2008 rate join" | First forecast quarter is **Apr 2008**; the history ends Jan 2008. | `forecast_2008_2028.csv` |
| Liquid "~13,000 → ~6,100 STB/d" | 12,923–12,954 STB/d (Apr 2008) → 5,602–6,308 STB/d (Jan 2028); P50 6,256. | `forecast_2008_2028.csv` |
| Water injection "11.8k → 9.3k STB/d", "42,512 active cells" | Not in the CSV outputs. Injection comes from `02 Field Production.xlsx` via the export script; the cell count comes from `explore.py` grid check — confirm it from your own run before presenting. | — |
| GOR "confirms pressure above bubble point" | Forecast gas = GOR × oil **by construction** (constant 363 scf/STB), so the forecast GOR is flat by design. Only the **observed** GOR tests the assumption, and a flat producing GOR is *consistent with* P > Pb — there is no PVT data to confirm it. | `step2_features.py` |
| "PCA across the 11 principal components" | Two separate PCAs: **5 components for oil, 6 for water** (11 in total). | `pca_check.csv` |
| "Net Cash Flow" | Simplified: revenue − lifting cost − produced-water handling. No capex, royalty or tax. Label it that way on the report. | — |
| Native Q&A visual | **Microsoft is retiring Power BI Q&A by the end of December 2026** ([MC1218421](https://mc.merill.net/message/MC1218421), [Power BI blog](https://powerbi.microsoft.com/blog/deprecating-power-bi-qa)); the replacement is Copilot. Build the Q&A button now if you need it for a demo before then, and plan the Copilot pane as the long-term "AI prompt box" (Section 9). | Microsoft |

---

## 1. Prepare the dataset

From the repo root:

```bash
python src/run_pipeline.py                 # if not already run
python dashboard/export_powerbi_data.py    # writes outputs/powerbi/*.csv
```

The export prints one line per file. You need these in `outputs/powerbi/`:

| Table | Grain | Key columns |
|---|---|---|
| `fact_profile` | case × quarter, observed 1998–2008 **replicated under every selected case** + forecast 2008–2028 | `case_label, rank, case, date, source, oil_cum, gas_cum, water_cum, oil_rate, gas_rate, water_rate, liquid_rate, water_cut, gor_scf_stb, d_oil, d_gas, d_water, t_years, water_inj_rate` |
| `dim_case` | 10 selected cases | `case_label, rank, case, split, history_mismatch_J, J_oil_cum, J_oil_rate, J_water_cum, J_water_rate, poro_mult, perm_mult, aquifer_pv, fault_trans, oil_cum_2008, gas_cum_2008, water_cum_2008, is_p50, *_2028` |
| `all_cases` | 100 simulated cases | `case, split, J, oil_cum, oil_rate, water_cum, water_rate, poro_mult, perm_mult, aquifer_pv, fault_trans` |
| `proxy_optimised_sets` | 10 GP-optimised sets | `rank, poro_mult, perm_mult, aquifer_pv, fault_trans, J, cluster, oil_2008_std_%, water_2008_std_%` |
| `sensitivity_long` | parameter × outcome × order | `parameter, outcome, order, rho` |
| `model_test_long` | model × split × metric | `family, setting, split, metric, value, phase` |
| `method_sensitivity` | method × window × tie-in | `method, window, tie_in, oil_2028_mmstb_median` |
| `pca_variance` | phase × k | `phase, k, explained_var, cum_explained_var, selected` |

Why history is replicated: a case slicer on Page 2 then still draws one continuous observed→forecast line. Measures
that aggregate history across cases use `AVERAGE`, never `SUM`, for that reason.

`d_oil / d_gas / d_water` are per-quarter incremental volumes (first quarter measured from the Jan-2008 cumulative);
`t_years` is mid-quarter time from 1 Jan 2008 for discounting. `is_p50` flags the case whose 2028 oil EUR is nearest
the 10-case median (sim #40) — the economics use that one case so the waterfall components add up.

---

## 2. Import and model

1. **Power BI Desktop → Home → Get data → Text/CSV**, load each file above (or **Get data → Folder** on
   `outputs/powerbi`, then *Transform data* and keep the eight files). Click **Load**.
2. **Transform data (Power Query)** — check types, then *Close & Apply*:
   - `fact_profile[date]` → **Date**; `source`, `case_label` → Text; all volumes/rates/`water_cut`/`d_*`/`t_years` → Decimal number.
   - `dim_case[is_p50]` → **True/False**; `rank`, `case` → Whole number.
   - Set **Data → File → Options → Current file → Regional settings → Locale for import = English (United States)** if decimals import as text.
3. **Model view → relationships**
   - `dim_case[case_label]` (1) → `fact_profile[case_label]` (*), single direction. This is the only relationship.
   - All other tables stay **disconnected** (they feed Page 3 or are parameter/helper tables).
   - Turn off *Auto date/time* (File → Options → Current file → Data load) — it bloats the model and the charts use `fact_profile[date]` directly.
4. **Sort-by columns** (Table view, select column → *Column tools → Sort by column*):
   - `dim_case[case_label]` sort by `dim_case[rank]` (otherwise "Case 10" sorts after "Case 1").
5. **Calculated columns** (Table view → *New column*):

```DAX
// fact_profile
Year = YEAR ( fact_profile[date] )

// method_sensitivity
Method Window = method_sensitivity[method] & " · " & method_sensitivity[window] & "q"

// sensitivity_long — one legend entry per series in the tornado
Series = sensitivity_long[order] & " · " & sensitivity_long[outcome]

// model_test_long — readable metric names for the legend
Metric Label =
SWITCH (
    model_test_long[metric],
    "oil_2008_err_%", "Oil 2008 error %",
    "water_2008_err_%", "Water 2008 error %",
    "oil_worst_case_%", "Oil worst-case %",
    "water_worst_case_%", "Water worst-case %",
    model_test_long[metric]
)
```

6. Create an empty **measures table**: *Home → Enter data*, name it `_Measures`, load, then (after adding the first
   measure) delete its default column. All measures below go here.

---

## 3. Theme, canvas and navigation

1. **View → Themes → Browse for themes →** `exxon_theme.json`. This sets phase colours (Oil `#2E7D32`, Water `#0288D1`,
   Gas `#D32F2F`), crimson accents, `#F4F6F9` page canvas, white visual cards with a soft shadow, and the navigator styling.
2. **Canvas** — for each page: *Format page → Canvas settings → Type: Custom, 1600 × 1150 px*, vertical alignment *Top*.
   (The report scrolls vertically in the service; 6 charts + KPI row + commentary do not fit legibly at 16:9.)
3. **Rename pages**: `Business & Commercial`, `Reservoir & Facilities`, `Subsurface & ML`.
4. **Header band** (Page 1, then copy to the others):
   - *Insert → Shapes → Rectangle*: X 0, Y 0, W 1600, H 64, fill `#1E2229`, no outline.
   - Thin accent: second rectangle X 0, Y 64, W 1600, H 4, fill `#ED1B2D`.
   - *Insert → Text box* on the band: "DWC26 Reservoir Intelligence Suite", Segoe UI Semibold 18, white.
5. **Page navigator**: *Insert → Buttons → Navigator → Page navigator*. Position X 760, Y 12, W 820, H 40.
   *Format → Grid layout*: Orientation **Horizontal**. The theme styles default `#2A2F3A`, selected `#ED1B2D`, hover
   `#3A4150`, white Segoe UI Semibold 11. Select the header band, text box and navigator → **Ctrl+C**, go to pages 2
   and 3 → **Ctrl+V** (pastes at the same coordinates). The navigator highlights the current page automatically.
6. **Page subtitle band** under the header on each page: rectangle X 20, Y 80, W 1560, H 54, fill `#2A2F3A`, with a
   6 px `#ED1B2D` rectangle on its left edge, and a text box: page title (white, 15 pt) + audience line (`#C9CED8`, 10 pt).

---

## 4. What-if parameters and helper tables

### 4.1 What-if parameters (*Modeling → New parameter → Numeric range*)

| Name | Min | Max | Increment | Default | Add slicer |
|---|---|---|---|---|---|
| `Oil Price` | 50 | 110 | 5 | 80 | ✔ (Page 1) |
| `Gas Price` | 1 | 8 | 0.5 | 3 | ✔ |
| `Lifting Cost` | 0 | 30 | 1 | 12 | ✔ |
| `Water Cost` | 0 | 5 | 0.25 | 1.5 | ✔ |
| `Discount Rate` | 0 | 15 | 1 | 10 | ✔ |

Each creates a table plus a measure named `<Name> Value` (e.g. `[Oil Price Value]`). Keep the Oil Price slicer on the
page; put the other four in a collapsible panel (Section 6, step 1).

### 4.2 Helper tables (*Modeling → New table*)

```DAX
Phase =
DATATABLE ( "Phase", STRING, "Order", INTEGER, { { "Oil", 1 }, { "Gas", 2 }, { "Water", 3 } } )

Reserve Split =
DATATABLE (
    "Phase", STRING, "Period", STRING, "Order", INTEGER,
    {
        { "Oil", "Historical 1998–2008", 1 }, { "Oil", "Incremental 2008–2028", 2 },
        { "Gas", "Historical 1998–2008", 1 }, { "Gas", "Incremental 2008–2028", 2 },
        { "Water", "Historical 1998–2008", 1 }, { "Water", "Incremental 2008–2028", 2 }
    }
)

CF Item =
DATATABLE (
    "Item", STRING, "Order", INTEGER,
    { { "Oil revenue", 1 }, { "Gas revenue", 2 }, { "Lifting OPEX", 3 }, { "Water handling", 4 } }
)

Price Axis = GENERATESERIES ( 50, 110, 5 )      // column is named [Value]
```

Sort `Phase[Phase]` by `Phase[Order]`, `Reserve Split[Period]` by `Reserve Split[Order]`, `CF Item[Item]` by `CF Item[Order]`.

---

## 5. Measures

Create each with *Home → New measure* in `_Measures`. Display folders (Properties pane) keep the field list tidy;
suggested folders are in the headings.

### 5.1 Core profile (`01 Core`)

```DAX
Forecast End =
CALCULATE ( MAX ( fact_profile[date] ), REMOVEFILTERS ( fact_profile ), REMOVEFILTERS ( dim_case ) )

Forecast Start =
CALCULATE ( MIN ( fact_profile[date] ), fact_profile[source] = "Forecast", REMOVEFILTERS ( fact_profile ), REMOVEFILTERS ( dim_case ) )

Oil EUR (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( AVERAGE ( fact_profile[oil_cum] ), fact_profile[date] = d, fact_profile[source] = "Forecast" )

Gas EUR (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( AVERAGE ( fact_profile[gas_cum] ), fact_profile[date] = d, fact_profile[source] = "Forecast" )

Water EUR (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( AVERAGE ( fact_profile[water_cum] ), fact_profile[date] = d, fact_profile[source] = "Forecast" )

WCT 2028 (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( AVERAGE ( fact_profile[water_cut] ), fact_profile[date] = d, fact_profile[source] = "Forecast" )

Oil Rate 2028 (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( AVERAGE ( fact_profile[oil_rate] ), fact_profile[date] = d, fact_profile[source] = "Forecast" )
```

### 5.2 Page 1 KPIs (`02 Reserves`)

```DAX
P50 Oil EUR = MEDIANX ( ALL ( dim_case[case_label] ), [Oil EUR (case)] )
Min Oil EUR = MINX ( ALL ( dim_case[case_label] ), [Oil EUR (case)] )
Max Oil EUR = MAXX ( ALL ( dim_case[case_label] ), [Oil EUR (case)] )
P50 Gas EUR = MEDIANX ( ALL ( dim_case[case_label] ), [Gas EUR (case)] )
P50 Water EUR = MEDIANX ( ALL ( dim_case[case_label] ), [Water EUR (case)] )
P50 WCT 2028 = MEDIANX ( ALL ( dim_case[case_label] ), [WCT 2028 (case)] )

P50 Incremental Oil =
MEDIANX (
    ALL ( dim_case[case_label] ),
    [Oil EUR (case)] - CALCULATE ( MAX ( dim_case[oil_cum_2008] ) )      // CALCULATE = context transition per case
)

KPI Oil EUR = FORMAT ( [P50 Oil EUR] / 1e6, "0.00" ) & " MMSTB"
KPI Oil EUR Sub = "range " & FORMAT ( [Min Oil EUR] / 1e6, "0.00" ) & "–" & FORMAT ( [Max Oil EUR] / 1e6, "0.00" )
KPI Incremental Sub = FORMAT ( DIVIDE ( [P50 Incremental Oil], [P50 Oil EUR] ), "0.0%" ) & " of EUR still to produce"
KPI Gas EUR = FORMAT ( [P50 Gas EUR] / 1e6, "0.00" ) & " Bcf"
KPI Water EUR = FORMAT ( [P50 Water EUR] / 1e6, "0.00" ) & " MMSTB"
KPI Water Sub = "water cut → " & FORMAT ( [P50 WCT 2028], "0.0%" )
```

### 5.3 Phase-aware measures for the fan chart and EUR columns (`03 Phase`)

```DAX
Selected Cum (case) =
VAR ph = SELECTEDVALUE ( Phase[Phase], "Oil" )
VAR v =
    SWITCH ( ph,
        "Oil", AVERAGE ( fact_profile[oil_cum] ),
        "Gas", AVERAGE ( fact_profile[gas_cum] ),
        AVERAGE ( fact_profile[water_cum] ) )
RETURN DIVIDE ( v, 1e6 )            // MMSTB, or Bcf for gas

Fan P50 =
CALCULATE ( MEDIANX ( VALUES ( dim_case[case_label] ), [Selected Cum (case)] ), fact_profile[source] = "Forecast" )

Fan Min =
CALCULATE ( MINX ( VALUES ( dim_case[case_label] ), [Selected Cum (case)] ), fact_profile[source] = "Forecast" )

Fan Max =
CALCULATE ( MAXX ( VALUES ( dim_case[case_label] ), [Selected Cum (case)] ), fact_profile[source] = "Forecast" )

Observed Cum =
CALCULATE ( [Selected Cum (case)], fact_profile[source] = "Observed" )   // AVERAGE collapses the 10 replicas

Selected EUR (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( [Selected Cum (case)], fact_profile[date] = d, fact_profile[source] = "Forecast" )

EUR Spread % =
VAR t = ADDCOLUMNS ( ALL ( dim_case[case_label] ), "@e", [Selected EUR (case)] )
RETURN DIVIDE ( MAXX ( t, [@e] ) - MINX ( t, [@e] ), MEDIANX ( t, [@e] ) )

Method Max 2028 = MAX ( method_sensitivity[oil_2028_mmstb_median] )
Method Min 2028 = MIN ( method_sensitivity[oil_2028_mmstb_median] )

Title G1 =
"G1 · Cumulative " & SELECTEDVALUE ( Phase[Phase], "Oil" )
    & " — Observed 1998–2008 → 10-Case Forecast Fan to 2028"

Title G3 =
"G3 · 2028 " & SELECTEDVALUE ( Phase[Phase], "Oil" ) & " EUR by Case — spread "
    & FORMAT ( [EUR Spread %], "0.00%" ) & " of P50"

Reserve Volume =
VAR ph = SELECTEDVALUE ( 'Reserve Split'[Phase] )
VAR per = SELECTEDVALUE ( 'Reserve Split'[Period] )
VAR eur = SWITCH ( ph, "Oil", [P50 Oil EUR], "Gas", [P50 Gas EUR], "Water", [P50 Water EUR] )
VAR base =
    SWITCH ( ph,
        "Oil", MEDIANX ( ALL ( dim_case ), dim_case[oil_cum_2008] ),
        "Gas", MEDIANX ( ALL ( dim_case ), dim_case[gas_cum_2008] ),
        "Water", MEDIANX ( ALL ( dim_case ), dim_case[water_cum_2008] ) )
RETURN IF ( LEFT ( per, 4 ) = "Hist", base, eur - base )
```

### 5.4 Economics, P50 case (`04 Economics`)

```DAX
Inc Oil P50 =
CALCULATE ( SUM ( fact_profile[d_oil] ), dim_case[is_p50] = TRUE (), REMOVEFILTERS ( dim_case ) )
Inc Gas P50 =
CALCULATE ( SUM ( fact_profile[d_gas] ), dim_case[is_p50] = TRUE (), REMOVEFILTERS ( dim_case ) )
Inc Water P50 =
CALCULATE ( SUM ( fact_profile[d_water] ), dim_case[is_p50] = TRUE (), REMOVEFILTERS ( dim_case ) )

Oil Revenue P50 = [Inc Oil P50] * [Oil Price Value]
Gas Revenue P50 = [Inc Gas P50] * [Gas Price Value]
Lift OPEX P50 = [Inc Oil P50] * [Lifting Cost Value]
Water OPEX P50 = [Inc Water P50] * [Water Cost Value]
NCF P50 = [Oil Revenue P50] + [Gas Revenue P50] - [Lift OPEX P50] - [Water OPEX P50]

NPV P50 =
VAR p = [Oil Price Value]
VAR g = [Gas Price Value]
VAR l = [Lifting Cost Value]
VAR w = [Water Cost Value]
VAR r = [Discount Rate Value] / 100
RETURN
    CALCULATE (
        SUMX (
            FILTER ( fact_profile, fact_profile[source] = "Forecast" ),
            ( fact_profile[d_oil] * ( p - l ) + fact_profile[d_gas] * g - fact_profile[d_water] * w )
                / POWER ( 1 + r, fact_profile[t_years] )
        ),
        dim_case[is_p50] = TRUE (), REMOVEFILTERS ( dim_case )
    )

Break-even Oil Price = DIVIDE ( [Water OPEX P50] + [Lift OPEX P50] - [Gas Revenue P50], [Inc Oil P50] )

KPI NCF = "$" & FORMAT ( [NCF P50] / 1e9, "0.00" ) & " B"
KPI NCF Label = "Net Cash Flow @ $" & [Oil Price Value]
KPI NCF Sub = "NPV" & [Discount Rate Value] & " $" & FORMAT ( [NPV P50] / 1e9, "0.00" ) & " B · P50 case"

CF Component =
SWITCH (
    SELECTEDVALUE ( 'CF Item'[Item] ),
    "Oil revenue", [Oil Revenue P50],
    "Gas revenue", [Gas Revenue P50],
    "Lifting OPEX", - [Lift OPEX P50],
    "Water handling", - [Water OPEX P50]
) / 1e6

// G5 sensitivity — price comes from the disconnected Price Axis, costs from the sliders
NCF Curve (base) =
VAR p = SELECTEDVALUE ( 'Price Axis'[Value] )
RETURN DIVIDE ( [Inc Oil P50] * ( p - [Lifting Cost Value] ) + [Gas Revenue P50] - [Water OPEX P50], 1e9 )

NCF Curve (water −50%) =
VAR p = SELECTEDVALUE ( 'Price Axis'[Value] )
RETURN DIVIDE ( [Inc Oil P50] * ( p - [Lifting Cost Value] ) + [Gas Revenue P50] - 0.5 * [Water OPEX P50], 1e9 )

NCF Curve (water ×2) =
VAR p = SELECTEDVALUE ( 'Price Axis'[Value] )
RETURN DIVIDE ( [Inc Oil P50] * ( p - [Lifting Cost Value] ) + [Gas Revenue P50] - 2 * [Water OPEX P50], 1e9 )
```

### 5.5 Page 2 — selected case (`05 Engineering`)

```DAX
Sel J = SELECTEDVALUE ( dim_case[history_mismatch_J] )
Sel Rank = SELECTEDVALUE ( dim_case[rank] )
Sel Sim = SELECTEDVALUE ( dim_case[case] )

Avg Oil Rate = AVERAGE ( fact_profile[oil_rate] )
Avg Gas Rate = AVERAGE ( fact_profile[gas_rate] )
Avg Water Rate = AVERAGE ( fact_profile[water_rate] )
Avg Liquid Rate = AVERAGE ( fact_profile[liquid_rate] )
Avg Water Cut = AVERAGE ( fact_profile[water_cut] )
Avg GOR = AVERAGE ( fact_profile[gor_scf_stb] )
Avg Injection = AVERAGE ( fact_profile[water_inj_rate] )
Injection / Liquid = DIVIDE ( [Avg Injection], [Avg Liquid Rate] )

Oil Cum MMSTB = DIVIDE ( AVERAGE ( fact_profile[oil_cum] ), 1e6 )
Water Cum MMSTB = DIVIDE ( AVERAGE ( fact_profile[water_cum] ), 1e6 )
Gas Cum Bcf = DIVIDE ( AVERAGE ( fact_profile[gas_cum] ), 1e6 )

Start Liquid (case) =
VAR d = [Forecast Start]
RETURN CALCULATE ( [Avg Liquid Rate], fact_profile[date] = d )
End Liquid (case) =
VAR d = [Forecast End]
RETURN CALCULATE ( [Avg Liquid Rate], fact_profile[date] = d )

WCT Deviation pp =
VAR m =
    MEDIANX ( ALL ( dim_case[case_label] ), CALCULATE ( AVERAGE ( fact_profile[water_cut] ) ) )
RETURN ( AVERAGE ( fact_profile[water_cut] ) - m ) * 100

GOR Mean (obs) = CALCULATE ( [Avg GOR], fact_profile[source] = "Observed" )
GOR SD (obs) =
CALCULATE (
    STDEVX.S ( VALUES ( fact_profile[date] ), CALCULATE ( [Avg GOR] ) ),
    fact_profile[source] = "Observed"
)
GOR UCL = [GOR Mean (obs)] + 3 * [GOR SD (obs)]
GOR LCL = [GOR Mean (obs)] - 3 * [GOR SD (obs)]

KPI J = FORMAT ( [Sel J], "0.0000" )
KPI J Sub = "rank " & [Sel Rank] & " of 100 · " & SELECTEDVALUE ( dim_case[split] ) & " set"
KPI WCT = FORMAT ( [WCT 2028 (case)], "0.0%" )
KPI Oil Rate = FORMAT ( [Oil Rate 2028 (case)], "#,0" ) & " STB/d"

Title P2 G2 =
"G2 · Surface Liquid Handling — " & FORMAT ( [Start Liquid (case)], "#,0" ) & " → "
    & FORMAT ( [End Liquid (case)], "#,0" ) & " STB/d"
```

### 5.6 Page 3 (`06 Governance`)

```DAX
GP Oil Test Err =
CALCULATE ( MAX ( model_test_long[value] ), model_test_long[family] = "Gaussian Process",
            model_test_long[split] = "test", model_test_long[metric] = "oil_2008_err_%" )
GP Water Test Err =
CALCULATE ( MAX ( model_test_long[value] ), model_test_long[family] = "Gaussian Process",
            model_test_long[split] = "test", model_test_long[metric] = "water_2008_err_%" )
MLP Oil Test Err =
CALCULATE ( MAX ( model_test_long[value] ), model_test_long[family] = "MLP (neural net)",
            model_test_long[split] = "test", model_test_long[metric] = "oil_2008_err_%" )

Proxy Poro Spread % = DIVIDE ( MAX ( proxy_optimised_sets[poro_mult] ), MIN ( proxy_optimised_sets[poro_mult] ) ) - 1
Proxy Perm Ratio = DIVIDE ( MAX ( proxy_optimised_sets[perm_mult] ), MIN ( proxy_optimised_sets[perm_mult] ) )
Porosity R2 Oil =
CALCULATE ( MAX ( sensitivity_long[rho] ), sensitivity_long[order] = "R² porosity only", sensitivity_long[outcome] = "oil_2008" )
Simulator P50 MMSTB = [P50 Oil EUR] / 1e6
```

### 5.7 AI commentary measures (`07 AI`)

Each returns one paragraph; `UNICHAR(10)` makes a line break in the Card (new) visual with word-wrap on.

```DAX
AI_Page1_Commentary =
VAR price = [Oil Price Value]
VAR gross = [Oil Revenue P50] + [Gas Revenue P50]
VAR eurMin = [Min Oil EUR] / 1e6
VAR eurMax = [Max Oil EUR] / 1e6
VAR caseSpread = eurMax - eurMin
VAR mMin = [Method Min 2028]
VAR mMax = [Method Max 2028]
VAR wctStart =
    MEDIANX ( ALL ( dim_case[case_label] ),
              VAR d = [Forecast Start] RETURN CALCULATE ( AVERAGE ( fact_profile[water_cut] ), fact_profile[date] = d ) )
RETURN
    "At $" & price & "/bbl the P50 case (sim #" & CALCULATE ( MAX ( dim_case[case] ), dim_case[is_p50] = TRUE (), REMOVEFILTERS ( dim_case ) )
    & ") returns a simplified 20-year net cash flow of $" & FORMAT ( [NCF P50] / 1e9, "0.00" ) & " B (NPV"
    & [Discount Rate Value] & " $" & FORMAT ( [NPV P50] / 1e9, "0.00" ) & " B). Water handling consumes "
    & FORMAT ( DIVIDE ( [Water OPEX P50], gross ), "0.0%" ) & " of gross revenue as water cut climbs from "
    & FORMAT ( wctStart, "0%" ) & " to " & FORMAT ( [P50 WCT 2028], "0%" ) & "; cash-flow break-even is $"
    & FORMAT ( [Break-even Oil Price], "0.0" ) & "/bbl."
    & UNICHAR ( 10 )
    & "Reserves risk between cases is low: 2028 oil spans " & FORMAT ( eurMin, "0.00" ) & "–" & FORMAT ( eurMax, "0.00" )
    & " MMSTB (" & FORMAT ( DIVIDE ( caseSpread, [P50 Oil EUR] / 1e6 ), "0.00%" ) & "). Method risk dominates: decline-curve "
    & "alternatives span " & FORMAT ( mMin, "0.0" ) & "–" & FORMAT ( mMax, "0.0" ) & " MMSTB, about "
    & FORMAT ( DIVIDE ( mMax - mMin, caseSpread ), "0" ) & "× the case spread. Plan on the P50 profile; carry the method envelope as the reserves range."

AI_Page2_Diagnosis =
VAR rk = [Sel Rank]
VAR sim = [Sel Sim]
VAR j = [Sel J]
VAR jBest = MINX ( ALL ( dim_case ), dim_case[history_mismatch_J] )
VAR tOil = SELECTEDVALUE ( dim_case[J_oil_rate] )
VAR tWat = SELECTEDVALUE ( dim_case[J_water_rate] )
VAR worst =
    SWITCH ( TRUE (),
        tWat >= MAX ( tOil, SELECTEDVALUE ( dim_case[J_water_cum] ) ), "water rate",
        tOil >= SELECTEDVALUE ( dim_case[J_water_cum] ), "oil rate",
        "water cumulative" )
VAR liq0 = [Start Liquid (case)]
VAR liq1 = [End Liquid (case)]
VAR wct = [WCT 2028 (case)]
RETURN
    IF ( ISBLANK ( rk ), "Select one case to see its diagnosis.",
        "Case " & rk & " (sim #" & sim & ", " & SELECTEDVALUE ( dim_case[split] ) & " set) ranks " & rk
        & " of 100 with J = " & FORMAT ( j, "0.0000" ) & " (" & FORMAT ( DIVIDE ( j, jBest ) - 1, "+0.0%" ) & " vs best). "
        & "Multipliers: porosity " & FORMAT ( SELECTEDVALUE ( dim_case[poro_mult] ), "0.000" )
        & ", permeability " & FORMAT ( SELECTEDVALUE ( dim_case[perm_mult] ), "0.000" )
        & ", aquifer PV " & FORMAT ( SELECTEDVALUE ( dim_case[aquifer_pv] ), "0.0" )
        & ", fault transmissibility " & FORMAT ( SELECTEDVALUE ( dim_case[fault_trans] ), "0.000" ) & ". "
        & "Largest misfit term: " & worst & "; water-rate misfit is " & FORMAT ( DIVIDE ( tWat, tOil ), "0.0" )
        & "× the oil-rate misfit, so water timing is the weakest-constrained output."
        & UNICHAR ( 10 )
        & "Facilities: liquid falls from " & FORMAT ( liq0, "#,0" ) & " to " & FORMAT ( liq1, "#,0" )
        & " STB/d while water cut rises to " & FORMAT ( wct, "0.0%" ) & " — "
        & FORMAT ( DIVIDE ( wct, 1 - wct ), "0.0" ) & " bbl water per bbl oil by 2028. "
        & "Prioritise water-handling debottlenecking over oil-train capacity."
    )

AI_Page3_Governance =
// 42,512 active cells: from explore.py grid_check — confirm against your own run.
"Grid: 42,512 active cells; most grid properties are identical across realizations and the rest scale with the four multipliers, "
    & "so a 4-parameter proxy loses no geological information. "
    & "Identifiability: porosity is pinned by history (" & FORMAT ( [Porosity R2 Oil], "0.0%" )
    & " of oil-2008 variance; the 10 trusted GP optima sit within " & FORMAT ( [Proxy Poro Spread %], "0.0%" )
    & "), while permeability varies " & FORMAT ( [Proxy Perm Ratio], "0.0" ) & "× at equal J — history cannot resolve it. "
    & "Fault transmissibility is not identifiable (GP length scale at its bound)."
    & UNICHAR ( 10 )
    & "ML governance: 5+6 PCA components feed a Matérn-2.5 GP with " & FORMAT ( [GP Oil Test Err], "0.000" ) & "% / "
    & FORMAT ( [GP Water Test Err], "0.000" ) & "% error on 15 untouched test cases ("
    & FORMAT ( DIVIDE ( [MLP Oil Test Err], [GP Oil Test Err] ), "0.0" ) & "× better than the MLP). Optima are accepted only inside "
    & "the GP trust region. Residual risk sits in the forecast method (" & FORMAT ( [Method Min 2028], "0.0" ) & "–"
    & FORMAT ( [Method Max 2028], "0.0" ) & " MMSTB), not in the proxy."
```

---

## 6. Page 1 — Business & Commercial (Asset Managers, Commercial Planners)

Layout grid (px, X / Y / W / H):

| Element | X | Y | W | H |
|---|---|---|---|---|
| Header + navigator | 0 | 0 | 1600 | 68 |
| Subtitle band | 20 | 80 | 1560 | 54 |
| Oil Price slicer | 20 | 146 | 380 | 70 |
| Phase slicer | 410 | 146 | 300 | 70 |
| Assumptions button | 720 | 156 | 180 | 44 |
| Q&A / Copilot prompt bar | 910 | 150 | 670 | 60 |
| 5 KPI cards | 20 + 316·i | 228 | 300 | 100 |
| G1 fan chart | 20 | 340 | 1560 | 330 |
| G2 / G3 | 20 / 805 | 682 | 775 | 300 |
| G4 / G5 | 20 / 805 | 994 | 775 | 300 |
| G6 | 20 | 1306 | 1560 | 300 |
| AI commentary | 20 | 1618 | 1560 | 120 |

(Set canvas height to ~1760 for Page 1 if you keep G6 full-width; or put G6 beside G5 at 1/3 width each to stay at 1150.)

**Step 1 — Slicers.**
- Oil Price: the slicer created by the parameter; *Format → Slicer settings → Style: Single value* (slider). Title "Oil price ($/bbl)".
- Phase: *Insert → Slicer*, field `Phase[Phase]`; *Slicer settings → Style: Tile*, *Selection → Single select* ON,
  *Force selection* ON. Selected tile fill `#ED1B2D`, text white.
- Economic assumptions panel: put the Gas Price, Lifting Cost, Water Cost and Discount Rate slicers in a group on a
  `#FFFFFF` rectangle; *View → Bookmarks* → create "Assumptions shown" / "Assumptions hidden" (Selection pane toggles
  the group), clear *Data* on both bookmarks so slider values persist; *Insert → Buttons → Blank*, text "Economic
  assumptions ▾", action *Bookmark → Assumptions shown*, and a close (✕) button inside the panel → "Assumptions hidden".

**Step 2 — KPI cards.** *Insert → Card (new)*; one card per KPI. Drag the text measure into *Data*, then
*Format → Callout value* (Segoe UI Semibold 24) and *Reference labels → Add* the sub-label measure.
The theme adds the 4 px crimson top accent.

| Card | Callout | Reference label | Title |
|---|---|---|---|
| 1 | `[KPI Oil EUR]` | `[KPI Oil EUR Sub]` | 2028 P50 OIL EUR |
| 2 | `FORMAT([P50 Incremental Oil]/1e6,"0.00") & " MMSTB"` (create as measure `KPI Incremental`) | `[KPI Incremental Sub]` | INCREMENTAL OIL 2008–28 |
| 3 | `[KPI Gas EUR]` | `"GOR " & FORMAT(CALCULATE([Avg GOR], fact_profile[source]="Forecast"),"0") & " scf/STB"` (`KPI GOR Sub`) | 2028 GAS EUR |
| 4 | `[KPI Water EUR]` | `[KPI Water Sub]` | 2028 WATER EUR |
| 5 | `[KPI NCF]` | `[KPI NCF Sub]` | title via *fx* → `[KPI NCF Label]` |

**Step 3 — G1 Fan chart (Line chart).**
- X-axis `fact_profile[date]` (*Type: Continuous*). Y-axis `[Fan P50]`, `[Observed Cum]`. No legend field.
- *Analytics → Error bars → `Fan P50`*: Upper bound `[Fan Max]`, Lower bound `[Fan Min]`, *Bar → Style: Band*,
  colour `#ED1B2D` 85% transparency. This is the 10-case envelope.
- *Analytics → Y-axis constant line* (oil only — the method envelope is an oil result): value *fx* `[Method Max 2028]`, label
  "Decline-method upper (arps_wor 8q)"; second line `[Method Min 2028]`, "Decline-method lower (liquid_wor 16q)";
  dashed, `#ED1B2D`. Add a third constant line on the **X-axis** at *fx* `[Forecast Start]`, dotted grey, label "forecast start".
- Series colours: `Fan P50` → set by *fx* per phase? Line colours cannot use *fx*; use `#2E7D32` and note the phase in
  the title. `Observed Cum` → `#1E2229`, markers on.
- *Title → fx* `[Title G1]`.
- *Comparative points to call out in the subtitle*: observed history and forecast join without a step; the 10-case
  band is barely visible (1% wide) while the decline-method lines sit 0–6 MMSTB above it.

**Step 4 — G2 Historical vs Incremental (100% stacked bar chart).**
- Y-axis `'Reserve Split'[Phase]`, Legend `'Reserve Split'[Period]`, X-axis `[Reserve Volume]`.
- Colours: Historical `#2A2F3A`, Incremental `#ED1B2D` (or use per-phase colours by turning legend off and using
  *Bars → fx* rules on `'Reserve Split'[Phase]` — only available without a legend field).
- Data labels ON (percent of total is automatic in 100% charts). Sort axis by `Phase[Order]` ascending.
- Insight: oil ~71% produced (mature), water ~80% still ahead — facility spend is water-driven.

**Step 5 — G3 EUR by case (Clustered column chart).**
- X-axis `dim_case[case_label]` (sorted by rank), Y-axis `[Selected EUR (case)]`. Tooltips: `dim_case[case]`, `dim_case[history_mismatch_J]`.
- *Y-axis → Range*: Minimum *fx* `[Min Oil EUR]/1e6 - 0.3` is phase-blind, so use **Auto** min with *Start* blank and
  enable *Columns → fx* conditional colour: rules on `[Selected EUR (case)]` — highest and lowest bar `#ED1B2D`,
  others phase colour. (Create measure `EUR Bar Colour` = `VAR v=[Selected EUR (case)] VAR t=ADDCOLUMNS(ALL(dim_case[case_label]),"@e",[Selected EUR (case)]) RETURN IF(v=MAXX(t,[@e])||v=MINX(t,[@e]),"#ED1B2D","#2E7D32")` and use *Field value*.)
- *Analytics → Median line*, dashed `#1E2229`, label "P50".
- *Title → fx* `[Title G3]`. Truncate the Y-axis manually (e.g. min 53.0 for oil) so 0.5 MMSTB differences are visible, and say so in the subtitle.

**Step 6 — G4 Cash-flow bridge (Waterfall chart).**
- Category `'CF Item'[Item]` (sorted by Order), Y-axis `[CF Component]`. Total is added automatically; rename it
  *Format → Total → Label* "Net cash flow".
- Colours: Increase `#2E7D32`, Decrease `#ED1B2D`, Total `#2A2F3A`. Data labels `$#,0M`.
- Subtitle: "Simplified, undiscounted; excludes capex, royalty and tax."

**Step 7 — G5 Price sensitivity (Line chart).**
- X-axis `'Price Axis'[Value]` (Continuous), Y-axis `[NCF Curve (base)]`, `[NCF Curve (water −50%)]`, `[NCF Curve (water ×2)]`.
- Base `#ED1B2D` 3 px; others `#2A2F3A` dotted / dashed.
- *Analytics → X-axis constant line* value *fx* `[Oil Price Value]`, colour `#2E7D32` — moves with the slider.
- *Y-axis constant line* at 0. Tooltip: `[Break-even Oil Price]`.
- Insight: each $10/bbl ≈ `[Inc Oil P50] × 10`; doubling water cost costs `[Water OPEX P50]` — show both in the subtitle.

**Step 8 — G6 EUR vs water cut (Scatter chart).**
- Values `dim_case[case_label]`; X `[WCT 2028 (case)]`; Y `[Oil EUR (case)]` (display units Millions); Size `Sum of dim_case[aquifer_pv]`.
- *Markers → Colour → fx*: Gradient on `Sum of dim_case[history_mismatch_J]`, min `#2E7D32`, centre `#F9A825`, max `#ED1B2D` (no legend field, or *fx* is disabled).
- *Category label* ON. X format `0.00%`.
- Insight: case-to-case EUR and water cut move together; Case 2 (#73) is the low-EUR, low-WCT outlier.

**Step 9 — AI commentary.** *Insert → Card (new)*, Data `[AI_Page1_Commentary]`; *Callout value*: font 11, white,
word wrap ON, *Horizontal alignment* Left; *Visual → Background* `#1E2229`; add a 6 px `#ED1B2D` rectangle on the left
edge; *Title* "✦ AI Commercial Commentary", white. It recalculates on every slider move and phase click.

**Step 10 — Edit interactions** (*Format → Edit interactions*): the Phase slicer → **None** on G2, G4, G5 and the KPI
cards (they are phase-independent); keep it on G1 and G3.

---

## 7. Page 2 — Reservoir & Facilities (Production & Facility Engineers)

**Top row.**
- Case selector: *Insert → Slicer* `dim_case[case_label]`; *Style: Dropdown* (or *Tile*), *Single select* ON, *Force selection* ON; default "Case 1".
- KPI cards (Card new): `[KPI J]` / `[KPI J Sub]`; `[KPI WCT]`; `[KPI Oil Rate]`; `FORMAT([End Liquid (case)],"#,0") & " STB/d"` (`KPI Liquid`).
- Q&A / Copilot prompt bar (Section 9).

**G1 — Daily fluid rates (Line chart).** X `fact_profile[date]` (Continuous); Y `[Avg Oil Rate]` `#2E7D32`,
`[Avg Water Rate]` `#0288D1`, `[Avg Gas Rate]` `#D32F2F`, `[Avg Liquid Rate]` `#6D4C41` dotted. X-axis constant line at
`[Forecast Start]` ("forecast start", `#ED1B2D`). Insight: oil decline vs water plateau → water is the controlling stream.

**G2 — Liquid handling (Line and stacked column chart).** X `fact_profile[Year]`; Column Y `[Avg Oil Rate]`,
`[Avg Water Rate]`; Line Y `[Avg Water Cut]` (secondary axis, format `0%`, range 0.5–1, colour `#ED1B2D`).
*Visual-level filter*: `fact_profile[source]` = Forecast. Title *fx* `[Title P2 G2]`.
Insight: total liquid halves (≈12.9k → ≈6k STB/d) but the water share rises to ~87% — the water-treatment train sets the load.

**G3 — Water injection throttling (Line chart).** X `fact_profile[date]`; Y `[Avg Injection]` `#0288D1`, `[Avg Liquid Rate]`
`#6D4C41` dashed; Secondary Y `[Injection / Liquid]` `#ED1B2D`. *Visual filter* source = Observed. Title from the data,
e.g. *fx* `"G3 · Water Injection — " & FORMAT(CALCULATE([Avg Injection], fact_profile[date] = CALCULATE(MIN(fact_profile[date]), fact_profile[water_inj_rate] > 0))/1000,"0.0") & "k → " & FORMAT(CALCULATE([Avg Injection], fact_profile[date] = CALCULATE(MAX(fact_profile[date]), fact_profile[source]="Observed"))/1000,"0.0") & "k STB/d"`.
Subtitle: "Surface-volume ratio (no formation volume factors); falling ratio = less pressure support, which explains part of the simulator drift late in history."

**G4 — Cumulative growth (Stacked area chart).** X `fact_profile[date]`; Y `[Oil Cum MMSTB]` `#2E7D32`, `[Water Cum MMSTB]`
`#0288D1` (stacked = gross liquid). Gas is in MSCF and cannot be stacked with barrels: add `[Gas Cum Bcf]` to *Tooltips*
(or place a small separate line chart beside it). X-axis constant line at the date water cumulative overtakes oil
(measure `Water>Oil Date = CALCULATE(MIN(fact_profile[date]), FILTER(VALUES(fact_profile[date]), [Water Cum MMSTB] > [Oil Cum MMSTB]))`).

**G5 — Water-cut progression, 10 cases (Line chart).** X `fact_profile[date]`; Legend `dim_case[case_label]`;
Y `[WCT Deviation pp]` (the absolute curves overlap within 0.5 pp, so plot each case's offset from the 10-case median).
*Visual filter* source = Forecast. *Edit interactions*: case slicer → **None** on this visual so all 10 lines stay; the
user highlights a case by clicking its legend entry. Constant Y line at 0, "10-case median".

**G6 — GOR control chart (Line chart).** X `fact_profile[date]`; Y `[Avg GOR]`. *Analytics → Y-axis constant lines*:
*fx* `[GOR Mean (obs)]` (solid `#2E7D32`), `[GOR UCL]` and `[GOR LCL]` (dashed grey, "+3σ", "−3σ").
Subtitle (keep it honest): "Forecast gas = GOR × oil by construction (363 scf/STB). Observed GOR inside ±3σ is consistent
with reservoir pressure above bubble point; no PVT data confirms it."

**AI diagnosis.** Card (new) with `[AI_Page2_Diagnosis]`, same styling as Page 1, title "✦ AI Engineering Diagnosis".

---

## 8. Page 3 — Subsurface Physics & ML Governance (Geomodellers, Data Scientists)

**G1 — K-Means trust-region scatter (Scatter chart).** Values `proxy_optimised_sets[rank]` (Don't summarize);
X `poro_mult`; Y `perm_mult`; Size `aquifer_pv`; *Markers → fx* gradient on `J` (green→amber→crimson). Category
labels: `cluster` via a measure `"k" & FORMAT(MAX(proxy_optimised_sets[cluster]),"0")` in *Tooltips*.
Insight: porosity spans only ~1.2% across the 10 trusted optima; permeability spans ~2.3× at near-identical J.

**G2 — 1st- vs 2nd-order sensitivity (Clustered bar chart = tornado).** Y `sensitivity_long[parameter]`;
Legend `sensitivity_long[Series]`; X `Sum of rho`. *Visual filter* `Series` in: "1st order · oil_2008",
"2nd order (after porosity) · oil_2008", "2nd order (after porosity) · water_2008". X range −1 to 1. Colours `#2A2F3A`,
`#2E7D32`, `#0288D1`. Card beside it: `[Porosity R2 Oil]` "explained by porosity alone".
Insight: porosity ρ = 0.99 first-order; after removing it, permeability drives the oil residual (ρ 0.89) and aquifer PV the
water residual (ρ 0.82); fault transmissibility |ρ| < 0.05 = noise.

**G3 — Surrogate test-set error (Clustered column chart).** X `model_test_long[family]`; Legend `[Metric Label]`;
Y `Sum of value`. *Visual filters*: split = test; metric in the four `*_2008_err_%` / `*_worst_case_%`. *Y-axis → Scale type: Log*.
Sort by Oil 2008 error ascending. Insight: GP 0.038% oil vs MLP 0.121% (3.2× lower); kNN and LightGBM have negative
2nd-order R² (add a small table of `oil_2nd_order_R2` / `water_2nd_order_R2` as tooltip).

**G4 — Extrapolation-method range (Clustered bar chart).** Y `method_sensitivity[Method Window]`; Legend `tie_in`
(`rate_ratio` `#ED1B2D`, `wor_shift` `#2A2F3A`); X `oil_2028_mmstb_median` (Sum). X range 50–62. *Analytics →
constant line* *fx* `[Simulator P50 MMSTB]`, `#2E7D32`, "Simulator P50". Insight: liquid_wor falls 59.1 → 53.8 as the
window lengthens 8 → 16q; arps_wor moves less (60.1 → 58.4); liquid_wor 16q had the best 2005 back-test (3.29) and lands on the simulator P50.

**G5 — Porosity vs mismatch J (Scatter chart).** Values `all_cases[case]`; X `poro_mult`; Y `J` (*Scale type Log*);
Legend `split`. Add `proxy_optimised_sets` as a second scatter overlaid exactly on top (transparent background), or
show it on G1 only. Insight: J should bottom out in a narrow porosity window — the 10 GP optima sit at 1.362–1.378 — confirming porosity as the identifiable parameter. Check the 100-case cloud agrees once `all_cases` carries the parameters.

**G6 — PCA variance (Line chart).** X `pca_variance[k]` (Continuous, 1–12); Y `cum_explained_var` (format `0.000%`);
Legend `phase`. X-axis constant lines at 5 ("oil k=5") and 6 ("water k=6"). Subtitle: "k chosen as the smallest that rebuilds
every train and validation curve within 0.1%; worst test-curve error 0.055% (oil) / 0.052% (water)."

**AI governance box.** Card (new) `[AI_Page3_Governance]`, title "✦ Subsurface AI Governance & Physics Takeaway".

---

## 9. AI features

### 9.1 Prompt box at the top of each page

- **Until December 2026 — Q&A:** *Insert → Buttons → Q&A* (speech-bubble icon) at the right of the top row; it opens
  the Q&A explorer. Or *Insert → Q&A* visual sized 670 × 60 as an inline prompt bar. Teach it terms via
  *Modeling → Q&A setup → Synonyms*: `oil EUR` → `Oil EUR (case)`, `mismatch` → `history_mismatch_J`, `case` → `case_label`.
  Add suggested questions: "P50 oil EUR", "history mismatch J by case_label", "water cut 2028 by case_label".
- **Long-term — Copilot:** Q&A retires by end of December 2026. With a Fabric/Premium capacity that has Copilot
  enabled, viewers use the **Copilot pane** in the report toolbar. Prepare the model with *Prep data for AI*:
  AI schema (hide `d_*`, `t_years`, helper tables), verified answers for the questions above, and AI instructions,
  e.g. "P50 means the 10-case median at Jan 2028. Volumes are STB except gas (MSCF). Net cash flow is simplified."

### 9.2 Dynamic commentary at the bottom of each page

The three `AI_*` DAX measures (Section 5.7) are the commentary. They are deterministic — every sentence is computed
from the same measures as the charts, so they cannot drift from the visuals and need no licence. If Copilot is
available you may *add* a Copilot narrative visual beside them, but keep the DAX boxes as the audited version.

---

## 10. Finishing

1. **Sync slicers** (*View → Sync slicers*): the economic parameters live on Page 1 only; the case slicer on Page 2 only. The Phase slicer is Page 1 only.
2. **Tooltips**: on every case-level visual add `dim_case[case]` ("sim #"), `history_mismatch_J`, `split`.
3. **Accessibility**: alt text on each visual (*Format → General → Alt text*), tab order (*View → Selection → Tab order*), contrast ≥ 4.5:1 on the dark boxes (the theme's white on `#1E2229` passes).
4. **Performance**: *View → Performance analyzer → Start recording → Refresh visuals*; every visual should render < 500 ms on this ~1.2k-row model.
5. **Publish**: *Home → Publish* to the workspace; set the CSV folder as the refresh source (gateway or SharePoint folder) if the pipeline will be re-run.

---

## 11. Acceptance check — values that must match the prototype

With defaults (oil $80, gas $3, lifting $12, water $1.5, discount 10%) and the observed file loaded:

| Item | Expected |
|---|---|
| P50 oil EUR | 53.81 MMSTB, range 53.27–53.82 |
| P50 gas EUR | 19.55 Bcf, GOR 363 scf/STB |
| P50 water EUR | 65.50 MMSTB, water cut 86.7% |
| P50 case | sim #40 (Case 6) |
| G3 spread (oil) | 1.03% |
| Method envelope | 53.2–60.1 MMSTB |
| GP test error | 0.038% oil / 0.088% water |
| Porosity-only R² (oil 2008) | 98.5% |
| Page 2, Case 1 | J 0.0187, 2028 WCT 86.6%, oil 810 STB/d, liquid 12,934 → 6,029 STB/d |
| Incremental oil / NCF / NPV10 | Depend on the observed Jan-2008 cumulative. With the back-calculated base: 15.43 MMSTB, $0.99 B, $0.58 B. Run the Streamlit app on the same `outputs/powerbi` folder (`DWC_DATA=outputs/powerbi streamlit run dashboard/app.py`) and compare. |
