import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomUUID } from "node:crypto";
import test from "node:test";
import { FakeAudit, FakeResolver, mintGet } from "../src/mint.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const goldenPath = path.resolve(here, "../../../tests/fixtures/web_ui_bff/mint_golden.json");
const golden = JSON.parse(fs.readFileSync(goldenPath, "utf8"));
const NOW = new Date(golden.now);
const BODY = Buffer.from(golden.body_hex, "hex");
const SHA = createHash("sha256").update(BODY).digest("hex");

function refFrom(spec) {
  return {
    object_key: spec.object_key,
    source_table: spec.source_table,
    source_id: spec.source_id,
    status: spec.status,
    sha256: SHA,
    size_bytes: BODY.length,
  };
}

function makeR2(keys, headOverride) {
  const set = new Set(keys);
  return {
    deliveryBucketIsPublic() {
      return false;
    },
    headObject(objectKey) {
      if (!set.has(objectKey)) {
        const err = new Error("missing");
        err.name = "NotFound";
        throw err;
      }
      return {
        size_bytes: headOverride?.size_bytes ?? BODY.length,
        byte_sha256: headOverride?.byte_sha256 ?? SHA,
      };
    },
    presignGetObject(objectKey, ttl) {
      return `https://example.r2.cloudflarestorage.com/bucket/${objectKey}?X-Amz-Expires=${ttl}&X-Amz-Signature=fake`;
    },
  };
}

async function runCase(caseRow) {
  const committed = refFrom(golden.committed);
  const resolver = new FakeResolver([committed]);
  const keys = [committed.object_key];
  if (caseRow.extra_object) {
    resolver.add(refFrom(caseRow.extra_object));
    keys.push(caseRow.extra_object.object_key);
  }
  const audit = new FakeAudit();
  const ports = {
    entitlement: {
      prove() {
        return caseRow.proof || "unproven";
      },
    },
    resolver,
    audit,
    r2: makeR2(keys, caseRow.head_override),
    now: () => NOW,
    newId: () => randomUUID(),
  };
  let priorGrant = null;
  if (caseRow.setup === "issued") {
    const issued = golden.cases.find((c) => c.id === "issued");
    ports.entitlement = { prove() { return "proven"; } };
    const seed = await mintGet(issued.request, ports);
    assert.equal(seed.exit_code, 0);
    priorGrant = seed.grant_id;
    ports.entitlement = {
      prove() {
        return caseRow.proof || "proven";
      },
    };
  }
  const out = await mintGet(caseRow.request, ports);
  assert.equal(out.exit_code, caseRow.expect.exit_code, caseRow.id);
  assert.equal(out.mint_result, caseRow.expect.mint_result, caseRow.id);
  assert.equal(out.reason_code, caseRow.expect.reason_code, caseRow.id);
  if (out.mint_result === "issued") {
    assert.ok(out.signed_url.includes("r2.cloudflarestorage.com"));
  } else {
    assert.equal(out.signed_url, null);
  }
  if (caseRow.expect.same_grant) {
    assert.equal(out.grant_id, priorGrant);
  }
}

test("mint golden js matches fixture", async () => {
  for (const caseRow of golden.cases) {
    await runCase(caseRow);
  }
});
