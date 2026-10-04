import { COPY_TEMPORARY, COPY_UNAVAILABLE, corsHeaders, handlePreflight } from "./cors.js";
import { verifyAccessToken } from "./jwt.js";
import { mintGet, TTL_DEFAULT_SECONDS } from "./mint.js";
import { deliveryBucketIsPublic, headObject, presignGetObject } from "./r2.js";

function json(body, status, extra) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...(extra || {}),
    },
  });
}

function bearer(request) {
  const h = request.headers.get("Authorization") || "";
  const m = /^Bearer\s+(.+)$/i.exec(h);
  return m ? m[1].trim() : "";
}

async function sb(env, path, init) {
  const url = String(env.SUPABASE_URL || "").replace(/\/$/, "") + path;
  const key = String(env.SUPABASE_SECRET_KEY || "").trim();
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    ...(init && init.headers ? init.headers : {}),
  };
  return fetch(url, { ...(init || {}), headers });
}

async function activeMetricSetId(env) {
  const res = await sb(
    env,
    "/rest/v1/active_metric_set?pointer_key=eq.default&select=metric_set_version_id&limit=1",
  );
  if (!res.ok) throw new Error("active_metric_set");
  const rows = await res.json();
  const id = rows && rows[0] ? String(rows[0].metric_set_version_id || "").trim() : "";
  if (!id) throw new Error("active_metric_set");
  return id;
}

async function loadEntitlement(env, uid) {
  const res = await sb(
    env,
    `/rest/v1/entitlements?user_id=eq.${encodeURIComponent(uid)}&select=user_id,role,status,email`,
  );
  if (!res.ok) throw new Error("entitlements");
  const rows = await res.json();
  return rows[0] || null;
}

function proofFromEntitlement(row) {
  if (!row) return "unproven";
  if (row.status === "revoked") return "denied";
  if (row.status === "proven" && (row.role === "operator" || row.role === "internal_beta")) {
    return "proven";
  }
  return "unproven";
}

function makeAudit(env, actorRef) {
  return {
    async getByRequestId(requestId) {
      const res = await sb(
        env,
        `/rest/v1/download_grants?request_id=eq.${encodeURIComponent(requestId)}&select=*`,
      );
      if (!res.ok) throw new Error("grants read");
      return res.json();
    },
    async insert(row) {
      const res = await sb(env, "/rest/v1/download_grants", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify(row),
      });
      if (!res.ok) throw new Error("grants insert");
      const rows = await res.json();
      return rows[0] || row;
    },
    async updateIssued(grantId, fields) {
      const res = await sb(
        env,
        `/rest/v1/download_grants?id=eq.${encodeURIComponent(grantId)}`,
        {
          method: "PATCH",
          headers: { Prefer: "return=representation" },
          body: JSON.stringify({
            expires_at_utc: fields.expires_at_utc,
            ttl_seconds: fields.ttl_seconds,
            sha256: fields.sha256,
            object_key: fields.object_key,
            source_table: fields.source_table,
            source_id: fields.source_id,
            mint_result: "issued",
            reason_code: null,
          }),
        },
      );
      if (!res.ok) throw new Error("grants update");
      const rows = await res.json();
      return rows[0];
    },
    actorRef,
  };
}

function makeR2(env) {
  return {
    deliveryBucketIsPublic() {
      return deliveryBucketIsPublic(env);
    },
    headObject(objectKey) {
      return headObject(env, objectKey);
    },
    presignGetObject(objectKey, ttlSeconds) {
      return presignGetObject(env, objectKey, ttlSeconds);
    },
  };
}

async function requireSession(request, env) {
  const token = bearer(request);
  if (!token) {
    const err = new Error("unauthenticated");
    err.status = 401;
    throw err;
  }
  try {
    const claims = await verifyAccessToken(token, env);
    const ent = await loadEntitlement(env, claims.sub);
    const proof = proofFromEntitlement(ent);
    return { claims, ent, proof, uid: claims.sub };
  } catch (e) {
    if (e.status) throw e;
    const err = new Error("unauthenticated");
    err.status = 401;
    throw err;
  }
}

