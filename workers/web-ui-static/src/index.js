/** Static UI Worker. Serves assets plus public Auth/BFF config. */
const TEMPORARY_COPY = "\u4e00\u6642\u7684\u306b\u5229\u7528\u3067\u304d\u307e\u305b\u3093";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/config.json") {
      const supabaseUrl = String(env.SUPABASE_URL || "").trim();
      const publishable = String(
        env.SUPABASE_PUBLISHABLE_KEY || env.SUPABASE_ANON_KEY || "",
      ).trim();
      const bffOrigin = String(env.BFF_ORIGIN || "").replace(/\/$/, "");
      if (!supabaseUrl.startsWith("https://") || !publishable || !bffOrigin.startsWith("https://")) {
        return json({ ok: false, copy: "temporary", message: TEMPORARY_COPY }, 503);
      }
      return json({
        ok: true,
        supabaseUrl,
        supabasePublishableKey: publishable,
        emailRedirectTo: url.origin + "/",
        bffOrigin,
      });
    }
    return env.ASSETS.fetch(request);
  },
};
