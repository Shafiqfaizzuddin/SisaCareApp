# Active waste rules

Edit [`waste_rules.json`](waste_rules.json) for the Florence-2 waste mapping.
It is the single maintained catalog for active labels, canonical names,
aliases, materials, four final categories, condition questions, handling text,
station material keys, bulky flags, and stable rule IDs. Increment the catalog
version and affected rule IDs when a rule changes. The two older files,
`object_names.json` and `waste_categories.json`, are retained for the legacy
YOLO/VLM comparison path and historical interpretation; do not delete them.

The classifier matches only normalized explicit aliases and ordinary final-word
singular/plural forms. Generic bottles, cans, containers and unmatched labels
retain a null category and a confirmation question. A recyclable item can have
`waste_category: Recyclable Waste` while condition questions remain unanswered.
That category does not establish station acceptance. Check the exact
`station_material_key` against a registered station and confirm relevant item
conditions before recommending recycling. Unknown acceptance stays unknown.
`Hazardous Waste` takes priority over `Bulky Waste`; `bulky` remains a separate
flag. Furniture needs confirmation that it is discarded waste. The response
keeps the original model label, rule ID and classification source. No model
confidence is fabricated by these rules.

The handling text is fixed in the catalog. The reviewed references used for
this migration are the [Malaysia Department of Environment's registered
e-waste collection guidance](https://ewaste.doe.gov.my/index.php/about/where-can-i-discharge-recycle-e-waste/),
the [US EPA guidance for household batteries](https://www.epa.gov/recycle/used-household-batteries),
the [US EPA guidance on common recyclables and local acceptance](https://www.epa.gov/recycle/how-do-i-recycle-common-recyclables),
[Cornwall Council lighter guidance](https://www.cornwall.gov.uk/rubbish-recycling-and-waste/recycling/recycling-items/lighters/),
and the [US EPA recycling FAQ for aerosol cans](https://www.epa.gov/recycle/frequent-questions-recycling).
Lighters and aerosol cans use the application's conservative special-collection
route; the mapping does not assert that every such item has one legal hazardous
classification. Users are not asked to release fuel or puncture containers.
Each rule includes `guidance_source`; entries marked `existing_project_mapping_v1`
retain the project's earlier fixed wording, reviewed here for conservative
handling language. Local collection policy still determines which streams
accept an item. The app never asks Ollama to write safety handling guidance.
