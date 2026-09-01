import { DAILY_WORKFLOW_FILE, MNC_DISPATCH_WORKFLOW_FILE, MONTHLY_WORKFLOW_FILE, ROUTING_TABLE } from "./constants.js";
import {
  dispatchWorkflow,
  logEvent,
  mergeDailyInputs,
  missingRequiredEnv,
} from "./dispatch.js";

/**
 * @param {string} cron
 * @returns {import("./constants.js").DispatchTarget[] | null}
 */
export function resolveTargetsForCron(cron) {
  return ROUTING_TABLE[cron] ?? null;
}

/**
 * @param {Record<string, string | undefined>} env
 * @param {string} workflowId
 * @returns {boolean}
 */
export function isMonthlyDispatchEnabled(env, workflowId) {
  if (workflowId !== MONTHLY_WORKFLOW_FILE) {
    return true;
  }
  const raw = env.MONTHLY_DISPATCH_ENABLED;
  if (raw === undefined || raw === "") {
    return false;
  }
  return String(raw).trim().toLowerCase() === "true";
}

/**
 * ADR-005 poller gate. Default false (unlike daily). Not isMonthlyDispatchEnabled.
 * @param {Record<string, string | undefined>} env
 * @param {string} workflowId
 * @returns {boolean}
 */
export function isMncDispatchEnabled(env, workflowId) {
  if (workflowId !== MNC_DISPATCH_WORKFLOW_FILE) {
    return true;
  }
  const raw = env.MNC_DISPATCH_ENABLED;
  if (raw === undefined || raw === "") {
    return false;
  }
  return String(raw).trim().toLowerCase() === "true";
}

/**
 * @param {number | Date | string | null | undefined} scheduledTime
 * @param {number} [nowMs]
 * @returns {Date}
 */
function mncClock(scheduledTime, nowMs = Date.now()) {
  if (scheduledTime === undefined || scheduledTime === null || scheduledTime === "") {
    return new Date(nowMs);
  }
  const t = new Date(scheduledTime);
  return Number.isNaN(t.getTime()) ? new Date(nowMs) : t;
}

/**
 * Monthly runs at 02:00 UTC on day 1 (= 11:00 JST). Polling the empty outbox
 * before that is pure GHA noise — skip MNC dispatch on day-1 UTC hours 0–1.
 *
 * @param {number | Date | string | null | undefined} scheduledTime
 * @param {number} [nowMs]
 * @returns {boolean}
 */
export function isMncBeforeMonthlyWindow(scheduledTime, nowMs = Date.now()) {
  const t = mncClock(scheduledTime, nowMs);
  if (t.getUTCDate() !== 1) {
    return false;
  }
  return t.getUTCHours() < 2;
}

/**
 * Active poller window: day-1 UTC hours 2-5 only (matches cron every 15m in hours 2-5 on day 1).
 * Once Monthly has written the outbox, a few same-morning ticks are enough;
 * multi-day empty fifteen-minute launches are not.
 *
 * @param {number | Date | string | null | undefined} scheduledTime
 * @param {number} [nowMs]
 * @returns {boolean}
 */
export function isMncActiveDrainWindow(scheduledTime, nowMs = Date.now()) {
  const t = mncClock(scheduledTime, nowMs);
  if (t.getUTCDate() !== 1) {
    return false;
  }
  const hour = t.getUTCHours();
  return hour >= 2 && hour <= 5;
}

/**
 * @param {number | Date | string | null | undefined} scheduledTime
 * @param {number} [nowMs]
 * @returns {string | null} skip reason, or null to dispatch
 */
export function mncPollerSkipReason(scheduledTime, nowMs = Date.now()) {
  if (isMncBeforeMonthlyWindow(scheduledTime, nowMs)) {
    return "before_monthly_window_day1_utc";
  }
  if (!isMncActiveDrainWindow(scheduledTime, nowMs)) {
    return "outside_active_drain_window";
  }
  return null;
}

