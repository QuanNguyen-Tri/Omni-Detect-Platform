import { probabilityBadge } from "./ProbabilityBadge.js";
import { escapeHtml, titleCase } from "../utils/format.js";

/**
 * @param {string | null} imagePreviewUrl
 * @param {import('../types/detection.js').ImageDetectionResult} result
 */
export function imageResultViewer(imagePreviewUrl, result) {
  const regions = result.regions || [];
  return `
    <section class="result-panel" aria-labelledby="image-result-heading">
      <div class="section-heading">
        <h2 id="image-result-heading">Suspicious image regions</h2>
        <p>${regions.length ? "Bounding boxes use normalized percentages so they scale with the preview." : "Pixel-level mask output from the backend is shown when boxes are not available."}</p>
      </div>

      <div class="image-result-layout">
        <div class="image-preview-frame">
          ${
            imagePreviewUrl
              ? `<img src="${imagePreviewUrl}" alt="Uploaded demo preview" />`
              : `<div class="status-empty">No image preview available.</div>`
          }
          ${regions.map(regionBox).join("")}
        </div>

        <div class="region-list">
          ${regions.length ? regions.map(regionItem).join("") : pixelLevelItem(result)}
        </div>
      </div>
    </section>
  `;
}

/** @param {import('../types/detection.js').ImageDetectionRegion} region */
function regionBox(region) {
  return `
    <div
      class="region-box"
      style="
        left: ${region.x}%;
        top: ${region.y}%;
        width: ${region.width}%;
        height: ${region.height}%;
      "
      title="${Math.round(region.ai_probability * 100)}% ${titleCase(region.label)}"
    ></div>
  `;
}

/** @param {import('../types/detection.js').ImageDetectionRegion} region */
function regionItem(region) {
  return `
    <article class="region-item">
      <div>
        <strong>${titleCase(region.label)}</strong>
        <span>${region.width}% x ${region.height}% region</span>
      </div>
      ${probabilityBadge(region.ai_probability)}
    </article>
  `;
}

/** @param {import('../types/detection.js').ImageDetectionResult} result */
function pixelLevelItem(result) {
  const coverage =
    typeof result.positive_pixel_fraction === "number"
      ? `${Math.round(result.positive_pixel_fraction * 1000) / 10}% mask coverage`
      : "Mask coverage unavailable";
  return `
    <article class="region-item region-item--note">
      <div>
        <strong>Pixel-level localization</strong>
        <span>No bounding boxes were returned by this model.</span>
        <span>${coverage}</span>
        ${assetLink("Overlay", result.overlay_url)}
        ${assetLink("Mask", result.mask_url)}
      </div>
    </article>
  `;
}

/**
 * @param {string} label
 * @param {string | null | undefined} url
 */
function assetLink(label, url) {
  if (!url) {
    return "";
  }
  return `<a class="result-asset-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label} output</a>`;
}
