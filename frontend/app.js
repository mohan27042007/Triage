const form = document.querySelector("#ingest-form");
const textInput = document.querySelector("#text");
const fileInput = document.querySelector("#file");
const result = document.querySelector("#result");
const error = document.querySelector("#error");
const button = form.querySelector("button");
const deadlineReminder = document.querySelector("#deadline-reminder");
const deadlineReminderText = document.querySelector("#deadline-reminder-text");
const deadlineReminderNavigate = document.querySelector("#deadline-reminder-navigate");
const deadlineReminderDismiss = document.querySelector("#deadline-reminder-dismiss");
const connectedSourcesList = document.querySelector("#connected-sources-list");
const queue = document.querySelector("#queue");
const refreshQueueButton = document.querySelector("#refresh-queue");
const studyForm = document.querySelector("#study-form");
const studyPlan = document.querySelector("#study-plan");
const studyError = document.querySelector("#study-error");
const pendingActions = document.querySelector("#pending-actions");
const approvalTrigger = document.querySelector("#approval-trigger");
const pendingCount = document.querySelector("#pending-count");
const approvalLayer = document.querySelector("#approval-layer");
const approvalDrawer = document.querySelector("#approval-drawer");
const assignmentForm = document.querySelector("#assignment-form");
const assignmentPrompt = document.querySelector("#assignment-prompt");
const assignmentError = document.querySelector("#assignment-error");
const assignmentResult = document.querySelector("#assignment-result");
const assignmentHistory = document.querySelector("#assignment-history");
const landingScreen = document.querySelector("#landing-screen");
const loginScreen = document.querySelector("#login-screen");
const loginForm = document.querySelector("#login-form");
const loginPassword = document.querySelector("#login-password");
const loginError = document.querySelector("#login-error");
const appShell = document.querySelector("#app-shell");
const railNodes = document.querySelectorAll(".rail-node");
const appSections = document.querySelectorAll(".app-section");
const panelScroller = document.querySelector(".panel-scroller");
const previousPanelButton = document.querySelector("#previous-panel");
const nextPanelButton = document.querySelector("#next-panel");
const backToLandingButton = document.querySelector("#back-to-landing");
const settingsFab = document.querySelector("#settings-fab");
const settingsMenu = document.querySelector("#settings-menu");
const settingsDrawer = document.querySelector("#settings-drawer");
const closeSettingsButton = document.querySelector("#close-settings");
const deadlineRemindersSetting = document.querySelector("#deadline-reminders-setting");
const reducedMotionSetting = document.querySelector("#reduced-motion-setting");
let wheelNavigationLocked = false;
let authToken = localStorage.getItem("triage-demo-token");
let drawerTrigger = null;
let deadlineReminderDismissed = false;
let deadlineRemindersEnabled = localStorage.getItem("triage-deadline-reminders") !== "false";
let currentUrgentItems = [];
const notifiedUrgentItemIds = new Set();
const notificationRequestStorageKey = "triage-reminder-notification-requested";
const apiBaseUrl = (window.TRIAGE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const connectedSourcesStorageKey = "triage-connected-sources";
const reconnectAfterDays = 30;
const sourceDefinitions = {
  gmail: { name: "Gmail", description: "Read recent inbox messages", endpoint: "/sources/gmail/sync", google: true },
  classroom: { name: "Google Classroom", description: "Read announcements and coursework", endpoint: "/sources/classroom/sync", google: true },
  whatsapp: { name: "WhatsApp", description: "Representative college-group messages only", endpoint: "/sources/whatsapp/demo-load", demo: true },
  slack: { name: "Slack", description: "Team messages and notices", comingSoon: true },
  teams: { name: "Microsoft Teams", description: "Course channels and updates", comingSoon: true },
};
let connectedSources = loadConnectedSources();
let googleAuthorized = false;
let syncingSource = null;

function apiUrl(path) {
  return `${apiBaseUrl}${path}`;
}

function showLoginScreen() {
  authToken = null;
  localStorage.removeItem("triage-demo-token");
  landingScreen.hidden = true;
  appShell.hidden = true;
  loginScreen.hidden = false;
  loginPassword.value = "";
}

function showLandingScreen() {
  authToken = null;
  localStorage.removeItem("triage-demo-token");
  landingScreen.hidden = false;
  loginScreen.hidden = true;
  appShell.hidden = true;
  closeSettingsDrawer();
}

function showApp() {
  landingScreen.hidden = true;
  loginScreen.hidden = true;
  appShell.hidden = false;
}

function closeSettingsDrawer() {
  settingsDrawer.classList.remove("is-open");
  settingsDrawer.setAttribute("aria-hidden", "true");
  settingsMenu.setAttribute("aria-hidden", "true");
  settingsFab.setAttribute("aria-expanded", "false");
  settingsMenu.classList.remove("is-open");
}

function openSettingsView(viewName) {
  document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.settingsPanel !== viewName;
  });
  settingsDrawer.setAttribute("aria-hidden", "false");
  settingsDrawer.classList.add("is-open");
  settingsMenu.setAttribute("aria-hidden", "true");
  settingsMenu.classList.remove("is-open");
  settingsFab.setAttribute("aria-expanded", "false");
}

