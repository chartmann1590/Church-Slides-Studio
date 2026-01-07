const els = {
  bulletinText: document.getElementById("bulletinText"),
  bulletinFile: document.getElementById("bulletinFile"),
  verifyOllama: document.getElementById("verifyOllama"),
  generateBtn: document.getElementById("generateBtn"),
  status: document.getElementById("status"),
  titleBgSelect: document.getElementById("titleBgSelect"),
  contentBgSelect: document.getElementById("contentBgSelect"),
  titleBgUpload: document.getElementById("titleBgUpload"),
  contentBgUpload: document.getElementById("contentBgUpload"),
  refreshBackgrounds: document.getElementById("refreshBackgrounds"),
  slideWidth: document.getElementById("slideWidth"),
  slideHeight: document.getElementById("slideHeight"),
  ollamaUrl: document.getElementById("ollamaUrl"),
  ollamaModel: document.getElementById("ollamaModel"),
  verifyPrompt: document.getElementById("verifyPrompt"),
  saveSettings: document.getElementById("saveSettings"),
  previewGrid: document.getElementById("previewGrid"),
  downloadZip: document.getElementById("downloadZip"),
  slideCount: document.getElementById("slideCount"),
};

const state = {
  backgrounds: [],
};

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.classList.toggle("issue", isError);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function populateSelect(select, items, type) {
  select.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "None";
  select.appendChild(none);
  items
    .filter((bg) => bg.type === type)
    .forEach((bg) => {
      const option = document.createElement("option");
      option.value = bg.filename;
      option.textContent = bg.filename;
      select.appendChild(option);
    });
}

function ensureSelection(select) {
  if (select.value) return;
  const options = Array.from(select.options).filter((opt) => opt.value);
  if (options.length > 0) {
    select.value = options[0].value;
  }
}

async function loadBackgrounds() {
  const backgrounds = await fetchJson("/api/backgrounds");
  state.backgrounds = backgrounds;
  populateSelect(els.titleBgSelect, backgrounds, "title");
  populateSelect(els.contentBgSelect, backgrounds, "content");
  ensureSelection(els.titleBgSelect);
  ensureSelection(els.contentBgSelect);
}

async function uploadBackground(type, file) {
  const form = new FormData();
  form.append("bg_type", type);
  form.append("file", file);
  await fetchJson("/api/backgrounds", {
    method: "POST",
    body: form,
  });
  await loadBackgrounds();
  const latest = state.backgrounds
    .filter((bg) => bg.type === type)
    .map((bg) => bg.filename)
    .pop();
  if (latest) {
    if (type === "title") {
      els.titleBgSelect.value = latest;
    } else {
      els.contentBgSelect.value = latest;
    }
  }
}

async function loadSettings() {
  const settings = await fetchJson("/api/settings");
  els.ollamaUrl.value = settings.ollama_base_url || "";
  els.ollamaModel.value = settings.ollama_model || "";
  els.verifyPrompt.value = settings.verify_prompt || "";
  els.slideWidth.value = settings.slide_width || 1920;
  els.slideHeight.value = settings.slide_height || 1080;
}

async function saveSettings() {
  const slideWidth = Number.parseInt(els.slideWidth.value, 10);
  const slideHeight = Number.parseInt(els.slideHeight.value, 10);
  if (!Number.isFinite(slideWidth) || slideWidth <= 0) {
    throw new Error("Slide width must be a positive number.");
  }
  if (!Number.isFinite(slideHeight) || slideHeight <= 0) {
    throw new Error("Slide height must be a positive number.");
  }
  const payload = {
    ollama_base_url: els.ollamaUrl.value.trim(),
    ollama_model: els.ollamaModel.value.trim(),
    verify_prompt: els.verifyPrompt.value.trim(),
    slide_width: slideWidth,
    slide_height: slideHeight,
  };
  await fetchJson("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function renderSlides(slides, verification, zipUrl) {
  els.previewGrid.innerHTML = "";
  els.slideCount.textContent = `${slides.length} slides`;
  els.downloadZip.href = zipUrl || "#";
  els.downloadZip.classList.toggle("disabled", !zipUrl);
  slides.forEach((slide) => {
    const card = document.createElement("div");
    card.className = "preview-card";
    const img = document.createElement("img");
    img.src = `${slide.url}?v=${Date.now()}`;
    img.alt = slide.filename;
    const meta = document.createElement("div");
    meta.className = "meta";
    const name = document.createElement("span");
    name.textContent = slide.filename;
    const status = document.createElement("span");
    const result = verification[slide.filename];
    if (result && result.ok === false) {
      status.textContent = "Check";
      status.className = "issue";
    } else if (result && result.ok === true) {
      status.textContent = "OK";
    } else {
      status.textContent = "";
    }
    meta.appendChild(name);
    meta.appendChild(status);
    card.appendChild(img);
    card.appendChild(meta);
    els.previewGrid.appendChild(card);
  });
}

async function generateSlides() {
  setStatus("Generating slides...");
  els.generateBtn.disabled = true;
  const form = new FormData();
  const text = els.bulletinText.value.trim();
  const file = els.bulletinFile.files[0];
  if (file) {
    form.append("bulletin_file", file);
  } else if (text) {
    form.append("bulletin_text", text);
  } else {
    setStatus("Please paste bulletin text or upload a file.", true);
    els.generateBtn.disabled = false;
    return;
  }
  if (els.titleBgSelect.value) {
    form.append("title_background", els.titleBgSelect.value);
  }
  if (els.contentBgSelect.value) {
    form.append("content_background", els.contentBgSelect.value);
  }
  form.append("verify_with_ollama", els.verifyOllama.checked ? "true" : "false");

  try {
    const result = await fetchJson("/api/generate", {
      method: "POST",
      body: form,
    });
    renderSlides(result.slides, result.verification || {}, result.zip_url);
    setStatus(`Generated ${result.slides.length} slides.`);
  } catch (error) {
    setStatus(error.message || "Generation failed.", true);
  } finally {
    els.generateBtn.disabled = false;
  }
}

els.titleBgUpload.addEventListener("change", async (event) => {
  if (!event.target.files.length) return;
  await uploadBackground("title", event.target.files[0]);
  event.target.value = "";
});

els.contentBgUpload.addEventListener("change", async (event) => {
  if (!event.target.files.length) return;
  await uploadBackground("content", event.target.files[0]);
  event.target.value = "";
});

els.refreshBackgrounds.addEventListener("click", loadBackgrounds);
els.generateBtn.addEventListener("click", generateSlides);
els.saveSettings.addEventListener("click", async () => {
  try {
    await saveSettings();
    setStatus("Settings saved.");
  } catch (error) {
    setStatus(error.message || "Failed to save settings.", true);
  }
});

Promise.all([loadSettings(), loadBackgrounds()]).catch((error) => {
  setStatus(error.message || "Failed to load app data.", true);
});
