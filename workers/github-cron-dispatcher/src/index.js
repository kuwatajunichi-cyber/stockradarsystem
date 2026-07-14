import { DAILY_WORKFLOW_FILE, MONTHLY_WORKFLOW_FILE, ROUTING_TABLE } from "./constants.js";
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
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      handleScheduledCron(controller, env).catch((err) => {
        logEvent({
          level: "error",
          event: "scheduled_failed",
          cron: controller.cron,
          message: err instanceof Error ? err.message : String(err),
        });
        throw err;
      }),
    );
  },

  async fetch(_request, _env, _ctx) {
    return new Response("ok", { status: 200 });
  },
};
