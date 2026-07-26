# Persona-Conditioned LLM Panel Scores

These scores support Table 2 and Multimedia Appendix 7 of JMIR manuscript 100769. The evaluators were **LLM personas**, not human experts. Each panel simulated three roles (Clinical Data Manager, Statistical Programmer, and Regulatory Specialist) and scored blinded A/B responses on structure, completeness, and terminology using the 1-5 rubric reported in Multimedia Appendix 4.

`persona_panel_scores.csv` contains the dimensional scores and A/B presentation metadata for both panels. `analyze_persona_panels.py --verify` reproduces the pooled means (baseline 3.60; framework 4.35; difference +0.75), interpanel choice Cohen kappa (0.76), and score Pearson correlation (0.95).

The condition mapping is included only for analysis; it was not exposed to the persona evaluators. Natural-language rationales and the complete rubric are provided in the submission appendices.
