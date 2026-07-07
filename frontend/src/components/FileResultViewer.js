import { probabilityBadge } from "./ProbabilityBadge.js";
import { escapeHtml, formatBytes, titleCase } from "../utils/format.js";

/** @param {import('../types/detection.js').FileDetectionResult} result */
export function fileResultViewer(result) {
  return `
    <section class="result-panel" aria-labelledby="file-result-heading">
      <div class="section-heading">
        <h2 id="file-result-heading">File detection details</h2>
        <p>Per-section probabilities for the uploaded document.</p>
      </div>

      <dl class="file-meta">
        <div>
          <dt>Name</dt>
          <dd>${escapeHtml(result.metadata.file_name)}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>${escapeHtml(result.metadata.file_type)}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>${formatBytes(result.metadata.file_size)}</dd>
        </div>
      </dl>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Section</th>
              <th>Probability</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            ${result.sections.map(sectionRow).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

/** @param {import('../types/detection.js').FileDetectionSection} section */
function sectionRow(section) {
  return `
    <tr>
      <td>${escapeHtml(section.section_label)}</td>
      <td>${probabilityBadge(section.ai_probability)}</td>
      <td>${titleCase(section.label)}</td>
    </tr>
  `;
}
