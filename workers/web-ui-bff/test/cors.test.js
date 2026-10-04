import assert from "node:assert/strict";
import test from "node:test";
import { corsHeaders, handlePreflight } from "../src/cors.js";

const STATIC = "https://web-ui-static.stockradarsystem.workers.dev";

test("cors allowlists exact static origin only", () => {
  const ok = corsHeaders(STATIC, STATIC);
  assert.equal(ok["Access-Control-Allow-Origin"], STATIC);
  assert.equal(ok["Access-Control-Allow-Headers"], "Authorization, Content-Type");
  assert.equal(ok["Access-Control-Allow-Methods"], "GET, POST, PATCH, OPTIONS");
  assert.equal(ok.Vary, "Origin");
  const bad = corsHeaders(STATIC, "https://evil.example");
  assert.equal(bad["Access-Control-Allow-Origin"], undefined);
  const pre = handlePreflight(ok);
  assert.equal(pre.status, 204);
});
