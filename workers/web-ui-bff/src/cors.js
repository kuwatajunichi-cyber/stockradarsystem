export const COPY_UNAVAILABLE = "\u5229\u7528\u3067\u304d\u307e\u305b\u3093";
export const COPY_TEMPORARY = "\u4e00\u6642\u7684\u306b\u5229\u7528\u3067\u304d\u307e\u305b\u3093";

export function corsHeaders(staticOrigin, requestOrigin) {
  const allowed = String(staticOrigin || "").replace(/\/$/, "");
  const origin = String(requestOrigin || "");
  const headers = {
    Vary: "Origin",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "600",
  };
  if (allowed && origin === allowed) {
    headers["Access-Control-Allow-Origin"] = allowed;
  }
  return headers;
}

export function handlePreflight(headers) {
  return new Response(null, { status: 204, headers });
}
