import { escapeHtml, formatTime, titleCase } from "../utils/format.js";

/** @param {import('../types/detection.js').DetectionJob | null} job */
export function jobStatusCard(job) {
  if (!job) {
    return `
      <section class="status-panel" aria-labelledby="status-heading">
        <div class="section-heading">
          <h2 id="status-heading">Job status</h2>
          <p>No job has been submitted yet.</p>
        </div>
        <div class="status-empty">Submit content to see the async workflow.</div>
      </section>
    `;
  }

  const isActive = job.status === "queued" || job.status === "running";
  return `
    <section class="status-panel" aria-labelledby="status-heading">
      <div class="section-heading">
        <h2 id="status-heading">Job status</h2>
        <p>Job <code>${escapeHtml(job.job_id)}</code></p>
      </div>

      <div class="status-line">
        <span class="status-pill status-pill--${job.status}">${titleCase(job.status)}</span>
        ${isActive ? `<span class="spinner" aria-hidden="true"></span>` : ""}
      </div>

      <ol class="status-steps" aria-label="Job lifecycle">
        ${step("queued", job.status)}
        ${step("running", job.status)}
        ${step("succeeded", job.status)}
      </ol>

      <dl class="job-meta">
        <div>
          <dt>Type</dt>
          <dd>${titleCase(job.kind)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>${formatTime(job.updated_at)}</dd>
        </div>
      </dl>

      ${
        job.status === "failed" && job.error
          ? `<div class="form-error" role="alert">${escapeHtml(job.error.message)}</div>`
          : ""
      }
    </section>
  `;
}

/**
 * @param {'queued' | 'running' | 'succeeded'} status
 * @param {import('../types/detection.js').JobStatus} current
 */
function step(status, current) {
  const order = ["queued", "running", "succeeded"];
  const currentIndex = order.indexOf(current);
  const statusIndex = order.indexOf(status);
  const complete = current === "failed" ? statusIndex < 2 : statusIndex <= currentIndex;
  return `
    <li class="${complete ? "is-complete" : ""}">
      <span></span>
      ${titleCase(status)}
    </li>
  `;
}
