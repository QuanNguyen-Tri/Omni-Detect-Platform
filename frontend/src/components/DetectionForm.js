import {
  ACCEPTED_DOCUMENT_EXTENSIONS,
  ACCEPTED_IMAGE_TYPES,
  DEMO_MAX_UPLOAD_BYTES,
  MODEL_OPTIONS,
  PRIORITY_OPTIONS,
} from "../config.js";
import { escapeHtml, formatBytes, titleCase } from "../utils/format.js";

/**
 * @param {{
 *   activeMode: import('../types/detection.js').DetectionMode,
 *   drafts: Array<{
 *     draft_id: string,
 *     kind: import('../types/detection.js').DetectionInputType,
 *     textValue: string,
 *     imageFile: File | null,
 *     documentFile: File | null,
 *     model: import('../types/detection.js').DetectionModel,
 *     priority: import('../types/detection.js').JobPriority,
 *     validationError: string,
 *     isSubmitting: boolean
 *   }>,
 *   isSubmittingAll: boolean
 * }} props
 */
export function detectionForm(props) {
  return `
    <section class="tool-panel" aria-labelledby="detection-form-heading">
      <div class="section-heading">
        <div>
          <h2 id="detection-form-heading">Draft jobs</h2>
          <p>Create several jobs, tune each one, then submit individually or as a batch.</p>
        </div>
        <button class="secondary-button" type="button" data-add-job>+ Add Job</button>
      </div>

      <div class="draft-list">
        ${props.drafts.map(draftCard).join("")}
      </div>

      <div class="batch-actions">
        <button class="primary-button" type="button" data-submit-all ${props.isSubmittingAll ? "disabled" : ""}>
          ${props.isSubmittingAll ? "Submitting jobs" : "Submit all valid jobs"}
        </button>
        <p class="demo-note">
          ${escapeHtml(noteForMode(props.activeMode))}
        </p>
      </div>
    </section>
  `;
}

/**
 * @param {Parameters<typeof detectionForm>[0]['drafts'][number]} draft
 */
function draftCard(draft) {
  return `
    <article class="draft-card" data-draft-id="${draft.draft_id}">
      <div class="draft-card__header">
        <div>
          <strong>${titleCase(draft.kind)} draft</strong>
          <span>${modelLabel(draft.model)} · ${titleCase(draft.priority)} priority</span>
        </div>
        <button class="icon-button" type="button" title="Remove draft" data-remove-draft="${draft.draft_id}">×</button>
      </div>

      <div class="draft-controls">
        <label>
          <span>Input type</span>
          <select data-draft-kind="${draft.draft_id}">
            ${option("text", "Text", draft.kind)}
            ${option("image", "Image", draft.kind)}
            ${option("file", "File", draft.kind)}
          </select>
        </label>
        <label>
          <span>Model</span>
          <select data-draft-model="${draft.draft_id}">
            ${MODEL_OPTIONS.map((model) =>
              option(model.value, model.label, draft.model),
            ).join("")}
          </select>
        </label>
        <label>
          <span>Priority</span>
          <select data-draft-priority="${draft.draft_id}">
            ${PRIORITY_OPTIONS.map((priority) =>
              option(priority.value, priority.label, draft.priority),
            ).join("")}
          </select>
        </label>
      </div>

      ${inputForDraft(draft)}

      ${
        draft.validationError
          ? `<div class="form-error" role="alert">${escapeHtml(draft.validationError)}</div>`
          : ""
      }

      <button class="primary-button primary-button--compact" type="button" data-submit-draft="${draft.draft_id}" ${draft.isSubmitting ? "disabled" : ""}>
        ${draft.isSubmitting ? "Submitting" : "Submit job"}
      </button>
    </article>
  `;
}

/**
 * @param {Parameters<typeof detectionForm>[0]['drafts'][number]} draft
 */
function inputForDraft(draft) {
  if (draft.kind === "text") {
    return `
      <label class="field-label" for="text-input-${draft.draft_id}">Text sample</label>
      <textarea
        id="text-input-${draft.draft_id}"
        data-draft-text="${draft.draft_id}"
        rows="7"
        maxlength="12000"
        placeholder="Paste a paragraph, article excerpt, or generated response..."
      >${escapeHtml(draft.textValue)}</textarea>
    `;
  }

  if (draft.kind === "image") {
    return `
      <label class="field-label" for="image-input-${draft.draft_id}">Image upload</label>
      <input
        id="image-input-${draft.draft_id}"
        data-draft-image="${draft.draft_id}"
        type="file"
        accept="${ACCEPTED_IMAGE_TYPES.join(",")}"
      />
      ${selectedFile(draft.imageFile)}
      <p class="field-help">Accepted: PNG, JPG, JPEG, WEBP. Max ${formatBytes(DEMO_MAX_UPLOAD_BYTES)}.</p>
    `;
  }

  return `
    <label class="field-label" for="file-input-${draft.draft_id}">Document upload</label>
    <input
      id="file-input-${draft.draft_id}"
      data-draft-file="${draft.draft_id}"
      type="file"
      accept="${ACCEPTED_DOCUMENT_EXTENSIONS.join(",")}"
    />
    ${selectedFile(draft.documentFile)}
    <p class="field-help">Accepted: PDF, TXT, DOC, DOCX. Max ${formatBytes(DEMO_MAX_UPLOAD_BYTES)}.</p>
  `;
}

/**
 * @param {File | null} file
 */
function selectedFile(file) {
  if (!file) {
    return "";
  }
  return `<p class="selected-file">Selected: ${escapeHtml(file.name)}</p>`;
}

/**
 * @param {string} value
 * @param {string} label
 * @param {string} selected
 */
function option(value, label, selected) {
  return `<option value="${value}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

/**
 * @param {string} value
 */
function modelLabel(value) {
  return MODEL_OPTIONS.find((model) => model.value === value)?.label || value;
}

/**
 * @param {import('../types/detection.js').DetectionMode} mode
 */
function noteForMode(mode) {
  if (mode === "backend") {
    return "Real Models Mode submits image drafts to the configured backend adapter. Text and file drafts remain available in Demo Mode.";
  }
  return "Demo Mode keeps all jobs in this browser and generates random fake results.";
}
