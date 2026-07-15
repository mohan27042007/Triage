const form = document.querySelector("#ingest-form");
const textInput = document.querySelector("#text");
const fileInput = document.querySelector("#file");
const result = document.querySelector("#result");
const error = document.querySelector("#error");
const button = form.querySelector("button");
const queue = document.querySelector("#queue");
const refreshQueueButton = document.querySelector("#refresh-queue");

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
  const summary = item.text.length > 150 ? `${item.text.slice(0, 150)}…` : item.text;
  const mandatory = item.mandatory === true ? "Mandatory" : item.mandatory === false ? "Optional" : "Requirement unclear";
  const deadline = item.deadline || "No explicit deadline";
  return `
    <article class="queue-item" data-item-id="${item.id}">
      <p class="summary">${escapeHtml(summary)}</p>
      <p class="muted">${escapeHtml(item.reason)}</p>
      <p class="metadata"><span>${escapeHtml(deadline)}</span><span class="mandatory">${mandatory}</span></p>
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
    doneButton.closest(".queue-item").remove();
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

loadQueue();
