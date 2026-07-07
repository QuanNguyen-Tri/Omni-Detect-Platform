# Omni-Detect

Omni-Detect is a platform foundation for AI-generated content and image
tampering detection. The current service implementation is a backend MVP: it
accepts detection requests, validates payloads, creates async jobs, schedules
limited GPU work, and calls a mockable RunPod client abstraction.

The repository also includes a dependency-free static demo UI under `frontend/`
and an offline real-model handoff toolkit under `backend/` for PIXAR/SIDA/LISA
image-tampering baselines. The UI defaults to browser-only mock mode. Real model
calls require a separate HTTP adapter around the offline backend toolkit.

## Main Features

- Async FastAPI server.
- Versioned detection endpoints:
  - `POST /v1/detect/text`
  - `POST /v1/detect/image`
  - `POST /v1/detect/file`
  - `GET /v1/jobs/{job_id}`
  - `GET /health`
- Typed Pydantic request and response schemas.
- In-memory job lifecycle with `queued`, `running`, `succeeded`, `failed`, and
  `cancelled` states.
- GPU scheduler with configurable concurrency, estimated job cost, short-job
  priority, FIFO ordering within priority, and long-job fairness.
- RunPod client protocol with fake and HTTP implementations.
- JSON error responses for validation, upload, not-found, and unexpected errors.
- Pytest coverage for validation, job transitions, scheduling, and mocked RunPod
  success/failure.
- Dependency-free static demo web UI with Demo Mode, Real Models Mode, multi-job
  drafts, job history, expandable results, and logo at
  `static/omni_detect_logo.png`.
- Offline backend handoff toolkit for six image-tampering models:
  `PIXAR-7B`, `PIXAR-13B`, `SIDA-7B`, `SIDA-13B`, `LISA-7B`, and `LISA-13B`.

## High-Level Architecture

Request flow:

```text
Client
  -> FastAPI route
  -> Pydantic validation
  -> JobStore creates queued job
  -> DetectionScheduler enqueues job
  -> Scheduler dispatches within GPU capacity
  -> RunPodClient submits and polls for result
  -> JobStore records succeeded or failed state
  -> Client polls GET /v1/jobs/{job_id}
```

The app is assembled in `omni_detect/api/app.py`. During FastAPI lifespan
startup, it creates:

- `Settings` from environment variables.
- `JobStore` for in-memory job state.
- `RunPodClient`, fake by default or HTTP when configured.
- `DetectionScheduler`, which runs as a background async task.

The current storage model is process-local memory. Jobs and uploaded payloads are
lost when the process restarts. Production deployments should add durable storage
and external object storage before handling real traffic.

The `backend/` directory is separate from the FastAPI MVP. It contains offline
CLI scripts for image/pixel-level tampering detection and localization. It does
not expose HTTP endpoints by itself, and it does not provide text or document
detection models.

## Code Structure

```text
omni_detect/
  api/
    app.py        FastAPI app factory and lifespan wiring.
    routes.py     HTTP endpoints, upload validation, job creation.
    errors.py     Consistent JSON error handlers.
  config.py       Typed settings loaded from environment variables.
  jobs.py         In-memory job model, store, and state transitions.
  runpod.py       RunPod client protocol, fake client, HTTP client, result parsing.
  scheduler.py    Async GPU scheduler and job execution loop.
  schemas.py      Request, response, job, and detection result models.

backend/
  HANDOFF.md      Model input/output contract for PIXAR, SIDA, and LISA.
  README.md       Offline baseline runner notes and model caveats.
  run.py          CLI entry point for single-image or batch inference.
  run_baselines.sh Thin wrapper around setup/run commands.
  setup.sh        Model and SAM weight download/check helper.
  prepare_inputs.py Input normalizer for images, folders, CSV, JSONL, JSON, TXT.
  infer_lisa.py   LISA inference worker.

frontend/
  index.html      Static demo UI entry point.
  package.json    Local dev, build, preview, and Pages build scripts.
  scripts/        Static GitHub Pages build and preview helpers.
  src/
    App.js        Browser app state, validation, submit, and polling flow.
    config.js     UI mode, backend URL, polling, and upload validation config.
    main.js       App bootstrap.
    components/   Reusable UI render modules.
    services/     Detection service selector, mock service, backend adapter client.
    styles/       Demo UI CSS.
    types/        JSDoc detection type definitions.

static/
  omni_detect_logo.png  Logo used by the demo UI header.

tests/
  conftest.py           Test app fixtures and job polling helper.
  test_api.py           API validation and fake RunPod result tests.
  test_jobs_scheduler.py Job lifecycle and scheduler behavior tests.

.github/
  workflows/
    deploy-pages.yml    GitHub Pages build and deployment workflow.
```

