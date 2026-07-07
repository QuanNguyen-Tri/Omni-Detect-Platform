#!/usr/bin/env node

import { createServer } from "node:http";
import { stat, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const distDir = path.join(frontendDir, "dist");
const basePath = normalizeBasePath(process.env.VITE_BASE_PATH || "/");
const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 4173);

const server = createServer(async (request, response) => {
  try {
    await handleRequest(request, response);
  } catch (error) {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end(error instanceof Error ? error.message : "Internal server error");
  }
});

server.listen(port, host, () => {
  console.log(`Previewing ${distDir}`);
  console.log(`Local: http://${host}:${port}${basePath}`);
});

/**
 * @param {import('node:http').IncomingMessage} request
 * @param {import('node:http').ServerResponse} response
 */
async function handleRequest(request, response) {
  const url = new URL(request.url || "/", `http://${host}:${port}`);
  if (basePath !== "/" && url.pathname === "/") {
    response.writeHead(302, { location: basePath });
    response.end();
    return;
  }

  const relativePath = stripBasePath(url.pathname);
  if (relativePath === null) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  const filePath = await resolveFile(relativePath);
  const body = await readFile(filePath);
  response.writeHead(200, { "content-type": contentType(filePath) });
  if (request.method === "HEAD") {
    response.end();
    return;
  }
  response.end(body);
}

/**
 * @param {string} pathname
 */
function stripBasePath(pathname) {
  if (basePath === "/") {
    return pathname.slice(1);
  }
  if (pathname === basePath.slice(0, -1)) {
    return "";
  }
  if (!pathname.startsWith(basePath)) {
    return null;
  }
  return pathname.slice(basePath.length);
}

/**
 * @param {string} relativePath
 */
async function resolveFile(relativePath) {
  const cleanPath = relativePath || "index.html";
  const resolved = path.resolve(distDir, cleanPath);
  const relativeToDist = path.relative(distDir, resolved);
  if (relativeToDist.startsWith("..") || path.isAbsolute(relativeToDist)) {
    return path.join(distDir, "404.html");
  }

  try {
    const info = await stat(resolved);
    if (info.isDirectory()) {
      return path.join(resolved, "index.html");
    }
    return resolved;
  } catch {
    return path.extname(cleanPath)
      ? path.join(distDir, "404.html")
      : path.join(distDir, "index.html");
  }
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
 * @param {string} filePath
 */
function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return (
    {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".png": "image/png",
      ".svg": "image/svg+xml",
      ".webp": "image/webp",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
    }[ext] || "application/octet-stream"
  );
}