function requireProven(session) {
  if (session.proof === "proven") return;
  const err = new Error("unavailable");
  err.status = 403;
  err.copy = "unavailable";
  throw err;
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(env.STATIC_ORIGIN, origin);
    if (request.method === "OPTIONS") return handlePreflight(cors);
    const url = new URL(request.url);
    try {
      if (url.pathname === "/v1/session" && request.method === "POST") {
        const session = await requireSession(request, env);
        if (session.proof !== "proven") {
          return json(
            { ok: false, copy: "unavailable", message: COPY_UNAVAILABLE },
            403,
            cors,
          );
        }
        return json(
          {
            ok: true,
            uid: session.uid,
            role: session.ent.role,
            status: session.ent.status,
          },
          200,
          cors,
        );
      }
      if (url.pathname === "/v1/dates" && request.method === "GET") {
        const session = await requireSession(request, env);
        requireProven(session);
        const setId = await activeMetricSetId(env);
        const res = await sb(
          env,
          "/rest/v1/derived_object_index?object_kind=eq.web_asof_bundle&status=eq.committed" +
            `&metric_set_version_id=eq.${encodeURIComponent(setId)}` +
            "&select=trade_date,benchmark&order=trade_date.desc",
        );
        if (!res.ok) throw new Error("dates");
        const rows = await res.json();
        const dates = [...new Set(rows.map((r) => r.trade_date).filter(Boolean))];
        return json({ ok: true, dates, default: dates[0] || null }, 200, cors);
      }
      if (url.pathname === "/v1/mint" && request.method === "POST") {
        const session = await requireSession(request, env);
        requireProven(session);
        const body = await request.json().catch(() => ({}));
        const asOf = String(body.as_of || "").trim();
        const bench = String(body.benchmark || "").trim().toLowerCase();
        if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf) || (bench !== "topix" && bench !== "nikkei")) {
          return json(
            { ok: false, copy: "unavailable", message: COPY_UNAVAILABLE, reason_code: "identity_mismatch" },
            403,
            cors,
          );
        }
        const setId = await activeMetricSetId(env);
        const q =
          "/rest/v1/derived_object_index?object_kind=eq.web_asof_bundle&status=eq.committed" +
          `&metric_set_version_id=eq.${encodeURIComponent(setId)}` +
          `&benchmark=eq.${encodeURIComponent(bench)}&trade_date=eq.${encodeURIComponent(asOf)}` +
          "&select=id,object_key,byte_sha256,size_bytes,status&order=committed_at_utc.desc&limit=1";
        const found = await sb(env, q);
        if (!found.ok) throw new Error("resolve");
        const rows = await found.json();
        const row = rows[0];
        if (!row) {
          return json(
            { ok: false, copy: "temporary", message: COPY_TEMPORARY, reason_code: "not_committed" },
            404,
            cors,
          );
        }
        const requestId = crypto.randomUUID();
        const out = await mintGet(
          {
            request_id: requestId,
            actor_ref: session.uid,
            operation: "GetObject",
            object_key: row.object_key,
            source_table: "derived_object_index",
            source_id: row.id,
            ttl_seconds: TTL_DEFAULT_SECONDS,
          },
          {
            entitlement: { prove() { return session.proof; } },
            resolver: {
              resolve() {
                return {
                  object_key: row.object_key,
                  source_table: "derived_object_index",
                  source_id: row.id,
                  status: row.status,
                  sha256: row.byte_sha256,
                  size_bytes: row.size_bytes,
                };
              },
            },
            audit: makeAudit(env, session.uid),
            r2: makeR2(env),
          },
        );
        if (out.exit_code !== 0) {
          const unavailable = ["entitlement_unproven", "entitlement_denied", "identity_mismatch"].includes(
            out.reason_code,
          );
          return json(
            {
              ok: false,
              copy: unavailable ? "unavailable" : "temporary",
              message: unavailable ? COPY_UNAVAILABLE : COPY_TEMPORARY,
              reason_code: out.reason_code,
            },
            unavailable ? 403 : 409,
            cors,
          );
        }
        return json(
          {
            ok: true,
            grant_id: out.grant_id,
            expires_at_utc: out.expires_at_utc,
            signed_url: out.signed_url,
          },
          200,
          cors,
        );
      }
      if (url.pathname === "/v1/preferences" && request.method === "GET") {
        const session = await requireSession(request, env);
        requireProven(session);
        const res = await sb(
          env,
          `/rest/v1/user_preferences?user_id=eq.${encodeURIComponent(session.uid)}&select=schema_version,bag,updated_at_utc`,
        );
        if (!res.ok) throw new Error("prefs");
        const rows = await res.json();
        const row = rows[0] || { schema_version: 1, bag: {} };
        return json({ ok: true, schema_version: row.schema_version, bag: row.bag || {} }, 200, cors);
      }
      if (url.pathname === "/v1/preferences" && request.method === "PATCH") {
        const session = await requireSession(request, env);
        requireProven(session);
        const body = await request.json().catch(() => ({}));
        const patch = body.bag && typeof body.bag === "object" ? body.bag : {};
        const blob = JSON.stringify(patch);
        if (blob.toLowerCase().includes("signed_url") || blob.includes("object_key")) {
          return json({ ok: false, copy: "unavailable", message: COPY_UNAVAILABLE }, 403, cors);
        }
        const currentRes = await sb(
          env,
          `/rest/v1/user_preferences?user_id=eq.${encodeURIComponent(session.uid)}&select=schema_version,bag`,
        );
        const currentRows = currentRes.ok ? await currentRes.json() : [];
        const current = currentRows[0] || { schema_version: 1, bag: {} };
        const merged = { ...(current.bag || {}) };
        for (const [ns, value] of Object.entries(patch)) {
          if (value && typeof value === "object" && !Array.isArray(value) && merged[ns] && typeof merged[ns] === "object") {
            merged[ns] = { ...merged[ns], ...value };
          } else {
            merged[ns] = value;
          }
        }
        if (new TextEncoder().encode(JSON.stringify(merged)).length > 65536) {
          return json({ ok: false, copy: "unavailable", message: COPY_UNAVAILABLE }, 413, cors);
        }
        const upsert = await sb(
          env,
          "/rest/v1/user_preferences?on_conflict=user_id",
          {
          method: "POST",
          headers: { Prefer: "resolution=merge-duplicates,return=representation" },
          body: JSON.stringify({
            user_id: session.uid,
            schema_version: current.schema_version || 1,
            bag: merged,
            updated_at_utc: new Date().toISOString(),
          }),
        });
        if (!upsert.ok) throw new Error("prefs write");
        const saved = (await upsert.json())[0] || { bag: merged, schema_version: 1 };
        return json({ ok: true, schema_version: saved.schema_version, bag: saved.bag }, 200, cors);
      }
      return json({ ok: false, copy: "temporary", message: COPY_TEMPORARY }, 404, cors);
    } catch (err) {
      if (err && err.status === 401) {
        return json({ ok: false, copy: "login" }, 401, cors);
      }
      if (err && err.status === 403) {
        return json({ ok: false, copy: "unavailable", message: COPY_UNAVAILABLE }, 403, cors);
      }
      return json({ ok: false, copy: "temporary", message: COPY_TEMPORARY }, 503, cors);
    }
  },
};
