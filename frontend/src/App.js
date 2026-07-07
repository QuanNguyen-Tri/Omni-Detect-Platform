import { detectionForm } from "./components/DetectionForm.js";
import { jobHistoryPanel } from "./components/JobHistoryPanel.js";
import {
  ACCEPTED_DOCUMENT_EXTENSIONS,
  ACCEPTED_DOCUMENT_TYPES,
  ACCEPTED_IMAGE_TYPES,
  DEMO_MAX_UPLOAD_BYTES,
  assetPath,
  detectionConfig,
} from "./config.js";
import { detectionServices as defaultDetectionServices } from "./services/detectionClient.js";
import { escapeHtml } from "./utils/format.js";

const FALLBACK_POLL_INTERVAL_MS = 1000;
const LOGO_PATH = assetPath("static/omni_detect_logo.png");
const DEFAULT_MODEL = "PIXAR-7B";
const IMAGE_ONLY_BACKEND_MESSAGE =
  "Real Models Mode supports image uploads only. The backend handoff models are image tampering and localization baselines.";

/**
 * @param {HTMLElement} root
 * @param {{
 *   mock: import('./types/detectionService.js').DetectionService,
 *   backend: import('./types/detectionService.js').DetectionService
 * } | import('./types/detectionService.js').DetectionService} detectionServices
 * @param {typeof detectionConfig} config
 */
