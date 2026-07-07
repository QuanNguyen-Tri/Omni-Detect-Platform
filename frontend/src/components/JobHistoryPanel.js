import { fileResultViewer } from "./FileResultViewer.js";
import { imageResultViewer } from "./ImageResultViewer.js";
import { probabilityBadge, probabilityText } from "./ProbabilityBadge.js";
import { textResultViewer } from "./TextResultViewer.js";
import { escapeHtml, formatTime, titleCase } from "../utils/format.js";

/**
 * @param {{
 *   history: Array<{
 *     history_id: string,
 *     mode: import('../types/detection.js').DetectionMode,
 *     job: import('../types/detection.js').DetectionJob,
 *     model: import('../types/detection.js').DetectionModel,
 *     priority: import('../types/detection.js').JobPriority,
 *     sourceText: string,
 *     imagePreviewUrl: string | null,
 *     inputLabel: string,
 *     expanded: boolean
 *   }>
 * }} props
 */
export function jobHistoryPanel(props) {
  return `
    <section class="history-panel" aria-labelledby="job-history-heading">
      <div class="section-heading">
        <div>
          <h2 id="job-history-heading">Job history</h2>
          <p>Submitted jobs run concurrently and remain available for review.</p>
        </div>
        <span class="history-count">${props.history.length} submitted</span>
      </div>

      ${
        props.history.length
          ? `<div class="history-list">${props.history.map(historyItem).join("")}</div>`
          : `<div class="status-empty">No jobs submitted yet.</div>`
      }
    </section>
  `;
}

/**
 * @param {Parameters<typeof jobHistoryPanel>[0]['history'][number]} item
 */
function historyItem(item) {
  const job = item.job;
  const completedAt = job.completed_at || null;
  const durationBase = job.started_at || job.created_at;
  const duration = completedAt ? formatDuration(completedAt - durationBase) : "In progress";
  const probability = job.result?.overall_ai_probability;
  return `
    <article class="history-item ${item.expanded ? "is-expanded" : ""}">
      <div class="history-item__summary">
        <div class="history-main">
          <span class="status-pill status-pill--${job.status}">${titleCase(job.status)}</span>
          <div>
            <strong>${escapeHtml(job.job_id)}</strong>
            <span>${modeLabel(item.mode)} · ${titleCase(job.kind)} · ${escapeHtml(item.model)} · ${titleCase(item.priority)} priority</span>
            ${job.status === "failed" ? `<span class="history-error">${escapeHtml(job.error?.message || "Job failed.")}</span>` : ""}
          </div>
        </div>

        <dl class="history-meta">
          ${meta("Created", formatTime(job.created_at))}
          ${meta("Completed", completedAt ? formatTime(completedAt) : "—")}
          ${meta("Duration", duration)}
          ${meta("Probability", probability === undefined ? "—" : probabilityText(probability))}
        </dl>

        <button class="secondary-button secondary-button--small" type="button" data-toggle-details="${item.history_id}">
          ${item.expanded ? "Hide Details" : "View Details"}
        </button>
      </div>

      ${item.expanded ? expandedDetails(item) : ""}
    </article>
  `;
}

/**
 * @param {Parameters<typeof jobHistoryPanel>[0]['history'][number]} item
 */
function expandedDetails(item) {
  const job = item.job;
  if (job.status === "failed") {
    return `
      <div class="history-details">
        <div class="form-error">${escapeHtml(job.error?.message || "Job failed.")}</div>
      </div>
    `;
  }

  if (job.status !== "succeeded" || !job.result) {
    return `
      <div class="history-details">
        <div class="status-empty">Results will appear when this job completes.</div>
      </div>
    `;
  }

  const summaryHeading =
    item.mode === "mock" ? "Fake analysis summary" : "Analysis summary";
  return `
    <div class="history-details">
      <section class="analysis-summary" aria-label="${summaryHeading}">
        <div>
          <h3>${summaryHeading}</h3>
          <p>${escapeHtml(job.result.analysis_summary || "Analysis completed.")}</p>
        </div>
        ${probabilityBadge(job.result.overall_ai_probability)}
      </section>
      ${detailViewer(item)}
    </div>
  `;
}

/**
 * @param {Parameters<typeof jobHistoryPanel>[0]['history'][number]} item
 */
function detailViewer(item) {
  if (item.job.kind === "text") {
    return textResultViewer(item.sourceText, item.job.result);
  }
  if (item.job.kind === "image") {
    return imageResultViewer(item.imagePreviewUrl, item.job.result);
  }
  return fileResultViewer(item.job.result);
}

/**
 * @param {string} label
 * @param {string} value
 */
function meta(label, value) {
  return `
    <div>
      <dt>${label}</dt>
      <dd>${escapeHtml(value)}</dd>
    </div>
  `;
}

/**
 * @param {number} milliseconds
 */
function formatDuration(milliseconds) {
  const seconds = Math.max(0, milliseconds / 1000);
  if (seconds < 1) {
    return `${Math.round(milliseconds)} ms`;
  }
  return `${seconds.toFixed(1)} s`;
}

/**
 * @param {import('../types/detection.js').DetectionMode} mode
 */
function modeLabel(mode) {
  return mode === "backend" ? "Real Models" : "Demo";
}
