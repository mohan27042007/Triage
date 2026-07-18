const form = document.querySelector("#ingest-form");
const textInput = document.querySelector("#text");
const fileInput = document.querySelector("#file");
const result = document.querySelector("#result");
const error = document.querySelector("#error");
const button = form.querySelector("button");
const queue = document.querySelector("#queue");
const refreshQueueButton = document.querySelector("#refresh-queue");
const studyForm = document.querySelector("#study-form");
const studyPlan = document.querySelector("#study-plan");
const studyError = document.querySelector("#study-error");
const pendingActions = document.querySelector("#pending-actions");
const railNodes = document.querySelectorAll(".rail-node");
const appSections = document.querySelectorAll(".app-section");
const panelScroller = document.querySelector(".panel-scroller");
let wheelNavigationLocked = false;

function getScrollableParent(target, stopElement) {
  let el = target;
  while (el && el !== stopElement) {
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      return el;
    }
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

panelScroller.addEventListener("wheel", (event) => {
  if (!event.deltaY) return;

  const scrollableParent = getScrollableParent(event.target, panelScroller);
  if (scrollableParent) {
    // Let the element scroll vertically inside the panel
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

function scrollToSection(sectionName) {
  const section = document.querySelector(`#${sectionName}-section`);
  if (!section) return;
  panelScroller.scrollTo({ left: section.offsetLeft, behavior: "smooth" });
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

  const activeIndex = [...railNodes].findIndex((railNode) => railNode.classList.contains("is-active"));
  const nextIndex = activeIndex + (event.key === "ArrowRight" ? 1 : -1);
  if (nextIndex < 0 || nextIndex >= railNodes.length) return;

  event.preventDefault();
  scrollToSection(railNodes[nextIndex].dataset.section);
});

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
      response = await fetch("http://localhost:8000/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    } else {
      const formData = new FormData();
      formData.append("file", file);
      response = await fetch("http://localhost:8000/ingest", { method: "POST", body: formData });
    }

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Classification failed.");

    document.querySelector("#category").textContent = data.category;
    document.querySelector("#category").className = `badge ${data.category.toLowerCase().replace(" ", "-")}`;
    document.querySelector("#reason").textContent = data.reason;
    document.querySelector("#deadline").textContent = data.deadline || "No explicit deadline";
    document.querySelector("#mandatory").textContent = data.mandatory === null ? "Not specified" : data.mandatory ? "Yes" : "No";
    result.hidden = false;
    if (data.category === "Obligation") loadQueue();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Classify with Triage";
  }
});

refreshQueueButton.addEventListener("click", loadQueue);

async function loadQueue() {
  queue.innerHTML = "<p class=\"muted\">Loading queue…</p>";
  try {
    const response = await fetch("http://localhost:8000/queue");
    const groups = await response.json();
    if (!response.ok) throw new Error(groups.detail || "Could not load the queue.");

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

function queueItem(item) {
  const summary = item.text.length > 150 ? `${item.text.slice(0, 150)}...` : item.text;
  const mandatory = item.mandatory === true ? "Mandatory" : item.mandatory === false ? "Optional" : "Requirement unclear";
  const deadline = item.deadline || "No explicit deadline";
  const deadlineClass = isDeadlineWithin24Hours(item.deadline) ? " deadline-soon" : "";
  return `
    <article class="queue-item" data-item-id="${item.id}">
      <p class="summary">${escapeHtml(summary)}</p>
      <p class="muted">${escapeHtml(item.reason)}</p>
      <p class="metadata"><span class="deadline${deadlineClass}">${escapeHtml(deadline)}</span><span class="mandatory ${item.mandatory === true ? "is-mandatory" : "is-optional"}">${mandatory}</span></p>
      <button class="done-button" type="button" data-item-id="${item.id}">Mark done</button>
    </article>
  `;
}

queue.addEventListener("click", async (event) => {
  const doneButton = event.target.closest(".done-button");
  if (!doneButton) return;

  doneButton.disabled = true;
  try {
    const response = await fetch(`http://localhost:8000/queue/${doneButton.dataset.itemId}/done`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not update this item.");
    loadPendingActions();
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

loadQueue();
loadStudyPlan();
loadPendingActions();

studyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  studyError.textContent = "";
  const button = studyForm.querySelector("button");
  button.disabled = true;
  button.textContent = "Building plan…";

  try {
    const response = await fetch("http://localhost:8000/study/upload", {
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
    const response = await fetch("http://localhost:8000/study/plan");
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
    </details>
  `).join("");
}

async function loadPendingActions() {
  try {
    const response = await fetch("http://localhost:8000/pending");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load pending actions.");
    renderPendingActions(data.actions);
  } catch (requestError) {
    pendingActions.innerHTML = `<p class="error">${escapeHtml(requestError.message)}</p>`;
  }
}

function renderPendingActions(actions) {
  if (!actions.length) {
    pendingActions.innerHTML = "<p class=\"empty-state\">No actions are waiting for review.</p>";
    return;
  }
  pendingActions.innerHTML = actions.map((action) => `
    <article class="pending-action" data-action-id="${action.id}">
      <p class="summary">${escapeHtml(action.payload.message)}</p>
      <p class="muted">Triage will not make this change until you approve it.</p>
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
    const response = await fetch(
      `http://localhost:8000/pending/${actionButton.dataset.actionId}/${decision}`,
      { method: "POST" },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not update this action.");
    loadPendingActions();
    loadQueue();
    loadStudyPlan();
  } catch (requestError) {
    error.textContent = requestError.message;
    actionButton.disabled = false;
  }
});
