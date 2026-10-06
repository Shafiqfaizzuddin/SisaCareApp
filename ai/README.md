# AI assets

This directory contains runtime assets and configuration for waste detection.

- `models/expV2.pt` is the trained YOLOv8s model expected by the backend.
- `config/waste_categories.json` maps model class names to application categories.

Model weights are intentionally excluded from Git. Place the trained model at
`ai/models/expV2.pt` in each runtime environment. Override `YOLO_MODEL_PATH` in
`backend/.env` when selecting a different compatible Ultralytics checkpoint.
