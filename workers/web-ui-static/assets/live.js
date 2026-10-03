const COPY = {
  login: "ログインしてください",
  unavailable: "利用できません",
  temporary: "一時的に利用できません",
  inbox: "メールを確認してください",
};

function $(id) {
  return document.getElementById(id);
}

function showTemporary(text) {
  $("t5-temporary").hidden = false;
  $("t5-login").hidden = true;
  $("form").hidden = true;
  $("msg").textContent = text || COPY.temporary;
}

function showUnavailable(text) {
  $("t5-unavailable").hidden = false;
  $("t5-login").hidden = true;
  $("form").hidden = true;
  $("msg").textContent = text || COPY.unavailable;
}

async function enterApp(cfg, session) {
  const token = session.access_token;
  let res;
  try {
    res = await fetch(String(cfg.bffOrigin).replace(/\/$/, "") + "/v1/session", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    });
  } catch (_err) {
    showTemporary(COPY.temporary);
    return;
  }
  if (res.status === 401) {
    $("login-shell").hidden = false;
    $("app-root").hidden = true;
    $("msg").textContent = COPY.login;
    return;
  }
  if (res.status === 403) {
    showUnavailable(COPY.unavailable);
    return;
  }
  if (!res.ok) {
    showTemporary(COPY.temporary);
    return;
  }
  const body = await res.json();
  window.__WEB_UI_CTX = {
    bffOrigin: cfg.bffOrigin,
    accessToken: token,
    uid: body.uid,
    role: body.role,
  };
  $("login-shell").hidden = true;
  $("app-root").hidden = false;
  if (typeof window.__webUiBoot === "function") {
    await window.__webUiBoot();
  }
}

async function boot() {
  let cfg;
  try {
    const res = await fetch("/config.json", { cache: "no-store" });
    cfg = await res.json();
    if (!res.ok || !cfg.ok || !cfg.bffOrigin) {
      showTemporary((cfg && cfg.message) || COPY.temporary);
      return;
    }
  } catch (_err) {
    showTemporary(COPY.temporary);
    return;
  }
  const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
  const supabase = createClient(cfg.supabaseUrl, cfg.supabasePublishableKey);
  const { data } = await supabase.auth.getSession();
  if (data && data.session) {
    await enterApp(cfg, data.session);
    return;
  }
  $("form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("msg").textContent = "";
    const email = $("email").value.trim();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: cfg.emailRedirectTo || (window.location.origin + "/") },
    });
    if (error) {
      const status = String(error.status || "");
      if (status.startsWith("5") || error.message === "Failed to fetch") {
        showTemporary(COPY.temporary);
        return;
      }
      showUnavailable(COPY.unavailable);
      return;
    }
    $("msg").textContent = COPY.inbox;
  });
}

boot();
