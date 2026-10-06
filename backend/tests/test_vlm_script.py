from pathlib import Path
from runpy import run_path
from typing import Any, Mapping


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "ai" / "test_vlm.py"
SCRIPT = run_path(str(SCRIPT_PATH))
run_case = SCRIPT["run_case"]
run_suite = SCRIPT["run_suite"]


def vlm_result(
    name: str,
    category: str,
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "scene_description": f"A {name} is visible.",
        "objects": [
            {
                "name": name,
                "display_name": name.title(),
                "suggested_category": category,
                "confidence_level": confidence,
                "reason": f"The {name} is visibly identifiable.",
            }
        ],
    }


def suite_images() -> dict[str, Path]:
    return {
        "recyclable": Path("recyclable.jpg"),
        "non_recyclable": Path("non-recyclable.jpg"),
        "bulky": Path("bulky.jpg"),
        "mixed": Path("mixed.jpg"),
        "unclear": Path("unclear.jpg"),
        "no_waste": Path("no-waste.jpg"),
    }


def test_single_case_prints_raw_structured_result(capsys: Any) -> None:
    expected = vlm_result("plastic bottle", "Recyclable Waste")

    def analyzer(path: str | Path) -> Mapping[str, Any]:
        assert path == Path("waste.jpg")
        return expected

    result = run_case("VLM waste analysis", Path("waste.jpg"), analyzer=analyzer)

    output = capsys.readouterr().out
    assert result is expected
    assert '"scene_description": "A plastic bottle is visible."' in output
    assert '"suggested_category": "Recyclable Waste"' in output
    assert '"confidence_level": "high"' in output
    assert "YOLO" not in output


def test_six_case_suite_calls_only_supplied_vlm_analyzer(capsys: Any) -> None:
    images = suite_images()
    called_paths: list[Path] = []
    outputs = {
        images["recyclable"]: vlm_result("plastic bottle", "Recyclable Waste"),
        images["non_recyclable"]: vlm_result("food wrapper", "Non-Recyclable"),
        images["bulky"]: vlm_result("mattress", "Bulky Waste"),
        images["mixed"]: {
            "scene_description": "A bottle and wrapper are visible.",
            "objects": [
                *vlm_result("plastic bottle", "Recyclable Waste")["objects"],
                *vlm_result("food wrapper", "Non-Recyclable")["objects"],
            ],
        },
        images["unclear"]: vlm_result("container", "Unknown", "low"),
        images["no_waste"]: {
            "scene_description": "An empty paved area is visible.",
            "objects": [],
        },
    }

    def analyzer(path: str | Path) -> Mapping[str, Any]:
        resolved = Path(path)
        called_paths.append(resolved)
        return outputs[resolved]

    exit_code = run_suite(images, analyzer=analyzer)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called_paths == list(images.values())
    assert output.count('"scene_description"') == 6
    assert "VLM local suite: PASSED" in output


def test_suite_fails_when_expected_category_is_absent(capsys: Any) -> None:
    images = suite_images()

    def analyzer(path: str | Path) -> Mapping[str, Any]:
        if Path(path) == images["no_waste"]:
            return {"scene_description": "No waste is visible.", "objects": []}
        if Path(path) == images["mixed"]:
            return {
                "scene_description": "Several bottles are visible.",
                "objects": [
                    *vlm_result("plastic bottle", "Recyclable Waste")["objects"],
                    *vlm_result("drink can", "Recyclable Waste")["objects"],
                ],
            }
        return vlm_result("plastic bottle", "Recyclable Waste")

    exit_code = run_suite(images, analyzer=analyzer)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Non-recyclable image did not produce Non-Recyclable" in output
    assert "Bulky image did not produce Bulky Waste" in output
    assert "Mixed image did not produce" in output
    assert "VLM local suite: FAILED" in output