export function createApp(
  root,
  detectionServices = defaultDetectionServices,
  config = detectionConfig,
) {
  const services = normalizeServiceMap(detectionServices);
  const initialMode = normalizeMode(config.defaultMode);
  const state = {
    activeMode: initialMode,
    backendStatus: {
      state: "idle",
      message: config.backendUrl
        ? `Backend URL: ${config.backendUrl}`
        : "VITE_OMNI_DETECT_BACKEND_URL is not configured.",
    },
    drafts: [createDraft(initialMode)],
    history: [],
    isSubmittingAll: false,
    pollTimer: 0,
  };

  function render() {
    root.innerHTML = `
      <main class="app-shell">
        <header class="app-header">
          <div class="brand-block">
            <img class="brand-logo" src="${escapeHtml(LOGO_PATH)}" alt="Omni-Detect logo" />
            <div>
              <p class="eyebrow">${state.activeMode === "backend" ? "Real model adapter" : "Browser demo"}</p>
              <h1>Omni-Detect</h1>
              <p class="subtitle">${escapeHtml(subtitleForMode(state.activeMode))}</p>
            </div>
          </div>
          <div class="header-controls">
            <div class="mode-toggle" role="group" aria-label="Detection mode">
              ${modeButton("mock", "Demo Mode")}
              ${modeButton("backend", "Real Models Mode")}
            </div>
            <div class="mode-note" role="note">${escapeHtml(noteForMode(state.activeMode))}</div>
          </div>
        </header>

        ${state.activeMode === "backend" ? backendStatusBanner() : ""}

        <div class="workspace-grid workspace-grid--multi">
          <div class="input-column">
            ${detectionForm({
              activeMode: state.activeMode,
              drafts: state.drafts,
              isSubmittingAll: state.isSubmittingAll,
            })}
          </div>
          <div class="output-column" aria-live="polite">
            ${jobHistoryPanel({ history: state.history })}
          </div>
        </div>
      </main>
    `;

    bindEvents();
  }

  /**
   * @param {import('./types/detection.js').DetectionMode} mode
   * @param {string} label
   */
  function modeButton(mode, label) {
    const active = state.activeMode === mode;
    return `
      <button class="mode-toggle__button ${active ? "is-active" : ""}" type="button" data-mode-switch="${mode}" aria-pressed="${active}">
        ${label}
      </button>
    `;
  }

  function backendStatusBanner() {
    const statusClass = `integration-banner--${state.backendStatus.state}`;
    return `
      <section class="integration-banner ${statusClass}" aria-label="Backend integration status">
        <div>
          <strong>${backendStatusTitle()}</strong>
          <p>${escapeHtml(state.backendStatus.message)}</p>
        </div>
        <button class="secondary-button secondary-button--small" type="button" data-check-backend ${state.backendStatus.state === "checking" ? "disabled" : ""}>
          ${state.backendStatus.state === "checking" ? "Checking" : "Check backend health"}
        </button>
      </section>
    `;
  }

  function backendStatusTitle() {
    if (state.backendStatus.state === "ok") {
      return "Backend reachable";
    }
    if (state.backendStatus.state === "error") {
      return "Backend unavailable";
    }
    if (state.backendStatus.state === "checking") {
      return "Checking backend";
    }
    return "Backend adapter";
  }

  /**
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  function subtitleForMode(mode) {
    if (mode === "backend") {
      return "Submit image jobs to a configured PIXAR/SIDA/LISA HTTP adapter. Text and document drafts stay demo-only.";
    }
    return "Queue multiple text, image, and file jobs with local mock results. Nothing leaves this browser.";
  }

  /**
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  function noteForMode(mode) {
    return mode === "backend"
      ? "Real Models Mode uses VITE_OMNI_DETECT_BACKEND_URL."
      : "Demo Mode generates random fake results.";
  }

  function bindEvents() {
    root.querySelectorAll("[data-mode-switch]").forEach((button) => {
      button.addEventListener("click", () => {
        switchMode(button.getAttribute("data-mode-switch"));
      });
    });

    root.querySelector("[data-check-backend]")?.addEventListener("click", () => {
      void checkBackendHealth();
    });

    root.querySelector("[data-add-job]")?.addEventListener("click", () => {
      state.drafts.push(createDraft(state.activeMode));
      render();
    });

    root.querySelector("[data-submit-all]")?.addEventListener("click", () => {
      void submitAllValidDrafts();
    });

    root.querySelectorAll("[data-remove-draft]").forEach((button) => {
      button.addEventListener("click", () => {
        removeDraft(button.getAttribute("data-remove-draft"));
      });
    });

    root.querySelectorAll("[data-submit-draft]").forEach((button) => {
      button.addEventListener("click", () => {
        void submitSingleDraft(button.getAttribute("data-submit-draft"));
      });
    });

    root.querySelectorAll("[data-toggle-details]").forEach((button) => {
      button.addEventListener("click", () => {
        toggleHistoryDetails(button.getAttribute("data-toggle-details"));
      });
    });

    root.querySelectorAll("[data-draft-kind]").forEach((select) => {
      select.addEventListener("change", (event) => {
        const draftId = select.getAttribute("data-draft-kind");
        const draft = findDraft(draftId);
        if (draft?.imagePreviewUrl) {
          URL.revokeObjectURL(draft.imagePreviewUrl);
        }
        updateDraft(draftId, {
          kind: event.target.value,
          imageFile: null,
          imagePreviewUrl: null,
          documentFile: null,
          validationError: "",
        });
      });
    });

    root.querySelectorAll("[data-draft-model]").forEach((select) => {
      select.addEventListener("change", (event) => {
        updateDraft(select.getAttribute("data-draft-model"), {
          model: event.target.value,
          validationError: "",
        });
      });
    });

    root.querySelectorAll("[data-draft-priority]").forEach((select) => {
      select.addEventListener("change", (event) => {
        updateDraft(select.getAttribute("data-draft-priority"), {
          priority: event.target.value,
          validationError: "",
        });
      });
    });

    root.querySelectorAll("[data-draft-text]").forEach((textarea) => {
      textarea.addEventListener("input", (event) => {
        updateDraft(
          textarea.getAttribute("data-draft-text"),
          {
            textValue: event.target.value,
            validationError: "",
          },
          false,
        );
      });
    });

    root.querySelectorAll("[data-draft-image]").forEach((input) => {
      input.addEventListener("change", (event) => {
        const draftId = input.getAttribute("data-draft-image");
        const file = event.target.files?.[0] || null;
        const error = validateImageFile(file);
        const draft = findDraft(draftId);
        if (draft?.imagePreviewUrl) {
          URL.revokeObjectURL(draft.imagePreviewUrl);
        }
        updateDraft(draftId, {
          imageFile: error ? null : file,
          imagePreviewUrl: !error && file ? URL.createObjectURL(file) : null,
          validationError: error,
        });
      });
    });

    root.querySelectorAll("[data-draft-file]").forEach((input) => {
      input.addEventListener("change", (event) => {
        const file = event.target.files?.[0] || null;
        const error = validateDocumentFile(file);
        updateDraft(input.getAttribute("data-draft-file"), {
          documentFile: error ? null : file,
          validationError: error,
        });
      });
    });
  }

  /**
   * @param {string | null} mode
   */
  function switchMode(mode) {
    const nextMode = normalizeMode(mode);
    if (nextMode === state.activeMode) {
      return;
    }
    state.activeMode = nextMode;
    state.drafts = state.drafts.map((draft) => ({
      ...draft,
      validationError: "",
    }));
    render();
    if (nextMode === "backend") {
      void checkBackendHealth();
    }
  }

  async function checkBackendHealth() {
    const service = serviceForMode("backend");
    state.backendStatus = {
      state: "checking",
      message: "Checking configured backend adapter...",
    };
    render();
    const result = service.checkHealth
      ? await service.checkHealth()
      : { ok: false, message: "The backend service does not expose a health check." };
    state.backendStatus = {
      state: result.ok ? "ok" : "error",
      message: result.message,
    };
    render();
  }

  async function submitSingleDraft(draftId) {
    const draft = findDraft(draftId);
    if (!draft) {
      return;
    }
    const mode = state.activeMode;
    const error = validateDraft(draft, mode);
    if (error) {
      updateDraft(draftId, { validationError: error });
      return;
    }

    updateDraft(draftId, { isSubmitting: true, validationError: "" });
    try {
      await submitDraft(draft, mode);
    } catch (error) {
      updateDraft(draftId, {
        validationError:
          error instanceof Error ? error.message : "Unable to submit job.",
      });
    } finally {
      updateDraft(draftId, { isSubmitting: false }, false);
      render();
    }
  }

  async function submitAllValidDrafts() {
    const mode = state.activeMode;
    const validation = state.drafts.map((draft) => ({
      draft,
      error: validateDraft(draft, mode),
    }));

    state.drafts = state.drafts.map((draft) => {
      const result = validation.find((item) => item.draft.draft_id === draft.draft_id);
      return {
        ...draft,
        validationError: result?.error || "",
        isSubmitting: !result?.error,
      };
    });

    const validDrafts = validation
      .filter((item) => !item.error)
      .map((item) => item.draft);

    if (!validDrafts.length) {
      render();
      return;
    }

    state.isSubmittingAll = true;
    render();

    await Promise.all(
      validDrafts.map(async (draft) => {
        try {
          await submitDraft(draft, mode);
        } catch (error) {
          updateDraft(
            draft.draft_id,
            {
              validationError:
                error instanceof Error ? error.message : "Unable to submit job.",
            },
            false,
          );
        } finally {
          updateDraft(draft.draft_id, { isSubmitting: false }, false);
        }
      }),
    );

    state.isSubmittingAll = false;
    render();
  }

  /**
   * @param {ReturnType<typeof createDraft>} draft
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  async function submitDraft(draft, mode) {
    const service = serviceForMode(mode);
    const options = {
      model: draft.model,
      priority: draft.priority,
    };
    let job;
    if (draft.kind === "text") {
      job = await service.submitTextDetection(draft.textValue.trim(), options);
    } else if (draft.kind === "image") {
      job = await service.submitImageDetection(draft.imageFile, options);
    } else {
      job = await service.submitFileDetection(draft.documentFile, options);
    }

    state.history.unshift(createHistoryItem(draft, job, mode));
    startPolling();
  }

  /**
   * @param {ReturnType<typeof createDraft>} draft
   * @param {import('./types/detection.js').DetectionJob} job
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  function createHistoryItem(draft, job, mode) {
    const imagePreviewUrl =
      draft.kind === "image" && draft.imageFile
        ? URL.createObjectURL(draft.imageFile)
        : null;
    return {
      history_id: `history_${newRandomId()}`,
      mode,
      job: normalizeJob(job, draft),
      model: draft.model,
      priority: draft.priority,
      sourceText: draft.kind === "text" ? draft.textValue.trim() : "",
      imagePreviewUrl,
      inputLabel: inputLabelForDraft(draft),
      expanded: false,
    };
  }

  function startPolling() {
    if (state.pollTimer) {
      return;
    }
    state.pollTimer = window.setInterval(
      pollActiveJobs,
      config.pollIntervalMs || FALLBACK_POLL_INTERVAL_MS,
    );
  }

  async function pollActiveJobs() {
    const activeItems = state.history.filter((item) =>
      ["queued", "running"].includes(item.job.status),
    );
    if (!activeItems.length) {
      stopPolling();
      render();
      return;
    }

    const updates = await Promise.all(
      activeItems.map(async (item) => {
        try {
          const service = serviceForMode(item.mode);
          const poller = service.pollJobStatus || service.getJob;
          const job = await poller.call(service, item.job.job_id);
          return { item, job: normalizeJob(job, item), error: null };
        } catch (error) {
          return { item, job: null, error };
        }
      }),
    );

    for (const update of updates) {
      const index = state.history.findIndex(
        (item) => item.history_id === update.item.history_id,
      );
      if (index < 0) {
        continue;
      }
      if (update.error) {
        state.history[index].job = {
          ...state.history[index].job,
          status: "failed",
          updated_at: Date.now(),
          completed_at: Date.now(),
          error: {
            code:
              update.item.mode === "backend"
                ? "backend_poll_failed"
                : "demo_poll_failed",
            message:
              update.error instanceof Error
                ? update.error.message
                : "Unable to poll job.",
          },
        };
      } else {
        state.history[index] = {
          ...state.history[index],
          job: update.job,
          model: update.job.model,
          priority: update.job.priority,
        };
      }
    }

    if (!state.history.some((item) => ["queued", "running"].includes(item.job.status))) {
      stopPolling();
    }
    render();
  }

  function stopPolling() {
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = 0;
    }
  }

  /**
   * @param {string | null} draftId
   */
  function removeDraft(draftId) {
    const draft = findDraft(draftId);
    if (draft?.imagePreviewUrl) {
      URL.revokeObjectURL(draft.imagePreviewUrl);
    }
    state.drafts = state.drafts.filter((item) => item.draft_id !== draftId);
    if (!state.drafts.length) {
      state.drafts.push(createDraft(state.activeMode));
    }
    render();
  }

  /**
   * @param {string | null} draftId
   * @param {Partial<ReturnType<typeof createDraft>>} changes
   * @param {boolean} shouldRender
   */
  function updateDraft(draftId, changes, shouldRender = true) {
    state.drafts = state.drafts.map((draft) =>
      draft.draft_id === draftId ? { ...draft, ...changes } : draft,
    );
    if (shouldRender) {
      render();
    }
  }

  /**
   * @param {string | null} historyId
   */
  function toggleHistoryDetails(historyId) {
    state.history = state.history.map((item) =>
      item.history_id === historyId ? { ...item, expanded: !item.expanded } : item,
    );
    render();
  }

  /**
   * @param {string | null} draftId
   */
  function findDraft(draftId) {
    return state.drafts.find((draft) => draft.draft_id === draftId);
  }

  /**
   * @param {ReturnType<typeof createDraft>} draft
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  function validateDraft(draft, mode) {
    if (mode === "backend" && draft.kind !== "image") {
      return IMAGE_ONLY_BACKEND_MESSAGE;
    }
    if (draft.kind === "text" && !draft.textValue.trim()) {
      return "Enter text before submitting this job.";
    }
    if (draft.kind === "image") {
      return validateImageFile(draft.imageFile);
    }
    return validateDocumentFile(draft.documentFile);
  }

  /**
   * @param {File | null} file
   */
  function validateImageFile(file) {
    if (!file) {
      return "Choose a PNG, JPG, JPEG, or WEBP image.";
    }
    if (file.size > DEMO_MAX_UPLOAD_BYTES) {
      return "Uploads are limited to 10 MB in this UI.";
    }
    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      return "Unsupported image type. Use PNG, JPG, JPEG, or WEBP.";
    }
    return "";
  }

  /**
   * @param {File | null} file
   */
  function validateDocumentFile(file) {
    if (!file) {
      return "Choose a PDF, TXT, DOC, or DOCX file.";
    }
    if (file.size > DEMO_MAX_UPLOAD_BYTES) {
      return "Uploads are limited to 10 MB in this UI.";
    }
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const acceptedType = ACCEPTED_DOCUMENT_TYPES.includes(file.type);
    const acceptedExtension = ACCEPTED_DOCUMENT_EXTENSIONS.includes(extension);
    if (!acceptedType && !acceptedExtension) {
      return "Unsupported file type. Use PDF, TXT, DOC, or DOCX.";
    }
    return "";
  }

  /**
   * @param {import('./types/detection.js').DetectionMode} mode
   */
  function serviceForMode(mode) {
    return mode === "backend" ? services.backend : services.mock;
  }

  function cleanupObjectUrls() {
    for (const draft of state.drafts) {
      if (draft.imagePreviewUrl) {
        URL.revokeObjectURL(draft.imagePreviewUrl);
      }
    }
    for (const item of state.history) {
      if (item.imagePreviewUrl) {
        URL.revokeObjectURL(item.imagePreviewUrl);
      }
    }
  }

  window.addEventListener("beforeunload", cleanupObjectUrls);

  render();

  return {
    destroy() {
      stopPolling();
      window.removeEventListener("beforeunload", cleanupObjectUrls);
      cleanupObjectUrls();
    },
  };
}

