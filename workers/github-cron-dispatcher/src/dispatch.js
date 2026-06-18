/**
 * GitHub Actions workflow_dispatch client (pure helpers + dispatch).
 */

const REQUIRED_ENV = ["GH_DISPATCH_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_REF"];

/**
 * @param {Record<string, string | undefined>} env
 * @returns {string[]}
 */
export function missingRequiredEnv(env) {
  return REQUIRED_ENV.filter((key) => {
    const value = env[key];
    return typeof value !== "string" || value.trim() === "";
  });
}

/**
 * @param {string} owner
 * @param {string} repo
 * @param {string} workflowId
 */
export function buildDispatchUrl(owner, repo, workflowId) {
  const encoded = encodeURIComponent(workflowId);
  return `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${encoded}/dispatches`;
}

/**
 * @param {string} ref
 * @param {Record<string, string>} [inputs]
 */
export function buildDispatchBody(ref, inputs) {
  /** @type {{ ref: string, inputs?: Record<string, string> }} */
  const body = { ref };
  if (inputs && Object.keys(inputs).length > 0) {
    body.inputs = inputs;
  }
  return body;
}

/**
 * Merge optional env overrides into daily dispatch inputs.
 * Normal cron path does NOT pass run_date (schedule-equivalent: is_replay=false).
 *
 * @param {Record<string, string | undefined>} env
 * @returns {Record<string, string>}
 */
export function resolveDailyInputsFromEnv(env) {
  /** @type {Record<string, string>} */
  const inputs = {};
  if (env.DISPATCH_SKIP_PUBLISH === "true") {
    inputs.skip_publish = "true";
  }
  if (env.DISPATCH_FORCE_INDEX === "true") {
    inputs.force_index = "true";
  }
  return inputs;
}

/**
 * @param {Record<string, string | undefined>} env
 * @param {Record<string, string>} baseInputs
 */
export function mergeDailyInputs(env, baseInputs) {
  return { ...baseInputs, ...resolveDailyInputsFromEnv(env) };
}

/**
 * @param {object} params
 * @param {typeof fetch} params.fetchImpl
 * @param {Record<string, string | undefined>} params.env
 * @param {string} params.workflowId
 * @param {Record<string, string>} [params.inputs]
 */
export async function dispatchWorkflow({ fetchImpl, env, workflowId, inputs = {} }) {
  const missing = missingRequiredEnv(env);
  if (missing.length > 0) {
    return {
      ok: false,
      error: "missing_env",
      missing,
    };
  }

  if (env.DRY_RUN === "true") {
    return {
      ok: true,
      dryRun: true,
      workflowId,
      ref: env.GITHUB_REF,
      inputs,
    };
  }

  const url = buildDispatchUrl(env.GITHUB_OWNER, env.GITHUB_REPO, workflowId);
  const body = buildDispatchBody(env.GITHUB_REF, inputs);

  const response = await fetchImpl(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      "User-Agent": "stockradar-github-cron-dispatcher",
    },
    body: JSON.stringify(body),
  });

  if (response.status !== 204) {
    const responseBody = await response.text();
    return {
      ok: false,
      error: "github_dispatch_failed",
      status: response.status,
      body: responseBody,
    };
  }

  return {
    ok: true,
    status: 204,
    workflowId,
    ref: env.GITHUB_REF,
    inputs,
  };
}

/**
 * Structured log object (never include token values).
 *
 * @param {Record<string, unknown>} fields
 */
export function logEvent(fields) {
  console.log(JSON.stringify({ source: "github-cron-dispatcher", ...fields }));
}
