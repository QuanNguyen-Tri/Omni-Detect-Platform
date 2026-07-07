/** @typedef {import('../types/detection.js').DetectionJob} DetectionJob */
/** @typedef {import('../types/detection.js').DetectionInputType} DetectionInputType */

const jobs = new Map();
const pendingTimers = new Map();
const FAILURE_RATE = 0.08;

/** @type {import('../types/detectionService.js').DetectionService & { clear: () => void }} */
export const mockDetectionService = {
  /**
   * @param {string} text
   * @param {import('../types/detectionService.js').DetectionSubmitOptions} [options]
   * @returns {Promise<DetectionJob>}
   */
  async submitTextDetection(text, options = {}) {
    const job = createJob("text", { text }, options);
    scheduleJob(job.job_id, () => generateTextResult(text, job));
    return cloneJob(job);
  },

  /**
   * @param {File} file
   * @param {import('../types/detectionService.js').DetectionSubmitOptions} [options]
   * @returns {Promise<DetectionJob>}
   */
  async submitImageDetection(file, options = {}) {
    const job = createJob("image", { file }, options);
    scheduleJob(job.job_id, () => generateImageResult(job));
    return cloneJob(job);
  },

  /**
   * @param {File} file
   * @param {import('../types/detectionService.js').DetectionSubmitOptions} [options]
   * @returns {Promise<DetectionJob>}
   */
  async submitFileDetection(file, options = {}) {
    const job = createJob("file", { file }, options);
    scheduleJob(job.job_id, () => generateFileResult(file, job));
    return cloneJob(job);
  },

  /**
   * @param {import('../types/detectionService.js').DetectionSubmitBatchItem[]} items
   * @returns {Promise<DetectionJob[]>}
   */
  async submitMultipleJobs(items) {
    return Promise.all(
      items.map((item) => {
        if (item.kind === "text") {
          return this.submitTextDetection(item.text || "", item.options || {});
        }
        if (item.kind === "image" && item.file) {
          return this.submitImageDetection(item.file, item.options || {});
        }
        if (item.kind === "file" && item.file) {
          return this.submitFileDetection(item.file, item.options || {});
        }
        throw new Error("Invalid demo batch item");
      }),
    );
  },

  /**
   * @param {string} jobId
   * @returns {Promise<DetectionJob>}
   */
  async getJob(jobId) {
    const job = jobs.get(jobId);
    if (!job) {
      throw new Error("Demo job not found");
    }
    return cloneJob(job);
  },

  async listJobs() {
    return Array.from(jobs.values()).map(cloneJob);
  },

  async pollJobStatus(jobId) {
    return this.getJob(jobId);
  },

  async checkHealth() {
    return {
      ok: true,
      message: "Demo service is running locally in this browser.",
    };
  },

  clear() {
    for (const timer of pendingTimers.values()) {
      globalThis.clearTimeout(timer);
    }
    pendingTimers.clear();
    jobs.clear();
  },
};

/**
 * @param {DetectionInputType} kind
 * @param {Record<string, unknown>} payload
 * @param {import('../types/detectionService.js').DetectionSubmitOptions} options
 * @returns {DetectionJob}
 */
function createJob(kind, payload, options) {
  const now = Date.now();
  const job = {
    job_id: `demo_${newRandomId()}`,
    kind,
    status: "queued",
    model: options.model || "PIXAR-7B",
    priority: options.priority || "normal",
    created_at: now,
    updated_at: now,
    started_at: null,
    completed_at: null,
    result: null,
    error: null,
    payload,
  };
  jobs.set(job.job_id, job);
  return job;
}

/**
 * @param {string} jobId
 * @param {() => import('../types/detection.js').DetectionResult} resultFactory
 */
function scheduleJob(jobId, resultFactory) {
  const job = jobs.get(jobId);
  const priority = job?.priority || "normal";
  const model = job?.model || "PIXAR-7B";
  const queuedDelay = delayByPriority(priority, 380, 950);
  const runningDelay = delayByModel(model, priority);

  const runningTimer = globalThis.setTimeout(() => {
    updateJob(jobId, { status: "running", started_at: Date.now() });

    const completeTimer = globalThis.setTimeout(() => {
      const shouldFail = Math.random() < FAILURE_RATE;
      if (shouldFail) {
        updateJob(jobId, {
          status: "failed",
          error: {
            code: "demo_random_failure",
            message: "The demo job failed randomly. Try submitting again.",
          },
          completed_at: Date.now(),
        });
      } else {
        updateJob(jobId, {
          status: "succeeded",
          result: resultFactory(),
          completed_at: Date.now(),
        });
      }
      pendingTimers.delete(jobId);
    }, runningDelay);

    pendingTimers.set(jobId, completeTimer);
  }, queuedDelay);

  pendingTimers.set(jobId, runningTimer);
}

/**
 * @param {string} jobId
 * @param {Partial<DetectionJob> & { completed_at?: number }} changes
 */
function updateJob(jobId, changes) {
  const job = jobs.get(jobId);
  if (!job) {
    return;
  }
  jobs.set(jobId, { ...job, ...changes, updated_at: Date.now() });
}

/**
 * @param {DetectionJob} job
 * @returns {DetectionJob}
 */
