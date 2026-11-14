const COPY = {
  login: "ログインしてください",
  unavailable: "利用できません",
  temporary: "一時的に利用できません",
  inbox: "メールを確認してください",
};

function $(id) {
  return document.getElementById(id);
}

function showBootProgress(label, ratio) {
  const root = $("boot-progress");
  const bar = $("boot-progress-bar");
  const lab = $("boot-progress-label");
  if (!root) return;
  root.hidden = false;
  root.setAttribute("aria-busy", "true");
  if (lab && label) lab.textContent = label;
  if (!bar) return;
  if (typeof ratio === "number" && Number.isFinite(ratio)) {
    const pct = Math.max(4, Math.min(100, Math.round(ratio * 100)));
    bar.indeterminate = false;
    bar.value = pct;
    bar.setAttribute("aria-valuenow", String(pct));
  } else {
    bar.indeterminate = true;
    bar.removeAttribute("aria-valuenow");
  }
}

function hideBootProgress() {
  const root = $("boot-progress");
  if (!root) return;
  root.hidden = true;
  root.setAttribute("aria-busy", "false");
}

window.__webUiProgress = {
  show: showBootProgress,
  hide: hideBootProgress,
};

let supabaseClient = null;
const ACCESS_TOKEN_REFRESH_MS = 330000;

function publishAccessToken(session) {
  if (!window.__WEB_UI_CTX || !session || !session.access_token) return;
  window.__WEB_UI_CTX.accessToken = session.access_token;
}

function accessTokenExpiresSoon(session, withinMs) {
  if (!session || !session.access_token || !session.expires_at) return true;
  return session.expires_at * 1000 - Date.now() <= withinMs;
}

window.__webUiFreshAccessToken = async function webUiFreshAccessToken(force) {
  if (!supabaseClient) return null;
  let session = null;
  try {
    const out = await supabaseClient.auth.getSession();
    session = out && out.data ? out.data.session : null;
  } catch (_err) {
    session = null;
  }
  if (force || accessTokenExpiresSoon(session, ACCESS_TOKEN_REFRESH_MS)) {
    try {
      const refreshed = await supabaseClient.auth.refreshSession();
      const next = refreshed && refreshed.data ? refreshed.data.session : null;
      if (next && next.access_token) session = next;
    } catch (_err) {
      /* keep a stored session that has not expired */
    }
  }
  if (!session || !session.access_token || accessTokenExpiresSoon(session, 0)) return null;
  publishAccessToken(session);
  return session.access_token;
};

window.__webUiLogout = async function webUiLogout() {
  try {
    if (supabaseClient) await supabaseClient.auth.signOut();
  } catch (_err) {
    /* still return to the login shell */
  }
  window.__WEB_UI_CTX = null;
  const app = $("app-root");
  if (app) app.hidden = true;
  revealLoginForm();
};

let loginCredentialGeneration = 0;

function setLoginCredentialArmed(armed) {
  const email = $("email");
  if (!email) return;
  const generation = ++loginCredentialGeneration;
  email.disabled = !armed;
  email.autocomplete = armed ? "username" : "off";
  email.name = armed ? "email" : "";
  if (armed) email.setAttribute("name", "email");
  else email.removeAttribute("name");
  const sync = () => {
    if (generation !== loginCredentialGeneration) return;
    const inner = email.shadowRoot && email.shadowRoot.querySelector("input");
    if (!inner) return;
    inner.disabled = !armed;
    inner.autocomplete = armed ? "username" : "off";
    inner.setAttribute("autocomplete", armed ? "username" : "off");
    if (armed) inner.setAttribute("name", "email");
    else inner.removeAttribute("name");
  };
  sync();
  const ready = email.updateComplete;
  if (ready && typeof ready.then === "function") ready.then(sync);
}

function revealLoginForm() {
  hideBootProgress();
  setLoginCredentialArmed(true);
  const shell = $("login-shell");
  const app = $("app-root");
  if (shell) shell.hidden = false;
  if (app) app.hidden = true;
  const form = $("form");
  if (form) form.hidden = false;
  const loginCopy = $("t5-login");
  const unavailableCopy = $("t5-unavailable");
  const temporaryCopy = $("t5-temporary");
  if (loginCopy) loginCopy.hidden = false;
  if (unavailableCopy) unavailableCopy.hidden = true;
  if (temporaryCopy) temporaryCopy.hidden = true;
}

function showTemporary(text) {
  hideBootProgress();
  setLoginCredentialArmed(false);
  $("login-shell").hidden = false;
  $("app-root").hidden = true;
  $("t5-temporary").hidden = false;
  $("t5-login").hidden = true;
  $("form").hidden = true;
  $("msg").textContent = text || COPY.temporary;
}

function showUnavailable(text) {
  hideBootProgress();
  setLoginCredentialArmed(false);
  $("login-shell").hidden = false;
  $("app-root").hidden = true;
  $("t5-unavailable").hidden = false;
  $("t5-login").hidden = true;
  $("form").hidden = true;
  $("msg").textContent = text || COPY.unavailable;
}

function bindLoginForm(supabase, cfg) {
  const form = $("form");
  if (!form || form.dataset.bound === "1") return;
  form.dataset.bound = "1";
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("msg").textContent = "";
    const emailEl = $("email");
    const email = String(emailEl && emailEl.value ? emailEl.value : "").trim();
    if (!email) return;
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

async function enterApp(cfg, session) {
  const token = session.access_token;
  showBootProgress("ログインを確認しています", 0.28);
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
    revealLoginForm();
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
  setLoginCredentialArmed(false);
  showBootProgress("データを読み込んでいます", 0.4);
  if (typeof window.__webUiBoot === "function") {
    await window.__webUiBoot();
  }
  hideBootProgress();
  $("app-root").hidden = false;
}

async function boot() {
  setLoginCredentialArmed(false);
  showBootProgress("設定を読み込んでいます", 0.08);
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
  showBootProgress("セッションを確認しています", 0.16);
  let supabase;
  try {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    supabase = createClient(cfg.supabaseUrl, cfg.supabasePublishableKey);
  } catch (_err) {
    showTemporary(COPY.temporary);
    return;
  }
  supabaseClient = supabase;
  bindLoginForm(supabase, cfg);
  let session = null;
  try {
    const out = await supabase.auth.getSession();
    session = out && out.data ? out.data.session : null;
  } catch (_err) {
    showTemporary(COPY.temporary);
    return;
  }
  if (session) {
    await enterApp(cfg, session);
  } else {
    revealLoginForm();
  }
  supabase.auth.onAuthStateChange((event, session) => {
    if (event === "SIGNED_OUT") {
      window.__WEB_UI_CTX = null;
      const app = $("app-root");
      if (app && !app.hidden) revealLoginForm();
      return;
    }
    publishAccessToken(session);
  });
}

boot();
