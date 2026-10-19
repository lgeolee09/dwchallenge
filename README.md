# DWC26 Dashboard

Three-page reservoir dashboard: Streamlit prototype + Power BI build kit.

```bash
pip install -r requirements-dashboard.txt
streamlit run app.py                      # runs on the CSVs in ./data

# full version (history, injection, case parameters, PCA variance):
python export_powerbi_data.py --repo ..   # after src/run_pipeline.py; writes ../outputs/powerbi
DWC_DATA=../outputs/powerbi streamlit run app.py
```

- `POWERBI_BUILD_GUIDE.md` — click-by-click Power BI build, data model and every DAX measure
- `exxon_theme.json` — Power BI theme (View → Themes → Browse for themes)

Put this folder at `<repo>/dashboard/`.
