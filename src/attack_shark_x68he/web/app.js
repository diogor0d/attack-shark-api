(function () {
  "use strict";

  const DEVICE_FALLBACK = "x68he";
  const SOURCE_ID = "web-ui";
  const KEY_GEOMETRY = {
    backspace: { span: 4 },
    tab: { span: 3 },
    backslash: { span: 3 },
    caps_lock: { span: 3 },
    enter: { span: 5 },
    shift_left: { span: 4 },
    shift_right: { span: 4 },
    space: { span: 14 },
    arrow_left: { span: 2, start: 27 },
  };
  const KEY_LABELS = {
    escape: "Esc",
    digit1: "1!", digit2: "2@", digit3: "3#", digit4: "4$", digit5: "5%",
    digit6: "6^", digit7: "7&", digit8: "8*", digit9: "9(", digit0: "0)",
    minus: "-_", equal: "=+", delete: "Del", page_up: "PgUp", page_down: "PgDn",
    bracket_left: "[{", bracket_right: "]}", backslash: "\\", caps_lock: "Caps",
    semicolon: ";:", quote: "\"'", shift_left: "Shift", shift_right: "Shift",
    comma: ",<", period: ".>", slash: "/?",
    control_left: "Ctrl", control_right: "Ctrl", meta_left: "Win", alt_left: "Alt",
    arrow_up: "↑", arrow_left: "←", arrow_down: "↓", arrow_right: "→",
  };
  const state = {
    device: null,
    deviceId: DEVICE_FALLBACK,
    leds: [],
    pattern: Object.create(null),
    activeRow: 0,
    paintColour: "#16D9E3",
    background: "#05090D",
    layers: [],
  };

  const $ = (id) => document.getElementById(id);
  const byId = (value) => encodeURIComponent(value);

  function text(element, value) {
    element.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  }

  function colour(value) {
    if (Array.isArray(value) && value.length === 3) {
      return `#${value.map((part) => Number(part).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
    }
    if (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value)) return value.toUpperCase();
    return "#000000";
  }

  function friendlyError(status, message) {
    const detail = message || "The lighting service did not return a reason.";
    if (status === 409) return `Device busy or already owned. ${detail}`;
    if (status === 422) return `The service rejected these values. ${detail}`;
    if (status === 503) return `Hardware unavailable. ${detail}`;
    if (status === 501) return `Capability unavailable. ${detail}`;
    if (status === 404) return `Device not found. ${detail}`;
    return detail;
  }

  async function request(path, options) {
    let response;
    try {
      response = await fetch(path, { headers: { Accept: "application/json", "Content-Type": "application/json" }, ...options });
    } catch (error) {
      throw new Error("Cannot reach the local API. Is the service running on port 8768?");
    }
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* Empty error bodies are handled below. */ }
    if (!response.ok) {
      const message = payload && (payload.detail || payload.error || payload.message);
      const failure = new Error(friendlyError(response.status, message));
      failure.status = response.status;
      throw failure;
    }
    return payload;
  }

  function toast(message, kind = "info") {
    const node = document.createElement("div");
    node.className = "toast";
    node.dataset.kind = kind;
    node.textContent = message;
    $("toast-region").append(node);
    window.setTimeout(() => node.remove(), 5200);
  }

  function setConnection(status, label) {
    const badge = $("connection-badge");
    badge.dataset.state = status;
    text($("connection-label"), label);
  }

  function setUnavailable(kind, detail) {
    const label = kind === "busy" ? "Device busy" : "Device unavailable";
    setConnection(kind === "busy" ? "busy" : "error", label);
    text($("status-value"), label);
    text($("status-detail"), detail || "Refresh after reconnecting the keyboard.");
    ["identity-value", "identity-detail", "owner-value", "owner-detail", "capture-value", "capture-detail"].forEach((id) => text($(id), "—"));
    text($("device-name"), "—"); text($("internal-id"), "—"); text($("revision"), "—"); text($("led-count"), "—"); text($("static-storage"), "—");
    $("capability-list").replaceChildren();
    $("preset-mode").replaceChildren();
    $("keyboard-grid").replaceChildren();
    state.device = null;
    updatePatternCount();
  }

  function displayName(name) {
    return String(name).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function renderKeyboard() {
    const grid = $("keyboard-grid");
    grid.replaceChildren();
    const byRow = new Map();
    for (const led of state.leds) {
      const row = Number(led.row) || 0;
      if (!byRow.has(row)) byRow.set(row, []);
      byRow.get(row).push(led);
    }
    for (const [row, leds] of [...byRow.entries()].sort((a, b) => a[0] - b[0])) {
      const rowNode = document.createElement("div");
      rowNode.className = "key-row";
      rowNode.dataset.row = String(row);
      rowNode.setAttribute("role", "row");
      for (const led of leds.sort((a, b) => Number(a.column) - Number(b.column))) {
        const key = document.createElement("button");
        const geometry = KEY_GEOMETRY[led.name] || { span: 2 };
        key.type = "button";
        key.className = "key";
        key.style.gridColumn = geometry.start
          ? `${geometry.start} / span ${geometry.span}`
          : `span ${geometry.span}`;
        key.dataset.keyName = String(led.name);
        key.dataset.row = String(row);
        key.setAttribute("role", "gridcell");
        key.setAttribute("aria-label", `${displayName(led.name)}, row ${row + 1}, column ${Number(led.column) + 1}`);
        key.title = `${led.name} · slot ${led.matrix_slot ?? "unverified"}`;
        const label = document.createElement("span");
        label.className = "key-label";
        label.textContent = KEY_LABELS[led.name] || displayName(led.name);
        key.append(label);
        key.addEventListener("click", (event) => {
          state.activeRow = row;
          if (event.shiftKey || state.pattern[led.name] === state.paintColour) delete state.pattern[led.name];
          else state.pattern[led.name] = state.paintColour;
          paintKey(key, state.pattern[led.name]);
          updatePatternCount();
        });
        key.addEventListener("contextmenu", (event) => {
          event.preventDefault();
          delete state.pattern[led.name];
          paintKey(key, null);
          updatePatternCount();
        });
        rowNode.append(key);
        paintKey(key, state.pattern[led.name]);
      }
      grid.append(rowNode);
    }
    updatePatternCount();
  }

  function paintKey(key, value) {
    const painted = Boolean(value);
    key.dataset.painted = String(painted);
    if (painted) key.style.setProperty("--key-colour", value);
    else key.style.removeProperty("--key-colour");
  }

  function updatePatternCount() {
    const count = Object.keys(state.pattern).length;
    text($("pattern-count"), `${count} / ${state.leds.length || 66} painted`);
    $("commit-pattern").disabled = !$("flash-confirm").checked || count === 0 || !state.device;
  }

  function setPaintColour(value) {
    state.paintColour = colour(value);
    $("paint-colour").value = state.paintColour.toLowerCase();
    $("paint-preview").style.backgroundColor = state.paintColour;
    $("paint-preview").style.boxShadow = `0 0 12px ${state.paintColour}55`;
    text($("paint-value"), state.paintColour);
  }

  function renderMetadata(device) {
    state.device = device;
    state.deviceId = String(device.id || DEVICE_FALLBACK);
    state.leds = Array.isArray(device.led_map) ? device.led_map : [];
    setConnection("connected", "Device connected");
    text($("status-value"), `${device.led_count || state.leds.length || 0} mapped LEDs`);
    text($("status-detail"), `${device.max_frame_rate || 20} FPS global colour ceiling`);
    text($("identity-value"), `${Number(device.vendor_id).toString(16).padStart(4, "0").toUpperCase()} : ${Number(device.product_id).toString(16).padStart(4, "0").toUpperCase()}`);
    text($("identity-detail"), `${device.name || "Attack Shark X68HE"}${device.revision ? ` · rev ${device.revision}` : ""}`);
    text($("owner-value"), device.owner ? "Claimed" : "Available");
    text($("owner-detail"), device.owner ? "A stream currently owns the HID path" : "No active stream owner");
    text($("capture-value"), device.capabilities?.global_color_streaming ? "20 FPS / global" : "Unavailable");
    text($("capture-detail"), device.capabilities?.static_per_key ? "Static per-key is flash-backed" : "Static per-key unavailable");
    text($("device-name"), device.name);
    text($("internal-id"), device.internal_id);
    text($("revision"), device.revision);
    text($("led-count"), `${device.led_count || state.leds.length || 0} physical keys`);
    text($("static-storage"), device.capabilities?.static_per_key_storage || "Unsupported");
    renderCapabilities(device.capabilities || {});
    renderPresets(Array.isArray(device.capabilities?.preset_modes) ? device.capabilities.preset_modes : []);
    renderKeyboard();
  }

  function renderCapabilities(capabilities) {
    const list = $("capability-list");
    list.replaceChildren();
    const labels = [
      ["global_color_layers", "global layers"], ["global_color_streaming", "global output"], ["static_per_key", "flash patterns"], ["mapping_verified", "map verified"], ["streaming_supported", "volatile frames"],
    ];
    for (const [key, label] of labels) {
      const chip = document.createElement("span");
      chip.className = `capability${capabilities[key] ? "" : " muted"}`;
      chip.textContent = capabilities[key] ? `✓ ${label}` : `— ${label}`;
      list.append(chip);
    }
  }

  function renderPresets(modes) {
    const select = $("preset-mode");
    select.replaceChildren();
    if (!modes.length) {
      const option = document.createElement("option"); option.textContent = "No presets reported"; option.value = ""; select.append(option); return;
    }
    for (const mode of modes) {
      const option = document.createElement("option");
      option.value = String(mode); option.textContent = displayName(mode); select.append(option);
    }
    select.value = modes.includes("static") ? "static" : String(modes[0]);
  }

  function renderLightingState(current) {
    if (!current) return;
    if (current.mode_name && [...$("preset-mode").options].some((item) => item.value === current.mode_name)) {
      $("preset-mode").value = current.mode_name;
    }
    $("preset-colour").value = colour(current.rgb).toLowerCase();
    $("preset-brightness").value = String(current.brightness ?? 4);
    $("preset-speed").value = String(current.speed ?? 2);
    $("preset-option").value = String(current.option ?? 0);
    text($("brightness-output"), `${$("preset-brightness").value} / 4`);
    text($("speed-output"), `${$("preset-speed").value} / 4`);
  }

  function renderLayers(payload) {
    state.layers = Array.isArray(payload?.layers) ? payload.layers : [];
    const list = $("layer-list");
    list.replaceChildren();
    text($("layer-count"), state.layers.length);
    if (!state.layers.length) {
      const empty = document.createElement("p"); empty.className = "empty-state"; empty.textContent = "No active layers. Add a layer to claim the global colour path."; list.append(empty); return;
    }
    for (const layer of state.layers) {
      const row = document.createElement("div"); row.className = "layer-row";
      const name = document.createElement("div"); name.className = "layer-name";
      const dot = document.createElement("span"); dot.className = "layer-dot"; dot.style.setProperty("--layer-colour", colour(layer.color)); dot.style.backgroundColor = colour(layer.color); dot.setAttribute("aria-hidden", "true");
      const strong = document.createElement("strong"); strong.textContent = `${layer.source_id || "?"} / ${layer.layer_id || "?"}`; name.append(dot, strong);
      const priority = document.createElement("span"); priority.className = "layer-meta"; priority.textContent = `P${layer.priority ?? 0}`;
      const mode = document.createElement("span"); mode.className = "layer-meta"; mode.textContent = `${layer.blend_mode || "replace"} · ${Math.round(Number(layer.opacity ?? 1) * 100)}%`;
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "remove-layer"; remove.textContent = "remove"; remove.dataset.source = String(layer.source_id || ""); remove.dataset.layer = String(layer.layer_id || "");
      remove.addEventListener("click", () => removeLayer(remove.dataset.source, remove.dataset.layer));
      row.append(name, priority, mode, remove); list.append(row);
    }
  }

  async function refresh() {
    setConnection("unknown", "Scanning device");
    text($("status-value"), "Scanning local HID bus"); text($("status-detail"), "Reading /v1/devices…");
    try {
      const inventory = await request("/v1/devices");
      const devices = Array.isArray(inventory?.devices) ? inventory.devices : [];
      if (!devices.length) {
        setUnavailable(inventory?.busy ? "busy" : "error", inventory?.error || "Connect the X68HE and refresh.");
        renderLayers({ layers: [] });
        return;
      }
      const selected = devices.find((device) => device.id === DEVICE_FALLBACK) || devices[0];
      const metadata = await request(`/v1/devices/${byId(selected.id || DEVICE_FALLBACK)}`);
      renderMetadata(metadata);
      if (!metadata.owner) {
        try { renderLightingState(await request(`/v1/devices/${byId(state.deviceId)}/lighting/state`)); }
        catch (error) { if (error.status !== 409) toast(error.message, "warning"); }
      }
      try { renderLayers(await request(`/v1/devices/${byId(state.deviceId)}/lighting/global-layers`)); }
      catch (error) { renderLayers({ layers: [] }); if (error.status !== 501) toast(error.message, "warning"); }
      toast("Device metadata refreshed");
    } catch (error) {
      setUnavailable(error.status === 409 ? "busy" : "error", error.message);
      toast(error.message, "error");
    }
    text($("footer-time"), new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  }

  async function applyPreset(event) {
    event.preventDefault();
    if (!state.device) { toast("Connect the keyboard before applying a preset.", "warning"); return; }
    const body = { mode: $("preset-mode").value, color: $("preset-colour").value, brightness: Number($("preset-brightness").value), speed: Number($("preset-speed").value), option: Number($("preset-option").value) };
    try { await request(`/v1/devices/${byId(state.deviceId)}/lighting/preset`, { method: "PUT", body: JSON.stringify(body) }); toast(`Preset applied: ${displayName(body.mode)}`); await refresh(); }
    catch (error) { toast(error.message, error.status === 422 ? "warning" : "error"); }
  }

  async function commitPattern() {
    if (!state.device || !$("flash-confirm").checked) return;
    const colors = Object.assign({}, state.pattern);
    if (!Object.keys(colors).length) { toast("Paint at least one key before writing.", "warning"); return; }
    try {
      const result = await request(`/v1/devices/${byId(state.deviceId)}/lighting/custom`, { method: "PUT", body: JSON.stringify({ colors, background: state.background, confirm_flash_write: true }) });
      toast(result?.written === false ? "Pattern unchanged; no flash write was needed." : "Static pattern written to USERPIC slot 0.");
      $("flash-confirm").checked = false; updatePatternCount(); await refresh();
    } catch (error) { toast(error.message, error.status === 422 ? "warning" : "error"); }
  }

  async function saveLayer(event) {
    event.preventDefault();
    if (!state.device) { toast("Connect the keyboard before adding a live layer.", "warning"); return; }
    const layerId = $("layer-id").value.trim();
    const ttlRaw = $("layer-ttl").value.trim(); const fadeRaw = $("layer-fade").value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(layerId)) { toast("Layer ID must start with a letter or number and use only . _ -.", "warning"); return; }
    if (fadeRaw && !ttlRaw) { toast("Fade out needs a TTL.", "warning"); return; }
    const body = { color: $("layer-colour").value, priority: Number($("layer-priority").value), opacity: Number($("layer-opacity").value), blend_mode: $("layer-blend").value };
    if (ttlRaw) body.ttl_ms = Number(ttlRaw); if (fadeRaw) body.fade_out_ms = Number(fadeRaw);
    try { await request(`/v1/devices/${byId(state.deviceId)}/lighting/global-layers/${SOURCE_ID}/${byId(layerId)}`, { method: "PUT", body: JSON.stringify(body) }); toast(`Layer set: ${SOURCE_ID} / ${layerId}`); await refresh(); }
    catch (error) { toast(error.message, error.status === 422 ? "warning" : "error"); }
  }

  async function removeLayer(source, layer) {
    if (!state.device) { toast("Connect the keyboard before changing layers.", "warning"); return; }
    try { await request(`/v1/devices/${byId(state.deviceId)}/lighting/global-layers/${byId(source)}/${byId(layer)}`, { method: "DELETE" }); toast(`Layer removed: ${source} / ${layer}`); await refresh(); }
    catch (error) { toast(error.message, "error"); }
  }

  async function clearLayers() {
    if (!state.device) { toast("Connect the keyboard before changing layers.", "warning"); return; }
    try { await request(`/v1/devices/${byId(state.deviceId)}/lighting/global-layers/${SOURCE_ID}`, { method: "DELETE" }); toast("All web-ui layers cleared."); await refresh(); }
    catch (error) { toast(error.message, "error"); }
  }

  function clearDraft() { state.pattern = Object.create(null); renderKeyboard(); toast("Draft cleared"); }
  function fillRow() { for (const led of state.leds.filter((item) => Number(item.row) === state.activeRow)) state.pattern[led.name] = state.paintColour; renderKeyboard(); toast(`Row ${state.activeRow + 1} filled`); }

  function wire() {
    $("refresh-button").addEventListener("click", refresh); $("preset-form").addEventListener("submit", applyPreset); $("commit-pattern").addEventListener("click", commitPattern); $("layer-form").addEventListener("submit", saveLayer); $("clear-layers").addEventListener("click", clearLayers); $("clear-pattern").addEventListener("click", clearDraft); $("fill-row").addEventListener("click", fillRow);
    $("paint-colour").addEventListener("input", (event) => setPaintColour(event.target.value));
    $("background-colour").addEventListener("input", (event) => { state.background = colour(event.target.value); text($("background-value"), state.background); });
    $("flash-confirm").addEventListener("change", updatePatternCount);
    for (const swatch of document.querySelectorAll(".quick-swatch")) swatch.addEventListener("click", () => setPaintColour(swatch.dataset.colour));
    for (const id of [["preset-brightness", "brightness-output"], ["preset-speed", "speed-output"]]) $(id[0]).addEventListener("input", () => text($(id[1]), `${$(id[0]).value} / 4`));
    $("layer-opacity").addEventListener("input", () => text($("opacity-output"), `${Math.round(Number($("layer-opacity").value) * 100)}%`));
    document.addEventListener("keydown", (event) => { if (event.key.toLowerCase() === "r" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) refresh(); });
    setPaintColour(state.paintColour); text($("background-value"), state.background); renderKeyboard(); refresh();
  }

  document.addEventListener("DOMContentLoaded", wire);
}());
