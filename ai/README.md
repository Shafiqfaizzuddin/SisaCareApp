# AI assets

This directory contains runtime assets and configuration for waste detection.

- `models/best.pt` is the trained YOLO11n model expected by the backend.
- `config/waste_categories.json` maps model class names to application categories.

Model weights are intentionally excluded from Git. Place the trained model at
`ai/models/best.pt` in each runtime environment.