function applyTheme(theme) {
  if (theme === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
  localStorage.setItem("triage-theme", theme);
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.themeChoice === theme);
  });
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) showLoginScreen();
  return response;
}

function loadAppData() {
  loadQueue();
  loadStudyPlan();
  loadPendingActions();
  loadAssignmentHistory();
  loadConnectedSourcesPanel();
}

function openApprovalDrawer(trigger = approvalTrigger) {
  drawerTrigger = trigger;
  approvalLayer.classList.add("is-open");
  approvalLayer.setAttribute("aria-hidden", "false");
  approvalTrigger.classList.add("is-open");
  approvalTrigger.setAttribute("aria-expanded", "true");
  approvalTrigger.setAttribute("aria-label", "Close Human Review drawer");
  const firstAction = approvalDrawer.querySelector("button:not([disabled])");
  (firstAction || approvalDrawer).focus();
}

function closeApprovalDrawer() {
  approvalLayer.classList.remove("is-open");
  approvalLayer.setAttribute("aria-hidden", "true");
  approvalTrigger.classList.remove("is-open");
  approvalTrigger.setAttribute("aria-expanded", "false");
  approvalTrigger.setAttribute(
    "aria-label",
    `Human Review, ${pendingCount.textContent} pending action${pendingCount.textContent === "1" ? "" : "s"}`,
  );
  if (drawerTrigger?.isConnected) {
    drawerTrigger.focus();
  } else {
    approvalTrigger.focus();
  }
}

function updatePendingIndicator(count) {
  pendingCount.textContent = String(count);
  if (!approvalLayer.classList.contains("is-open")) {
    approvalTrigger.setAttribute(
      "aria-label",
      `Human Review, ${count} pending action${count === 1 ? "" : "s"}`,
    );
  }
  approvalTrigger.classList.toggle("has-pending", count > 0);
}

approvalTrigger.addEventListener("click", () => {
  if (approvalLayer.classList.contains("is-open")) {
    closeApprovalDrawer();
  } else {
    openApprovalDrawer();
  }
});
approvalLayer.querySelector(".approval-scrim").addEventListener("click", closeApprovalDrawer);

document.addEventListener("keydown", (event) => {
  if (!approvalLayer.classList.contains("is-open")) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeApprovalDrawer();
    return;
  }
  if (event.key !== "Tab") return;

  const focusable = approvalDrawer.querySelectorAll(
    "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
  );
  const elements = [...focusable];
  const first = elements[0];
  const last = elements.at(-1);
  if (!first || !last) return;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const submitButton = loginForm.querySelector("button");
  submitButton.disabled = true;
  submitButton.textContent = "Opening…";
  try {
    const response = await fetch(apiUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: loginPassword.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not sign in.");
    authToken = data.token;
    localStorage.setItem("triage-demo-token", authToken);
    showApp();
    loadAppData();
  } catch (requestError) {
    loginError.textContent = requestError.message;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Open Triage";
  }
});

document.querySelectorAll("[data-open-login]").forEach((button) => {
  button.addEventListener("click", showLoginScreen);
});
function scrollLandingTo(sectionId) {
  const target = landingScreen.querySelector(`#${sectionId}`);
  const nav = landingScreen.querySelector(".landing-nav");
  if (!target || landingScreen.hidden) return;

  const targetTop = target.getBoundingClientRect().top;
  const landingTop = landingScreen.getBoundingClientRect().top;
  const navHeight = nav?.getBoundingClientRect().height || 0;
  landingScreen.scrollTo({
    top: landingScreen.scrollTop + targetTop - landingTop - navHeight - 20,
    behavior: "smooth",
  });
}

document.querySelectorAll("[data-scroll-to]").forEach((button) => {
  button.addEventListener("click", () => scrollLandingTo(button.dataset.scrollTo));
});
backToLandingButton.addEventListener("click", showLandingScreen);

