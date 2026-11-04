"""Evidence-count material summary for the active Florence analysis.

These are shares of detector observations, not image area, waste volume,
physical item counts, or calibrated class probabilities.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from app.services.ai.waste_rules import normalize_label

CATEGORIES = ("Organic", "Plastic", "Paper", "Glass", "Metal", "Electronic", "Hazardous", "Other", "Unknown")
MATERIAL_CATEGORY = {
    "organic_material": "Organic", "food": "Organic", "wood": "Organic",
    "plastic": "Plastic", "pet": "Plastic", "soft_plastic": "Plastic",
    "expanded_plastic_foam": "Plastic", "paper": "Paper", "paper_and_cardboard": "Paper",
    "cardboard": "Paper", "glass": "Glass", "metal": "Metal", "aluminum": "Metal",
    "aluminium": "Metal", "electronic_components": "Electronic",
}
ELECTRONIC_ITEMS = frozenset({"power_bank", "washing_machine", "television", "mobile_phone",
                              "laptop", "circuit_board", "electronic_waste"})
ORGANIC_ITEMS = frozenset({"food_waste", "tree_branch"})
MIXED_MATERIALS = frozenset({"mixed_material", "mixed_packaging_material",
                             "contaminated_packaging_material", "mixed_furniture_material",
                             "mixed_bedding_material", "textile", "rubber", "ceramic",
                             "composite_carton"})
OTHER_ITEMS = frozenset({"general_waste", "rope_strings", "small_accessory", "disposable_cutlery",
                         "dirty_food_container", "wet_wipes", "diaper", "cigarette_butt",
                         "chair", "table", "cabinet", "bed_frame", "sofa", "mattress"})


def classify_observation(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return a material class and its evidence source without changing disposal rules."""
    if item.get("review_status") == "background":
        return {"normalized_category": None, "normalized_basis": "excluded_background",
                "normalized_uncertainty": None}
    if item.get("review_status") != "likely_waste":
        return {"normalized_category": "Unknown", "normalized_basis": "insufficient_evidence",
                "normalized_uncertainty": item.get("confirmation_reason") or "Waste identity needs confirmation."}
    visual = item.get("visual_assessment")
    if isinstance(visual, Mapping) and visual.get("uncertain") is True:
        return {"normalized_category": "Unknown", "normalized_basis": "uncertain_visual_assessment",
                "normalized_uncertainty": visual.get("visual_justification") or "Visual assessment was uncertain."}

    name = normalize_label(str(item.get("canonical_name") or item.get("name") or ""))
    material = normalize_label(str(item.get("material") or ""))
    disposal = item.get("suggested_category")
    rule_id = item.get("rule_id")
    source = "rule" if rule_id and item.get("classification_source") != "vision" else "local_vision"
    if name in ELECTRONIC_ITEMS:
        category = "Electronic"
    elif disposal == "Hazardous Waste":
        category = "Hazardous"
    elif name in ORGANIC_ITEMS:
        category = "Organic"
    elif material in MATERIAL_CATEGORY:
        category = MATERIAL_CATEGORY[material]
    elif material in MIXED_MATERIALS or name in OTHER_ITEMS:
        category = "Other"
    else:
        category = "Unknown"
    return {"normalized_category": category,
            "normalized_basis": source if category != "Unknown" else "insufficient_material_evidence",
            "normalized_uncertainty": (item.get("confirmation_reason") if item.get("needs_confirmation") else None)
            or ("The image does not establish the material category." if category == "Unknown" else None)}


def summarize_detections(detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Count each non-background Florence detection once, including Unknown."""
    counts: Counter[str] = Counter()
    background = 0
    uncertain = 0
    special_handling = False
    hazardous = False
    for item in detections:
        result = classify_observation(item)
        item.update(result)
        category = result["normalized_category"]
        if category is None:
            background += 1
            continue
        counts[category] += 1
        if result["normalized_uncertainty"]:
            uncertain += 1
        if category == "Hazardous" or (category != "Unknown" and item.get("suggested_category") == "Hazardous Waste"):
            hazardous = True
        if category == "Electronic" or item.get("suggested_category") == "Bulky Waste":
            special_handling = True
    denominator = sum(counts.values())
    distribution = [{"category": category, "count": counts[category],
                     "percentage": round(counts[category] * 100 / denominator, 1)}
                    for category in CATEGORIES if counts[category] and denominator]
    maximum = max(counts.values(), default=0)
    leaders = [category for category in CATEGORIES if maximum and counts[category] == maximum]
    dominant = leaders[0] if len(leaders) == 1 else "Unknown"
    if not denominator:
        dominant_reason = "No non-background detections were available."
    elif len(leaders) != 1:
        dominant_reason = "The largest detection shares are tied."
    elif dominant == "Unknown":
        dominant_reason = "Unresolved detections form the largest share."
    else:
        dominant_reason = "Largest share of non-background detection observations."

    if hazardous:
        severity = "High"
        severity_reason = "At least one detected item has a hazardous or special-collection handling rule. Contents and impact are unverified."
    elif not denominator or counts["Unknown"] or uncertain:
        severity = "Unknown"
        severity_reason = "The image leaves at least one relevant item or handling condition unresolved."
    elif special_handling:
        severity = "Medium"
        severity_reason = "A detected electronic or bulky item needs a separate collection route."
    else:
        severity = "Low"
        severity_reason = "Only ordinary material categories were identified; environmental impact is not measured."
    return {
        "version": "1.0.0", "source": "florence2_detections_plus_rules",
        "denominator_definition": "Non-background Florence detection observations, including Unknown; one observation per detector box.",
        "total_detections": len(detections), "background_excluded": background,
        "denominator": denominator, "unknown_count": counts["Unknown"],
        "uncertain_count": uncertain, "distribution": distribution,
        "dominant_category": dominant, "dominant_reason": dominant_reason,
        "severity": {"level": severity, "method": "rule_based_handling_priority_v1", "reason": severity_reason,
                     "is_physical_measurement": False},
        "confidence": {"florence_detection_score": None, "category_probability": None,
                       "explanation": "Florence-2 boxes provide no calibrated confidence or category probability in this pipeline."},
        "limitations": ["Detection share is not physical composition, mass, volume, or image area.",
                        "Model labels and local visual assessments require citizen review and administrator verification."],
    }
