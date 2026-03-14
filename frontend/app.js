"use strict";

// ── Auth state ───────────────────────────────────────────────────────────────
let auth0Client = null;
let accessToken = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const loginScreen      = document.getElementById("login-screen");
const loginBtn         = document.getElementById("login-btn");
const loginError       = document.getElementById("login-error");
const registerOverlay  = document.getElementById("register-overlay");
const registerForm     = document.getElementById("register-form");
const registerError    = document.getElementById("register-error");
const appShell         = document.getElementById("app");
const userLabel        = document.getElementById("user-label");
const logoutBtn        = document.getElementById("logout-btn");

// ── Auth0 bootstrap ──────────────────────────────────────────────────────────
async function initAuth() {
  loginBtn.disabled = true;
  loginBtn.textContent = "Loading…";

  const cfg = await fetch("/auth/config").then(r => r.json());

  if (!cfg.domain || !cfg.client_id) {
    throw new Error("AUTH0_DOMAIN or AUTH0_CLIENT_ID not configured on the server.");
  }

  auth0Client = await window.auth0.createAuth0Client({
    domain:              cfg.domain,
    clientId:            cfg.client_id,
    authorizationParams: {
      redirect_uri: window.location.origin,
      audience:     cfg.audience,
    },
    cacheLocation: "localstorage",
  });

  if (window.location.search.includes("code=") && window.location.search.includes("state=")) {
    try {
      await auth0Client.handleRedirectCallback();
    } catch (e) {
      showLoginError(`Auth0 callback error: ${e.message}`);
      return;
    }
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  loginBtn.disabled = false;
  loginBtn.textContent = "Sign in";

  if (await auth0Client.isAuthenticated()) {
    await onAuthenticated();
  } else {
    showLoginScreen();
  }
}

function showLoginScreen() {
  loginScreen.hidden = false;
  appShell.hidden    = true;
}

function showLoginError(msg) {
  loginError.textContent = msg;
  loginError.hidden = false;
}

async function onAuthenticated() {
  accessToken = await auth0Client.getTokenSilently();
  const user  = await auth0Client.getUser();

  const meRes = await fetch("/workspaces/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (meRes.ok) {
    await meRes.json();
    showApp(user);
  } else if (meRes.status === 401) {
    showRegisterModal(user);
  } else {
    showLoginError(`Unexpected server error (${meRes.status}). Please try again.`);
  }
}

function showApp(auth0User) {
  loginScreen.hidden     = true;
  registerOverlay.hidden = true;
  appShell.hidden        = false;

  userLabel.textContent = auth0User.name || auth0User.email || "";
  checkHealth();
}

function showRegisterModal(auth0User) {
  loginScreen.hidden     = true;
  registerOverlay.hidden = false;

  const displayNameInput = document.getElementById("display-name");
  if (auth0User.name && auth0User.name !== auth0User.email) {
    displayNameInput.value = auth0User.name;
  }
}

// ── Login button ─────────────────────────────────────────────────────────────
loginBtn.addEventListener("click", async () => {
  if (!auth0Client) {
    showLoginError("Auth not ready yet — please wait a moment and try again.");
    return;
  }
  loginError.hidden = true;
  loginBtn.disabled = true;
  try {
    await auth0Client.loginWithRedirect();
  } catch (e) {
    showLoginError(`Sign-in failed: ${e.message}`);
    loginBtn.disabled = false;
  }
});

// ── Logout button ────────────────────────────────────────────────────────────
logoutBtn.addEventListener("click", () => {
  auth0Client.logout({ logoutParams: { returnTo: window.location.origin } });
});

// ── Registration form ────────────────────────────────────────────────────────
registerForm.addEventListener("submit", async e => {
  e.preventDefault();
  registerError.classList.remove("visible");
  const registerBtn = document.getElementById("register-btn");
  registerBtn.disabled = true;

  const user          = await auth0Client.getUser();
  const workspaceName = document.getElementById("workspace-name").value.trim();
  const displayName   = document.getElementById("display-name").value.trim();

  try {
    const res = await fetch("/auth/register", {
      method:  "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({
        email:          user.email,
        display_name:   displayName,
        workspace_name: workspaceName,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    await fetch("/workspaces/me", { headers: { Authorization: `Bearer ${accessToken}` } });
    showApp(user);
  } catch (err) {
    registerError.textContent = err.message;
    registerError.classList.add("visible");
    registerBtn.disabled = false;
  }
});

// ── Tab switching ────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn, .panel").forEach(el => el.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById(btn.dataset.tab);
    panel.classList.add("active");

    // Load dashboard data when the tab is first opened
    if (btn.dataset.tab === "panel-dashboard") {
      loadDashboard();
    }
  });
});