Root-level files:

- `pyproject.toml`: package metadata, dependencies, and pytest config.
- `LICENSE`: Apache 2.0 license.
- `.gitignore`: local Python and virtualenv artifacts.

## Demo Web UI

The demo web UI is a dependency-free static prototype under `frontend/`. It uses
plain HTML, browser-native JavaScript modules, and CSS. The header logo is loaded
from `static/omni_detect_logo.png`.

The UI has two modes:

- `Demo Mode`: default. All jobs stay in browser memory and use randomized fake
  results from `frontend/src/services/mockDetectionService.js`.
- `Real Models Mode`: submits image jobs to a configured HTTP adapter for the
  real PIXAR/SIDA/LISA image-tampering models. This mode does not call RunPod,
  model weights, or `backend/run.py` directly from the browser.

The real model handoff in `backend/HANDOFF.md` describes an offline CLI toolkit,
not an HTTP API. To use Real Models Mode, operators must run or build an adapter
that exposes:

- `GET /health`
- `POST /v1/detect/image`
- `GET /v1/jobs/{job_id}`

Real Models Mode is image-only because the handoff models perform image and
pixel-level tampering detection, not text or document detection. Text and file
drafts remain available in Demo Mode. In Real Models Mode they show a validation
error instead of submitting.

### Install Frontend Dependencies

There are no frontend package dependencies yet. Node and npm are not required.
`frontend/package.json` exists only to mark the modules as ESM and provide an
optional static-server script.

### Run The Demo UI Locally

From the repository root:

```bash
python3 -m http.server 5173 --directory .
```

If Node/npm is installed, this equivalent command is also available:

```bash
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173/frontend/
```

### Build The Frontend Locally

The current frontend is plain browser ESM, not Vite, Create React App, Next.js,
or React Router. The build step copies the static app into `frontend/dist`,
injects public runtime config, copies `static/` assets, writes `.nojekyll`, and
adds a `404.html` fallback for static hosting.

Install frontend package metadata and run the build:

```bash
cd frontend
npm install
npm run build
```

To test the same repository subpath that GitHub Pages will use, set
`VITE_BASE_PATH` during build:

```bash
cd frontend
VITE_BASE_PATH=/Omni-Detect-Platform/ npm run build
```

Use the actual repository name in place of `Omni-Detect-Platform`, or set
`VITE_BASE_PATH=/` for a user or organization Pages site such as
`<username>.github.io`.

### Preview The Production Build Locally

After building:

```bash
cd frontend
npm run preview
```

Open:

```text
http://127.0.0.1:4173/
```

For subpath preview, use the same base path for build and preview:

```bash
cd frontend
VITE_BASE_PATH=/Omni-Detect-Platform/ npm run build
VITE_BASE_PATH=/Omni-Detect-Platform/ npm run preview
```

Open:

```text
http://127.0.0.1:4173/Omni-Detect-Platform/
```

### Frontend Configuration

Frontend configuration is read from `frontend/src/config.js`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_DETECTION_API_MODE` | `mock` | `mock` for Demo Mode, `backend` for Real Models Mode. The old value `api` is accepted as an alias for `backend`. |
| `VITE_BASE_PATH` | `/` | Public base path for generated asset URLs. Use `/<repo-name>/` for GitHub project Pages. |
| `VITE_OMNI_DETECT_BACKEND_URL` | unset | Base URL for the HTTP adapter used by Real Models Mode. |
| `VITE_OMNI_DETECT_POLL_INTERVAL_MS` | `1000` | Browser polling interval for active jobs. |

For a future Vite-based frontend:

```bash
VITE_DETECTION_API_MODE=backend
VITE_BASE_PATH=/Omni-Detect-Platform/
VITE_OMNI_DETECT_BACKEND_URL=http://127.0.0.1:8000
```

Because the current demo is static and does not run through Vite, configure mode
and backend URL by defining `window.OMNI_DETECT_CONFIG` before
`frontend/src/main.js` loads:

```html
<script>
  window.OMNI_DETECT_CONFIG = {
    detectionApiMode: "backend",
    omniDetectBackendUrl: "http://127.0.0.1:8000"
  };
