/**
 * @param {number} value
 */
export function probabilityBadge(value) {
  const percent = Math.round(value * 100);
  const level = percent >= 70 ? "high" : percent >= 40 ? "medium" : "low";
  return `<span class="probability-badge probability-badge--${level}">${percent}%</span>`;
}

/**
 * @param {number} value
 */
export function probabilityText(value) {
  return `${Math.round(value * 100)}%`;
}

