# Active waste rules

Edit [`waste_rules.json`](waste_rules.json) for the Florence-2 waste mapping.
It is the single maintained catalog for active labels, canonical names,
aliases, materials, four final categories, condition questions, handling text,
station material keys, bulky flags, and stable rule IDs. Increment the catalog
version and affected rule IDs when a rule changes. The two older files,
`object_names.json` and `waste_categories.json`, are retained for the legacy
YOLO/VLM comparison path and historical interpretation; do not delete them.

The classifier returns `category: null` and `needs_confirmation: true` when
identity, material, relevant item condition, or selected station acceptance is
unknown. A category on a hazardous item may coexist with `needs_confirmation`
when its precise material is unknown. `Hazardous Waste` takes priority over
`Bulky Waste`; `bulky` remains a separate flag. Station keys are only material
matches; they do not prove the item is suitable for that station. The selected
station must accept the key, and condition questions must be answered before
the rule returns `Recyclable Waste`.

The handling text is fixed in the catalog. The reviewed references used for
this migration are the [Malaysia Department of Environment's registered
e-waste collection guidance](https://ewaste.doe.gov.my/index.php/about/where-can-i-discharge-recycle-e-waste/),
the [US EPA guidance for household batteries](https://www.epa.gov/recycle/used-household-batteries),
and the [US EPA guidance on common recyclables and local acceptance](https://www.epa.gov/recycle/how-do-i-recycle-common-recyclables).
Each rule includes `guidance_source`; entries marked `existing_project_mapping_v1`
retain the project's earlier fixed wording, reviewed here for conservative
handling language. Local collection policy still determines which streams
accept an item. The app never asks Ollama to write safety handling guidance.
