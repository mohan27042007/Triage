const form = document.querySelector("#ingest-form");
const textInput = document.querySelector("#text");
const fileInput = document.querySelector("#file");
const result = document.querySelector("#result");
const error = document.querySelector("#error");
const button = form.querySelector("button");

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
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Classify with Triage";
  }
});
