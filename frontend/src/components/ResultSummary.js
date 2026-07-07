import { probabilityBadge } from "./ProbabilityBadge.js";
import { titleCase } from "../utils/format.js";

/** @param {import('../types/detection.js').DetectionJob | null} job */
export function resultSummary(job) {
  if (!job || job.status !== "succeeded" || !job.result) {
    return "";
  }

  return `
    <section class="summary-panel" aria-labelledby="result-summary-heading">
      <div class="summary-copy">
        <h2 id="result-summary-heading">Result summary</h2>
        <p>${titleCase(job.kind)} demo result generated locally.</p>
      </div>
      <div class="summary-score">
        <span>Overall AI probability</span>
        ${probabilityBadge(job.result.overall_ai_probability)}
      </div>
    </section>
  `;
}