/**
 * @param {ScheduledController} controller
 * @param {Record<string, string | undefined>} env
 * @param {typeof fetch} fetchImpl
 */
export async function handleScheduledCron(controller, env, fetchImpl = fetch) {
  const cron = controller.cron;
  const targets = resolveTargetsForCron(cron);
  if (!targets) {
    logEvent({ level: "error", event: "unknown_cron", cron });
    throw new Error(`unknown_cron:${cron}`);
  }

  const missing = missingRequiredEnv(env);
  if (missing.length > 0) {
    logEvent({ level: "error", event: "missing_env", missing, cron });
    throw new Error(`missing_env:${missing.join(",")}`);
  }

  /** @type {Array<Record<string, unknown>>} */
  const results = [];

  for (const target of targets) {
    if (!isMonthlyDispatchEnabled(env, target.workflowId)) {
      logEvent({
        level: "info",
        event: "monthly_dispatch_skipped",
        cron,
        workflowId: target.workflowId,
        reason: "MONTHLY_DISPATCH_ENABLED_not_true",
      });
      results.push({ workflowId: target.workflowId, ok: true, skipped: true });
      continue;
    }

    if (!isMncDispatchEnabled(env, target.workflowId)) {
      logEvent({
        level: "info",
        event: "mnc_dispatch_skipped",
        cron,
        workflowId: target.workflowId,
        reason: "MNC_DISPATCH_ENABLED_not_true",
      });
      results.push({ workflowId: target.workflowId, ok: true, skipped: true });
      continue;
    }

    if (target.workflowId === MNC_DISPATCH_WORKFLOW_FILE) {
      const skipReason = mncPollerSkipReason(controller.scheduledTime);
      if (skipReason) {
        logEvent({
          level: "info",
          event: "mnc_dispatch_skipped",
          cron,
          workflowId: target.workflowId,
          reason: skipReason,
          scheduledTime: controller.scheduledTime ?? null,
        });
        results.push({ workflowId: target.workflowId, ok: true, skipped: true });
        continue;
      }
    }

    let inputs = target.inputs ?? {};
    if (target.workflowId === DAILY_WORKFLOW_FILE) {
      inputs = mergeDailyInputs(env, inputs);
    }

    const result = await dispatchWorkflow({
      fetchImpl,
      env,
      workflowId: target.workflowId,
      inputs,
    });

    logEvent({
      level: result.ok ? "info" : "error",
      event: "dispatch",
      cron,
      workflowId: target.workflowId,
      ok: result.ok,
      dryRun: result.dryRun ?? false,
      status: result.status,
      error: result.error,
      missing: result.missing,
      githubStatus: result.status,
    });

    results.push({ workflowId: target.workflowId, ...result });
  }

  const allOk = results.every((r) => r.ok);
  if (!allOk) {
    const failed = results
      .filter((r) => !r.ok)
      .map((r) => ({ workflowId: r.workflowId, error: r.error, status: r.status }));
    logEvent({ level: "error", event: "dispatch_failed", cron, failed });
    throw new Error(`dispatch_failed:${JSON.stringify(failed)}`);
  }

  return { ok: true, cron, results };
}

export default {
  async scheduled(controller, env, _ctx) {
    logEvent({
      level: "info",
      event: "scheduled_start",
      cron: controller.cron,
      scheduledTime: controller.scheduledTime ?? null,
    });
    try {
      // Await the dispatch. waitUntil-only returns success before GitHub POST
      // settles and hides dispatch_failed from Cron Events.
      return await handleScheduledCron(controller, env);
    } catch (err) {
      logEvent({
        level: "error",
        event: "scheduled_failed",
        cron: controller.cron,
        message: err instanceof Error ? err.message : String(err),
      });
      throw err;
    }
  },

  async fetch(_request, _env, _ctx) {
    return new Response("ok", { status: 200 });
  },
};
