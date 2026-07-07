import { detectionConfig } from "../config.js";

const DEFAULT_MODEL = "PIXAR-7B";
const DEFAULT_PRIORITY = "normal";
const IMAGE_ONLY_MESSAGE =
  "Real Models Mode supports image uploads only. The backend handoff models are image tampering and localization baselines, not text or document detectors.";

export class BackendDetectionError extends Error {
  /**
   * @param {string} code
   * @param {string} message
   * @param {Record<string, unknown>} [details]
   */
  constructor(code, message, details = {}) {
    super(message);
    this.name = "BackendDetectionError";
    this.code = code;
    this.details = details;
  }
}

/**
 * Creates a detection service backed by an HTTP adapter around the real
 * image-tampering models documented in backend/HANDOFF.md.
 *
 * The handoff backend is a CLI toolkit, not a browser-callable API. This
 * client expects a serving adapter at VITE_OMNI_DETECT_BACKEND_URL that exposes
 * /health, /v1/detect/image, and /v1/jobs/{job_id}.
 *
 * @param {typeof detectionConfig} config
 * @param {typeof fetch} [fetchImpl]
 * @returns {import('../types/detectionService.js').DetectionService}
 */
export function createBackendDetectionService(
  config = detectionConfig,
  fetchImpl = globalThis.fetch?.bind(globalThis),
) {
  const baseUrl = (config.backendUrl || "").replace(/\/$/, "");
  const jobMetadata = new Map();

  async function submitImageDetection(file, options = {}) {
    ensureConfigured(baseUrl, fetchImpl);

    const metadata = {
      kind: "image",
      model: options.model || DEFAULT_MODEL,
      priority: options.priority || DEFAULT_PRIORITY,
      created_at: Date.now(),
    };
    const formData = new FormData();
    formData.append("file", file);
    formData.append("model", metadata.model);
    formData.append("priority", metadata.priority);

    const response = await requestJson(fetchImpl, `${baseUrl}/v1/detect/image`, {
      method: "POST",
      body: formData,
    });
    const job = jobFromCreateResponse(response, metadata);
    jobMetadata.set(job.job_id, {
      ...metadata,
      created_at: job.created_at,
    });
    return job;
  }

  async function getJob(jobId) {
    ensureConfigured(baseUrl, fetchImpl);
    const response = await requestJson(fetchImpl, `${baseUrl}/v1/jobs/${jobId}`);
    const cached = jobMetadata.get(jobId);
    const job = jobFromBackendResponse(response, cached);
    jobMetadata.set(job.job_id, {
      kind: job.kind,
      model: job.model,
      priority: job.priority,
      created_at: job.created_at,
    });
    return job;
  }

  return {
    async submitTextDetection() {
      throw new BackendDetectionError("backend_image_only", IMAGE_ONLY_MESSAGE);
    },

    submitImageDetection,

    async submitFileDetection() {
      throw new BackendDetectionError("backend_image_only", IMAGE_ONLY_MESSAGE);
    },

    async submitMultipleJobs(jobs) {
      return Promise.all(
        jobs.map((job) => {
          if (job.kind !== "image" || !job.file) {
            throw new BackendDetectionError("backend_image_only", IMAGE_ONLY_MESSAGE);
          }
          return submitImageDetection(job.file, job.options || {});
        }),
      );
    },

    getJob,

    pollJobStatus: getJob,

    async checkHealth() {
      if (!baseUrl) {
        return {
          ok: false,
          message:
            "VITE_OMNI_DETECT_BACKEND_URL is not configured. Real Models Mode needs an HTTP adapter around backend/run.py.",
        };
      }
      if (typeof fetchImpl !== "function") {
        return {
          ok: false,
          message: "This browser does not provide fetch, so the backend cannot be checked.",
        };
      }
      try {
        const response = await requestJson(fetchImpl, `${baseUrl}/health`);
        return {
          ok: true,
          message: response.status
            ? `Backend health: ${response.status}`
            : "Backend health check succeeded.",
        };
      } catch (error) {
        return {
          ok: false,
          message:
            error instanceof Error
              ? error.message
              : "Backend health check failed.",
        };
      }
    },
  };
}

/**
 * @param {string} baseUrl
 * @param {typeof fetch | undefined} fetchImpl
 */
function ensureConfigured(baseUrl, fetchImpl) {
  if (!baseUrl) {
    throw new BackendDetectionError(
      "backend_not_configured",
      "Real Models Mode needs VITE_OMNI_DETECT_BACKEND_URL. backend/HANDOFF.md documents an offline CLI toolkit, so the browser needs a small HTTP adapter to submit jobs.",
      { env: "VITE_OMNI_DETECT_BACKEND_URL" },
    );
  }
  if (typeof fetchImpl !== "function") {
    throw new BackendDetectionError(
      "fetch_unavailable",
      "This browser does not provide fetch, so the backend cannot be reached.",
    );
  }
}