settingsFab.addEventListener("click", () => {
  const open = !settingsMenu.classList.contains("is-open");
  settingsMenu.classList.toggle("is-open", open);
  settingsMenu.setAttribute("aria-hidden", String(!open));
  settingsFab.setAttribute("aria-expanded", String(open));
});
document.querySelectorAll("[data-settings-view]").forEach((button) => button.addEventListener("click", () => openSettingsView(button.dataset.settingsView)));
closeSettingsButton.addEventListener("click", () => {
  settingsDrawer.setAttribute("aria-hidden", "true");
  settingsDrawer.classList.remove("is-open");
});
document.querySelectorAll("[data-theme-choice]").forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeChoice)));
deadlineRemindersSetting.checked = deadlineRemindersEnabled;
deadlineRemindersSetting.addEventListener("change", () => {
  deadlineRemindersEnabled = deadlineRemindersSetting.checked;
  localStorage.setItem("triage-deadline-reminders", String(deadlineRemindersEnabled));
  if (!deadlineRemindersEnabled) deadlineReminder.hidden = true;
});
reducedMotionSetting.checked = localStorage.getItem("triage-reduced-motion") === "true";
document.documentElement.dataset.reducedMotion = String(reducedMotionSetting.checked);
reducedMotionSetting.addEventListener("change", () => {
  document.documentElement.dataset.reducedMotion = String(reducedMotionSetting.checked);
  localStorage.setItem("triage-reduced-motion", String(reducedMotionSetting.checked));
});
document.querySelector("#settings-sign-out").addEventListener("click", showLandingScreen);
applyTheme(localStorage.getItem("triage-theme") || "system");

function getScrollableParent(target, stopElement) {
  let el = target;
  while (el && el !== stopElement) {
    const style = window.getComputedStyle(el);
    const overflowY = style.overflowY || style.overflow || "";
    const isScrollable = (overflowY === "auto" || overflowY === "scroll") && el.scrollHeight > el.clientHeight;
    if (isScrollable) {
      return el;
    }
    el = el.parentElement;
  }
  return null;
}

function isAtScrollBoundary(element, deltaY) {
  if (deltaY < 0) return element.scrollTop <= 0;
  return element.scrollTop + element.clientHeight >= element.scrollHeight - 1;
}

panelScroller.addEventListener("wheel", (event) => {
  if (!event.deltaY) return;

  const scrollableParent = getScrollableParent(event.target, panelScroller);
  if (scrollableParent && !isAtScrollBoundary(scrollableParent, event.deltaY)) {
    // Keep scrolling inside the panel until its relevant boundary is reached.
    return;
  }

  event.preventDefault();
  if (wheelNavigationLocked) return;

  const activeIndex = [...railNodes].findIndex((railNode) => railNode.classList.contains("is-active"));
  const nextIndex = activeIndex + (event.deltaY > 0 ? 1 : -1);
  if (nextIndex < 0 || nextIndex >= railNodes.length) return;

  wheelNavigationLocked = true;
  scrollToSection(railNodes[nextIndex].dataset.section);
  window.setTimeout(() => {
    wheelNavigationLocked = false;
  }, 350);
}, { passive: false, capture: true });

railNodes.forEach((railNode) => {
  railNode.addEventListener("click", () => scrollToSection(railNode.dataset.section));
});

function moveBetweenPanels(direction) {
  const activeIndex = [...railNodes].findIndex((railNode) => railNode.classList.contains("is-active"));
  const nextIndex = activeIndex + direction;
  if (nextIndex < 0 || nextIndex >= railNodes.length) return;
  scrollToSection(railNodes[nextIndex].dataset.section);
}

previousPanelButton.addEventListener("click", () => moveBetweenPanels(-1));
nextPanelButton.addEventListener("click", () => moveBetweenPanels(1));

function scrollToSection(sectionName) {
  const section = document.querySelector(`#${sectionName}-section`);
  if (!section) return;
  const centeredLeft = Math.max(0, section.offsetLeft - (panelScroller.clientWidth - section.clientWidth) / 2);
  panelScroller.scrollTo({ left: centeredLeft, behavior: "smooth" });
  setActiveRailNode(sectionName);
}

function setActiveRailNode(sectionName) {
  railNodes.forEach((railNode) => {
    const isActive = railNode.dataset.section === sectionName;
    railNode.classList.toggle("is-active", isActive);
    if (isActive) {
      railNode.setAttribute("aria-current", "location");
    } else {
      railNode.removeAttribute("aria-current");
    }
  });
  const activeIndex = [...railNodes].findIndex((railNode) => railNode.dataset.section === sectionName);
  previousPanelButton.hidden = activeIndex <= 0;
  nextPanelButton.hidden = activeIndex === railNodes.length - 1;
}

panelScroller.addEventListener("scroll", () => {
  const scrollLeft = panelScroller.scrollLeft;
  let closestSection = null;
  let minDistance = Infinity;

  appSections.forEach((section) => {
    const distance = Math.abs(section.offsetLeft - scrollLeft);
    if (distance < minDistance) {
      minDistance = distance;
      closestSection = section;
    }
  });

  if (closestSection) {
    const sectionName = closestSection.id.replace("-section", "");
    setActiveRailNode(sectionName);
  }
});

