# Campus waste recognition evaluation

The active pipeline is local Florence-2 `<OD>` candidates, user confirmation,
application waste rules, and optional local Ollama prose drafting. A prompt or
rule edit does not retrain Florence-2. Keep the older YOLO weights and evaluation
results as a comparison baseline. Do not alter historical analyses or reports.

## Audit before training

Collect representative photos with permission and remove personal identifiers.
Include plastic bottles, generic bottles, food waste, furniture, batteries,
electronics, lighters, aerosol cans, mixed piles, no-waste scenes, attached and
detached components, small objects, occlusion, and difficult lighting. Include
photos outside campus boundaries when they reflect the reporting workflow.

Annotate every visible candidate with a pixel bounding box, object label,
material only when visually supported, and a flag for background versus likely
waste. Record uncertain identity separately. Keep disposal category and station
acceptance as rule/confirmation outcomes, not image-model ground truth. For each
photo, compare raw Florence boxes and labels with annotations, then separately
review user confirmation, mapping outcome, station matching, and report draft.
Count missed objects, false background candidates, wrong labels, and wrong rule
mapping in separate error buckets. Fix mapping and integration errors before
considering fine-tuning.

Measure per-class detection precision/recall and mAP at stated IoU thresholds,
small-object recall, false candidate rate on no-waste photos, and the fraction
requiring user correction. Report metrics by lighting and mixed-scene subset.
Keep one incident or scene, including near-duplicate frames, wholly within one
train, validation, or held-out test split. Record checkpoint revision, code
version, rule version, hardware, and timing for repeatability.

## If evaluation justifies fine-tuning

Define classes from observed campus objects, with generic bottle separate from
plastic bottle and special-collection electronics separate from ordinary
recyclables. Create reviewed box and label annotations in a format supported by
the chosen Florence-2 fine-tuning procedure. Reserve the held-out test split
before model work; use validation data for checkpoint selection only. Compare
the tuned model to the pinned Florence-2-base checkpoint and retained YOLO
baseline on the same held-out incidents. Require a measurable improvement in
relevant recall without an unacceptable increase in false waste suggestions or
latency. No training should start until this dataset and evaluation protocol
exist.

At this change, the repository has no representative campus photo dataset and
the local Florence and Ollama services were unavailable for live evaluation.
Model quality therefore remains unverified; backend mapping and workflow tests
do not substitute for an image-level evaluation.