// ── Health check ─────────────────────────────────────────────────────────────
const healthDot = document.getElementById("health-dot");

async function checkHealth() {
  try {
    const res = await fetch("/workspaces/me", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) throw new Error("non-OK");
    const data = await res.json();
    const ok = data.jira_configured;
    healthDot.className = "health-dot " + (ok ? "ok" : "fail");
    healthDot.title = ok ? `Jira: ${data.jira_base_url} (${data.jira_project_key})` : "Jira: not configured";
    healthDot.textContent = ok ? "Jira connected" : "Jira not configured";
  } catch {
    healthDot.className = "health-dot fail";
    healthDot.textContent = "API unreachable";
  }
}

// ── Shared result rendering ──────────────────────────────────────────────────
const resultsSection = document.getElementById("results");
const storyGrid      = document.getElementById("story-grid");

function renderStories(stories) {
  storyGrid.innerHTML = "";
  resultsSection.hidden = stories.length === 0;

  stories.forEach((s) => {
    const card = document.createElement("article");
    card.className = `story-card ${s.priority || ""}`;

    const jiraBadge = s.jira_key
      ? `<a class="badge badge-jira" href="${s.jira_url}" target="_blank" rel="noopener">${s.jira_key}</a>`
      : "";

    const acItems = (s.acceptance_criteria || [])
      .map(ac => `<li>${escHtml(ac)}</li>`)
      .join("");

    const explanation = s.priority_explanation
      ? `<div class="story-meta">Priority rationale: ${escHtml(s.priority_explanation)}</div>`
      : "";

    const issueType = s.issue_type || "Story";
    card.innerHTML = `
      <div class="story-header">
        <div class="story-title">${escHtml(s.title)}</div>
        <div class="badges">
          <span class="badge badge-type-${issueType}">${issueType}</span>
          <span class="badge badge-priority-${s.priority}">${s.priority}</span>
          <span class="badge badge-points">${s.story_points} pts</span>
          ${jiraBadge}
        </div>
      </div>
      <div class="story-text">${escHtml(s.story)}</div>
      <ul class="ac-list">${acItems}</ul>
      ${explanation}
      ${buildQusSection(s.qus_scores)}
    `;

    storyGrid.appendChild(card);
  });
}

function buildQusSection(qus) {
  if (!qus) return "";
  const pct = Math.round((qus.overall_qus ?? 0) * 100);
  const cls = pct >= 75 ? "qus-good" : pct >= 50 ? "qus-ok" : "qus-low";
  const criteria = [
    ["Well-formed", qus.well_formed],
    ["Atomic",      qus.atomic],
    ["Minimal",     qus.minimal],
    ["Complete",    qus.complete],
    ["Testable",    qus.testable],
    ["Estimable",   qus.estimable],
  ];
  const bars = criteria.map(([label, score]) => {
    const p = Math.round((score ?? 0) * 100);
    const c = p >= 75 ? "qus-good" : p >= 50 ? "qus-ok" : "qus-low";
    return `
      <div class="qus-criterion">
        <span class="qus-crit-label">${label}</span>
        <div class="qus-bar-track"><div class="qus-bar-fill ${c}" style="width:${p}%"></div></div>
        <span class="qus-crit-score">${p}%</span>
      </div>`;
  }).join("");
  return `
    <div class="qus-section">
      <div class="qus-header">
        <span class="qus-label">QUS Quality</span>
        <span class="qus-score ${cls}">${pct}%</span>
      </div>
      <div class="qus-criteria">${bars}</div>
    </div>`;
}

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Error / loader helpers ───────────────────────────────────────────────────
function showError(boxEl, msg) {
  boxEl.textContent = msg;
  boxEl.classList.add("visible");
}
function hideError(boxEl)     { boxEl.classList.remove("visible"); }
function showLoader(loaderEl) { loaderEl.classList.add("visible"); }
function hideLoader(loaderEl) { loaderEl.classList.remove("visible"); }

