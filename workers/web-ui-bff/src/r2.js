function hmacHex(key, data) {
  return crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
    .then((cryptoKey) => crypto.subtle.sign("HMAC", cryptoKey, data))
    .then((buf) => new Uint8Array(buf));
}

async function hmac(key, text) {
  return hmacHex(typeof key === "string" ? new TextEncoder().encode(key) : key, new TextEncoder().encode(text));
}

function toHex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return toHex(new Uint8Array(buf));
}

function amzDate(d) {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

export function s3Endpoint(env) {
  const account = String(env.R2_ACCOUNT_ID || "").trim();
  const fromEnv = String(env.R2_ENDPOINT_URL || "").trim();
  if (fromEnv.includes("r2.cloudflarestorage.com")) {
    return fromEnv.replace(/\/$/, "");
  }
  return `https://${account}.r2.cloudflarestorage.com`;
}

function physicalKey(env, objectKey) {
  const prefix = String(env.R2_BASE_PREFIX || "").replace(/^\/+|\/+$/g, "");
  const key = String(objectKey || "").replace(/^\/+/, "");
  return prefix ? `${prefix}/${key}` : key;
}

export function deliveryBucketIsPublic(env) {
  const flag = String(env.R2_PUBLIC_BUCKET || "").trim().toLowerCase();
  return !["0", "false", "no"].includes(flag);
}

async function signingKey(secret, dateStamp) {
  let k = await hmac(`AWS4${secret}`, dateStamp);
  k = await hmac(k, "auto");
  k = await hmac(k, "s3");
  return hmac(k, "aws4_request");
}

async function signS3(env, method, objectKey, { expires, queryOnly }) {
  const access = String(env.R2_ACCESS_KEY_ID || "").trim();
  const secret = String(env.R2_SECRET_ACCESS_KEY || "").trim();
  const bucket = String(env.R2_BUCKET || "").trim();
  const host = new URL(s3Endpoint(env)).host;
  const keyPath = `${bucket}/${physicalKey(env, objectKey)}`.split("/").map(encodeURIComponent).join("/");
  const now = new Date();
  const dateStamp = amzDate(now).slice(0, 8);
  const amz = amzDate(now);
  const credential = `${access}/${dateStamp}/auto/s3/aws4_request`;
  const params = new URLSearchParams();
  params.set("X-Amz-Algorithm", "AWS4-HMAC-SHA256");
  params.set("X-Amz-Credential", credential);
  params.set("X-Amz-Date", amz);
  params.set("X-Amz-Expires", String(expires));
  params.set("X-Amz-SignedHeaders", "host");
  const canonicalQuery = [...params.entries()]
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .sort()
    .join("&");
  const canonical = [
    method,
    `/${keyPath}`,
    canonicalQuery,
    `host:${host}\n`,
    "host",
    "UNSIGNED-PAYLOAD",
  ].join("\n");
  const canonicalHash = await sha256Hex(canonical);
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amz,
    `${dateStamp}/auto/s3/aws4_request`,
    canonicalHash,
  ].join("\n");
  const kSign = await signingKey(secret, dateStamp);
  const sigBuf = await hmacHex(kSign, new TextEncoder().encode(stringToSign));
  const signature = toHex(sigBuf);
  params.set("X-Amz-Signature", signature);
  const query = [...params.entries()]
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .sort()
    .join("&");
  return `${s3Endpoint(env)}/${keyPath}?${query}`;
}

export async function presignGetObject(env, objectKey, ttlSeconds) {
  return signS3(env, "GET", objectKey, { expires: ttlSeconds, queryOnly: true });
}

export async function headObject(env, objectKey) {
  const access = String(env.R2_ACCESS_KEY_ID || "").trim();
  const secret = String(env.R2_SECRET_ACCESS_KEY || "").trim();
  const bucket = String(env.R2_BUCKET || "").trim();
  const host = new URL(s3Endpoint(env)).host;
  const keyPath = `${bucket}/${physicalKey(env, objectKey)}`.split("/").map(encodeURIComponent).join("/");
  const now = new Date();
  const amz = amzDate(now);
  const dateStamp = amz.slice(0, 8);
  const payloadHash = "UNSIGNED-PAYLOAD";
  const canonical = [
    "HEAD",
    `/${keyPath}`,
    "",
    `host:${host}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amz}\n`,
    "host;x-amz-content-sha256;x-amz-date",
    payloadHash,
  ].join("\n");
  const canonicalHash = await sha256Hex(canonical);
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amz,
    `${dateStamp}/auto/s3/aws4_request`,
    canonicalHash,
  ].join("\n");
  const kSign = await signingKey(secret, dateStamp);
  const sig = toHex(await hmacHex(kSign, new TextEncoder().encode(stringToSign)));
  const auth = `AWS4-HMAC-SHA256 Credential=${access}/${dateStamp}/auto/s3/aws4_request, SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=${sig}`;
  const url = `${s3Endpoint(env)}/${keyPath}`;
  const res = await fetch(url, {
    method: "HEAD",
    headers: {
      Authorization: auth,
      "x-amz-content-sha256": payloadHash,
      "x-amz-date": amz,
    },
  });
  if (res.status === 404) {
    const err = new Error("missing");
    err.name = "NotFound";
    throw err;
  }
  if (!res.ok) throw new Error(`R2 HEAD ${res.status}`);
  const size = Number(res.headers.get("content-length") || "0");
  const metaSha = (
    res.headers.get("x-amz-meta-byte_sha256") ||
    res.headers.get("x-amz-meta-byte-sha256") ||
    ""
  ).trim().toLowerCase();
  return { size_bytes: size, byte_sha256: metaSha || null };
}