document.addEventListener("keydown", (event) => {
  if (
    event.key !== "ArrowLeft" &&
    event.key !== "ArrowRight" ||
    ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(document.activeElement.tagName)
  ) return;

  event.preventDefault();
  moveBetweenPanels(event.key === "ArrowRight" ? 1 : -1);
});

const classificationTravel = {
  Obligation: { section: "queue", tone: "obligation" },
  "Study Material": { section: "study", tone: "study-material" },
  Noise: { tone: "noise" },
};

function playClassificationTravel(category) {
  const destination = classificationTravel[category];
  if (!destination || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return Promise.resolve();
  }

  const source = result.getBoundingClientRect();
  const traveler = document.createElement("span");
  traveler.className = `classification-traveler ${destination.tone}`;
  traveler.setAttribute("aria-hidden", "true");
  traveler.style.left = `${source.left + source.width * 0.72}px`;
  traveler.style.top = `${source.top + source.height * 0.38}px`;
  document.body.append(traveler);

  if (!destination.section) {
    const animation = traveler.animate(
      [{ opacity: 1, transform: "translate(-50%, -50%) scale(1)" }, { opacity: 0, transform: "translate(-50%, -50%) scale(.45)" }],
      { duration: 520, easing: "ease-out", fill: "forwards" },
    );
    return animation.finished.finally(() => traveler.remove());
  }

  const target = document.querySelector(`.rail-node[data-section="${destination.section}"]`);
  if (!target) {
    traveler.remove();
    return Promise.resolve();
  }
  const targetBounds = target.getBoundingClientRect();
  const travelX = targetBounds.left + targetBounds.width / 2 - (source.left + source.width * 0.72);
  const travelY = targetBounds.top + targetBounds.height / 2 - (source.top + source.height * 0.38);
  const animation = traveler.animate(
    [
      { opacity: 1, transform: "translate(-50%, -50%) scale(1)" },
      { opacity: 1, offset: 0.72, transform: `translate(calc(-50% + ${travelX * 0.72}px), calc(-50% + ${travelY * 0.72 - 30}px)) scale(.9)` },
      { opacity: 0.35, transform: `translate(calc(-50% + ${travelX}px), calc(-50% + ${travelY}px)) scale(.45)` },
    ],
    { duration: 620, easing: "ease-out", fill: "forwards" },
  );
  return animation.finished.finally(() => {
    traveler.remove();
    target.classList.add("is-arrival");
    window.setTimeout(() => target.classList.remove("is-arrival"), 260);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  result.hidden = true;

  const text = textInput.value.trim();
  const file = fileInput.files[0];
  if (!text && !file) {
    error.textContent = "Paste text or choose a .txt file first.";
    return;
  }

  button.disabled = true;
  button.textContent = "Classifying…";

  try {
    let response;
    if (text) {
      response = await apiFetch(apiUrl("/ingest"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    } else {
      const formData = new FormData();
      formData.append("file", file);
      response = await apiFetch(apiUrl("/ingest"), { method: "POST", body: formData });
    }

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Classification failed.");

    document.querySelector("#category").textContent = data.category;
    document.querySelector("#category").className = `badge ${data.category.toLowerCase().replace(" ", "-")}`;
    document.querySelector("#reason").textContent = data.reason;
    document.querySelector("#deadline").textContent = data.deadline || "No explicit deadline";
    document.querySelector("#mandatory").textContent = data.mandatory === null ? "Not specified" : data.mandatory ? "Yes" : "No";
    result.hidden = false;
    button.disabled = false;
    button.textContent = "Classify with Triage";
    playClassificationTravel(data.category).then(() => {
      if (data.category === "Obligation") loadQueue();
    });
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Classify with Triage";
  }
});

function loadConnectedSources() {
  try {
    return JSON.parse(localStorage.getItem(connectedSourcesStorageKey)) || {};
  } catch {
    return {};
  }
}

function saveConnectedSources() {
  localStorage.setItem(connectedSourcesStorageKey, JSON.stringify(connectedSources));
}

async function loadConnectedSourcesPanel() {
  try {
    const response = await apiFetch(apiUrl("/sources/google/status"));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not check Google authorization.");
    googleAuthorized = data.authorized;
  } catch {
    googleAuthorized = false;
  }
  renderConnectedSources();
}

function renderConnectedSources() {
  connectedSourcesList.innerHTML = Object.entries(sourceDefinitions).map(([key, source]) => {
    const state = connectedSources[key] || {};
    const isSyncing = syncingSource === key;
    const reconnectNeeded = source.google && state.connected && isReconnectDue(state.lastSynced);
    const setupRequired = source.google && !googleAuthorized;
    if (source.comingSoon) {
      return `<article class="source-card is-coming-soon" aria-disabled="true"><div><p class="source-name">${source.name}</p><p class="muted">${source.description}</p></div><span class="coming-soon-tag">Coming soon</span></article>`;
    }
    const status = isSyncing
      ? "Syncing…"
      : state.error
        ? state.error
      : setupRequired
        ? "One-time setup required"
        : state.connected
          ? `Last synced: ${formatRelativeTime(state.lastSynced)}`
          : source.demo
            ? "Load representative sample data"
            : "Turn on to sync";
    return `
      <article class="source-card${state.connected ? " is-connected" : ""}" data-source="${key}">
        <div class="source-card-copy">
          <div class="source-title-row"><p class="source-name">${source.name}</p>${source.demo ? '<span class="demo-data-tag">Demo data</span>' : ""}</div>
          <p class="muted">${source.description}</p>
          <p class="source-status${setupRequired ? " setup-required" : ""}">${status}</p>
          ${setupRequired ? '<p class="source-setup">In a terminal, run <code>cd backend</code> then <code>python setup_google_auth.py</code>. Return here and turn this source on.</p>' : ""}
          ${reconnectNeeded ? `<button class="source-reconnect" type="button" data-reconnect-source="${key}">Reconnect</button>` : ""}
        </div>
        <label class="source-toggle" aria-label="${state.connected ? "Disconnect" : "Connect"} ${source.name}">
          <input type="checkbox" data-source-toggle="${key}" ${state.connected ? "checked" : ""} ${isSyncing ? "disabled" : ""} />
          <span class="source-toggle-slider"></span>
        </label>
      </article>
    `;
  }).join("");
}

function isReconnectDue(lastSynced) {
  if (!lastSynced || Number.isNaN(new Date(lastSynced).getTime())) return false;
  return Date.now() - new Date(lastSynced).getTime() > reconnectAfterDays * 24 * 60 * 60 * 1000;
}

function formatRelativeTime(timestamp) {
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 60000));
  if (elapsedMinutes < 1) return "just now";
  if (elapsedMinutes < 60) return `${elapsedMinutes} minute${elapsedMinutes === 1 ? "" : "s"} ago`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours} hour${elapsedHours === 1 ? "" : "s"} ago`;
  const elapsedDays = Math.floor(elapsedHours / 24);
  return `${elapsedDays} day${elapsedDays === 1 ? "" : "s"} ago`;
}

connectedSourcesList.addEventListener("change", async (event) => {
  const toggle = event.target.closest("[data-source-toggle]");
  if (!toggle) return;
  const sourceKey = toggle.dataset.sourceToggle;
  if (!toggle.checked) {
    connectedSources[sourceKey] = { ...connectedSources[sourceKey], connected: false, error: null };
    saveConnectedSources();
    renderConnectedSources();
    return;
  }
  await connectSource(sourceKey);
});

connectedSourcesList.addEventListener("click", async (event) => {
  const reconnectButton = event.target.closest("[data-reconnect-source]");
  if (reconnectButton) await connectSource(reconnectButton.dataset.reconnectSource);
});

async function connectSource(sourceKey) {
  const source = sourceDefinitions[sourceKey];
  if (source.google && !googleAuthorized) {
    connectedSources[sourceKey] = { ...connectedSources[sourceKey], connected: false };
    saveConnectedSources();
    renderConnectedSources();
    return;
  }
  syncingSource = sourceKey;
  renderConnectedSources();
  try {
    const response = await apiFetch(apiUrl(source.endpoint), { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Could not sync ${source.name}.`);
    connectedSources[sourceKey] = { connected: true, lastSynced: new Date().toISOString() };
    saveConnectedSources();
    await loadQueue();
  } catch (requestError) {
    connectedSources[sourceKey] = { ...connectedSources[sourceKey], connected: false, error: requestError.message };
    saveConnectedSources();
  } finally {
    syncingSource = null;
    renderConnectedSources();
  }
}