</script>
```

Keep this unset for the default browser-only mock demo. Real Models Mode may
require backend CORS configuration when the static UI and adapter are served
from different origins.

### Deploy The Frontend To GitHub Pages

The GitHub Pages workflow lives at:

```text
.github/workflows/deploy-pages.yml
```

It runs on pushes to `main` and can also be started manually with
`workflow_dispatch`. The workflow:

1. checks out the repository;
2. sets up Node.js LTS;
3. detects npm, pnpm, or yarn from lockfiles in `frontend/`;
4. installs dependencies;
5. builds the frontend from `frontend/`;
6. uploads `frontend/dist` as the Pages artifact;
7. deploys with the official GitHub Pages deploy action.

The workflow uses the official Pages actions:

- `actions/checkout`
- `actions/setup-node`
- `actions/configure-pages`
- `actions/upload-pages-artifact`
- `actions/deploy-pages`

Required workflow permissions are already configured:

- `contents: read`
- `pages: write`
- `id-token: write`

The deployment environment is `github-pages`.

To enable GitHub Pages in repository settings:

1. Open the GitHub repository.
2. Go to `Settings` -> `Pages`.
3. Set `Source` to `GitHub Actions`.
4. Save the setting.
5. Push to `main` or run `Deploy Frontend to GitHub Pages` manually from the
   Actions tab.

For project Pages, the workflow defaults `VITE_BASE_PATH` to:

```text
/<repository-name>/
```

For a user or organization Pages repository such as `<username>.github.io`, add
a repository variable named `VITE_BASE_PATH` with value `/`.

To configure a public backend adapter URL for Real Models Mode on Pages, add a
repository variable:

```text
VITE_OMNI_DETECT_BACKEND_URL=https://your-backend.example.com
```

Do not use GitHub Pages for secrets. Frontend environment variables are compiled
into static files and are visible to anyone who can load the site. Never put
RunPod API keys, Hugging Face tokens, model registry credentials, or private
backend secrets in frontend variables. Use a backend proxy or API for real model
calls.

GitHub Pages mode behavior:

- Demo Mode is the default and works without any backend or RunPod service.
- Real Models Mode remains selectable.
- If `VITE_OMNI_DETECT_BACKEND_URL` is not configured, Real Models Mode shows a
  friendly missing-backend message and does not crash.
- If the backend is unreachable, the UI shows a backend connection error and
  users can switch back to Demo Mode.

GitHub Pages deployment checklist:

1. Run `cd frontend && npm install`.
2. Run `npm run build`.
3. Run `npm run preview`.
4. Confirm the logo loads.
5. Confirm Demo Mode works.
6. Confirm multiple demo jobs work.
7. Confirm job history expands.
8. Confirm text highlights render.
9. Confirm image bounding boxes render.
10. Confirm file result tables render.
11. Push to `main`.
12. Confirm the GitHub Actions deployment succeeds.
13. Open the GitHub Pages URL.

### Multi-Job Workflow

Users can click `+ Add Job` to create multiple draft jobs. Each draft has:

- input type: text, image, or file;
- its own input and validation state;
- model selector for `PIXAR-7B`, `PIXAR-13B`, `SIDA-7B`, `SIDA-13B`, `LISA-7B`,
  or `LISA-13B`;
- priority selector: low, normal, or high.

Users can submit one draft or submit all valid drafts at once. Submitted jobs
move into the job history panel and transition through `Queued`, `Running`,
`Succeeded`, or `Failed`. Jobs remember the mode they were submitted with, so
switching modes does not change how existing jobs are polled.

### Detection Service Contract

The UI talks to a shared frontend service contract in
`frontend/src/types/detectionService.js`:

- `submitTextDetection(text, options)`
- `submitImageDetection(file, options)`
- `submitFileDetection(file, options)`
- `submitMultipleJobs(jobs)`
- `getJob(jobId)`
- `pollJobStatus(jobId)`
- `checkHealth()`

Implementations live in `frontend/src/services/`:

- `mockDetectionService.js`: browser-only fake service.
- `backendDetectionService.js`: HTTP client for a real-model backend adapter.
- `detectionClient.js`: creates the `mock` and `backend` service map.

Keep UI code pointed at this contract instead of importing implementation
details directly.

### How The Mock Service Works

`mockDetectionService.js` stores jobs in a browser memory `Map`, schedules
`setTimeout` state transitions, generates random detection results, and
occasionally returns a fake failed job. It supports concurrent fake jobs, model
and priority metadata, random text spans, random image regions, random file
sections, fake analysis summaries, and health checks. Refreshing the page clears
all demo jobs.

### Real Model Result Normalization

`backendDetectionService.js` accepts either existing Omni-Detect `/v1` job
responses or HANDOFF-style image records from `summary_all.json`. HANDOFF-style
records are normalized into the UI image result shape:

- `document_level.p_tampered` becomes `overall_ai_probability`;
- `pixel_level.mask_png` becomes `mask_url`;
- `pixel_level.overlay_png` becomes `overlay_url`;
- `pixel_level.positive_pixel_fraction` is displayed as mask coverage;
- no bounding boxes are invented because the real models return pixel masks, not
  boxes.

### Job History And Details

Every submitted job appears in the job history panel with:

- job ID;
- mode: Demo or Real Models;
- input type;
- model;
- priority;
- created time;
- completed time;
- duration;
- status;
- overall AI probability when a result is available.

Use `View Details` to expand a submitted job:

- text demo jobs show highlighted suspicious spans and a spans table;
- image demo jobs show the uploaded preview with fake bounding boxes;
- image real-mode jobs show mask/overlay outputs when the adapter returns them;
- file demo jobs show file metadata and fake section/page probabilities;
- failed jobs show the structured error message.

### Demo Validation

The UI validates inputs before creating a job:

- text input cannot be empty;
- image uploads must be PNG, JPG, JPEG, or WEBP;
- document uploads must be PDF, TXT, DOC, or DOCX;
- uploads are limited to 10 MB in the demo UI;
- Real Models Mode accepts image drafts only.

Unsupported files and unsupported real-mode modalities show friendly validation
errors.

### Manual Verification

1. Start the demo UI with `python3 -m http.server 5173 --directory .`.
2. Open `http://127.0.0.1:5173/frontend/`.
3. Confirm the Omni-Detect logo appears in the header.
4. Confirm the app starts in Demo Mode.
5. Click `+ Add Job` and create at least three drafts.
6. Configure one text draft, one image draft, and one file draft.
7. Change model and priority values on the drafts.
8. Submit one job and confirm it appears in job history with mode `Demo`.
9. Click `Submit all valid jobs` and confirm multiple jobs run concurrently.
10. Confirm statuses change from `Queued` to `Running` to `Succeeded` or
    `Failed`.
