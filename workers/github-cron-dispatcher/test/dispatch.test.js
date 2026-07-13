import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { DAILY_CRON, DAILY_WORKFLOW_FILE, MONTHLY_CRON, MONTHLY_WORKFLOW_FILE, UNIVERSE_PATCH_CRON, UNIVERSE_PATCH_WORKFLOW_FILE, ROUTING_TABLE } from "../src/constants.js";
import {
  buildDispatchBody,
  buildDispatchUrl,
  dispatchWorkflow,
  missingRequiredEnv,
  resolveDailyInputsFromEnv,
} from "../src/dispatch.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const workerRoot = join(__dirname, "..");

const mock204 = () => ({ status: 204, ok: true, text: async () => "" });

describe("constants and wrangler cron alignment", () => {
  it("cron constants match wrangler.toml triggers.crons", () => {
    const wrangler = readFileSync(join(workerRoot, "wrangler.toml"), "utf8");
    assert.match(
      wrangler,
      /crons\s*=\s*\["45 6 \* \* \*", "0 3 \* \* \*", "0 2 1 \* \*"\]/,
    );
  });

  it("routing table registers daily, patch, and monthly workflows", () => {
    assert.deepEqual(ROUTING_TABLE[DAILY_CRON], [{ workflowId: DAILY_WORKFLOW_FILE, inputs: {} }]);
    assert.deepEqual(ROUTING_TABLE[UNIVERSE_PATCH_CRON], [
      { workflowId: UNIVERSE_PATCH_WORKFLOW_FILE, inputs: {} },
    ]);
    assert.deepEqual(ROUTING_TABLE[MONTHLY_CRON], [{ workflowId: MONTHLY_WORKFLOW_FILE, inputs: {} }]);
    assert.equal(Object.keys(ROUTING_TABLE).length, 3);
  });
});

describe("buildDispatchUrl", () => {
  it("builds GitHub workflow dispatch endpoint", () => {
    const url = buildDispatchUrl("owner", "repo", "daily.yml");
    assert.equal(
      url,
      "https://api.github.com/repos/owner/repo/actions/workflows/daily.yml/dispatches",
    );
  });
});

describe("buildDispatchBody", () => {
  it("omits inputs when empty (schedule-equivalent dispatch)", () => {
    assert.deepEqual(buildDispatchBody("main", {}), { ref: "main" });
  });

  it("includes inputs when provided", () => {
    assert.deepEqual(buildDispatchBody("main", { skip_publish: "true" }), {
      ref: "main",
      inputs: { skip_publish: "true" },
    });
  });
});

describe("resolveDailyInputsFromEnv", () => {
  it("returns empty by default", () => {
    assert.deepEqual(resolveDailyInputsFromEnv({}), {});
  });

  it("maps optional env overrides", () => {
    assert.deepEqual(
      resolveDailyInputsFromEnv({
        DISPATCH_SKIP_PUBLISH: "true",
        DISPATCH_FORCE_INDEX: "true",
      }),
      { skip_publish: "true", force_index: "true" },
    );
  });
});

describe("missingRequiredEnv", () => {
  it("lists missing keys", () => {
    assert.deepEqual(missingRequiredEnv({}), [
      "GH_DISPATCH_TOKEN",
      "GITHUB_OWNER",
      "GITHUB_REPO",
      "GITHUB_REF",
    ]);
  });
});

describe("dispatchWorkflow", () => {
  const baseEnv = {
    GH_DISPATCH_TOKEN: "secret-token-value",
    GITHUB_OWNER: "owner",
    GITHUB_REPO: "repo",
    GITHUB_REF: "main",
  };

  it("fail-fast without calling GitHub when env is incomplete", async () => {
    let called = false;
    const result = await dispatchWorkflow({
      fetchImpl: async () => {
        called = true;
        return mock204();
      },
      env: { GITHUB_OWNER: "owner" },
      workflowId: DAILY_WORKFLOW_FILE,
    });
    assert.equal(result.ok, false);
    assert.equal(result.error, "missing_env");
    assert.equal(called, false);
  });

  it("POSTs to workflow_dispatch with empty inputs by default", async () => {
    let capturedInit;
    let capturedUrl = "";
    const result = await dispatchWorkflow({
      fetchImpl: async (url, init) => {
        capturedUrl = String(url);
        capturedInit = init;
        return mock204();
      },
      env: baseEnv,
      workflowId: DAILY_WORKFLOW_FILE,
      inputs: {},
    });

    assert.equal(result.ok, true);
    assert.equal(capturedUrl, buildDispatchUrl("owner", "repo", DAILY_WORKFLOW_FILE));
    assert.equal(capturedInit?.method, "POST");
    const headers = capturedInit?.headers;
    assert.equal(headers.Authorization, "Bearer secret-token-value");
    const body = JSON.parse(String(capturedInit?.body));
    assert.equal(body.ref, "main");
    assert.equal(body.inputs, undefined);
  });

  it("treats non-204 GitHub response as failure", async () => {
    const result = await dispatchWorkflow({
      fetchImpl: async () => ({ status: 422, ok: false, text: async () => "bad request" }),
      env: baseEnv,
      workflowId: DAILY_WORKFLOW_FILE,
    });
    assert.equal(result.ok, false);
    assert.equal(result.status, 422);
    assert.equal(result.body, "bad request");
  });

  it("does not leak token in error payload", async () => {
    const result = await dispatchWorkflow({
      fetchImpl: async () => ({ status: 500, ok: false, text: async () => "error" }),
      env: baseEnv,
      workflowId: DAILY_WORKFLOW_FILE,
    });
    const serialized = JSON.stringify(result);
    assert.doesNotMatch(serialized, /secret-token-value/);
  });

  it("supports DRY_RUN without network", async () => {
    let called = false;
    const result = await dispatchWorkflow({
      fetchImpl: async () => {
        called = true;
        return mock204();
      },
      env: { ...baseEnv, DRY_RUN: "true" },
      workflowId: DAILY_WORKFLOW_FILE,
    });
    assert.equal(result.ok, true);
    assert.equal(result.dryRun, true);
    assert.equal(called, false);
  });
});

describe("source static checks", () => {
  it("does not log GH_DISPATCH_TOKEN in dispatch module console calls", () => {
    const source = readFileSync(join(workerRoot, "src", "dispatch.js"), "utf8");
    assert.doesNotMatch(source, /console\.(log|error|warn)\([^)]*GH_DISPATCH_TOKEN/);
    assert.doesNotMatch(source, /console\.(log|error|warn)\([^)]*env\.GH_DISPATCH_TOKEN/);
  });
});