// ── POST helper (attaches Bearer token) ─────────────────────────────────────
async function submitToApi(url, body, isFormData = false) {
  const opts = {
    method:  "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  };
  if (isFormData) {
    opts.body = body;
  } else {
    opts.body = JSON.stringify(body);
    opts.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function getFromApi(url) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ────────────────────────────────────────────────────────────────────────────
// TEXT PANEL
// ────────────────────────────────────────────────────────────────────────────
const textForm   = document.getElementById("text-form");
const textArea   = document.getElementById("transcript");
const ctxText    = document.getElementById("ctx-text");
const textLoader = document.getElementById("text-loader");
const textError  = document.getElementById("text-error");
const textSubmit = document.getElementById("text-submit");

textForm.addEventListener("submit", async e => {
  e.preventDefault();
  hideError(textError);
  showLoader(textLoader);
  textSubmit.disabled = true;

  try {
    const data = await submitToApi("/stories/from-text", {
      transcript:      textArea.value.trim(),
      project_context: ctxText.value.trim() || "Software development project",
    });
    renderStories(data.stories);
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showError(textError, err.message);
  } finally {
    hideLoader(textLoader);
    textSubmit.disabled = false;
  }
});

// ────────────────────────────────────────────────────────────────────────────
// AUDIO PANEL
// ────────────────────────────────────────────────────────────────────────────
const recordBtn   = document.getElementById("record-btn");
const stopBtn     = document.getElementById("stop-btn");
const submitAudio = document.getElementById("submit-audio");
const micRing     = document.getElementById("mic-ring");
const recStatus   = document.getElementById("rec-status");
const recTimer    = document.getElementById("rec-timer");
const ctxAudio    = document.getElementById("ctx-audio");
const audioLoader = document.getElementById("audio-loader");
const audioError  = document.getElementById("audio-error");

let mediaRecorder  = null;
let recordedChunks = [];
let timerInterval  = null;
let elapsedSeconds = 0;
let audioBlob      = null;

function formatTime(s) {
  const m   = Math.floor(s / 60).toString().padStart(2, "0");
  const sec = (s % 60).toString().padStart(2, "0");
  return `${m}:${sec}`;
}

recordBtn.addEventListener("click", async () => {
  hideError(audioError);
  audioBlob = null;
  submitAudio.disabled = true;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"]
      .find(t => MediaRecorder.isTypeSupported(t)) || "";

    mediaRecorder  = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    recordedChunks = [];

    mediaRecorder.addEventListener("dataavailable", e => {
      if (e.data.size > 0) recordedChunks.push(e.data);
    });

    mediaRecorder.addEventListener("stop", () => {
      stream.getTracks().forEach(t => t.stop());
      audioBlob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      recStatus.textContent = `Recording ready (${(audioBlob.size / 1024).toFixed(0)} KB). Click Submit to process.`;
      submitAudio.disabled  = false;
    });

    mediaRecorder.start();
    micRing.classList.add("recording");
    recordBtn.disabled = true;
    stopBtn.disabled   = false;
    recTimer.classList.add("visible");
    elapsedSeconds = 0;
    recTimer.textContent = formatTime(0);
    timerInterval = setInterval(() => {
      elapsedSeconds++;
      recTimer.textContent = formatTime(elapsedSeconds);
    }, 1000);
    recStatus.textContent = "Recording…";

  } catch (err) {
    showError(audioError, `Microphone access denied: ${err.message}`);
  }
});

stopBtn.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  clearInterval(timerInterval);
  micRing.classList.remove("recording");
  recordBtn.disabled = false;
  stopBtn.disabled   = true;
  recTimer.classList.remove("visible");
  recStatus.textContent = "Processing recording…";
});

submitAudio.addEventListener("click", async () => {
  if (!audioBlob) return;
  hideError(audioError);
  showLoader(audioLoader);
  submitAudio.disabled = true;

  const ext  = (audioBlob.type.split("/")[1] || "webm").split(";")[0];
  const file = new File([audioBlob], `recording.${ext}`, { type: audioBlob.type });

  const form = new FormData();
  form.append("file", file);
  form.append("project_context", ctxAudio.value.trim() || "Software development project");

  try {
    const data = await submitToApi("/stories/from-audio", form, true);
    renderStories(data.stories);
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showError(audioError, err.message);
  } finally {
    hideLoader(audioLoader);
    submitAudio.disabled = false;
  }
});

// ────────────────────────────────────────────────────────────────────────────
// DASHBOARD
// ────────────────────────────────────────────────────────────────────────────
const dashLoader   = document.getElementById("dash-loader");
const dashContent  = document.getElementById("dash-content");
let dashLoaded     = false;
let storiesPage    = 0;
const storiesLimit = 20;

