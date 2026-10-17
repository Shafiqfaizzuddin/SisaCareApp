# Local Florence-2 object detection

This service runs only the Microsoft Florence-2 `<OD>` task. It is an isolated
detector for the application backend. The active authenticated analysis route is
`POST /api/waste/analyze`; the backend calls this service. The former YOLO/VLM
workflow remains at `POST /api/waste/analyze-legacy` for baseline comparison.
The detector itself listens on `127.0.0.1:8765`
by default and has no public authentication, so keep it on loopback.

The [official Microsoft model card](https://huggingface.co/microsoft/Florence-2-base)
documents `<OD>`, `post_process_generation`, and float16 on CUDA/float32 on CPU.
The checked-in [config.json](config.json) pins the official base checkpoint to
commit `5ca5edf5bd017b9919c05d08aebef5e4c7ac3bac`. That checkpoint requires
`trust_remote_code=True`; the pinned commit's model code and its `timm` and
`einops` imports were reviewed for this integration. The service loads only
safetensors weights. Do not change the model revision without reviewing the
new model code. To evaluate official `microsoft/Florence-2-large`, change both
`model_id` and `model_revision` to a reviewed commit, or set the matching
`FLORENCE_MODEL_ID` and `FLORENCE_MODEL_REVISION` environment variables.

## Install on Windows

Use Python 3.11 or 3.12 in `florence_service/.venv`. The application's
`backend/.venv` remains separate. If Python 3.11 is already installed, create
the environment with its executable. On the current Windows setup, where only
Python 3.14 was initially installed, the following keeps Python 3.11 and the
package cache inside `florence_service/`:

```powershell
python -m pip install --target florence_service/.bootstrap uv==0.13.0
$env:UV_PYTHON_INSTALL_DIR = (Resolve-Path florence_service).Path + '\.python'
$env:UV_CACHE_DIR = (Resolve-Path florence_service).Path + '\.cache'
florence_service/.bootstrap/bin/uv.exe python install 3.11
florence_service/.bootstrap/bin/uv.exe venv florence_service/.venv --python florence_service/.python/cpython-3.11.17-windows-x86_64-none/python.exe
florence_service/.bootstrap/bin/uv.exe pip install --python florence_service/.venv/Scripts/python.exe torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
florence_service/.bootstrap/bin/uv.exe pip install --python florence_service/.venv/Scripts/python.exe -r florence_service/requirements.txt
florence_service/.venv/Scripts/python.exe -m florence_service.run
```

The CUDA wheel pair follows [PyTorch's official 2.9.1 installation
instructions](https://pytorch.org/get-started/previous-versions/). For CPU-only
operation, use the PyTorch `/whl/cpu` index in the fifth command. If an already
installed Python 3.11/3.12 is available, a normal `venv` and `pip` installation
of these same pinned requirements works too.
The service selects `cuda:0` when available, otherwise `cpu`; `/health` reports
the actual selected device and precision. Set `device_preference` to `cpu` in
`config.json` to run on CPU even when CUDA is available. Model loading begins
once on startup.
`/health` responds with `service_available: true` even during loading or after
a model load error, while `model_ready` stays false. Detection requests then
return `MODEL_NOT_READY` (503). Run one worker only: each worker would otherwise
load another model copy. The service also serializes inference, returning
`INFERENCE_BUSY` (503) rather than queueing indefinitely.

`config.json` is the default deployment configuration. Each key can be
overridden with `FLORENCE_<UPPERCASE_KEY>`. The configured host must be a loopback
address. The application backend's URL and timeout live in `backend/.env` as
`FLORENCE_SERVICE_URL` and `FLORENCE_SERVICE_TIMEOUT_SECONDS`.

## API

`POST /detect` accepts multipart field `image`, with matching JPEG, PNG or WEBP
MIME type and decoded content. Uploads are limited to 10 MiB, 40 million pixels,
and 10,000 pixels per side by default. EXIF orientation is applied before
inference, and returned dimensions and boxes refer to the oriented RGB image.

```json
{
  "success": true,
  "analysis_id": "2ae88f6d3bbf49f9a27643de3899d856",
  "image_width": 640,
  "image_height": 480,
  "model_id": "microsoft/Florence-2-base",
  "model_revision": "5ca5edf5bd017b9919c05d08aebef5e4c7ac3bac",
  "device": "cuda:0",
  "precision": "float16",
  "detections": [{
    "label": "bottle",
    "bounding_box": {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 150.0},
    "confidence": null
  }],
  "processing_time_ms": 345,
  "warnings": [],
  "error": null
}
```

Boxes are floating-point pixel **edges** in `x1,y1,x2,y2` order, measured from
the top-left of the oriented image. They are clipped to `[0,width]` and
`[0,height]`; right and bottom edges are exclusive. Empty or invalid boxes are
omitted with warnings. No calibrated detection probability is exposed. A valid
empty `<OD>` result is `success: true` with an empty array and a warning;
inference or post-processing errors are `success: false` with a non-2xx status
and an `error` code. This `analysis_id` identifies the inference call and is
not the application database draft ID returned by `/api/waste/analyze`.

The service performs generic object detection. The application suggests waste,
background, or uncertain review states and requires participant confirmation.
Report details are entered and reviewed before submission.
