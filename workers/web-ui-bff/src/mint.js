/** Fail-closed GetObject mint. Ports match stockradar.storage.signed_url. */

export const KNOWN_OBJECT_PREFIXES = [
  "published/",
  "runs/",
  "cache/",
  "monthly/",
  "derived-snapshots/",
  "derived-series/",
  "derived-inputs/",
  "derived-web-asof/",
  "0011_work/",
  "0012_paid/",
];

export const ALLOWED_SOURCE_TABLES = new Set([
  "artifact_index",
  "cache_index",
  "publish_status",
  "derived_object_index",
  "monthly_snapshots",
]);

export const TTL_DEFAULT_SECONDS = 300;
export const TTL_MIN_SECONDS = 60;
export const TTL_MAX_SECONDS = 3600;
export const OPERATION_GET_OBJECT = "GetObject";
export const MINT_ISSUED = "issued";
export const MINT_DENIED = "denied";

export const REASON_ENTITLEMENT_UNPROVEN = "entitlement_unproven";
export const REASON_ENTITLEMENT_DENIED = "entitlement_denied";
export const REASON_NOT_COMMITTED = "not_committed";
export const REASON_ORPHAN = "orphan";
export const REASON_OBJECT_MISSING = "object_missing";
export const REASON_IDENTITY_MISMATCH = "identity_mismatch";
export const REASON_CHECKSUM_MISMATCH = "checksum_mismatch";
export const REASON_PREFIX_REJECTED = "prefix_rejected";
export const REASON_TTL_INVALID = "ttl_invalid";
export const REASON_OPERATION_REJECTED = "operation_rejected";
export const REASON_PUBLIC_BUCKET_FORBIDDEN = "public_bucket_forbidden";
export const REASON_REQUEST_ID_CONFLICT = "request_id_conflict";

const REASONS = new Set([
  REASON_ENTITLEMENT_UNPROVEN,
  REASON_ENTITLEMENT_DENIED,
  REASON_NOT_COMMITTED,
  REASON_ORPHAN,
  REASON_OBJECT_MISSING,
  REASON_IDENTITY_MISMATCH,
  REASON_CHECKSUM_MISMATCH,
  REASON_PREFIX_REJECTED,
  REASON_TTL_INVALID,
  REASON_OPERATION_REJECTED,
  REASON_PUBLIC_BUCKET_FORBIDDEN,
  REASON_REQUEST_ID_CONFLICT,
]);

export function objectKeyPrefixOk(objectKey) {
  const key = String(objectKey || "").trim();
  if (!key || key.startsWith("/") || key.includes("..")) return false;
  return KNOWN_OBJECT_PREFIXES.some((p) => key.startsWith(p));
}

export function sourceTableAllowed(sourceTable) {
  const table = String(sourceTable || "").trim();
  if (!table) return true;
  return ALLOWED_SOURCE_TABLES.has(table);
}

export function normalizeTtl(ttlSeconds) {
  if (!Number.isInteger(ttlSeconds)) return REASON_TTL_INVALID;
  if (ttlSeconds < TTL_MIN_SECONDS || ttlSeconds > TTL_MAX_SECONDS) {
    return REASON_TTL_INVALID;
  }
  return null;
}