async function loadDashboard(forceReload = false) {
  if (dashLoaded && !forceReload) return;

  dashLoader.classList.add("visible");
  dashContent.hidden = true;

  try {
    const stats = await getFromApi("/dashboard/stats");
    renderStats(stats);
    renderIssuesBanner(stats.issues_to_watch || []);
    renderPriorityChart(stats.by_priority);
    renderRecentSessions(stats.recent_sessions || []);
  } catch (err) {
    console.error("Dashboard stats failed:", err);
  }

  await loadStoriesTable(0);

  dashLoader.classList.remove("visible");
  dashContent.hidden = false;
  dashLoaded = true;
}

// ── Stats cards ──────────────────────────────────────────────────────────────
function renderStats(stats) {
  const grid = document.getElementById("stats-grid");
  const pct  = stats.total_stories > 0
    ? Math.round((stats.jira_linked / stats.total_stories) * 100)
    : 0;

  const qusCls = stats.avg_qus != null
    ? (stats.avg_qus >= 75 ? "stat-qus-good" : stats.avg_qus >= 50 ? "stat-qus-ok" : "stat-qus-low")
    : "";
  const qusStatCard = stats.avg_qus != null ? `
    <div class="stat-card">
      <div class="stat-value ${qusCls}">${stats.avg_qus}%</div>
      <div class="stat-label">Avg QUS Quality</div>
    </div>` : "";

  grid.innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${stats.total_stories}</div>
      <div class="stat-label">Stories Generated</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.total_sessions}</div>
      <div class="stat-label">Sessions</div>
    </div>
    <div class="stat-card stat-high">
      <div class="stat-value">${stats.by_priority.High ?? 0}</div>
      <div class="stat-label">High Priority</div>
    </div>
    <div class="stat-card stat-medium">
      <div class="stat-value">${stats.by_priority.Medium ?? 0}</div>
      <div class="stat-label">Medium Priority</div>
    </div>
    <div class="stat-card stat-low">
      <div class="stat-value">${stats.by_priority.Low ?? 0}</div>
      <div class="stat-label">Low Priority</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.jira_linked}</div>
      <div class="stat-label">Jira Linked (${pct}%)</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.avg_story_points}</div>
      <div class="stat-label">Avg Story Points</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.by_source.audio ?? 0}</div>
      <div class="stat-label">Audio Sessions</div>
    </div>
    ${qusStatCard}
  `;
}

// ── Issues banner ────────────────────────────────────────────────────────────
function renderIssuesBanner(issues) {
  const banner = document.getElementById("issues-banner");
  const list   = document.getElementById("issues-list");
  const title  = document.getElementById("issues-title");

  if (!issues.length) {
    banner.hidden = true;
    return;
  }

  title.textContent = `${issues.length} High Priority Issue${issues.length > 1 ? "s" : ""} to Watch`;
  list.innerHTML = issues.map(s => `
    <div class="issue-row">
      <span class="issue-title">${escHtml(s.title)}</span>
      <div class="issue-meta">
        ${s.project_context ? `<span class="issue-ctx">${escHtml(s.project_context)}</span>` : ""}
        ${s.jira_key ? `<a class="badge badge-jira" href="${escHtml(s.jira_url)}" target="_blank" rel="noopener">${escHtml(s.jira_key)}</a>` : ""}
        <span class="issue-date">${fmtDate(s.created_at)}</span>
      </div>
    </div>
  `).join("");
  banner.hidden = false;
}

// ── Priority bar chart (CSS-based) ───────────────────────────────────────────
function renderPriorityChart(byPriority) {
  const container = document.getElementById("priority-chart");
  const total = (byPriority.High || 0) + (byPriority.Medium || 0) + (byPriority.Low || 0);

  if (total === 0) {
    container.innerHTML = '<div class="dash-empty-inline">No stories yet.</div>';
    return;
  }

  const rows = [
    { label: "High",   count: byPriority.High   || 0, cls: "High" },
    { label: "Medium", count: byPriority.Medium || 0, cls: "Medium" },
    { label: "Low",    count: byPriority.Low    || 0, cls: "Low" },
  ];

  container.innerHTML = rows.map(r => {
    const pct = total > 0 ? Math.round((r.count / total) * 100) : 0;
    return `
      <div class="priority-bar">
        <span class="priority-bar-label">${r.label}</span>
        <div class="priority-bar-track">
          <div class="priority-bar-fill ${r.cls}" style="width:${pct}%"></div>
        </div>
        <span class="priority-bar-count">${r.count}</span>
        <span class="priority-bar-pct">${pct}%</span>
      </div>
    `;
  }).join("");
}

// ── Recent sessions ──────────────────────────────────────────────────────────
function renderRecentSessions(sessions) {
  const container = document.getElementById("recent-sessions");

  if (!sessions.length) {
    container.innerHTML = '<div class="dash-empty-inline">No sessions yet.</div>';
    return;
  }

  container.innerHTML = sessions.map(s => {
    const icon = s.source_type === "audio" ? "🎙️" : "📝";
    const pb   = s.priority_breakdown || {};
    const badges = ["High", "Medium", "Low"]
      .filter(p => pb[p])
      .map(p => `<span class="badge badge-priority-${p}">${pb[p]} ${p}</span>`)
      .join("");

    const label = s.source_type === "audio"
      ? (s.audio_filename || "Recording")
      : (s.project_context || "Transcript");

    return `
      <div class="session-row">
        <span class="session-icon">${icon}</span>
        <div class="session-body">
          <div class="session-label">${escHtml(label)}</div>
          <div class="session-footer">
            <span class="session-count">${s.story_count} stor${s.story_count === 1 ? "y" : "ies"}</span>
            ${badges}
            <span class="session-date">${fmtDate(s.created_at)}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

