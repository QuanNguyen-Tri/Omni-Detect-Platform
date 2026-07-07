/**
 * Shared frontend detection client contract.
 *
 * The mock browser service and backend adapter client both implement this shape
 * so the UI does not care where jobs come from.
 *
 * @typedef {Object} DetectionService
 * @property {(text: string, options?: DetectionSubmitOptions) => Promise<import('./detection.js').DetectionJob>} submitTextDetection
 * @property {(file: File, options?: DetectionSubmitOptions) => Promise<import('./detection.js').DetectionJob>} submitImageDetection
 * @property {(file: File, options?: DetectionSubmitOptions) => Promise<import('./detection.js').DetectionJob>} submitFileDetection
 * @property {(jobs: DetectionSubmitBatchItem[]) => Promise<import('./detection.js').DetectionJob[]>} [submitMultipleJobs]
 * @property {(jobId: string) => Promise<import('./detection.js').DetectionJob>} getJob
 * @property {() => Promise<import('./detection.js').DetectionJob[]>} [listJobs]
 * @property {(jobId: string) => Promise<import('./detection.js').DetectionJob>} [pollJobStatus]
 * @property {() => Promise<{ok: boolean, message: string}>} [checkHealth]
 *
 * @typedef {Object} DetectionSubmitOptions
 * @property {import('./detection.js').DetectionModel} [model]
 * @property {import('./detection.js').JobPriority} [priority]
 *
 * @typedef {Object} DetectionSubmitBatchItem
 * @property {import('./detection.js').DetectionInputType} kind
 * @property {string} [text]
 * @property {File} [file]
 * @property {DetectionSubmitOptions} [options]
 */

export {};
