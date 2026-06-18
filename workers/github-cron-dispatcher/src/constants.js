/** @typedef {{ workflowId: string, inputs?: Record<string, string> }} DispatchTarget */

/** Issue #93 / Phase 1: single cron for daily.yml (UTC 06:37 = JST 15:37, Mon-Fri). */
export const DAILY_CRON = "37 6 * * MON-FRI";

export const DAILY_WORKFLOW_FILE = "daily.yml";

/** @type {Record<string, DispatchTarget[]>} */
export const ROUTING_TABLE = {
  [DAILY_CRON]: [{ workflowId: DAILY_WORKFLOW_FILE, inputs: {} }],
};