/**
 * @param {typeof fetch} fetchImpl
 * @param {string} url
 * @param {RequestInit} [options]
 */
async function requestJson(fetchImpl, url, options = {}) {
  let response;
  try {
    response = await fetchImpl(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    throw new BackendDetectionError(
      "backend_network_error",
      error instanceof Error
        ? `Backend request failed: ${error.message}`
        : "Backend request failed.",
      { url },
    );
  }

  const payload = await safeJson(response);
  if (!response.ok) {
    const errorPayload = payload?.error || payload?.detail || payload;
    const message =
      errorPayload?.message ||
      (typeof errorPayload === "string" ? errorPayload : "") ||
      `Backend request failed with HTTP ${response.status}.`;
    throw new BackendDetectionError(
      errorPayload?.code || "backend_http_error",
      message,
      { status: response.status, url, payload },
    );
  }
  return payload || {};
}

/**
 * @param {Response} response
 */
async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * @param {any} response
 * @param {{ kind: import('../types/detection.js').DetectionInputType, model: string, priority: string, created_at: number }} metadata
 * @returns {import('../types/detection.js').DetectionJob}
 */
function jobFromCreateResponse(response, metadata) {
  const now = Date.now();
  const result = extractResultRecord(response);
  const status = normalizeStatus(response.status || (result ? "succeeded" : "queued"));
  const createdAt = parseTimestamp(response.created_at) || metadata.created_at || now;
  const updatedAt = parseTimestamp(response.updated_at) || createdAt;
  const completedAt =
    parseTimestamp(response.completed_at) ||
    (["succeeded", "failed"].includes(status) ? updatedAt : null);

  return {
    job_id: response.job_id || response.id || `backend_${newRandomId()}`,
    kind: normalizeKind(response.kind || metadata.kind),
    status,
    model: response.model || response.metadata?.model || result?.model || metadata.model,
    priority: response.priority || response.metadata?.priority || metadata.priority,
    created_at: createdAt,
    updated_at: updatedAt,
    started_at: parseTimestamp(response.started_at) || null,
    completed_at: completedAt,
    result: result ? adaptResult(metadata.kind, result) : null,
    error: normalizeError(response.error, status),
  };
}

/**
 * @param {any} response
 * @param {{ kind?: string, model?: string, priority?: string, created_at?: number } | undefined} cached
 * @returns {import('../types/detection.js').DetectionJob}
 */
function jobFromBackendResponse(response, cached) {
  const result = extractResultRecord(response);
  const kind = normalizeKind(response.kind || cached?.kind || "image");
  const status = normalizeStatus(response.status || response.state || (result ? "succeeded" : "queued"));
  const now = Date.now();
  const updatedAt = parseTimestamp(response.updated_at) || now;

  return {
    job_id: response.job_id || response.id || cached?.job_id || `backend_${newRandomId()}`,
    kind,
    status,
    model: response.model || response.metadata?.model || result?.model || cached?.model || DEFAULT_MODEL,
    priority:
      response.priority ||
      response.metadata?.priority ||
      cached?.priority ||
      DEFAULT_PRIORITY,
    created_at:
      parseTimestamp(response.created_at) || cached?.created_at || updatedAt,
    updated_at: updatedAt,
    started_at: parseTimestamp(response.started_at) || null,
    completed_at:
      parseTimestamp(response.completed_at) ||
      (["succeeded", "failed"].includes(status) ? updatedAt : null),
    result: result ? adaptResult(kind, result) : null,
    error: normalizeError(response.error, status),
  };
}

/**
 * @param {any} response
 */
function extractResultRecord(response) {
  const result = response.result || response.output?.result || response.output;
  if (Array.isArray(response.results)) {
    return response.results[0] || null;
  }
  if (Array.isArray(result?.results)) {
    return result.results[0] || null;
  }
  return result || null;
}

/**
 * @param {import('../types/detection.js').DetectionInputType} kind
 * @param {any} result
 */
function adaptResult(kind, result) {
  if (!result) {
    return null;
  }
  if (kind === "text") {
    return {
      overall_ai_probability: clampProbability(result.overall_ai_probability),
      spans: result.spans || [],
      analysis_summary:
        result.analysis_summary ||
        "Backend text result returned by the configured adapter.",
    };
  }
  if (kind === "file") {
    return {
      overall_ai_probability: clampProbability(result.overall_ai_probability),
      metadata: result.metadata || {
        file_name: "Uploaded file",
        file_type: "unknown",
        file_size: 0,
      },
      sections: (result.sections || []).map((section, index) => ({
        section_label:
          section.section_label ||
          section.title ||
          section.section_id ||
          (section.start_page ? `Page ${section.start_page}` : `Section ${index + 1}`),
        ai_probability: clampProbability(section.ai_probability),
        label: section.label || "needs_review",
      })),
      analysis_summary:
        result.analysis_summary ||
        "Backend file result returned by the configured adapter.",
    };
  }

  if (result.document_level || result.pixel_level || result.localization) {
    return adaptHandoffImageResult(result);
  }

  return {
    overall_ai_probability: clampProbability(result.overall_ai_probability),
    regions: result.regions || [],
    analysis_summary:
      result.analysis_summary ||
      "Backend image result returned by the configured adapter.",
    mask_url: result.mask_url || null,
    overlay_url: result.overlay_url || null,
    positive_pixel_fraction:
      typeof result.positive_pixel_fraction === "number"
        ? result.positive_pixel_fraction
        : null,
  };
}

/**
 * @param {any} record
 * @returns {import('../types/detection.js').ImageDetectionResult}
 */
function adaptHandoffImageResult(record) {
  const documentLevel = record.document_level || {};
  const pixelLevel = record.pixel_level || record.localization || {};
  const probability =
    typeof documentLevel.p_tampered === "number"
      ? documentLevel.p_tampered
      : documentLevel.label === "tampered"
        ? 0.75
        : clampProbability(pixelLevel.positive_pixel_fraction || 0.25);

  return {
    overall_ai_probability: clampProbability(probability),
    regions: [],
    analysis_summary: handoffSummary(record, documentLevel, pixelLevel),
    mask_url: pixelLevel.mask_png || pixelLevel.mask_url || null,
    overlay_url: pixelLevel.overlay_png || pixelLevel.overlay_url || null,
    positive_pixel_fraction:
      typeof pixelLevel.positive_pixel_fraction === "number"
        ? pixelLevel.positive_pixel_fraction
        : null,
  };
}

/**
 * @param {any} record
 * @param {any} documentLevel
 * @param {any} pixelLevel
 */
function handoffSummary(record, documentLevel, pixelLevel) {
  const parts = [];
  const model = record.model || "The selected model";
  if (documentLevel.label) {
    parts.push(
      `${model} returned image-level label ${documentLevel.label}${
        typeof documentLevel.p_tampered === "number"
          ? ` with ${Math.round(documentLevel.p_tampered * 100)}% tamper probability`
          : ""
      }.`,
    );
  }
  if (typeof pixelLevel.positive_pixel_fraction === "number") {
    parts.push(
      `The pixel mask covers ${Math.round(pixelLevel.positive_pixel_fraction * 1000) / 10}% of the image.`,
    );
  }
  if (Array.isArray(record.object_level) && record.object_level.length) {
    const objects = record.object_level
      .slice(0, 3)
      .map((item) => item.name)
      .filter(Boolean)
      .join(", ");
    if (objects) {
      parts.push(`Object-level candidates: ${objects}.`);
    }
  } else if (record.object_level_note) {
    parts.push(String(record.object_level_note));
  }
  if (record.text) {
    parts.push(String(record.text));
  }
  return parts.join(" ") || "Backend image tampering result returned.";
}

/**
 * @param {string} kind
 * @returns {import('../types/detection.js').DetectionInputType}
 */
function normalizeKind(kind) {
  return kind === "text" || kind === "file" || kind === "image" ? kind : "image";
}

/**
 * @param {string} status
 * @returns {import('../types/detection.js').JobStatus}
 */
function normalizeStatus(status) {
  const value = String(status || "").toLowerCase();
  if (["queued", "pending", "in_queue"].includes(value)) {
    return "queued";
  }
  if (["running", "in_progress", "processing"].includes(value)) {
    return "running";
  }
  if (["succeeded", "completed", "success", "done"].includes(value)) {
    return "succeeded";
  }
  return "failed";
}

/**
 * @param {any} error
 * @param {import('../types/detection.js').JobStatus} status
 */
function normalizeError(error, status) {
  if (error) {
    return {
      code: error.code || "backend_job_failed",
      message: error.message || String(error),
      details: error.details || null,
    };
  }
  if (status === "failed") {
    return {
      code: "backend_job_failed",
      message: "The backend reported a failed, cancelled, or unknown job status.",
    };
  }
  return null;
}

/**
 * @param {unknown} value
 */
function parseTimestamp(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * @param {unknown} value
 */
function clampProbability(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return 0;
  }
  return Math.max(0, Math.min(1, number));
}

function newRandomId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2, 12);
}