refreshQueueButton.addEventListener("click", loadQueue);

async function loadQueue() {
  queue.innerHTML = "<p class=\"muted\">Loading queue…</p>";
  try {
    const response = await apiFetch(apiUrl("/queue"));
    const groups = await response.json();
    if (!response.ok) throw new Error(groups.detail || "Could not load the queue.");
    updateDeadlineReminder(groups.Immediate);

    const totalItems = Object.values(groups).reduce((total, items) => total + items.length, 0);
    if (!totalItems) {
      queue.innerHTML = "<p class=\"empty-state\">Nothing urgent right now.</p>";
      return;
    }

    queue.innerHTML = Object.entries(groups).map(([name, items]) => `
      <section class="queue-group">
        <h3>${name} <span>${items.length}</span></h3>
        ${items.length ? items.map(queueItem).join("") : "<p class=\"muted\">Nothing here.</p>"}
      </section>
    `).join("");
  } catch (requestError) {
    queue.innerHTML = `<p class="error">${requestError.message}</p>`;
  }
}

function updateDeadlineReminder(immediateItems) {
  const urgentItems = (immediateItems || [])
    .map((item) => ({ item, deadline: parseDeadline(item.deadline) }))
    .filter(({ item }) => isDeadlineWithin24Hours(item.deadline))
    .sort((first, second) => first.deadline - second.deadline);

  currentUrgentItems = urgentItems.map(({ item }) => item);
  notifyNewUrgentItems(currentUrgentItems);
  if (!deadlineRemindersEnabled || deadlineReminderDismissed || !urgentItems.length) {
    deadlineReminder.hidden = true;
    return;
  }

  const nearest = urgentItems[0].item.deadline;
  const count = urgentItems.length;
  deadlineReminderText.textContent = `You have ${count} item${count === 1 ? "" : "s"} due soon — nearest: ${nearest}.`;
  deadlineReminder.hidden = false;
}