11. Confirm created time, completed time, duration, model, priority, mode, and
    probability fields appear in history.
12. Expand a text job and confirm highlighted spans appear.
13. Expand an image job and confirm bounding boxes appear over the preview.
14. Expand a file job and confirm fake file section/page results appear.
15. Switch to Real Models Mode with no backend URL configured and confirm the
    backend status banner reports the missing `VITE_OMNI_DETECT_BACKEND_URL`.
16. In Real Models Mode, try submitting text or file drafts and confirm the
    image-only validation error appears.
17. Configure `window.OMNI_DETECT_CONFIG.omniDetectBackendUrl` for a local
    adapter and confirm the `Check backend health` button reports health.

## API Behavior

### `POST /v1/detect/text`

JSON body:

```json
{
  "text": "Text to inspect",
  "estimated_cost": 1.0,
  "metadata": {"source": "example"}
}
```

`text` is required, must not be blank, and is capped at 100,000 characters.
`estimated_cost` is optional and must be greater than `0` and less than or equal
to `1000`. If omitted, the API estimates cost from text length.

### `POST /v1/detect/image`

Multipart form fields:

- `file`: required upload.
- `estimated_cost`: optional float.

Allowed image content types:

- `image/jpeg`
- `image/png`
- `image/webp`

Default image upload limit: 20 MiB.

### `POST /v1/detect/file`

Multipart form fields:

- `file`: required upload.
- `estimated_cost`: optional float.

Allowed file content types:

- `application/pdf`
- `text/plain`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

Default file upload limit: 50 MiB.

### Job Create Response