// ── Stories table ────────────────────────────────────────────────────────────
const filterPriority = document.getElementById("filter-priority");
const filterSource   = document.getElementById("filter-source");

filterPriority.addEventListener("change", () => loadStoriesTable(0));
filterSource.addEventListener("change",   () => loadStoriesTable(0));

async function loadStoriesTable(offset) {
  const tbody      = document.getElementById("stories-tbody");
  const emptyEl    = document.getElementById("stories-empty");
  const pagination = document.getElementById("stories-pagination");

  const priority   = filterPriority.value;
  const sourceType = filterSource.value;

  let url = `/dashboard/stories?limit=${storiesLimit}&offset=${offset}`;
  if (priority)   url += `&priority=${encodeURIComponent(priority)}`;
  if (sourceType) url += `&source_type=${encodeURIComponent(sourceType)}`;

  try {
    const data = await getFromApi(url);
    storiesPage = offset;

    if (!data.stories.length) {
      tbody.innerHTML = "";
      emptyEl.hidden  = false;
      pagination.innerHTML = "";
      return;
    }

    emptyEl.hidden = true;
    tbody.innerHTML = data.stories.map(s => {
      const jira = s.jira_key
        ? `<a class="badge badge-jira" href="${escHtml(s.jira_url)}" target="_blank" rel="noopener">${escHtml(s.jira_key)}</a>`
        : "—";
      const srcIcon  = s.source_type === "audio" ? "🎙️" : "📝";
      const issueType = s.issue_type || "Story";
      let qusCell = "—";
      if (s.qus_scores && s.qus_scores.overall_qus != null) {
        const pct = Math.round(s.qus_scores.overall_qus * 100);
        const cls = pct >= 75 ? "qus-good" : pct >= 50 ? "qus-ok" : "qus-low";
        qusCell = `<span class="qus-badge ${cls}">${pct}%</span>`;
      }
      return `
        <tr>
          <td class="td-title">${escHtml(s.title)}</td>
          <td><span class="badge badge-type-${issueType}">${issueType}</span></td>
          <td><span class="badge badge-priority-${s.priority}">${s.priority || "—"}</span></td>
          <td class="td-center"><span class="badge badge-points">${s.story_points ?? "—"}</span></td>
          <td class="td-center" title="${escHtml(s.source_type || "")}">${srcIcon}</td>
          <td>${jira}</td>
          <td class="td-center">${qusCell}</td>
          <td class="td-date">${fmtDate(s.created_at)}</td>
        </tr>
      `;
    }).join("");

    // Pagination
    const totalPages = Math.ceil(data.total / storiesLimit);
    const curPage    = Math.floor(offset / storiesLimit);
    if (totalPages <= 1) {
      pagination.innerHTML = "";
      return;
    }
    pagination.innerHTML = `
      <button class="btn btn-outline btn-sm" ${curPage === 0 ? "disabled" : ""}
        onclick="loadStoriesTable(${(curPage - 1) * storiesLimit})">← Prev</button>
      <span class="page-info">Page ${curPage + 1} of ${totalPages}</span>
      <button class="btn btn-outline btn-sm" ${curPage >= totalPages - 1 ? "disabled" : ""}
        onclick="loadStoriesTable(${(curPage + 1) * storiesLimit})">Next →</button>
    `;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="td-error">${escHtml(err.message)}</td></tr>`;
  }
}

// ── Date helper ──────────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// ── Kick off auth on page load ───────────────────────────────────────────────
initAuth().catch(err => {
  showLoginError(`Failed to initialise authentication: ${err.message}`);
});
