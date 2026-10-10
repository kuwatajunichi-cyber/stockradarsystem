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

function revealLoginForm() {
  hideBootProgress();
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
  $("login-shell").hidden = false;
  $("app-root").hidden = true;
  $("t5-temporary").hidden = false;
  $("t5-login").hidden = true;
  $("form").hidden = true;
  $("msg").textContent = text || COPY.temporary;
}

function showUnavailable(text) {
  hideBootProgress();
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
  showBootProgress("データを読み込んでいます", 0.4);
  if (typeof window.__webUiBoot === "function") {
    await window.__webUiBoot();
  }
  hideBootProgress();
  $("app-root").hidden = false;
}

async function boot() {
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
    return;
  }
  revealLoginForm();
}

boot();