All detection endpoints return `202 Accepted`:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "kind": "text",
  "estimated_cost": 1.0,
  "status_url": "/v1/jobs/uuid"
}
```

### `GET /v1/jobs/{job_id}`

Returns current job state, timestamps, and either a detection result or an error.

Text results include:

- `overall_ai_probability`
- `spans` with `start_char`, `end_char`, `text`, `ai_probability`, `label`

Image results include:

- `overall_ai_probability`
- `regions` with `x`, `y`, `width`, `height`, `ai_probability`, `label`

File results include:

- `overall_ai_probability`
- `sections` with `section_id`, optional page range, `ai_probability`, `label`

## Configuration

Backend API configuration is loaded from environment variables in
`omni_detect/config.py`. Frontend-only variables are documented in
`Frontend Configuration` above.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OMNI_MAX_CONCURRENT_GPU_JOBS` | `6` | Maximum scheduler jobs running at once. |
| `OMNI_SHORT_JOB_COST_THRESHOLD` | `1.0` | Jobs at or below this estimated cost are short jobs. |
| `OMNI_MAX_SHORT_JOB_STREAK` | `3` | Number of short jobs allowed before promoting a waiting long job. |
| `OMNI_LONG_JOB_FAIRNESS_WAIT_SECONDS` | `30.0` | Waiting time after which a long job can be promoted. |
| `OMNI_RUNPOD_BACKEND` | `fake` | `fake` for local tests/dev, `http` for RunPod API calls. |
| `RUNPOD_API_KEY` | unset | Required when `OMNI_RUNPOD_BACKEND=http`. |
| `RUNPOD_ENDPOINT_ID` | unset | Required when `OMNI_RUNPOD_BACKEND=http`. |
| `RUNPOD_API_BASE_URL` | `https://api.runpod.ai` | Base URL for RunPod HTTP API. |
| `OMNI_RUNPOD_REQUEST_TIMEOUT_SECONDS` | `30.0` | Per-request timeout for RunPod submit, status, and cancel calls. |
| `OMNI_RUNPOD_MAX_REQUEST_RETRIES` | `3` | Number of retry attempts after an initial retryable RunPod HTTP request failure. |
| `OMNI_RUNPOD_RETRY_BASE_DELAY_SECONDS` | `0.25` | Base exponential backoff delay between retry attempts. |
| `OMNI_RUNPOD_RESULT_POLL_INTERVAL_SECONDS` | `1.0` | Delay between RunPod status polls. |
| `OMNI_RUNPOD_MAX_RESULT_POLLS` | `120` | Maximum status polls before marking a job failed. |
| `OMNI_MAX_IMAGE_UPLOAD_BYTES` | `20971520` | Max image upload size in bytes. |
| `OMNI_MAX_FILE_UPLOAD_BYTES` | `52428800` | Max file upload size in bytes. |

Allowed upload content types are currently code-level settings in `Settings`.
Expose them as environment variables only if operators need to change them
without a deploy.

Do not hardcode secrets. Provide `RUNPOD_API_KEY` through the deployment
environment or secret manager.

## Run Locally

Create a virtual environment and install the project:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
```

Start the backend with the default fake RunPod client:

```bash
.venv/bin/python -m uvicorn omni_detect.api.app:app --reload --host 127.0.0.1 --port 8000
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

Submit a text detection job:

```bash
curl -X POST http://127.0.0.1:8000/v1/detect/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"This is a local test."}'
```

Poll the returned `status_url`:

```bash
curl http://127.0.0.1:8000/v1/jobs/<job_id>
```

## Run Offline Image-Tampering Baselines

The `backend/` folder contains the real image-tampering model handoff. These
scripts are GPU-oriented CLI tools, not the FastAPI server and not a browser
API.

Check which weights are present:

```bash
bash backend/setup.sh --check
```

Run a dry-run without loading models:

```bash
python3 backend/run.py --input path/to/images/ --output_dir out --dry-run
```

Run selected models on one image:

```bash
bash backend/run_baselines.sh \
  --input path/to/image.png \
  --models PIXAR-7B SIDA-7B LISA-7B \
  --output_dir out \
  --gpu 0 \
  --precision bf16
```

The main aggregate output is:

```text
out/summary_all.json
```

Each result record contains the selected model, image path, image-level
probabilities where available, optional object output for PIXAR, pixel-level mask
and overlay paths, mask coverage, and generated text. See `backend/HANDOFF.md`
for the full contract and caveats.

To connect these real models to the frontend, build an HTTP adapter that:

1. Accepts an image upload at `POST /v1/detect/image`.
2. Runs or queues `backend/run.py` with the selected model.
3. Stores the CLI output somewhere the browser can fetch if mask/overlay assets
   should be clickable.
4. Returns a `job_id` immediately.
5. Exposes `GET /v1/jobs/{job_id}` with `queued`, `running`, `succeeded`, or
   `failed` status.
6. Returns either an Omni-Detect image result or a HANDOFF-style
   `summary_all.json` record.

This adapter is not implemented in the current repo. The frontend
`backendDetectionService.js` is ready to call it once it exists.

