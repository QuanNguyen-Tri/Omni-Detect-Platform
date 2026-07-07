export const DETECTION_MODES = /** @type {const} */ (["mock", "backend"]);

export const DEMO_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const ACCEPTED_DOCUMENT_EXTENSIONS = [".pdf", ".txt", ".doc", ".docx"];
export const ACCEPTED_DOCUMENT_TYPES = [
  "application/pdf",
  "text/plain",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

export const MODEL_OPTIONS = [
  {
    value: "PIXAR-7B",
    label: "PIXAR-7B",
    description: "Image-level, object, mask, and text outputs",
  },
  {
    value: "PIXAR-13B",
    label: "PIXAR-13B",
    description: "Larger PIXAR checkpoint; requires more VRAM",
  },
  {
    value: "SIDA-7B",
    label: "SIDA-7B",
    description: "Image-level, mask, and text outputs",
  },
  {
    value: "SIDA-13B",
    label: "SIDA-13B",
    description: "Larger SIDA checkpoint; object head suppressed",
  },
  {
    value: "LISA-7B",
    label: "LISA-7B",
    description: "Instruction-driven segmentation baseline",
  },
  {
    value: "LISA-13B",
    label: "LISA-13B",
    description: "Larger segmentation-only LISA baseline",
  },
];

export const PRIORITY_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
];

export const detectionConfig = {
  defaultMode: readMode(),
  basePath: readBasePath(),
  backendUrl: readStringConfig(
    "VITE_OMNI_DETECT_BACKEND_URL",
    readStringConfig("VITE_DETECTION_API_BASE_URL", ""),
  ),
  pollIntervalMs: readNumberConfig("VITE_OMNI_DETECT_POLL_INTERVAL_MS", 1000),
};

/**
 * @param {string} path
 */
export function assetPath(path) {
  return `${detectionConfig.basePath}${path.replace(/^\/+/, "")}`;
}

function readMode() {
  const value = readStringConfig("VITE_DETECTION_API_MODE", "mock").toLowerCase();
  const normalized = value === "api" ? "backend" : value;
  return DETECTION_MODES.includes(normalized) ? normalized : "mock";
}

function readBasePath() {
  return normalizeBasePath(readStringConfig("VITE_BASE_PATH", "/"));
}

/**
 * @param {string} key
 * @param {string} fallback
 */
function readStringConfig(key, fallback) {
  const browserConfig = globalThis.window?.OMNI_DETECT_CONFIG || {};
  const camelKey = key
    .replace(/^VITE_/, "")
    .toLowerCase()
    .replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  return browserConfig[camelKey] || import.meta.env?.[key] || fallback;
}

/**
 * @param {string} key
 * @param {number} fallback
 */
function readNumberConfig(key, fallback) {
  const value = readStringConfig(key, "");
  if (!value) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/**
 * @param {string} value
 */
function normalizeBasePath(value) {
  const trimmed = value.trim();
  if (!trimmed || trimmed === ".") {
    return "/";
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return withLeadingSlash.endsWith("/") ? withLeadingSlash : `${withLeadingSlash}/`;
}