function notifyNewUrgentItems(urgentItems) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const newlyDetected = urgentItems.filter((item) => !notifiedUrgentItemIds.has(item.id));
  newlyDetected.forEach((item) => notifiedUrgentItemIds.add(item.id));
  if (!newlyDetected.length) return;

  const nearest = [...newlyDetected].sort((first, second) => parseDeadline(first.deadline) - parseDeadline(second.deadline))[0];
  try {
    new Notification("Triage deadline reminder", {
      body: `${newlyDetected.length} item${newlyDetected.length === 1 ? "" : "s"} due soon. Nearest: ${nearest.deadline}.`,
    });
  } catch {
    // The in-app banner remains available if the browser blocks notifications.
  }
}

function requestReminderNotifications() {
  if (
    !("Notification" in window) ||
    Notification.permission !== "default" ||
    localStorage.getItem(notificationRequestStorageKey)
  ) return;
  localStorage.setItem(notificationRequestStorageKey, "true");
  try {
    const permissionRequest = Notification.requestPermission();
    if (permissionRequest?.then) {
      permissionRequest.then((permission) => {
        if (permission === "granted") notifyNewUrgentItems(currentUrgentItems);
      }).catch(() => {});
    }
  } catch {
    // Notification permission is an optional enhancement.
  }
}

deadlineReminderNavigate.addEventListener("click", () => {
  requestReminderNotifications();
  scrollToSection("queue");
});

deadlineReminderDismiss.addEventListener("click", () => {
  deadlineReminderDismissed = true;
  deadlineReminder.hidden = true;
});

function queueItem(item) {
  const summary = item.text.length > 150 ? `${item.text.slice(0, 150)}...` : item.text;
  const mandatory = item.mandatory === true ? "Mandatory" : item.mandatory === false ? "Optional" : "Requirement unclear";
  const deadline = item.deadline || "No explicit deadline";
  const deadlineClass = isDeadlineWithin24Hours(item.deadline) ? " deadline-soon" : "";
  return `
    <article class="queue-item" data-item-id="${item.id}">
      <p class="summary">${escapeHtml(summary)}</p>
      <p class="muted">${escapeHtml(item.reason)}</p>
      <p class="metadata"><span class="deadline${deadlineClass}">${escapeHtml(deadline)}</span><span class="mandatory ${item.mandatory === true ? "is-mandatory" : "is-optional"}">${mandatory}</span>${item.source === "whatsapp-demo" ? '<span class="simulated-tag">Simulated</span>' : ""}</p>
      ${archiveDownloadLink(item.archived_path)}
      <button class="done-button" type="button" data-item-id="${item.id}">Mark done</button>
    </article>
  `;
}

function archiveDownloadLink(archivedPath, label = "Download original") {
  if (!archivedPath) return "";
  const filename = escapeHtml(archivedPath);
  return `<a class="download-original" href="${apiUrl(`/archive/${encodeURIComponent(archivedPath)}`)}" data-archive-filename="${filename}">${label}</a>`;
}

document.addEventListener("click", async (event) => {
  const link = event.target.closest(".download-original");
  if (!link) return;

  event.preventDefault();
  try {
    const response = await apiFetch(link.href);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || "Could not download the original file.");
    }
    const downloadUrl = URL.createObjectURL(await response.blob());
    const downloadLink = document.createElement("a");
    downloadLink.href = downloadUrl;
    downloadLink.download = link.dataset.archiveFilename;
    downloadLink.click();
    URL.revokeObjectURL(downloadUrl);
  } catch (requestError) {
    error.textContent = requestError.message;
  }
});