## Run Tests

```bash
.venv/bin/python -m pytest -q
```

Optional syntax check:

```bash
env PYTHONPYCACHEPREFIX=/tmp/omni_detect_pycache python3 -m compileall omni_detect tests
```

The `PYTHONPYCACHEPREFIX` form is useful in sandboxed macOS environments where
Python cannot write bytecode to the default user cache.

## Connect to RunPod

The local default is `OMNI_RUNPOD_BACKEND=fake`, which returns deterministic
mock results and requires no secrets.

To call RunPod over HTTP:

```bash
export OMNI_RUNPOD_BACKEND=http
export RUNPOD_API_KEY='<your-api-key>'
export RUNPOD_ENDPOINT_ID='<your-endpoint-id>'
export RUNPOD_API_BASE_URL='https://api.runpod.ai'

.venv/bin/python -m uvicorn omni_detect.api.app:app --host 0.0.0.0 --port 8000
```

The HTTP client currently submits to:

```text
POST /v2/{RUNPOD_ENDPOINT_ID}/run
```

with this JSON shape:

```json
{
  "input": {
    "job_id": "omni-detect-job-id",
    "kind": "text",
    "payload": {}
  }
}
```

It polls:

```text
GET /v2/{RUNPOD_ENDPOINT_ID}/status/{runpod_job_id}
```

and attempts cancellation through:

```text
POST /v2/{RUNPOD_ENDPOINT_ID}/cancel/{runpod_job_id}
```

The RunPod worker should return an `output` object containing a detection result
matching the schemas in `omni_detect/schemas.py`. For example:

```json
{
  "status": "COMPLETED",
  "output": {
    "result": {
      "overall_ai_probability": 0.12,
      "spans": [
        {
          "start_char": 0,
          "end_char": 12,
          "text": "example text",
          "ai_probability": 0.12,
          "label": "likely_human"
        }
      ]
    }
  }
}
```

If the worker returns `IN_QUEUE`, `IN_PROGRESS`, `RUNNING`, or `PENDING`, the
backend keeps polling. If RunPod reports `FAILED`, `CANCELLED`, or `TIMED_OUT`,
the Omni-Detect job is marked `failed`.

The RunPod HTTP client retries transient request failures. Retryable failures
include request timeouts, connection/request errors, and HTTP `408`, `409`,
`425`, `429`, `500`, `502`, `503`, and `504`. Non-retryable HTTP failures such
as `401` are returned immediately as structured job errors. Failed jobs include
an error `code`, user-safe `message`, and structured `details` such as status
code, request path, retry attempt, and RunPod response payload where available.

## GPU Scheduling

The scheduler lives in `omni_detect/scheduler.py`.

Core behavior:

- At most `max_concurrent_gpu_jobs` jobs run at the same time.
- Each job has an `estimated_cost`.
- Jobs with `estimated_cost <= short_job_cost_threshold` are short jobs.
- Short jobs are preferred over long jobs.
- FIFO order is preserved within each priority group by job sequence.
- Long jobs are protected from starvation in two ways:
  - after `max_short_job_streak` short jobs are dispatched, the oldest long job
    is promoted;
  - if any long job waits at least `long_job_fairness_wait_seconds`, the oldest
    long job is promoted.

This scheduling policy favors low-latency short requests while still ensuring
large jobs eventually receive capacity.

## Maintenance

For routine changes:

1. Keep public request and response types in `omni_detect/schemas.py`.
2. Keep endpoint-specific validation and request handling in
   `omni_detect/api/routes.py`.
3. Keep job state transitions in `omni_detect/jobs.py`.
4. Keep scheduling policy changes in `omni_detect/scheduler.py`.
5. Keep provider integration changes behind the `RunPodClient` protocol in
   `omni_detect/runpod.py`.
6. Keep frontend service changes behind
   `frontend/src/types/detectionService.js` and the implementations in
   `frontend/src/services/`.
7. Keep real model CLI contract changes reflected in `backend/HANDOFF.md` and
   the frontend normalization code if the output shape changes.
8. Add or update tests in `tests/` with every backend behavioral change. For
   frontend-only changes, run the JavaScript module checks and the manual UI
   verification steps above until a formal frontend test runner is added.

Before merging:

```bash
.venv/bin/python -m pytest -q
```

Recommended review checklist:

