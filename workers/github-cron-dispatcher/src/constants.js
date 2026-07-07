/** @typedef {{ workflowId: string, inputs?: Record<string, string> }} DispatchTarget */

/** Issue #93 / Phase 1: daily.yml (UTC 06:45 = JST 15:45, daily). */
export const DAILY_CRON = "45 6 * * *";

/** Issue #93: daily_universe_patch.yml (UTC 03:00 = JST 12:00, daily). */
export const UNIVERSE_PATCH_CRON = "0 3 * * *";

export const DAILY_WORKFLOW_FILE = "daily.yml";

export const UNIVERSE_PATCH_WORKFLOW_FILE = "daily_universe_patch.yml";

/** @type {Record<string, DispatchTarget[]>} */
export const ROUTING_TABLE = {
  [DAILY_CRON]: [{ workflowId: DAILY_WORKFLOW_FILE, inputs: {} }],
  [UNIVERSE_PATCH_CRON]: [{ workflowId: UNIVERSE_PATCH_WORKFLOW_FILE, inputs: {} }],
};