function iso(dt) {
  return new Date(dt).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export class FakeAudit {
  constructor() {
    this.rows = [];
  }
  getByRequestId(requestId) {
    const rid = String(requestId || "").trim();
    return this.rows.filter((r) => r.request_id === rid);
  }
  insert(row) {
    this.rows.push(row);
    return row;
  }
  updateIssued(grantId, fields) {
    const idx = this.rows.findIndex((r) => r.id === grantId);
    if (idx < 0) throw new Error("grant not found");
    const prev = this.rows[idx];
    const next = { ...prev, ...fields, mint_result: MINT_ISSUED, reason_code: null };
    this.rows[idx] = next;
    return next;
  }
}

export class FakeResolver {
  constructor(objects = []) {
    this.objects = objects;
  }
  add(ref) {
    this.objects.push(ref);
  }
  resolve({ object_key, source_table, source_id }) {
    const key = String(object_key || "").trim() || null;
    const table = String(source_table || "").trim() || null;
    const sid = String(source_id || "").trim() || null;
    if (table && !ALLOWED_SOURCE_TABLES.has(table)) return null;
    const hits = [];
    for (const ref of this.objects) {
      if (key && ref.object_key !== key) continue;
      if (table && ref.source_table !== table) continue;
      if (sid && ref.source_id !== sid) continue;
      if (key || (table && sid)) hits.push(ref);
    }
    if (!hits.length) return null;
    if (hits.length > 1) {
      const keys = new Set(hits.map((h) => h.object_key));
      const ids = new Set(hits.map((h) => `${h.source_table}:${h.source_id}`));
      if (keys.size > 1 || ids.size > 1) return null;
    }
    return hits[0];
  }
}

export async function mintGet(request, ports) {
  const now = ports.now ? ports.now() : new Date();
  const deny = (reason, objectKey, ref) =>
    _deny(request, ports.audit, now, reason, objectKey, ref);

  const requestId = String(request.request_id || "").trim();
  const actorRef = String(request.actor_ref || "").trim();
  if (!requestId || !actorRef) {
    return await deny(REASON_IDENTITY_MISMATCH, String(request.object_key || "").trim() || null);
  }
  const operation = String(request.operation || "").trim();
  if (operation !== OPERATION_GET_OBJECT) {
    return await deny(REASON_OPERATION_REJECTED, String(request.object_key || "").trim() || null);
  }
  const ttlReason = normalizeTtl(request.ttl_seconds);
  if (ttlReason) {
    return await deny(ttlReason, String(request.object_key || "").trim() || null);
  }

  const objectKeyIn = String(request.object_key || "").trim() || null;
  const sourceTable = String(request.source_table || "").trim() || null;
  const sourceId = String(request.source_id || "").trim() || null;
  if (objectKeyIn === null && !(sourceTable && sourceId)) {
    return await deny(REASON_IDENTITY_MISMATCH, null);
  }
  if ((sourceTable && !sourceId) || (sourceId && !sourceTable)) {
    return await deny(REASON_IDENTITY_MISMATCH, objectKeyIn);
  }
  if (!sourceTableAllowed(sourceTable)) {
    return await deny(REASON_IDENTITY_MISMATCH, objectKeyIn);
  }

  let ref;
  if (objectKeyIn && sourceTable && sourceId) {
    ref = ports.resolver.resolve({
      object_key: null,
      source_table: sourceTable,
      source_id: sourceId,
    });
    if (!ref) return await deny(REASON_NOT_COMMITTED, objectKeyIn);
    if (ref.object_key !== objectKeyIn) return await deny(REASON_IDENTITY_MISMATCH, objectKeyIn, ref);
  } else {
    ref = ports.resolver.resolve({
      object_key: objectKeyIn,
      source_table: sourceTable,
      source_id: sourceId,
    });
    if (!ref) return await deny(objectKeyIn ? REASON_ORPHAN : REASON_NOT_COMMITTED, objectKeyIn);
  }

  if (objectKeyIn && objectKeyIn !== ref.object_key) {
    return await deny(REASON_IDENTITY_MISMATCH, objectKeyIn, ref);
  }
  if (sourceTable && (sourceTable !== ref.source_table || (sourceId && sourceId !== ref.source_id))) {
    return await deny(REASON_IDENTITY_MISMATCH, objectKeyIn || ref.object_key, ref);
  }

  const resolvedKey = ref.object_key;
  const status = String(ref.status || "").trim();
  if (status === "orphan") return await deny(REASON_ORPHAN, resolvedKey, ref);
  if (status !== "committed") return await deny(REASON_NOT_COMMITTED, resolvedKey, ref);
  if (!objectKeyPrefixOk(resolvedKey)) return await deny(REASON_PREFIX_REJECTED, resolvedKey, ref);

  const existingRaw = await ports.audit.getByRequestId(requestId);
  const existing = Array.isArray(existingRaw) ? existingRaw : [];
  const issuedExisting = existing.filter((r) => r.mint_result === MINT_ISSUED);
  if (issuedExisting.some((r) => r.object_key !== resolvedKey)) {
    return await deny(REASON_REQUEST_ID_CONFLICT, resolvedKey, ref);
  }
  const refreshRow = issuedExisting[0] || null;

  let proof;
  try {
    proof = ports.entitlement.prove({ actor_ref: actorRef, object_key: resolvedKey });
  } catch {
    return await deny(REASON_ENTITLEMENT_UNPROVEN, resolvedKey, ref);
  }
  if (proof === "denied") return await deny(REASON_ENTITLEMENT_DENIED, resolvedKey, ref);
  if (proof !== "proven") return await deny(REASON_ENTITLEMENT_UNPROVEN, resolvedKey, ref);

  if (ports.r2.deliveryBucketIsPublic()) {
    return await deny(REASON_PUBLIC_BUCKET_FORBIDDEN, resolvedKey, ref);
  }

  let head;
  try {
    head = await ports.r2.headObject(resolvedKey);
  } catch (err) {
    if (err && err.name === "NotFound") return await deny(REASON_OBJECT_MISSING, resolvedKey, ref);
    throw err;
  }
  const headSize = head.size_bytes == null ? null : Number(head.size_bytes);
  const headSha = head.byte_sha256 ? String(head.byte_sha256).trim().toLowerCase() : null;
  if (ref.size_bytes != null && headSize != null && Number(ref.size_bytes) !== headSize) {
    return await deny(REASON_CHECKSUM_MISMATCH, resolvedKey, ref);
  }
  if (ref.sha256 && headSha && String(ref.sha256).trim().toLowerCase() !== headSha) {
    return await deny(REASON_CHECKSUM_MISMATCH, resolvedKey, ref);
  }

  const expires = new Date(now.getTime() + request.ttl_seconds * 1000);
  const expiresS = iso(expires);
  const signedUrl = await ports.r2.presignGetObject(resolvedKey, request.ttl_seconds);
  if (!signedUrl || signedUrl.includes(" ")) {
    throw new Error("presign returned empty URL");
  }
  if (!signedUrl.includes("r2.cloudflarestorage.com")) {
    throw new Error("presign host is not R2 S3 API domain");
  }
  const shaOut = ref.sha256 ? String(ref.sha256).trim() : headSha;
  let stored;
  if (refreshRow) {
    stored = await ports.audit.updateIssued(refreshRow.id, {
      expires_at_utc: expiresS,
      ttl_seconds: request.ttl_seconds,
      sha256: shaOut,
      object_key: resolvedKey,
      source_table: ref.source_table,
      source_id: ref.source_id,
    });
  } else {
    stored = await ports.audit.insert({
      id: ports.newId ? ports.newId() : crypto.randomUUID(),
      created_at_utc: iso(now),
      request_id: requestId,
      object_key: resolvedKey,
      source_table: ref.source_table,
      source_id: ref.source_id,
      sha256: shaOut,
      actor_ref: actorRef,
      operation: OPERATION_GET_OBJECT,
      ttl_seconds: request.ttl_seconds,
      expires_at_utc: expiresS,
      mint_result: MINT_ISSUED,
      reason_code: null,
    });
  }
  return {
    exit_code: 0,
    mint_result: MINT_ISSUED,
    reason_code: null,
    grant_id: stored.id,
    object_key: resolvedKey,
    expires_at_utc: expiresS,
    signed_url: signedUrl,
    request_id: requestId,
  };
}

async function _deny(request, audit, now, reason, objectKey, ref) {
  const code = REASONS.has(reason) ? reason : REASON_ENTITLEMENT_UNPROVEN;
  const requestId = String(request.request_id || "").trim() || "invalid";
  const actorRef = String(request.actor_ref || "").trim() || "invalid";
  const ttl = Number.isInteger(request.ttl_seconds) ? request.ttl_seconds : TTL_DEFAULT_SECONDS;
  const row = await audit.insert({
    id: crypto.randomUUID(),
    created_at_utc: iso(now),
    request_id: requestId,
    object_key: objectKey || "",
    source_table: ref ? ref.source_table : request.source_table,
    source_id: ref ? ref.source_id : request.source_id,
    sha256: ref ? ref.sha256 : null,
    actor_ref: actorRef,
    operation: request.operation || OPERATION_GET_OBJECT,
    ttl_seconds: ttl,
    expires_at_utc: null,
    mint_result: MINT_DENIED,
    reason_code: code,
  });
  return {
    exit_code: 1,
    mint_result: MINT_DENIED,
    reason_code: code,
    grant_id: row.id,
    object_key: objectKey,
    expires_at_utc: null,
    signed_url: null,
    request_id: requestId,
  };
}

export function publicOutcome(out) {
  return {
    exit_code: out.exit_code,
    mint_result: out.mint_result,
    reason_code: out.reason_code,
    grant_id: out.grant_id,
    object_key: out.object_key,
    expires_at_utc: out.expires_at_utc,
    request_id: out.request_id,
    signed_url_present: Boolean(out.signed_url),
  };
}
