# Florence-2 classification summary

The existing Florence-2 service remains the object detector. The existing waste rules remain the authority for disposal classes (`Recyclable Waste`, `Non-Recyclable Waste`, `Bulky Waste`, `Hazardous Waste`). The new **material category** is a separate, versioned summary of the original photo analysis: Organic, Plastic, Paper, Glass, Metal, Electronic, Hazardous, Other, or Unknown. It does not alter report submission categories or retrain Florence-2.

## Distribution

The denominator is the number of Florence detection observations classified as possible waste, including unresolved observations. Background detections are excluded. Each detector box contributes at most one observation. `percentage = category observation count / denominator × 100`, rounded to one decimal for display; counts and denominator are stored. These are **detection shares**. They are not physical item counts, image-area shares, waste mass, volume, or category probabilities. Overlapping or repeated boxes may describe the same object, so the shares are provisional.

The material mapping uses exact maintained rule identities and known material labels. Mixed but identified items use `Other`; missing or uncertain material evidence uses `Unknown`. Electronic devices retain the existing special-collection disposal rule while appearing as `Electronic` in this material view. Batteries and other rule-listed hazardous items appear as `Hazardous`. The original Florence labels and boxes remain unchanged in `model_detections`; normalized suggestions are stored separately in `raw_detections` and the `classification_summary` snapshot.

The dominant category is the unique category with the largest detection count. Ties, no non-background observations, or an Unknown largest group produce `Unknown` with an explanation.

## Severity and uncertainty

The displayed Low/Medium/High value is a **rule-based handling-priority estimate**, not a measured environmental severity or physical quantity. High means a detected item has a hazardous handling rule, including an electronic device when the existing disposal rule classifies it as hazardous. Medium means a classified electronic or bulky item needs a separate collection route without a hazardous rule. Low means only ordinary, resolved material categories were identified. The result is Unknown when there are no relevant detections, an unresolved material category, or an unresolved handling condition, unless a rule-listed hazardous item already calls for the precautionary High tier. The summary reports Unknown and uncertain observation counts explicitly.

Florence-2 does not return a calibrated detection score or material-category probability in this pipeline. Both fields remain `null`; the UI does not turn a detector score into a category share. A local Ollama visual assessment supplies an uncertainty flag and short justification for ambiguous detections. Ollama report drafting remains a separate prose step and cannot set material percentages or severity.

## Provenance and persistence

The analysis draft saves the original model output, rule/local-vision suggestions, summary version, and uncertainty. On report submission, the report's `ai_analysis_json` and PostgreSQL `ai_results.raw_result` retain that snapshot. Citizen edits are saved in `confirmed_ai_result_json` and PostgreSQL `ai_results.reviewed_result`; they do not overwrite the original summary. The submission UI labels model output, rules, citizen corrections, and pending administrator verification. Historical reports without a summary continue to render through the existing API contract.
