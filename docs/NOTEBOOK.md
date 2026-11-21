# The notebook (`archive/AnalyticsPro_AI_Data_Analyst.ipynb`)

**What it is:** the original Google Colab prototype of the project ("Phase 1" and "Phase 2" cells: loading, cleaning, correlation, outliers, simple scikit-learn models, PDF/PowerPoint report experiments). It imports `google.colab`, `scikit-learn`, `python-pptx` and `reportlab`, none of which are dependencies of the app.

**Relationship to the app:** none at run time. The Streamlit app in `phase4/` does not import or execute the notebook, and the notebook does not import the app. It is kept as the project's history and as a portfolio exhibit of the analysis ideas the app grew from.

**Why it is 3.4 MB:** about 3.0 MB of that is embedded chart images saved as cell outputs. To shrink it without losing the code, run `jupyter nbconvert --clear-output --inplace archive/AnalyticsPro_AI_Data_Analyst.ipynb` (this was *not* done automatically because it would alter your file).

**Name:** the notebook's file name still says "AI Data Analyst". It contains machine-learning experiments; the app's rule-based "Ask Your Data" page does not.
