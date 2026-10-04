function b64urlToBytes(s) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function decodeJsonPart(part) {
  const bytes = b64urlToBytes(part);
  return JSON.parse(new TextDecoder().decode(bytes));
}

function jwkToCryptoKey(jwk) {
  return crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["verify"],
  );
}

export async function verifyAccessToken(token, env) {
  const raw = String(token || "").trim();
  if (!raw) throw new Error("missing token");
  const parts = raw.split(".");
  if (parts.length !== 3) throw new Error("bad jwt");
  const header = decodeJsonPart(parts[0]);
  const payload = decodeJsonPart(parts[1]);
  const issExpected = String(env.SUPABASE_URL || "").replace(/\/$/, "") + "/auth/v1";
  if (payload.iss !== issExpected) throw new Error("iss");
  const aud = payload.aud;
  const audOk = aud === "authenticated" || aud === env.SUPABASE_URL ||
    (Array.isArray(aud) && aud.includes("authenticated"));
  if (!audOk) throw new Error("aud");
  const now = Math.floor(Date.now() / 1000);
  if (typeof payload.exp !== "number" || payload.exp < now) throw new Error("exp");
  if (typeof payload.nbf === "number" && payload.nbf > now) throw new Error("nbf");
  if (!payload.sub) throw new Error("sub");
  if (header.alg !== "ES256") throw new Error("alg");
  const jwksUrl = issExpected + "/.well-known/jwks.json";
  let res;
  try {
    res = await fetch(jwksUrl, { headers: { apikey: env.SUPABASE_PUBLISHABLE_KEY || "" } });
  } catch {
    const err = new Error("jwks");
    err.status = 503;
    throw err;
  }
  if (!res.ok) {
    const err = new Error("jwks");
    err.status = 503;
    throw err;
  }
  const jwks = await res.json();
  if (!header.kid) throw new Error("kid");
  const jwk = (jwks.keys || []).find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("kid");
  const key = await jwkToCryptoKey(jwk);
  const data = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const sig = b64urlToBytes(parts[2]);
  const ok = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, sig, data);
  if (!ok) throw new Error("sig");
  return payload;
}