- Are new API fields typed and validated?
- Are error responses JSON and predictable?
- Does the change preserve job lifecycle invariants?
- Does scheduler behavior remain deterministic under test?
- Are secrets read from environment variables only?
- Are large payloads, logs, and error details handled safely?
- Does Demo Mode remain mock-only?
- Does Real Models Mode avoid text/file submission and avoid direct RunPod or
  model calls from the browser?

## Extending the Platform

Common extension paths:

- Add a new detection modality:
  - add a new `DetectionKind`;
  - add request/result schemas;
  - add an API route;
  - update fake and HTTP RunPod result parsing;
  - add validation and scheduler tests.
- Add persistent storage:
  - replace or wrap `JobStore`;
  - persist job timestamps, state, result, and error;
  - ensure scheduler recovery semantics are explicit after process restart.
- Add object storage for uploads:
  - store uploaded bytes outside process memory;
  - pass object references to RunPod instead of base64 payloads.
- Add authentication:
  - introduce middleware or dependency-based auth in `api/`;
  - add rate limits and tenant-aware scheduling before exposing public traffic.
- Add observability:
  - structured logs;
  - metrics for queue depth, active GPU jobs, job duration, failures, and RunPod
    latency;
  - tracing around submit and poll calls.
- Add or change a frontend model option:
  - update `MODEL_OPTIONS` in `frontend/src/config.js`;
  - update `DetectionModel` in `frontend/src/types/detection.js`;
  - update mock timing/result behavior in `mockDetectionService.js`;
  - update backend adapter normalization if the real output shape changes.
- Add the real-model HTTP adapter:
  - keep browser code pointed at `backendDetectionService.js`;
  - keep secrets and model credentials on the server side only;
  - translate uploaded images into `backend/run.py` invocations or a resident
    model worker;
  - expose mask and overlay assets through authenticated URLs if they should be
    visible in the browser.

Future work should be tracked explicitly. Do not document future behavior as
available until the code and tests exist.

## Troubleshooting

### Blank page after GitHub Pages deployment

Check the browser console and the built `frontend/dist/index.html`. The most
common cause is an incorrect `VITE_BASE_PATH`. For project Pages, it should be:

```text
/<repository-name>/
```

Set a repository variable named `VITE_BASE_PATH` if the default workflow value
does not match the final Pages URL. Re-run the workflow after changing
repository variables because frontend variables are applied at build time.

### CSS or JavaScript paths are broken on Pages

Run the production preview with the same base path:

```bash
cd frontend
VITE_BASE_PATH=/Omni-Detect-Platform/ npm run build
VITE_BASE_PATH=/Omni-Detect-Platform/ npm run preview
```

Open `http://127.0.0.1:4173/Omni-Detect-Platform/` and inspect network
requests. Static files should load from the configured base path, not from
localhost or from the domain root unless `VITE_BASE_PATH=/`.

### Logo does not load on Pages

The build copies root `static/` into `frontend/dist/static/`. Confirm the
deployed URL exists:

```text
https://<username>.github.io/<repo-name>/static/omni_detect_logo.png
```

If it 404s, check that `npm run build` created
`frontend/dist/static/omni_detect_logo.png` and that the Pages artifact path is
`frontend/dist`.

### Routing returns 404 on refresh

The current frontend does not use React Router or client-side routes. The build
still writes `404.html` as a static fallback for future route support. If routes
are added later, prefer hash-based routing for GitHub Pages unless the hosting
strategy changes.

### GitHub Pages environment variables are not applied

Only variables present during the GitHub Actions build are included in the
static output. Add public values as repository variables, not secrets, then
re-run the `Deploy Frontend to GitHub Pages` workflow. Do not expect runtime
environment changes to affect already deployed static files.

### Backend unavailable from GitHub Pages

Confirm `VITE_OMNI_DETECT_BACKEND_URL` points to a public HTTPS backend adapter
and that the adapter exposes `GET /health`, `POST /v1/detect/image`, and
`GET /v1/jobs/{job_id}`. GitHub Pages cannot run the backend, RunPod client, or
offline model scripts.

### CORS errors from Real Models Mode

The backend adapter must allow the GitHub Pages origin. For project Pages this
origin is usually:

```text
https://<username>.github.io
```

Allow only the expected Pages origin in production. Do not use permissive CORS
with credentials.

### `ModuleNotFoundError: fastapi` or `No module named pytest`

