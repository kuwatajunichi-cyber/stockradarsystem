import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { handleScheduledCron, resolveTargetsForCron } from "../src/index.js";
import { DAILY_CRON, DAILY_WORKFLOW_FILE } from "../src/constants.js";

describe("resolveTargetsForCron", () => {
  it("returns daily.yml for DAILY_CRON", () => {
    const targets = resolveTargetsForCron(DAILY_CRON);
    assert.deepEqual(targets, [{ workflowId: DAILY_WORKFLOW_FILE, inputs: {} }]);
  });

  it("returns null for unknown cron", () => {
    assert.equal(resolveTargetsForCron("0 0 * * *"), null);
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
});
