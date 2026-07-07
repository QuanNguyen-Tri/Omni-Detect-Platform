/**
 * @typedef {'text' | 'image' | 'file'} DetectionInputType
 * @typedef {'mock' | 'backend'} DetectionMode
 * @typedef {'queued' | 'running' | 'succeeded' | 'failed'} JobStatus
 * @typedef {'PIXAR-7B' | 'PIXAR-13B' | 'SIDA-7B' | 'SIDA-13B' | 'LISA-7B' | 'LISA-13B'} DetectionModel
 * @typedef {'low' | 'normal' | 'high'} JobPriority
 *
 * @typedef {Object} TextDetectionSpan
 * @property {number} start_char
 * @property {number} end_char
 * @property {string} text
 * @property {number} ai_probability
 * @property {string} label
 *
 * @typedef {Object} TextDetectionResult
 * @property {number} overall_ai_probability
 * @property {TextDetectionSpan[]} spans
 * @property {string} analysis_summary
 *
 * @typedef {Object} ImageDetectionRegion
 * @property {number} x Normalized percent from the left edge.
 * @property {number} y Normalized percent from the top edge.
 * @property {number} width Normalized percent width.
 * @property {number} height Normalized percent height.
 * @property {number} ai_probability
 * @property {string} label
 *
 * @typedef {Object} ImageDetectionResult
 * @property {number} overall_ai_probability
 * @property {ImageDetectionRegion[]} regions
 * @property {string} analysis_summary
 * @property {string | null} [mask_url]
 * @property {string | null} [overlay_url]
 * @property {number | null} [positive_pixel_fraction]
 *
 * @typedef {Object} FileDetectionSection
 * @property {string} section_label
 * @property {number} ai_probability
 * @property {string} label
 *
 * @typedef {Object} FileDetectionResult
 * @property {number} overall_ai_probability
 * @property {{file_name: string, file_type: string, file_size: number}} metadata
 * @property {FileDetectionSection[]} sections
 * @property {string} analysis_summary
 *
 * @typedef {TextDetectionResult | ImageDetectionResult | FileDetectionResult} DetectionResult
 *
 * @typedef {Object} DetectionJob
 * @property {string} job_id
 * @property {DetectionInputType} kind
 * @property {JobStatus} status
 * @property {DetectionModel} model
 * @property {JobPriority} priority
 * @property {number} created_at
 * @property {number} updated_at
 * @property {number | null} started_at
 * @property {number | null} completed_at
 * @property {DetectionResult | null} result
 * @property {{code: string, message: string} | null} error
 */

export const DETECTION_INPUT_TYPES = /** @type {const} */ ([
  "text",
  "image",
  "file",
]);

export const JOB_STATUSES = /** @type {const} */ ([
  "queued",
  "running",
  "succeeded",
  "failed",
]);

export const DETECTION_MODES = /** @type {const} */ ([
  "mock",
  "backend",
]);

export const DETECTION_MODELS = /** @type {const} */ ([
  "PIXAR-7B",
  "PIXAR-13B",
  "SIDA-7B",
  "SIDA-13B",
  "LISA-7B",
  "LISA-13B",
]);

export const JOB_PRIORITIES = /** @type {const} */ ([
  "low",
  "normal",
  "high",
]);