Install dependencies in the local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
```

### `RUNPOD_API_KEY is required`

You started with `OMNI_RUNPOD_BACKEND=http` but did not provide the required
RunPod environment variables:

```bash
export RUNPOD_API_KEY='<your-api-key>'
export RUNPOD_ENDPOINT_ID='<your-endpoint-id>'
```

For local development without RunPod, unset `OMNI_RUNPOD_BACKEND` or set it to
`fake`.

### Real Models Mode says backend URL is missing

Configure the frontend with:

```text
VITE_OMNI_DETECT_BACKEND_URL=http://127.0.0.1:8000
```

For the current static demo, set `window.OMNI_DETECT_CONFIG.omniDetectBackendUrl`
before `frontend/src/main.js` loads. The value must point to an HTTP adapter; the
offline `backend/run.py` CLI is not directly callable from the browser.

### Real Models Mode rejects text or file drafts

This is expected. `backend/HANDOFF.md` documents image and pixel-level tampering
models only. Use Demo Mode for mock text and file flows, or add real text/file
models behind a new backend contract before enabling those modalities.

### Real Models Mode health check fails

Check:

- the HTTP adapter process is running;
- it exposes `GET /health`;
- `VITE_OMNI_DETECT_BACKEND_URL` points to the adapter origin;
- CORS allows the static frontend origin;
- reverse proxies are not blocking multipart image uploads or job polling.

### Real image result has no boxes

This is expected for the PIXAR/SIDA/LISA handoff. Real localization is a
per-pixel mask at original image resolution, not a bounding box. The UI displays
mask and overlay output links when the backend adapter returns them.

### `backend/setup.sh --check` reports missing weights

The offline baselines need model checkpoints and SAM weights under `pretrains/`
or the path configured with `PRETRAINS`. Downloading all six checkpoints is
large and may require Hugging Face access and enough disk space. For a smoke
test, start with a subset such as `PIXAR-7B SIDA-7B LISA-7B`.

### Upload returns `415 Unsupported Media Type`

Check the uploaded file's content type. The backend validates `UploadFile`
content type against the allowed lists above.

### Upload returns `413 Payload Too Large`

Increase `OMNI_MAX_IMAGE_UPLOAD_BYTES` or `OMNI_MAX_FILE_UPLOAD_BYTES`, or use a
smaller upload. For production, prefer object storage over increasing in-memory
upload limits too far.

### Job remains queued

Check:

- the server process is still running;
- `/health` returns `status: ok`;
- `OMNI_MAX_CONCURRENT_GPU_JOBS` is greater than `0`;
- no long-running fake or RunPod jobs are occupying all scheduler capacity.

### Job fails with `runpod_timeout`

The RunPod job did not complete within:

```text
OMNI_RUNPOD_RESULT_POLL_INTERVAL_SECONDS * OMNI_RUNPOD_MAX_RESULT_POLLS
```

Increase the poll count or interval if the worker normally takes longer, and
check RunPod logs for the underlying job.

### Compile check cannot write bytecode

Use a writable bytecode cache path:

```bash
env PYTHONPYCACHEPREFIX=/tmp/omni_detect_pycache python3 -m compileall omni_detect tests
```

## Security and Production Notes

The current code is an MVP foundation, not a complete production deployment.

Important production gaps:

- No authentication or authorization.
- No tenant isolation.
- No persistent job store.
- No durable upload storage.
- No request rate limiting.
- No structured audit logging.
- No encryption or lifecycle policy for uploaded content.
- No distributed scheduler coordination across multiple API replicas.
- No full observability stack.
- No authenticated asset serving for real-model masks or overlays.
- No implemented HTTP adapter around the offline PIXAR/SIDA/LISA CLI yet.
- GitHub Pages is static hosting only and cannot securely run backend jobs or
  store private service credentials.

Before production:

- Put the service behind TLS and an authenticated gateway.
- Store `RUNPOD_API_KEY` in a secret manager.
- Keep model registry credentials, Hugging Face tokens, and checkpoint paths on
  the server side; never expose them to frontend code.
- Do not put RunPod secrets or backend private tokens in `VITE_*` variables or
  GitHub Pages repository variables.
- Avoid logging uploaded content, base64 payloads, or raw document text.
- Add size limits at the reverse proxy as well as in FastAPI.
- Replace in-memory payload handling with object storage and signed references.
- Replace in-memory job storage with a durable database.
- Serve real-model mask and overlay assets through authenticated, expiring URLs.
- Define retention and deletion policies for submitted content and results.
- Add alerts for queue depth, RunPod failures, timeout rate, and scheduler
  saturation.
- Decide whether cancellation should be exposed as an authenticated API endpoint.
