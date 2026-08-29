import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { handleScheduledCron, isMonthlyDispatchEnabled, isMncDispatchEnabled, resolveTargetsForCron } from "../src/index.js";
import {
  DAILY_CRON,
  DAILY_WORKFLOW_FILE,
  MONTHLY_CRON,
  MONTHLY_WORKFLOW_FILE,
  MNC_DISPATCH_CRON,
  MNC_DISPATCH_WORKFLOW_FILE,
  UNIVERSE_PATCH_CRON,
  UNIVERSE_PATCH_WORKFLOW_FILE,
} from "../src/constants.js";

describe("resolveTargetsForCron", () => {
  it("returns daily.yml for DAILY_CRON", () => {
    const targets = resolveTargetsForCron(DAILY_CRON);
    assert.deepEqual(targets, [{ workflowId: DAILY_WORKFLOW_FILE, inputs: {} }]);
  });

  it("returns daily_universe_patch.yml for UNIVERSE_PATCH_CRON", () => {
    const targets = resolveTargetsForCron(UNIVERSE_PATCH_CRON);
    assert.deepEqual(targets, [{ workflowId: UNIVERSE_PATCH_WORKFLOW_FILE, inputs: {} }]);
  });

  it("returns null for unknown cron", () => {
    assert.equal(resolveTargetsForCron("0 0 * * *"), null);
  });

  it("returns monthly.yml for MONTHLY_CRON", () => {
    const targets = resolveTargetsForCron(MONTHLY_CRON);
    assert.deepEqual(targets, [{ workflowId: MONTHLY_WORKFLOW_FILE, inputs: {} }]);
  });

  it("returns monthly_new_core_backfill_dispatch.yml for MNC_DISPATCH_CRON", () => {
    const targets = resolveTargetsForCron(MNC_DISPATCH_CRON);
    assert.deepEqual(targets, [{ workflowId: MNC_DISPATCH_WORKFLOW_FILE, inputs: {} }]);
  });
});

describe("scheduled handler source contract", () => {
  it("awaits handleScheduledCron instead of waitUntil-only", async () => {
    const { readFile } = await import("node:fs/promises");
    const source = await readFile(new URL("../src/index.js", import.meta.url), "utf8");
    assert.match(source, /await handleScheduledCron\(controller, env\)/);
    assert.doesNotMatch(source, /ctx\.waitUntil/);
  });
});

describe("isMonthlyDispatchEnabled", () => {
  it("defaults to false for monthly workflow", () => {
    assert.equal(isMonthlyDispatchEnabled({}, MONTHLY_WORKFLOW_FILE), false);
  });

  it("is true when MONTHLY_DISPATCH_ENABLED=true", () => {
    assert.equal(
      isMonthlyDispatchEnabled({ MONTHLY_DISPATCH_ENABLED: "true" }, MONTHLY_WORKFLOW_FILE),
      true,
    );
  });

  it("is always true for daily workflow", () => {
    assert.equal(isMonthlyDispatchEnabled({}, DAILY_WORKFLOW_FILE), true);
  });
});

describe("isMncDispatchEnabled", () => {
  it("defaults to false for poller workflow", () => {
    assert.equal(isMncDispatchEnabled({}, MNC_DISPATCH_WORKFLOW_FILE), false);
  });

  it("is true when MNC_DISPATCH_ENABLED=true", () => {
    assert.equal(
      isMncDispatchEnabled({ MNC_DISPATCH_ENABLED: "true" }, MNC_DISPATCH_WORKFLOW_FILE),
      true,
    );
  });

  it("is always true for daily workflow", () => {
    assert.equal(isMncDispatchEnabled({}, DAILY_WORKFLOW_FILE), true);
  });
});

describe("handleScheduledCron", () => {
  const env = {
    GH_DISPATCH_TOKEN: "token",
    GITHUB_OWNER: "owner",
    GITHUB_REPO: "repo",
    GITHUB_REF: "main",
  };

  it("throws on unknown cron without fetch", async () => {
    let called = false;
    await assert.rejects(
      () =>
        handleScheduledCron({ cron: "0 0 * * *" }, env, async () => {
          called = true;
          return { status: 204, ok: true, text: async () => "" };
        }),
      /unknown_cron:0 0 \* \* \*/,
    );
    assert.equal(called, false);
  });

  it("throws on missing env without fetch", async () => {
    let called = false;
    await assert.rejects(
      () =>
        handleScheduledCron({ cron: DAILY_CRON }, {}, async () => {
          called = true;
          return { status: 204, ok: true, text: async () => "" };
        }),
      /missing_env:/,
    );
    assert.equal(called, false);
  });

  it("throws when GitHub dispatch fails", async () => {
    await assert.rejects(
      () =>
        handleScheduledCron({ cron: DAILY_CRON }, env, async () => ({
          status: 422,
          ok: false,
          text: async () => "bad request",
        })),
      /dispatch_failed:/,
    );
  });

  it("dispatches daily.yml on DAILY_CRON", async () => {
    let capturedUrl = "";
    const result = await handleScheduledCron({ cron: DAILY_CRON }, env, async (url) => {
      capturedUrl = String(url);
      return { status: 204, ok: true, text: async () => "" };
    });
    assert.equal(result.ok, true);
    assert.match(capturedUrl, /daily\.yml/);
  });

  it("dispatches daily_universe_patch.yml on UNIVERSE_PATCH_CRON", async () => {
    let capturedUrl = "";
    const result = await handleScheduledCron({ cron: UNIVERSE_PATCH_CRON }, env, async (url) => {
      capturedUrl = String(url);
      return { status: 204, ok: true, text: async () => "" };
    });
    assert.equal(result.ok, true);
    assert.match(capturedUrl, /daily_universe_patch\.yml/);
  });

  it("skips monthly dispatch when gate is false", async () => {
    let called = false;
    const result = await handleScheduledCron({ cron: MONTHLY_CRON }, env, async () => {
      called = true;
      return { status: 204, ok: true, text: async () => "" };
    });
    assert.equal(result.ok, true);
    assert.equal(called, false);
  });

  it("dispatches monthly.yml when gate is true", async () => {
    let capturedUrl = "";
    const result = await handleScheduledCron(
      { cron: MONTHLY_CRON },
      { ...env, MONTHLY_DISPATCH_ENABLED: "true" },
      async (url) => {
        capturedUrl = String(url);
        return { status: 204, ok: true, text: async () => "" };
      },
    );
    assert.equal(result.ok, true);
    assert.match(capturedUrl, /monthly\.yml/);
  });

  it("skips mnc poller dispatch when MNC_DISPATCH_ENABLED is false", async () => {
    let called = false;
    const result = await handleScheduledCron({ cron: MNC_DISPATCH_CRON }, env, async () => {
      called = true;
      return { status: 204, ok: true, text: async () => "" };
    });
    assert.equal(result.ok, true);
    assert.equal(called, false);
  });

  it("dispatches mnc poller when MNC_DISPATCH_ENABLED=true", async () => {
    let capturedUrl = "";
    const result = await handleScheduledCron(
      { cron: MNC_DISPATCH_CRON },
      { ...env, MNC_DISPATCH_ENABLED: "true" },
      async (url) => {
        capturedUrl = String(url);
        return { status: 204, ok: true, text: async () => "" };
      },
    );
    assert.equal(result.ok, true);
    assert.match(capturedUrl, /monthly_new_core_backfill_dispatch\.yml/);
  });
});
