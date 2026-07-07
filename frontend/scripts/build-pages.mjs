#!/usr/bin/env node

import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendDir, "..");
const distDir = path.join(frontendDir, "dist");
const basePath = normalizeBasePath(process.env.VITE_BASE_PATH || "/");

await rm(distDir, { recursive: true, force: true });
await mkdir(distDir, { recursive: true });

await cp(path.join(frontendDir, "src"), path.join(distDir, "src"), {
  recursive: true,
});
await cp(path.join(repoRoot, "static"), path.join(distDir, "static"), {
  recursive: true,
});

const runtimeConfig = {
  basePath,
};

addPublicConfig(runtimeConfig, "detectionApiMode", process.env.VITE_DETECTION_API_MODE);
addPublicConfig(
  runtimeConfig,
  "omniDetectBackendUrl",
  process.env.VITE_OMNI_DETECT_BACKEND_URL,
);
addPublicConfig(
  runtimeConfig,
  "omniDetectPollIntervalMs",
  process.env.VITE_OMNI_DETECT_POLL_INTERVAL_MS,
);

const sourceHtml = await readText(path.join(frontendDir, "index.html"));
const html = injectPagesConfig(sourceHtml, basePath, runtimeConfig);
await writeFile(path.join(distDir, "index.html"), html);
await writeFile(path.join(distDir, "404.html"), html);
await writeFile(path.join(distDir, ".nojekyll"), "");

console.log(`Built GitHub Pages static site at ${relativeToCwd(distDir)}`);
console.log(`Base path: ${basePath}`);

/**
 * @param {Record<string, string>} config
 * @param {string} key
 * @param {string | undefined} value
 */
function addPublicConfig(config, key, value) {
  if (value !== undefined && value !== "") {
    config[key] = value;
  }
}

/**
 * @param {string} html
 * @param {string} pagesBasePath
 * @param {Record<string, string>} config
 */
function injectPagesConfig(html, pagesBasePath, config) {
  const safeConfig = JSON.stringify(config).replaceAll("<", "\\u003c");
  const baseTag = `<base href="${escapeAttribute(pagesBasePath)}" />`;
  const configScript = `<script>window.OMNI_DETECT_CONFIG = Object.assign(${safeConfig}, window.OMNI_DETECT_CONFIG || {});</script>`;
  return html.replace(
    "<head>",
    `<head>\n    ${baseTag}\n    ${configScript}`,
  );
}

/**
 * @param {string} filePath
 */
async function readText(filePath) {
  const { readFile } = await import("node:fs/promises");
  return readFile(filePath, "utf8");
}

/**
 * @param {string} value
 */
function normalizeBasePath(value) {
  const trimmed = value.trim();
  if (!trimmed || trimmed === ".") {
    return "/";
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return withLeadingSlash.endsWith("/") ? withLeadingSlash : `${withLeadingSlash}/`;
}

/**
 * @param {string} value
 */
function escapeAttribute(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/**
 * @param {string} targetPath
 */
function relativeToCwd(targetPath) {
  return path.relative(process.cwd(), targetPath) || ".";
}