queue.addEventListener("click", async (event) => {
  const doneButton = event.target.closest(".done-button");
  if (!doneButton) return;

  doneButton.disabled = true;
  try {
    const response = await apiFetch(apiUrl(`/queue/${doneButton.dataset.itemId}/done`), { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not update this item.");
    await loadPendingActions(data.id);
    openApprovalDrawer(doneButton);
    loadQueue();
  } catch (requestError) {
    error.textContent = requestError.message;
    doneButton.disabled = false;
  }
});

function escapeHtml(value) {
  const template = document.createElement("template");
  template.textContent = value;
  return template.innerHTML;
}

function isDeadlineWithin24Hours(deadline) {
  const parsed = parseDeadline(deadline);
  if (!parsed) return false;
  const millisecondsUntilDeadline = parsed.getTime() - Date.now();
  return millisecondsUntilDeadline >= 0 && millisecondsUntilDeadline <= 24 * 60 * 60 * 1000;
}

function parseDeadline(deadline) {
  if (!deadline) return null;
  const normalized = deadline.trim();
  const isoMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const slashMatch = normalized.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  const humanReadableMatch = normalized.match(
    /^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday,\s+)?([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM))?$/i,
  );

  if (isoMatch) return createValidatedDate(Number(isoMatch[1]), Number(isoMatch[2]), Number(isoMatch[3]));
  if (slashMatch) return createValidatedDate(Number(slashMatch[3]), Number(slashMatch[1]), Number(slashMatch[2]));
  if (!humanReadableMatch) return null;

  const [, monthName, dayText, yearText, hourText, minuteText, meridiem] = humanReadableMatch;
  const month = new Date(`${monthName} 1, 2000`).getMonth() + 1;
  if (!month) return null;

  const now = new Date();
  const year = yearText ? Number(yearText) : now.getFullYear();
  let hour = hourText ? Number(hourText) : 0;
  if (hourText && (hour < 1 || hour > 12)) return null;
  if (meridiem) hour = (hour % 12) + (meridiem.toUpperCase() === "PM" ? 12 : 0);

  let parsed = createValidatedDate(year, month, Number(dayText), hour, Number(minuteText || 0));
  if (!parsed) return null;
  if (!yearText && parsed < now) {
    parsed = createValidatedDate(year + 1, month, Number(dayText), hour, Number(minuteText || 0));
  }
  return parsed;
}

function createValidatedDate(year, month, day, hour = 0, minute = 0) {
  const parsed = new Date(year, month - 1, day, hour, minute);
  return (
    parsed.getFullYear() === year &&
    parsed.getMonth() === month - 1 &&
    parsed.getDate() === day &&
    parsed.getHours() === hour &&
    parsed.getMinutes() === minute
  ) ? parsed : null;
}

if (authToken) {
  showApp();
  loadAppData();
} else {
  showLandingScreen();
}

studyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  studyError.textContent = "";
  const button = studyForm.querySelector("button");
  button.disabled = true;
  button.textContent = "Building plan…";

  try {
    const response = await apiFetch(apiUrl("/study/upload"), {
      method: "POST",
      body: new FormData(studyForm),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not build the study plan.");
    renderStudyPlan(data.topics);
  } catch (requestError) {
    studyError.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Build study plan";
  }
});

async function loadStudyPlan() {
  try {
    const response = await apiFetch(apiUrl("/study/plan"));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load the study plan.");
    renderStudyPlan(data.topics);
  } catch (requestError) {
    studyPlan.innerHTML = `<p class="error">${escapeHtml(requestError.message)}</p>`;
  }
}

function renderStudyPlan(topics) {
  if (!topics.length) {
    studyPlan.innerHTML = "<p class=\"empty-state\">Upload a question bank to get started.</p>";
    return;
  }
  studyPlan.innerHTML = topics.map((item) => `
    <details class="study-topic">
      <summary>
        <span>${escapeHtml(item.topic)}</span>
        <span class="weight">${item.weight}/10</span>
      </summary>
      <div class="weight-track"><span style="width: ${item.weight * 10}%; --weight: ${item.weight}"></span></div>
      <ul>${item.subtopics.map((subtopic) => `<li>${escapeHtml(subtopic)}</li>`).join("")}</ul>
      <div class="study-archive-links">${archiveDownloadLink(item.question_bank_archived_path, "Download question bank")}${archiveDownloadLink(item.unit_notes_archived_path, "Download unit notes")}</div>
    </details>
  `).join("");
}

async function loadPendingActions(highlightedActionId = null) {
  try {
    const response = await apiFetch(apiUrl("/pending"));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load pending actions.");
    renderPendingActions(data.actions, highlightedActionId);
  } catch (requestError) {
    pendingActions.innerHTML = `<p class="error">${escapeHtml(requestError.message)}</p>`;
  }
}

function renderPendingActions(actions, highlightedActionId = null) {
  updatePendingIndicator(actions.length);
  if (!actions.length) {
    pendingActions.innerHTML = "<p class=\"empty-state\">No actions are waiting for review.</p>";
    return;
  }
  const orderedActions = [...actions].sort((first, second) => {
    if (first.id === highlightedActionId) return -1;
    if (second.id === highlightedActionId) return 1;
    return 0;
  });
  pendingActions.innerHTML = orderedActions.map((action) => `
    <article class="pending-action${action.id === highlightedActionId ? " is-highlighted" : ""}" data-action-id="${action.id}">
      <p class="summary">${escapeHtml(action.payload.message)}</p>
      <p class="muted">Triage will not make this change until you approve it.</p>
      ${action.payload.drafted_response ? `
        <label class="drafted-response-label" for="drafted-response-${action.id}">Draft to copy and send yourself</label>
        <textarea id="drafted-response-${action.id}" class="drafted-response" rows="3">${escapeHtml(action.payload.drafted_response)}</textarea>
        <p class="muted">Editing or approving this draft does not send it anywhere.</p>
      ` : ""}
      <div class="pending-buttons">
        <button class="approve-button" type="button" data-action-id="${action.id}">Approve</button>
        <button class="reject-button secondary" type="button" data-action-id="${action.id}">Reject</button>
      </div>
    </article>
  `).join("");
}

pendingActions.addEventListener("click", async (event) => {
  const actionButton = event.target.closest(".approve-button, .reject-button");
  if (!actionButton) return;

  const decision = actionButton.classList.contains("approve-button") ? "approve" : "reject";
  actionButton.disabled = true;
  try {
    const response = await apiFetch(
      apiUrl(`/pending/${actionButton.dataset.actionId}/${decision}`),
      { method: "POST" },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not update this action.");
    await loadPendingActions();
    loadQueue();
    loadStudyPlan();
  } catch (requestError) {
    error.textContent = requestError.message;
    actionButton.disabled = false;
  }
});

assignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  assignmentError.textContent = "";
  const prompt = assignmentPrompt.value.trim();
  if (!prompt) {
    assignmentError.textContent = "Paste an assignment prompt first.";
    return;
  }

  const submitButton = assignmentForm.querySelector("button");
  submitButton.disabled = true;
  submitButton.textContent = "Building scaffold…";
  try {
    const response = await apiFetch(apiUrl("/assignment/help"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const scaffold = await response.json();
    if (!response.ok) throw new Error(scaffold.detail || "Could not build the assignment scaffold.");
    renderAssignmentScaffold(scaffold);
    loadAssignmentHistory();
  } catch (requestError) {
    assignmentError.textContent = requestError.message;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Build scaffold";
  }
});

async function loadAssignmentHistory() {
  try {
    const response = await apiFetch(apiUrl("/assignment/history"));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load assignment history.");
    renderAssignmentHistory(data.assignments);
  } catch (requestError) {
    assignmentHistory.innerHTML = `<p class="error">${escapeHtml(requestError.message)}</p>`;
  }
}

function renderAssignmentScaffold(scaffold) {
  assignmentResult.innerHTML = assignmentScaffoldMarkup(scaffold, true);
}

function renderAssignmentHistory(assignments) {
  if (!assignments.length) {
    assignmentHistory.innerHTML = "<p class=\"empty-state\">No scaffolds saved yet.</p>";
    return;
  }
  assignmentHistory.innerHTML = assignments.map((assignment) => `
    <details class="assignment-history-item">
      <summary>${escapeHtml(formatAssignmentDate(assignment.created_at))}</summary>
      <p class="assignment-prompt-preview">${escapeHtml(assignment.prompt)}</p>
      ${assignmentScaffoldMarkup(assignment, false)}
    </details>
  `).join("");
}

function assignmentScaffoldMarkup(scaffold, open) {
  return `
    <details class="assignment-scaffold-section" ${open ? "open" : ""}>
      <summary>Requirements</summary>
      <ul>${scaffold.requirements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </details>
    <details class="assignment-scaffold-section" ${open ? "open" : ""}>
      <summary>Concepts</summary>
      <ul>${scaffold.concepts.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </details>
    <details class="assignment-scaffold-section" ${open ? "open" : ""}>
      <summary>Approach</summary>
      <ol>${scaffold.approach.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
    </details>
    <details class="assignment-scaffold-section" ${open ? "open" : ""}>
      <summary>Test Cases</summary>
      <ul class="assignment-test-cases">${scaffold.test_cases.map((testCase) => `<li><span>Input</span><code>${escapeHtml(testCase.input)}</code><span>Expected output</span><code>${escapeHtml(testCase.expected_output)}</code></li>`).join("")}</ul>
    </details>
  `;
}

function formatAssignmentDate(createdAt) {
  const parsed = new Date(createdAt);
  return Number.isNaN(parsed.getTime()) ? "Saved scaffold" : `Saved ${parsed.toLocaleString()}`;
}
