import { detectionConfig } from "../config.js";
import { createBackendDetectionService } from "./backendDetectionService.js";
import { mockDetectionService } from "./mockDetectionService.js";

/**
 * @param {typeof detectionConfig} config
 */
export function createDetectionServices(config = detectionConfig) {
  return {
    mock: mockDetectionService,
    backend: createBackendDetectionService(config),
  };
}

/**
 * @param {import('../types/detection.js').DetectionMode} mode
 * @param {typeof detectionConfig} config
 * @returns {import('../types/detectionService.js').DetectionService}
 */
export function createDetectionService(mode = "mock", config = detectionConfig) {
  return mode === "backend"
    ? createBackendDetectionService(config)
    : mockDetectionService;
}

export const detectionServices = createDetectionServices();
export const detectionService = createDetectionService(detectionConfig.defaultMode);