function cloneJob(job) {
  const { payload, ...publicJob } = job;
  return typeof structuredClone === "function"
    ? structuredClone(publicJob)
    : JSON.parse(JSON.stringify(publicJob));
}

/**
 * @param {string} text
 * @param {DetectionJob} job
 */
function generateTextResult(text, job) {
  const words = collectWords(text);
  const spanCount = Math.min(
    words.length,
    job.model.endsWith("-13B") ? randomInt(2, 6) : randomInt(1, 4),
  );
  const selected = shuffle(words).slice(0, spanCount);
  const spans = selected
    .map((word) => ({
      start_char: word.start,
      end_char: word.end,
      text: text.slice(word.start, word.end),
      ai_probability: randomProbability(0.55, 0.98),
      label: randomLabel(),
    }))
    .sort((a, b) => a.start_char - b.start_char);

  return {
    overall_ai_probability: randomProbability(0.12, 0.96),
    spans,
    analysis_summary: summaryFor("text", job, spans.length),
  };
}

/**
 * @param {DetectionJob} job
 */
function generateImageResult(job) {
  const regionCount = regionCountForModel(job.model);
  const regions = Array.from({ length: regionCount }, (_, index) => {
    const width = randomInt(14, 32);
    const height = randomInt(12, 30);
    return {
      x: randomInt(4, 92 - width),
      y: randomInt(4, 92 - height),
      width,
      height,
      ai_probability: randomProbability(0.52, 0.97),
      label: index % 2 === 0 ? "possible_edit" : "synthetic_region",
    };
  });

  return {
    overall_ai_probability: randomProbability(0.18, 0.94),
    regions,
    analysis_summary: summaryFor("image", job, regions.length),
  };
}

/**
 * @param {File} file
 * @param {DetectionJob} job
 */
function generateFileResult(file, job) {
  const sectionCount = job.model.endsWith("-13B") ? randomInt(5, 9) : randomInt(3, 7);
  const sections = Array.from({ length: sectionCount }, (_, index) => ({
    section_label: file.type === "application/pdf" ? `Page ${index + 1}` : `Section ${index + 1}`,
    ai_probability: randomProbability(0.08, 0.93),
    label: randomLabel(),
  }));

  return {
    overall_ai_probability: randomProbability(0.1, 0.92),
    metadata: {
      file_name: file.name,
      file_type: file.type || "unknown",
      file_size: file.size,
    },
    sections,
    analysis_summary: summaryFor("file", job, sections.length),
  };
}

/**
 * @param {DetectionInputType} kind
 * @param {DetectionJob} job
 * @param {number} findingCount
 */
function summaryFor(kind, job, findingCount) {
  const subject =
    kind === "text"
      ? "text spans"
      : kind === "image"
        ? "image regions"
        : "document sections";
  const modelTone = `${job.model} mock pass`;
  return `Demo ${modelTone} flagged ${findingCount} ${subject} for ${job.priority} priority review. This is randomly generated and not real model output.`;
}

/**
 * @param {string} text
 */
function collectWords(text) {
  const matches = [...text.matchAll(/\S+/g)];
  const words = matches
    .map((match) => ({
      start: match.index || 0,
      end: (match.index || 0) + match[0].length,
    }))
    .filter((word) => word.end - word.start > 3);

  if (words.length > 0) {
    return words;
  }
  return [{ start: 0, end: text.length }];
}

/**
 * @template T
 * @param {T[]} items
 * @returns {T[]}
 */
function shuffle(items) {
  return [...items].sort(() => Math.random() - 0.5);
}

function randomLabel() {
  return Math.random() > 0.5 ? "likely_ai" : "needs_review";
}

/**
 * @param {number} min
 * @param {number} max
 */
function randomProbability(min = 0, max = 1) {
  return Number((min + Math.random() * (max - min)).toFixed(4));
}

/**
 * @param {number} min
 * @param {number} max
 */
function randomInt(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

/**
 * @param {import('../types/detection.js').JobPriority} priority
 * @param {number} min
 * @param {number} max
 */
function delayByPriority(priority, min, max) {
  const multiplier = priority === "high" ? 0.55 : priority === "low" ? 1.35 : 1;
  return Math.round(randomInt(min, max) * multiplier);
}

/**
 * @param {import('../types/detection.js').DetectionModel} model
 * @param {import('../types/detection.js').JobPriority} priority
 */
function delayByModel(model, priority) {
  let base;
  if (model.endsWith("-13B")) {
    base = randomInt(1500, 2400);
  } else if (model.startsWith("LISA")) {
    base = randomInt(800, 1400);
  } else if (model.startsWith("PIXAR")) {
    base = randomInt(1100, 1900);
  } else {
    base = randomInt(950, 1650);
  }
  return delayByPriority(priority, base, base);
}

/**
 * @param {import('../types/detection.js').DetectionModel} model
 */
function regionCountForModel(model) {
  if (model.startsWith("PIXAR")) {
    return model.endsWith("-13B") ? randomInt(4, 7) : randomInt(3, 6);
  }
  if (model.startsWith("LISA")) {
    return randomInt(1, 3);
  }
  return model.endsWith("-13B") ? randomInt(3, 6) : randomInt(2, 5);
}

function randomId() {
  return Math.random().toString(36).slice(2, 12);
}

function newRandomId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return randomId();
}