/**
 * @param {import('./types/detection.js').DetectionMode} mode
 */
function createDraft(mode = "mock") {
  return {
    draft_id: `draft_${newRandomId()}`,
    kind: mode === "backend" ? "image" : "text",
    textValue: "",
    imageFile: null,
    imagePreviewUrl: null,
    documentFile: null,
    model: DEFAULT_MODEL,
    priority: "normal",
    validationError: "",
    isSubmitting: false,
  };
}

/**
 * @param {import('./types/detection.js').DetectionJob} job
 * @param {{ model?: string, priority?: string, job?: import('./types/detection.js').DetectionJob }} source
 */
function normalizeJob(job, source) {
  const status = normalizeUiStatus(job.status);
  const updatedAt = toTimestamp(job.updated_at) || Date.now();
  const createdAt = toTimestamp(job.created_at) || updatedAt;
  const startedAt = toTimestamp(job.started_at) || null;
  const completedAt =
    toTimestamp(job.completed_at) ||
    (["succeeded", "failed"].includes(status) ? updatedAt : null);
  return {
    ...job,
    status,
    model: job.model || source.model || source.job?.model || DEFAULT_MODEL,
    priority: job.priority || source.priority || source.job?.priority || "normal",
    created_at: createdAt,
    updated_at: updatedAt,
    started_at: startedAt,
    completed_at: completedAt,
    result: job.result || null,
    error:
      job.error ||
      (status === "failed"
        ? {
            code: "job_failed",
            message: "The job failed before returning a detailed error.",
          }
        : null),
  };
}

