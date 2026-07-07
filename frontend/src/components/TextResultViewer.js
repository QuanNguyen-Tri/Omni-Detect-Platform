import { probabilityBadge } from "./ProbabilityBadge.js";
import { escapeHtml, titleCase } from "../utils/format.js";

/**
 * @param {string} text
 * @param {import('../types/detection.js').TextDetectionResult} result
 */
export function textResultViewer(text, result) {
  return `
    <section class="result-panel" aria-labelledby="text-result-heading">
      <div class="section-heading">
        <h2 id="text-result-heading">Suspicious text spans</h2>
        <p>Highlighted ranges are randomly selected for demo purposes.</p>
      </div>
      <div class="text-highlight-viewer">${highlightText(text, result.spans)}</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Range</th>
              <th>Span</th>
              <th>Probability</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            ${result.spans.map(spanRow).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

/**
 * @param {string} text
 * @param {import('../types/detection.js').TextDetectionSpan[]} spans
 */
function highlightText(text, spans) {
  let cursor = 0;
  let html = "";
  for (const span of spans) {
    html += escapeHtml(text.slice(cursor, span.start_char));
    html += `
      <mark title="${Math.round(span.ai_probability * 100)}% AI probability">
        ${escapeHtml(text.slice(span.start_char, span.end_char))}
      </mark>
    `;
    cursor = span.end_char;
  }
  html += escapeHtml(text.slice(cursor));
  return html;
}

/** @param {import('../types/detection.js').TextDetectionSpan} span */
function spanRow(span) {
  return `
    <tr>
      <td>${span.start_char}-${span.end_char}</td>
      <td>${escapeHtml(span.text)}</td>
      <td>${probabilityBadge(span.ai_probability)}</td>
      <td>${titleCase(span.label)}</td>
    </tr>
  `;
}