/**
 * @param {ReturnType<typeof createDraft>} draft
 */
function inputLabelForDraft(draft) {
  if (draft.kind === "text") {
    const value = draft.textValue.trim();
    return value.length > 64 ? `${value.slice(0, 64)}...` : value;
  }
  if (draft.kind === "image") {
    return draft.imageFile?.name || "Image upload";
  }
  return draft.documentFile?.name || "File upload";
}

/**
 * @param {unknown} value
 * @returns {import('./types/detection.js').DetectionMode}
 */
function normalizeMode(value) {
  return value === "backend" ? "backend" : "mock";
}

/**
 * @param {unknown} value
 * @returns {import('./types/detection.js').JobStatus}
 */
function normalizeUiStatus(value) {
  return value === "queued" ||
    value === "running" ||
    value === "succeeded" ||
    value === "failed"
    ? value
    : "failed";
}

/**
 * @param {unknown} value
 */
function toTimestamp(value) {
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
 * @param {{
 *   mock?: import('./types/detectionService.js').DetectionService,
 *   backend?: import('./types/detectionService.js').DetectionService
 * } | import('./types/detectionService.js').DetectionService} services
 */
function normalizeServiceMap(services) {
  if (services && "mock" in services && "backend" in services) {
    return services;
  }
  return {
    mock: services,
    backend: services,
  };
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
