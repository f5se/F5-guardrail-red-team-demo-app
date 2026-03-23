const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const btnSend = document.getElementById("btnSend");
const btnClear = document.getElementById("btnClear");
const btnLogout = document.getElementById("btnLogout");
const chatTitleEl = document.getElementById("chatTitle");
const modeBadgeEl = document.getElementById("modeBadge");
const kbSkillBadgeEl = document.getElementById("kbSkillBadge");
const f5GuardrailOnlyBadgeEl = document.getElementById("f5GuardrailOnlyBadge");
const directModeToggleEl = document.getElementById("directModeToggle");
const directModeHintEl = document.getElementById("directModeHint");
const localEngineCards = [
  document.getElementById("cardPattern"),
  document.getElementById("cardHeuristic"),
  document.getElementById("cardToxic"),
  document.getElementById("cardProtect")
].filter(Boolean);
const navButtons = Array.from(document.querySelectorAll(".navBtn"));

// 攻击示例面板元素
const attackCardEl = document.getElementById("attackCard");
const attackPanelBodyEl = document.getElementById("attackPanelBody");
const attackPanelToggleEl = document.getElementById("attackPanelToggle");
const attackPresets = Array.isArray(window.ATTACK_PRESETS) ? window.ATTACK_PRESETS : [];
const guardrailIntegrationPresets = Array.isArray(window.GUARDRAIL_INTEGRATION_PRESETS) ? window.GUARDRAIL_INTEGRATION_PRESETS : [];
let attackTooltipEl = null;
let activeView = "CHAT";
let currentBackendProviderName = "";
let directModeAvailable = false;

async function authFetch(url, options) {
  const resp = await fetch(url, options);
  if (resp.status === 401) {
    clearSessionBadgeOverrides();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return resp;
}

function setLogoutButtonLabel(username) {
  if (!btnLogout) return;
  const name = (username || "").trim();
  btnLogout.textContent = name
    ? `退出登录（${name}） · Logout`
    : "退出登录 · Logout";
}

function setDirectModeAvailability(available, reason) {
  directModeAvailable = !!available;
  if (!directModeToggleEl) return;
  directModeToggleEl.disabled = !directModeAvailable;
  if (!directModeAvailable) {
    directModeToggleEl.checked = false;
  }
  if (directModeHintEl) {
    directModeHintEl.textContent = directModeAvailable
      ? "默认关闭 · Direct mode OFF by default"
      : (reason || "未配置直连参数 · Direct mode unavailable");
    directModeHintEl.classList.toggle("unavailable", !directModeAvailable);
  }
}
setDirectModeAvailability(false, "直连配置检测中 · Checking direct mode config");

function getCurrentAttackPresets() {
  return activeView === "GUARDRAIL_INTEGRATION" ? guardrailIntegrationPresets : attackPresets;
}

function ensureAttackTooltip() {
  if (attackTooltipEl) return attackTooltipEl;
  const div = document.createElement("div");
  div.className = "attackTooltip";
  div.style.display = "none";
  document.body.appendChild(div);
  attackTooltipEl = div;
  return div;
}

function renderAttackPresets() {
  if (!attackPanelBodyEl) return;

  var presets = getCurrentAttackPresets();
  attackPanelBodyEl.innerHTML = "";

  if (!presets.length) {
    const empty = document.createElement("div");
    empty.className = "attackEmpty";
    empty.textContent = activeView === "GUARDRAIL_INTEGRATION"
      ? "当前没有可用的攻击示例，请在 config/guardrail-integration-presets.json 中配置。"
      : "当前没有可用的攻击示例，请在 config/attack-presets.json 中配置。";
    attackPanelBodyEl.appendChild(empty);
    return;
  }

  // 分组：按 category 聚合
  const groups = {};
  presets.forEach(p => {
    const cat = (p.category || "未分类").toString();
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(p);
  });

  Object.keys(groups).sort().forEach(category => {
    const items = groups[category];

    const catEl = document.createElement("div");
    catEl.className = "attackCategory";

    const headerEl = document.createElement("button");
    headerEl.type = "button";
    headerEl.className = "attackCategoryHeader";
    headerEl.setAttribute("data-category", category);
    headerEl.setAttribute("aria-expanded", "true");
    headerEl.innerHTML = `<span class="attackCategoryName">${escapeHtml(category)}</span><span class="attackCategoryIcon">▼</span>`;

    const listEl = document.createElement("div");
    listEl.className = "attackList";

    items.forEach(preset => {
      const itemEl = document.createElement("button");
      itemEl.type = "button";
      itemEl.className = "attackItem";
      itemEl.textContent = preset.title || preset.id || "(未命名攻击示例)";
      // 自定义 tooltip 展示完整攻击内容
      const fullPrompt = String(preset.prompt || "");
      let lastMouseX = 0;
      let lastMouseY = 0;

      itemEl.addEventListener("mouseenter", () => {
        if (!fullPrompt) return;
        const tip = ensureAttackTooltip();
        tip.textContent = fullPrompt;
        tip.style.display = "block";

        // 初次根据上次记录的位置进行定位，稍后 mousemove 会精细调整
        const x = lastMouseX || (itemEl.getBoundingClientRect().right + 8);
        const y = lastMouseY || itemEl.getBoundingClientRect().top;
        tip.style.left = x + "px";
        tip.style.top = y + "px";
      });

      itemEl.addEventListener("mousemove", (ev) => {
        lastMouseX = ev.clientX;
        lastMouseY = ev.clientY;
        if (!attackTooltipEl || attackTooltipEl.style.display === "none") return;
        const tip = attackTooltipEl;
        const padding = 10;
        let x = ev.clientX + 14;
        let y = ev.clientY + 12;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const rect = tip.getBoundingClientRect();
        if (x + rect.width + padding > vw) {
          x = ev.clientX - rect.width - 14;
        }
        if (y + rect.height + padding > vh) {
          y = ev.clientY - rect.height - 12;
        }
        tip.style.left = x + "px";
        tip.style.top = y + "px";
      });

      itemEl.addEventListener("mouseleave", () => {
        if (attackTooltipEl) {
          attackTooltipEl.style.display = "none";
        }
      });

      itemEl.addEventListener("click", (ev) => {
        const text = String(preset.prompt || "");
        if (!text) return;

        if (activeView === "GUARDRAIL_INTEGRATION") {
          const gintPromptEl = document.getElementById("gintPrompt");
          if (gintPromptEl) {
            if (ev.shiftKey && gintPromptEl.value) {
              gintPromptEl.value = gintPromptEl.value.replace(/\s*$/, "") + "\n\n" + text;
            } else {
              gintPromptEl.value = text;
            }
            gintPromptEl.focus();
          }
          return;
        }
        if (!inputEl) return;
        // 默认覆盖；按住 Shift 追加
        if (ev.shiftKey && inputEl.value) {
          inputEl.value = inputEl.value.replace(/\s*$/,"") + "\n\n" + text;
        } else {
          inputEl.value = text;
        }
        inputEl.focus();
      });
      listEl.appendChild(itemEl);
    });

    headerEl.addEventListener("click", () => {
      const expanded = headerEl.getAttribute("aria-expanded") === "true";
      headerEl.setAttribute("aria-expanded", expanded ? "false" : "true");
      headerEl.querySelector(".attackCategoryIcon").textContent = expanded ? "▶" : "▼";
      listEl.style.display = expanded ? "none" : "";
    });

    catEl.appendChild(headerEl);
    catEl.appendChild(listEl);
    attackPanelBodyEl.appendChild(catEl);
  });
}

if (attackPanelToggleEl && attackPanelBodyEl) {
  attackPanelToggleEl.addEventListener("click", () => {
    const expanded = attackPanelToggleEl.getAttribute("aria-expanded") === "true";
    attackPanelToggleEl.setAttribute("aria-expanded", expanded ? "false" : "true");
    attackPanelToggleEl.textContent = expanded ? "展开" : "折叠";
    attackPanelBodyEl.style.display = expanded ? "none" : "";
  });
}

// 初始渲染攻击示例面板
renderAttackPresets();

// Guardrail panel elements
const guardrailCardEl = document.getElementById("guardrailCard");
const guardrailEmptyEl = document.getElementById("guardrailEmpty");
const guardrailContentEl = document.getElementById("guardrailContent");
const guardrailOutcomeEl = document.getElementById("guardrailOutcome");
const guardrailOutcomeLabelEl = document.getElementById("guardrailOutcomeLabel");
const guardrailOutcomeDescEl = document.getElementById("guardrailOutcomeDesc");
const guardrailSummaryNumberEl = document.getElementById("guardrailSummaryNumber");
const guardrailSummaryTextEl = document.getElementById("guardrailSummaryText");
const guardrailSummaryHintEl = document.getElementById("guardrailSummaryHint");
const guardrailListHeaderCountEl = document.getElementById("guardrailListHeaderCount");
const guardrailListEl = document.getElementById("guardrailList");

const chatView = document.getElementById("chatView");
const settingsView = document.getElementById("settingsView");
const toggleMultiTurnEl = document.getElementById("toggleMultiTurn");
const toggleAgentSkillEl = document.getElementById("toggleAgentSkill");
const toggleGuardrailDebugEl = document.getElementById("toggleGuardrailDebug");
const toggleF5GuardrailOnlyEl = document.getElementById("toggleF5GuardrailOnly");
const kbDirInputEl = document.getElementById("kbDirInput");

function asBool(v){
  if (typeof v === "boolean") return v;
  if (typeof v === "string") {
    return ["1", "true", "yes", "on"].includes(v.trim().toLowerCase());
  }
  return !!v;
}

// =====================
// ENGINE STATUS UPDATER
// =====================
function updateEngines(engines){
  const map = {
    pattern: "statusPattern",
    heuristic: "statusHeuristic",
    toxic: "statusToxic",
    protectai: "statusProtect",
    f5: "statusF5"
  };

  for (let key in map){
    const el = document.getElementById(map[key]);
    if(!el) continue;

    // Reset
    el.className = "engineStatus idle";
    el.textContent = "IDLE";

    if (!engines || !engines[key]) continue;

    const e = engines[key];
    const s = e.status || "IDLE";

    if (s === "IDLE") {
      el.className = "engineStatus idle";
    } else {
      el.className = "engineStatus " + (s === "PASS" ? "pass" : "block");
    }

    let text = s;

    if (e.label) {
      text += " · " + e.label;
    }

    if (e.score !== undefined && e.score !== null){
      text += " (" + e.score + ")";
    }

    el.textContent = text;
  }
}

// =========================
// GUARDRAIL RESULT PANEL
// =========================
function resetGuardrailPanel(){
  if (!guardrailCardEl) return;
  if (guardrailEmptyEl) guardrailEmptyEl.style.display = "";
  if (guardrailContentEl) guardrailContentEl.style.display = "none";
  if (guardrailOutcomeEl) {
    guardrailOutcomeEl.classList.remove("cleared","flagged","blocked");
  }
  if (guardrailOutcomeLabelEl) guardrailOutcomeLabelEl.textContent = "";
  if (guardrailOutcomeDescEl) guardrailOutcomeDescEl.textContent = "";
  if (guardrailSummaryNumberEl) guardrailSummaryNumberEl.textContent = "0 / 0";
  if (guardrailSummaryTextEl) guardrailSummaryTextEl.textContent = "Failed / Total";
  if (guardrailSummaryHintEl) guardrailSummaryHintEl.textContent = "";
  if (guardrailListHeaderCountEl) guardrailListHeaderCountEl.textContent = "";
  if (guardrailListEl) guardrailListEl.innerHTML = "";
}

/** Shared: resolve root-level scanners map from guardrail (for friendly names). Used by F5 Guardrail Result panel and Guardrail Decision Panel. */
function getScannersRootFromGuardrail(guardrail) {
  if (!guardrail || !guardrail.scanners) return null;
  const inner = guardrail.scanners.scanners;
  const isInnerMap = inner && typeof inner === "object" && !Array.isArray(inner);
  const direct = typeof guardrail.scanners === "object" && !Array.isArray(guardrail.scanners) && !("scanners" in guardrail.scanners) && !("configs" in guardrail.scanners) ? guardrail.scanners : null;
  return isInnerMap ? inner : direct;
}

function updateGuardrailPanel(guardrail){
  if (!guardrailCardEl) return;

  if (!guardrail || typeof guardrail !== "object" || !guardrail.result){
    resetGuardrailPanel();
    return;
  }

  const result = guardrail.result || {};
  const scannersRoot = getScannersRootFromGuardrail(guardrail);
  const scannerResults = Array.isArray(result.scannerResults) ? result.scannerResults : [];

  if (guardrailEmptyEl) guardrailEmptyEl.style.display = "none";
  if (guardrailContentEl) guardrailContentEl.style.display = "";

  // Outcome block
  const rawOutcome = (result.outcome || "").toString();
  const outcome = rawOutcome.toLowerCase();
  if (guardrailOutcomeEl){
    guardrailOutcomeEl.classList.remove("cleared","flagged","blocked","redacted");
    if (outcome === "cleared") guardrailOutcomeEl.classList.add("cleared");
    else if (outcome === "flagged") guardrailOutcomeEl.classList.add("flagged");
    else if (outcome === "blocked") guardrailOutcomeEl.classList.add("blocked");
    else if (outcome === "redacted") guardrailOutcomeEl.classList.add("redacted");
  }
  let labelText = rawOutcome || "Unknown";
  let descText = "";
  if (outcome === "cleared"){
    labelText = "Cleared";
    descText = "All guardrails passed, prompt was sent to providers.";
  } else if (outcome === "flagged"){
    labelText = "Flagged";
    descText = "At least one guardrail failed, but the prompt was still sent to providers.";
  } else if (outcome === "blocked"){
    labelText = "Blocked";
    descText = "At least one guardrail failed and the prompt was not sent to providers or response from LLM was blocked.";
  } else if (outcome === "redacted"){
    labelText = "Redacted";
    descText = "The Guardrail system has redacted part of the content.";
  } else {
    descText = "Guardrail outcome is unknown or not available.";
  }
  if (guardrailOutcomeLabelEl) guardrailOutcomeLabelEl.textContent = labelText;
  if (guardrailOutcomeDescEl) guardrailOutcomeDescEl.textContent = descText;

  // Summary
  const total = scannerResults.length;
  const failed = scannerResults.filter(r => (r.outcome || "").toString().toLowerCase() === "failed").length;
  if (guardrailSummaryNumberEl) guardrailSummaryNumberEl.textContent = failed + " / " + total;
  if (guardrailSummaryTextEl) guardrailSummaryTextEl.textContent = "Failed / Total";
  if (guardrailSummaryHintEl){
    if (!total){
      guardrailSummaryHintEl.textContent = "No scanner results were returned for this prompt.";
    } else if (failed === 0){
      guardrailSummaryHintEl.textContent = "All scanners passed for this prompt.";
    } else {
      guardrailSummaryHintEl.textContent = failed + " scanner(s) reported failed outcome.";
    }
  }

  // Build scanner meta map from root-level scanners{}: key = scanner id (string), value = { name, direction, ... }
  // When guardrail_verbose is true, API returns root.scanners[id] with friendly name; we look up by result.scannerResults[].scannerId or .id
  const metaMap = {};
  if (scannersRoot && typeof scannersRoot === "object" && !Array.isArray(scannersRoot)){
    Object.keys(scannersRoot).forEach(k => {
      const s = scannersRoot[k];
      if (!s) return;
      const sid = (s.id != null ? s.id : k).toString();
      metaMap[sid] = s;
    });
  }

  // List
  if (guardrailListHeaderCountEl) guardrailListHeaderCountEl.textContent = total ? (total + " scanners") : "";

  if (!guardrailListEl) return;
  if (!total){
    guardrailListEl.innerHTML = "<div class=\"scannerItem\"><div class=\"scannerMain\"><div class=\"scannerName\">No scanners</div><div class=\"scannerMetaRow\"><span>No scanner results available for this prompt.</span></div></div></div>";
    return;
  }

  // Sort: failed first, then passed (stable by original index)
  const sortedResults = [...scannerResults].sort((a, b) => {
    const aFailed = (a.outcome || "").toString().toLowerCase() === "failed";
    const bFailed = (b.outcome || "").toString().toLowerCase() === "failed";
    if (aFailed && !bFailed) return -1;
    if (!aFailed && bFailed) return 1;
    return 0;
  });

  let html = "";
  const formatDirection = (dir) => {
    const d = (dir || "").toString().toLowerCase();
    if (d === "request") return "Request";
    if (d === "response") return "Response";
    if (d === "both") return "Both";
    return "N/A";
  };

  sortedResults.forEach(r => {
    // Look up scanner by id: result.scannerResults[].scannerId or .id -> root.scanners[id].name
    const sid = (r.scannerId != null ? r.scannerId : r.id != null ? r.id : "").toString();
    const meta = sid && metaMap[sid] ? metaMap[sid] : null;
    const versionName = r.scannerVersionMeta && r.scannerVersionMeta.name;
    const name = (meta && meta.name) || (versionName && String(versionName)) || sid || "Unnamed scanner";
    const rawDirection = (meta && meta.direction) || r.scanDirection || r.direction;
    const directionLabel = formatDirection(rawDirection);

    // Determine source type from scannerVersionMeta.createdBy:
    // "system" => System (built-in), otherwise => Custom.
    const createdBy = r.scannerVersionMeta && r.scannerVersionMeta.createdBy;
    let sourceLabel = "Unknown";
    let sourceClass = "unknown";
    if (typeof createdBy === "string") {
      const c = createdBy.toLowerCase();
      if (c === "system") {
        sourceLabel = "System";
        sourceClass = "system";
      } else {
        sourceLabel = "Custom";
        sourceClass = "custom";
      }
    }
    const outcomeRaw = (r.outcome || "").toString();
    const outcomeLower = outcomeRaw.toLowerCase();
    const statusClass = outcomeLower === "failed" ? "failed" : "pass";
    const statusLabel = outcomeLower === "failed" ? "Failed" : "Passed";
    const itemClass = "scannerItem" + (outcomeLower === "failed" ? " scannerItem--failed" : "");

    html +=
      "<div class=\"" + itemClass + "\">" +
        "<div class=\"scannerMain\">" +
          "<div class=\"scannerName\">" + escapeHtml(name) + "</div>" +
          "<div class=\"scannerMetaRow\">" +
            "<span>Direction: " + escapeHtml(directionLabel) + "</span>" +
          "</div>" +
        "</div>" +
        "<div class=\"scannerBadges\">" +
          "<div class=\"scannerStatus " + statusClass + "\">" + statusLabel + "</div>" +
          "<div class=\"scannerSource " + sourceClass + "\">" + sourceLabel + "</div>" +
        "</div>" +
      "</div>";
  });

  guardrailListEl.innerHTML = html;
}

let isSending = false;
const persistedBadgeSettings = {
  multiTurn: false,
  agentSkill: false,
  f5GuardrailOnly: false
};
const sessionBadgeOverrides = {
  multiTurn: null,
  agentSkill: null,
  f5GuardrailOnly: null
};
let activeSettingsUsername = "";

function getBadgeSessionStorageKey(username){
  const u = String(username || "").trim();
  return u ? ("badgeSessionOverrides:" + u) : "";
}

function normalizeOverrideValue(v){
  if (typeof v === "boolean") return v;
  return null;
}

function loadSessionBadgeOverrides(username){
  activeSettingsUsername = String(username || "").trim();
  sessionBadgeOverrides.multiTurn = null;
  sessionBadgeOverrides.agentSkill = null;
  sessionBadgeOverrides.f5GuardrailOnly = null;
  const key = getBadgeSessionStorageKey(activeSettingsUsername);
  if (!key) return;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;
    sessionBadgeOverrides.multiTurn = normalizeOverrideValue(parsed.multiTurn);
    sessionBadgeOverrides.agentSkill = normalizeOverrideValue(parsed.agentSkill);
    sessionBadgeOverrides.f5GuardrailOnly = normalizeOverrideValue(parsed.f5GuardrailOnly);
  } catch (_) {
    // ignore invalid sessionStorage value
  }
}

function persistSessionBadgeOverrides(){
  const key = getBadgeSessionStorageKey(activeSettingsUsername);
  if (!key) return;
  try {
    sessionStorage.setItem(key, JSON.stringify(sessionBadgeOverrides));
  } catch (_) {
    // ignore storage errors
  }
}

function clearSessionBadgeOverrides(){
  const key = getBadgeSessionStorageKey(activeSettingsUsername);
  sessionBadgeOverrides.multiTurn = null;
  sessionBadgeOverrides.agentSkill = null;
  sessionBadgeOverrides.f5GuardrailOnly = null;
  if (!key) return;
  try {
    sessionStorage.removeItem(key);
  } catch (_) {
    // ignore storage errors
  }
}

function uuidv4(){
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === "x" ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

let conversationId = uuidv4();

function setMultiTurnEnabled(v){
  if (toggleMultiTurnEl) toggleMultiTurnEl.checked = !!v;
  refreshModeBadge();
}
function getMultiTurnEnabled(){
  return getEffectiveMultiTurnEnabled();
}
setMultiTurnEnabled(false);

function setEnterpriseKBSkillEnabled(v){
  if (!kbSkillBadgeEl) return;
  if (toggleAgentSkillEl) toggleAgentSkillEl.checked = !!v;
  refreshEnterpriseKBSkillBadge();
}

function setF5GuardrailOnlyBadge(v){
  if (toggleF5GuardrailOnlyEl) toggleF5GuardrailOnlyEl.checked = !!v;
  refreshF5GuardrailOnlyBadge();
}

function getEffectiveMultiTurnEnabled(){
  if (sessionBadgeOverrides.multiTurn === null) return !!persistedBadgeSettings.multiTurn;
  return !!sessionBadgeOverrides.multiTurn;
}
function getEffectiveAgentSkillEnabled(){
  if (sessionBadgeOverrides.agentSkill === null) return !!persistedBadgeSettings.agentSkill;
  return !!sessionBadgeOverrides.agentSkill;
}
function getEffectiveF5GuardrailOnlyEnabled(){
  if (sessionBadgeOverrides.f5GuardrailOnly === null) return !!persistedBadgeSettings.f5GuardrailOnly;
  return !!sessionBadgeOverrides.f5GuardrailOnly;
}

function refreshModeBadge(){
  if (!modeBadgeEl) return;
  const v = getEffectiveMultiTurnEnabled();
  modeBadgeEl.textContent = v ? "Multi-turn" : "Single-turn";
  modeBadgeEl.classList.toggle("multiTurnOn", !!v);
  modeBadgeEl.classList.toggle("multiTurnOff", !v);
  modeBadgeEl.setAttribute("aria-pressed", v ? "true" : "false");
}

function refreshEnterpriseKBSkillBadge(){
  if (!kbSkillBadgeEl) return;
  const v = getEffectiveAgentSkillEnabled();
  kbSkillBadgeEl.textContent = v ? "Enterprise KB Skill ON" : "Enterprise KB Skill OFF";
  kbSkillBadgeEl.classList.toggle("kbSkillOn", !!v);
  kbSkillBadgeEl.classList.toggle("kbSkillOff", !v);
  kbSkillBadgeEl.setAttribute("aria-pressed", v ? "true" : "false");
}

function refreshF5GuardrailOnlyBadge(){
  if (!f5GuardrailOnlyBadgeEl) return;
  const v = getEffectiveF5GuardrailOnlyEnabled();
  f5GuardrailOnlyBadgeEl.textContent = v ? "F5 Guardrail Only ON" : "F5 Guardrail Only OFF";
  f5GuardrailOnlyBadgeEl.classList.toggle("f5GuardrailOnlyOn", !!v);
  f5GuardrailOnlyBadgeEl.classList.toggle("f5GuardrailOnlyOff", !v);
  f5GuardrailOnlyBadgeEl.setAttribute("aria-pressed", v ? "true" : "false");
  updateLocalEngineCardsGray();
}

/** 当 F5 Guardrail Only 为 ON 时，本地引擎卡片置灰（与 Enterprise KB Skill 无关） */
function updateLocalEngineCardsGray(){
  const f5OnlyOn = getEffectiveF5GuardrailOnlyEnabled();
  localEngineCards.forEach(el => {
    if (!el) return;
    el.classList.toggle("localDisabled", !!f5OnlyOn);
  });
}

setEnterpriseKBSkillEnabled(!!toggleAgentSkillEl?.checked);
setF5GuardrailOnlyBadge(!!toggleF5GuardrailOnlyEl?.checked);
updateLocalEngineCardsGray();

toggleMultiTurnEl.addEventListener("change", () => {
  sessionBadgeOverrides.multiTurn = null;
  persistedBadgeSettings.multiTurn = !!toggleMultiTurnEl.checked;
  refreshModeBadge();
  saveSettings(false);

  // 🔥 RESET CONVERSATION
  conversationId = uuidv4();

  // Optional UX: clear chat window
  messagesEl.innerHTML = "";
  addBubble("assistant","Hi there! How can I help?");
});

const redteamView = document.getElementById("redteamView");
const guardrailIntegrationView = document.getElementById("guardrailIntegrationView");
const testGuideView = document.getElementById("testGuideView");
const testGuideContentEl = document.getElementById("testGuideContent");
const engineRow = document.getElementById("engineRow");
const layoutEl = document.querySelector(".layout");

let testGuideLoaded = false;

async function loadTestGuide(){
  if (!testGuideContentEl) return;
  if (testGuideLoaded) return;
  testGuideContentEl.innerHTML = `<div class="mdDoc__status">加载中…</div>`;
  try {
    const resp = await authFetch("/api/test-guide", { cache: "no-cache" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const md = await resp.text();
    testGuideContentEl.innerHTML = renderMarkdown(md);
    testGuideLoaded = true;
  } catch (e) {
    const msg = (e && e.message) ? e.message : String(e);
    testGuideContentEl.innerHTML = `<div class="mdDoc__status mdDoc__status--error">加载失败：${escapeHtml(msg)}</div>`;
  }
}

function setActiveView(view){
  activeView = view;
  navButtons.forEach(b => b.classList.toggle("active", b.dataset.view === view));

  chatView.style.display = "none";
  settingsView.style.display = "none";
  redteamView.style.display = "none";
  if (guardrailIntegrationView) guardrailIntegrationView.style.display = "none";
  if (testGuideView) testGuideView.style.display = "none";

  const chatOnlyEls = [engineRow, modeBadgeEl, kbSkillBadgeEl, f5GuardrailOnlyBadgeEl, btnClear];
  chatOnlyEls.forEach(el => { if(el) el.style.display = "none"; });

  const subEl = document.querySelector(".sub");

  if (view === "CHAT"){
    chatTitleEl.textContent = "AI Assistant";
    chatView.style.display = "";
    chatOnlyEls.forEach(el => { if(el) el.style.display = ""; });
    if (attackCardEl) attackCardEl.style.display = "";
    setChatSubtitle();
    if (guardrailCardEl) guardrailCardEl.style.display = "";
    if (layoutEl) layoutEl.classList.add("layout--with-guardrail");
    inputEl.focus();
  } else {
    if (attackCardEl) attackCardEl.style.display = "none";
    if (guardrailCardEl) guardrailCardEl.style.display = "none";
    if (layoutEl) layoutEl.classList.remove("layout--with-guardrail");
    if (view === "SETTINGS"){
      chatTitleEl.textContent = "Settings";
      settingsView.style.display = "";
      if (subEl) subEl.textContent = "Configure detection engines and thresholds";
    } else if (view === "REDTEAM"){
      chatTitleEl.textContent = "Red Team Pipeline";
      redteamView.style.display = "";
      if (subEl) subEl.textContent = "Simulated DevSecOps pipeline with F5 AI Red Team";
    } else if (view === "GUARDRAIL_INTEGRATION"){
      chatTitleEl.textContent = "Guardrail Integration";
      if (guardrailIntegrationView) guardrailIntegrationView.style.display = "";
      if (attackCardEl) attackCardEl.style.display = "";
      if (subEl) subEl.textContent = "F5 AI Guardrail 与 LLM Provider 集成架构与安全检查流程演示";
    } else if (view === "TEST_GUIDE"){
      chatTitleEl.textContent = "Test Guide";
      if (testGuideView) testGuideView.style.display = "";
      if (subEl) subEl.textContent = "使用说明与测试指引（Markdown 渲染）";
      loadTestGuide();
    }
  }
  if (view === "CHAT" || view === "GUARDRAIL_INTEGRATION") renderAttackPresets();
}
navButtons.forEach(btn => {
  btn.addEventListener("click", () => setActiveView(btn.dataset.view));
});

function buildChatSubtitle(){
  const provider = (currentBackendProviderName || "").trim();
  return provider
    ? `F5 AI Demo Chatbot · Connected to Backend ${provider}`
    : "F5 AI Demo Chatbot · Connected to Backend LLM";
}

function setChatSubtitle(){
  const subEl = document.querySelector(".sub");
  if (!subEl) return;
  subEl.textContent = buildChatSubtitle();
}

function addBubble(role, text, extraClass=""){
  const div = document.createElement("div");
  div.className = "bubble " + role + (extraClass ? (" " + extraClass) : "");
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function escapeHtml(s){
  return String(s)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

/** 将 Markdown 转为安全 HTML；无库时退回纯文本+换行 */
function renderMarkdown(text){
  const s = String(text || "").trim();
  if (!s) return "";
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    return escapeHtml(s).replace(/\n/g, "<br/>");
  }
  try {
    const raw = (typeof marked.parse === "function" ? marked.parse(s) : marked(s));
    return DOMPurify.sanitize(raw);
  } catch (e) {
    return escapeHtml(s).replace(/\n/g, "<br/>");
  }
}

function isRejected(text){
  const t = (text || "").trim();
  return t.startsWith("Prompt Rejected") || t.startsWith("Response Rejected");
}

function renderRejectedBubble(el, fullText){
  const safe = escapeHtml(fullText);
  const parts = safe.split("\n");
  const title = parts.shift() || "";
  const body = parts.join("\n").trim();

  el.classList.add("rejected");
  el.innerHTML =
    `<span class="rejectTitle">${title}</span>` +
    (body ? `<div>${body.replaceAll("\n","<br/>")}</div>` : "");
}

async function typeIntoBubble(el, fullText, speedMs = 10){
  el.textContent = "";
  const text = String(fullText || "");
  for (let i = 0; i < text.length; i++){
    el.textContent += text[i];
    messagesEl.scrollTop = messagesEl.scrollHeight;
    await new Promise(r => setTimeout(r, speedMs));
  }
}

async function send(){
  if (isSending) return;
  if (activeView !== "CHAT") setActiveView("CHAT");

  const msg = inputEl.value.trim();
  if(!msg) return;
  const useDirectMode = !!(directModeToggleEl && directModeToggleEl.checked && !directModeToggleEl.disabled);

  isSending = true;
  btnSend.disabled = true;
  inputEl.disabled = true;

  addBubble("user", msg, useDirectMode ? "direct-mode" : "");
  inputEl.value = "";

  const assistantBubble = addBubble("assistant", "…");

  try{
    const endpoint = useDirectMode ? "/api/chat-direct" : "/api/chat";
    const requestBody = useDirectMode
      ? {
          messages: [
            { role: "user", content: msg }
          ],
          agent_skill_enabled: getEffectiveAgentSkillEnabled()
        }
      : {
          message: msg,
          conversation_id: conversationId,
          multi_turn: getEffectiveMultiTurnEnabled(),
          agent_skill_enabled: getEffectiveAgentSkillEnabled(),
          f5_guardrail_only: getEffectiveF5GuardrailOnlyEnabled()
        };
    const res = await authFetch(endpoint, {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify(requestBody)
    });

    const data = await res.json();

    if(!res.ok){
      assistantBubble.textContent = "" + (data.detail || data.error || ("HTTP " + res.status));
      return;
    }

    const reply = data.reply || "(empty reply)";
    if (useDirectMode) {
      updateEngines(null);
      resetGuardrailPanel();
    } else {
      updateEngines(data.engines);
      if (data.guardrail) {
        updateGuardrailPanel(data.guardrail);
      } else {
        // If backend did not send guardrail payload, keep previous or reset.
        // Here we choose to reset to avoid showing stale data for incompatible responses.
        resetGuardrailPanel();
      }
      if (isRejected(reply)){
        renderRejectedBubble(assistantBubble, reply);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return;
      }
    }

    assistantBubble.textContent = "";
    assistantBubble.classList.add("md");
    assistantBubble.innerHTML = renderMarkdown(reply);
    messagesEl.scrollTop = messagesEl.scrollHeight;

  }catch(e){
    assistantBubble.textContent = "Failed to reach backend: " + e.message;
  } finally {
    isSending = false;
    btnSend.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }
}

btnSend.addEventListener("click", send);

btnClear.addEventListener("click", () => {
  messagesEl.innerHTML = "";
  addBubble("assistant","Hi there! How can I help?");
  conversationId = uuidv4();
  updateEngines(null);
  resetGuardrailPanel();
});

btnLogout?.addEventListener("click", async () => {
  clearSessionBadgeOverrides();
  try {
    await authFetch("/api/logout", { method: "POST" });
  } catch (_) {
    // ignore and continue to login page
  }
  window.location.href = "/login";
});

inputEl.addEventListener("keydown", (e) => {
  if(e.key === "Enter" && !e.shiftKey){
    e.preventDefault();
    send();
  }
});

// ======================
// SETTINGS LOAD / SAVE
// ======================
async function loadSettings(){
  try{
    const r = await authFetch("/api/settings", { cache: "no-store" });
    if(!r.ok) return;
    const s = await r.json();
    const username = String(s.username || "").trim();
    setLogoutButtonLabel(username);
    if (username && username !== activeSettingsUsername) {
      loadSessionBadgeOverrides(username);
    }
    persistedBadgeSettings.multiTurn = asBool(s.multi_turn_enabled);
    setMultiTurnEnabled(persistedBadgeSettings.multiTurn);

    document.getElementById("patternBox").value = s.patterns || "";
    document.getElementById("heuristicSlider").value = s.heuristic_threshold || 6;
    document.getElementById("toxSlider").value = s.toxic_threshold || 0.75;
    document.getElementById("piSlider").value = s.pi_threshold || 0.7;
    document.getElementById("heuristicVal").textContent = s.heuristic_threshold;
    document.getElementById("toxVal").textContent = s.toxic_threshold;
    document.getElementById("piVal").textContent = s.pi_threshold;

    if (toggleAgentSkillEl) {
      const enabled = asBool(s.agent_skill_enabled);
      persistedBadgeSettings.agentSkill = enabled;
      setEnterpriseKBSkillEnabled(enabled);
    }
    if (toggleGuardrailDebugEl) {
      toggleGuardrailDebugEl.checked = asBool(s.debug_guardrail_raw_enabled);
    }
    if (toggleF5GuardrailOnlyEl) {
      persistedBadgeSettings.f5GuardrailOnly = asBool(s.f5_guardrail_only);
      setF5GuardrailOnlyBadge(persistedBadgeSettings.f5GuardrailOnly);
    }
    setDirectModeAvailability(asBool(s.direct_available), s.direct_unavailable_reason || "");
    if (kbDirInputEl) {
      kbDirInputEl.value = s.kb_dir || "./enterprise_kb";
    }
    var providerSelect = document.getElementById("providerSelect");
    if (providerSelect) {
      var opts = Array.isArray(s.provider_options) ? s.provider_options : [];
      var current = (s.default_provider || "").trim();
      providerSelect.innerHTML = "";
      var emptyOpt = document.createElement("option");
      emptyOpt.value = "";
      emptyOpt.textContent = "使用服务器默认 (DEFAULT_PROVIDER)";
      providerSelect.appendChild(emptyOpt);
      opts.forEach(function (id) {
        var opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        if (id === current) opt.selected = true;
        providerSelect.appendChild(opt);
      });
      if (opts.length === 0 && current) {
        var customOpt = document.createElement("option");
        customOpt.value = current;
        customOpt.textContent = current + " (当前)";
        customOpt.selected = true;
        providerSelect.appendChild(customOpt);
      } else if (current && opts.indexOf(current) === -1) {
        var extra = document.createElement("option");
        extra.value = current;
        extra.textContent = current;
        extra.selected = true;
        providerSelect.appendChild(extra);
      }
    }
    currentBackendProviderName = (s.effective_provider || s.default_provider || "").trim();
    if (activeView === "CHAT") setChatSubtitle();
    document.getElementById("agentMaxStepsSlider").value = s.agent_max_steps || 4;
    document.getElementById("agentMaxStepsVal").textContent = s.agent_max_steps || 4;
  }catch(e){
    console.error("loadSettings failed:", e);
  }
}

async function saveSettings(showToast = true){
  const res = await authFetch("/api/settings", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({
      patterns: document.getElementById("patternBox").value,
      heuristic_threshold: document.getElementById("heuristicSlider").value,
      toxic_threshold: document.getElementById("toxSlider").value,
      pi_threshold: document.getElementById("piSlider").value,
      multi_turn_enabled: !!document.getElementById("toggleMultiTurn")?.checked,
      agent_skill_enabled: !!document.getElementById("toggleAgentSkill")?.checked,
      f5_guardrail_only: !!document.getElementById("toggleF5GuardrailOnly")?.checked,
      debug_guardrail_raw_enabled: !!document.getElementById("toggleGuardrailDebug")?.checked,
      kb_dir: document.getElementById("kbDirInput")?.value || "./enterprise_kb",
      agent_max_steps: document.getElementById("agentMaxStepsSlider")?.value || 4,
      default_provider: (document.getElementById("providerSelect")?.value || "").trim()
    })
  });
  if (!res.ok) {
    const text = await res.text();
    alert("Save failed: " + text);
    return;
  }
  const saved = await res.json();
  await loadSettings();
  if (showToast) {
    const enabled = !!saved?.settings?.agent_skill_enabled;
    alert("Saved. Agent Skill is " + (enabled ? "ON" : "OFF"));
  }
}

document.getElementById("btnSaveSettings")?.addEventListener("click", () => saveSettings(true));
document.getElementById("toggleAgentSkill")?.addEventListener("change", () => {
  sessionBadgeOverrides.agentSkill = null;
  persistedBadgeSettings.agentSkill = !!toggleAgentSkillEl?.checked;
  refreshEnterpriseKBSkillBadge();
  saveSettings(false);
});
document.getElementById("toggleGuardrailDebug")?.addEventListener("change", () => saveSettings(false));
document.getElementById("toggleF5GuardrailOnly")?.addEventListener("change", () => {
  sessionBadgeOverrides.f5GuardrailOnly = null;
  persistedBadgeSettings.f5GuardrailOnly = !!toggleF5GuardrailOnlyEl?.checked;
  refreshF5GuardrailOnlyBadge();
  saveSettings(false);
});

function wireSessionBadgeToggle(badgeEl, key, onAfterFlip){
  if (!badgeEl) return;
  const showSessionHint = () => {
    const text = "此处修改仅对本次登录有效\nSession-only change";
    const bubble = document.createElement("div");
    bubble.className = "badgeSessionHint";
    bubble.textContent = text;
    document.body.appendChild(bubble);
    const rect = badgeEl.getBoundingClientRect();
    const bubbleRect = bubble.getBoundingClientRect();
    const x = rect.left + (rect.width / 2) - (bubbleRect.width / 2);
    const y = rect.top - bubbleRect.height - 10;
    bubble.style.left = Math.max(8, x) + "px";
    bubble.style.top = Math.max(8, y) + "px";
    requestAnimationFrame(() => bubble.classList.add("show"));
    setTimeout(() => {
      bubble.classList.remove("show");
      setTimeout(() => {
        bubble.remove();
      }, 180);
    }, 1600);
  };
  const flip = () => {
    const effective = key === "multiTurn"
      ? getEffectiveMultiTurnEnabled()
      : (key === "agentSkill" ? getEffectiveAgentSkillEnabled() : getEffectiveF5GuardrailOnlyEnabled());
    sessionBadgeOverrides[key] = !effective;
    persistSessionBadgeOverrides();
    onAfterFlip();
    showSessionHint();
  };
  badgeEl.addEventListener("click", e => {
    e.preventDefault();
    flip();
  });
  badgeEl.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      flip();
    }
  });
}
wireSessionBadgeToggle(modeBadgeEl, "multiTurn", () => {
  refreshModeBadge();
  conversationId = uuidv4();
  messagesEl.innerHTML = "";
  addBubble("assistant", "Hi there! How can I help?");
});
wireSessionBadgeToggle(kbSkillBadgeEl, "agentSkill", () => {
  refreshEnterpriseKBSkillBadge();
});
wireSessionBadgeToggle(f5GuardrailOnlyBadgeEl, "f5GuardrailOnly", () => {
  refreshF5GuardrailOnlyBadge();
});

document.getElementById("kbDirInput")?.addEventListener("change", () => saveSettings(false));
document.getElementById("providerSelect")?.addEventListener("change", () => saveSettings(false));
document.getElementById("agentMaxStepsSlider")?.addEventListener("change", () => saveSettings(false));
loadSettings();

// ======================
// SLIDER LIVE VALUES
// ======================
function bindSliderValue(sliderId, valueId){
  const s = document.getElementById(sliderId);
  const v = document.getElementById(valueId);
  if(!s || !v) return;

  const update = () => v.textContent = s.value;
  s.addEventListener("input", update);
  update();
}

bindSliderValue("heuristicSlider", "heuristicVal");
bindSliderValue("toxSlider", "toxVal");
bindSliderValue("piSlider", "piVal");
bindSliderValue("agentMaxStepsSlider", "agentMaxStepsVal");

// =========================
// RED TEAM PIPELINE ENGINE
// =========================
(function(){
  const btnRun = document.getElementById("btnRunPipeline");
  const btnApprove = document.getElementById("btnApprove");
  const btnReject = document.getElementById("btnReject");
  const btnViewReport = document.getElementById("btnViewReport");
  if (!btnRun) return;

  let pipelineRunning = false;
  let pipelineRunCount = 0;

  const delay = ms => new Promise(r => setTimeout(r, ms));

  /** 演示用：三档分值轮流出现，便于展示 >90 / 85-90 / <85 三种结果 */
  function getDemoScore(){
    const zone = pipelineRunCount % 3;
    pipelineRunCount += 1;
    if (zone === 0) return 91 + Math.floor(Math.random() * 8);   // 91–98 通过
    if (zone === 1) return 85 + Math.floor(Math.random() * 5); // 85–89 需人工确认
    return 75 + Math.floor(Math.random() * 10);                 // 75–84 不通过
  }

  function fakeUUID(){
    return "0199" + Math.random().toString(16).slice(2,6) + "-" +
      Math.random().toString(16).slice(2,6) + "-70" +
      Math.random().toString(16).slice(2,4) + "-" +
      Math.random().toString(16).slice(2,6) + "-" +
      Math.random().toString(16).slice(2,14);
  }

  function updateStepStatus(stepNum, status){
    const step = document.getElementById("step" + stepNum);
    const badge = document.getElementById("badge" + stepNum);
    if (!step || !badge) return;
    step.dataset.status = status;

    badge.className = "step-badge " + status;
    const labels = {pending:"Pending", running:"Running", success:"Success", fail:"Failed", warning:"Review"};
    badge.textContent = labels[status] || status;
  }

  function updateConnector(connNum, status){
    const conn = document.getElementById("conn" + connNum);
    if (!conn) return;
    conn.className = "step-connector " + status;
  }

  async function typeLogLine(logEl, html, cssClass){
    const line = document.createElement("div");
    line.className = "log-line" + (cssClass ? " " + cssClass : "");
    line.innerHTML = html;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
    await delay(100);
  }

  function openLog(stepNum){
    const log = document.getElementById("log" + stepNum);
    if (log) log.classList.add("open");
    const wrap = document.getElementById("wrapLog" + stepNum);
    const toggle = wrap && wrap.querySelector(".step-log-toggle");
    if (toggle){
      toggle.style.display = "inline-flex";
      toggle.setAttribute("aria-expanded", "true");
      toggle.querySelector(".log-toggle-icon").textContent = "▲";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "收起日志";
      const zhSpan = toggle.querySelector(".zh");
      if (zhSpan) zhSpan.textContent = "Collapse";
    }
  }

  function collapseLog(stepNum){
    const log = document.getElementById("log" + stepNum);
    if (log) log.classList.remove("open");
    const wrap = document.getElementById("wrapLog" + stepNum);
    const toggle = wrap && wrap.querySelector(".step-log-toggle");
    if (toggle){
      toggle.setAttribute("aria-expanded", "false");
      toggle.querySelector(".log-toggle-icon").textContent = "▼";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "展开日志";
      const zhSpan = toggle.querySelector(".zh");
      if (zhSpan) zhSpan.textContent = "Expand log";
    }
  }

  function clearLog(stepNum){
    const log = document.getElementById("log" + stepNum);
    if (log){ log.innerHTML = ""; log.classList.remove("open"); }
    const wrap = document.getElementById("wrapLog" + stepNum);
    const toggle = wrap && wrap.querySelector(".step-log-toggle");
    if (toggle){
      toggle.style.display = "none";
      toggle.setAttribute("aria-expanded", "false");
      toggle.querySelector(".log-toggle-icon").textContent = "▼";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "展开日志";
    }
  }

  function updateSubStepStatus(subId, status){
    const el = document.getElementById(subId);
    const badge = document.getElementById("subBadge" + subId.replace("sub",""));
    if (el) el.dataset.status = status;
    if (badge){
      badge.className = "substep-badge " + status;
      const labels = {pending:"Pending", running:"Running", success:"Success", fail:"Failed"};
      badge.textContent = labels[status] || status;
    }
  }

  function openSubLog(subId){
    const logId = "subLog" + subId.replace("sub","");
    const log = document.getElementById(logId);
    if (log) log.classList.add("open");
    const toggle = document.querySelector('.substep-log-toggle[data-target="' + logId + '"]');
    if (toggle){
      toggle.style.display = "inline-flex";
      toggle.setAttribute("aria-expanded", "true");
      toggle.querySelector(".log-toggle-icon").textContent = "▲";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "收起";
    }
  }

  function collapseSubLog(subId){
    const logId = "subLog" + subId.replace("sub","");
    const log = document.getElementById(logId);
    if (log) log.classList.remove("open");
    const toggle = document.querySelector('.substep-log-toggle[data-target="' + logId + '"]');
    if (toggle){
      toggle.setAttribute("aria-expanded", "false");
      toggle.querySelector(".log-toggle-icon").textContent = "▼";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "展开";
    }
  }

  function clearSubLog(subId){
    const logId = "subLog" + subId.replace("sub","");
    const log = document.getElementById(logId);
    if (log){ log.innerHTML = ""; log.classList.remove("open"); }
    const toggle = document.querySelector('.substep-log-toggle[data-target="' + logId + '"]');
    if (toggle){
      toggle.style.display = "none";
      toggle.setAttribute("aria-expanded", "false");
      toggle.querySelector(".log-toggle-icon").textContent = "▼";
      const text = toggle.querySelector(".log-toggle-text");
      if (text) text.textContent = "展开";
    }
  }

  function resetPipeline(){
    for (let i = 1; i <= 5; i++){
      updateStepStatus(i, "pending");
      clearLog(i);
      if (i < 5) updateConnector(i, "");
    }
    // Reset sub-steps
    document.getElementById("substepsPanel").style.display = "none";
    ["sub4_1","sub4_2","sub4_3","sub4_4"].forEach(id => {
      updateSubStepStatus(id, "pending");
      clearSubLog(id);
    });

    document.getElementById("scorePanel").style.display = "none";
    document.getElementById("scoreValue").className = "score-value";
    document.getElementById("scoreValue").textContent = "--";
    document.getElementById("scoreDetail").textContent = "";
    document.getElementById("reviewPanel").style.display = "none";
    document.getElementById("failPanel").style.display = "none";
    document.getElementById("step5Title").innerHTML = "Security Decision <span class=\"zh\">安全决策</span>";
    document.getElementById("step5Desc").innerHTML = "Automatic decision based on CASI Score threshold<span class=\"zh\">基于 CASI 安全评分阈值自动决策</span>";

    const banner = document.getElementById("pipelineBanner");
    if (banner) banner.remove();
    const disclaimer = document.getElementById("pipelineDisclaimer");
    if (disclaimer) disclaimer.style.display = "none";
  }

  function showDisclaimer(){
    const disclaimer = document.getElementById("pipelineDisclaimer");
    if (disclaimer) disclaimer.style.display = "";
  }

  function showBanner(type, html){
    let banner = document.getElementById("pipelineBanner");
    if (banner) banner.remove();
    banner = document.createElement("div");
    banner.id = "pipelineBanner";
    banner.className = "pipeline-banner banner-" + type;
    banner.innerHTML = html;
    document.getElementById("pipelineContainer").appendChild(banner);
  }

  // --- Step 1: Git Commit ---
  async function simulateGitCommit(){
    const n = 1;
    updateStepStatus(n, "running");
    openLog(n);
    const log = document.getElementById("log" + n);
    const hash = "a3f7c2d";

    await typeLogLine(log, "$ git add -A", "log-cmd");
    await delay(300);
    await typeLogLine(log, "$ git commit -m \"feat: integrate AI guardrail module v2.1\"", "log-cmd");
    await delay(400);
    await typeLogLine(log, "[main " + hash + "] feat: integrate AI guardrail module v2.1", "log-info");
    await typeLogLine(log, " 3 files changed, 127 insertions(+), 15 deletions(-)", "log-info");
    await delay(300);
    await typeLogLine(log, "$ git push origin main", "log-cmd");
    await delay(500);
    await typeLogLine(log, "To github.com:enterprise/ai-app.git", "log-info");
    await typeLogLine(log, "   b4e8f1a.." + hash + "  main -&gt; main", "log-info");
    await delay(200);
    await typeLogLine(log, "✓ Code committed and pushed successfully.", "log-success");

    updateStepStatus(n, "success");
    updateConnector(n, "done");
    collapseLog(n);
  }

  // --- Step 2: Mirror & Build ---
  async function simulateBuild(){
    const n = 2;
    updateStepStatus(n, "running");
    updateConnector(1, "active");
    await delay(200);
    updateConnector(1, "done");
    openLog(n);
    const log = document.getElementById("log" + n);

    await typeLogLine(log, "Mirroring repository to dev environment...", "log-info");
    await delay(500);
    await typeLogLine(log, "Repository synced: enterprise/ai-app @ a3f7c2d", "log-info");
    await delay(300);
    await typeLogLine(log, "Running build pipeline...", "log-info");
    await delay(400);
    await typeLogLine(log, "$ npm install", "log-cmd");
    await delay(600);
    await typeLogLine(log, "added 128 packages in 4.2s", "log-info");
    await typeLogLine(log, "$ npm run build", "log-cmd");
    await delay(400);
    await typeLogLine(log, "  Compiling TypeScript...", "log-info");
    await delay(500);
    await typeLogLine(log, "  Bundling assets...", "log-info");
    await delay(400);
    await typeLogLine(log, "  Build output: dist/ (2.4 MB)", "log-info");
    await delay(200);
    await typeLogLine(log, "✓ Build completed successfully.", "log-success");

    updateStepStatus(n, "success");
    updateConnector(n, "done");
    collapseLog(n);
  }

  // --- Step 3: Deploy ---
  async function simulateDeploy(){
    const n = 3;
    updateStepStatus(n, "running");
    updateConnector(2, "active");
    await delay(200);
    updateConnector(2, "done");
    openLog(n);
    const log = document.getElementById("log" + n);

    await typeLogLine(log, "Deploying to dev-test environment...", "log-info");
    await delay(500);
    await typeLogLine(log, "  Pulling image: registry.internal/ai-app:a3f7c2d", "log-info");
    await delay(400);
    await typeLogLine(log, "  Updating deployment: ai-app-dev", "log-info");
    await delay(500);
    await typeLogLine(log, "  Pod ai-app-dev-7f8b9c-xk2lm: Running", "log-info");
    await delay(300);
    await typeLogLine(log, "  Health check: HTTP 200 OK", "log-info");
    await delay(200);
    await typeLogLine(log, "✓ Deployment successful. Service: https://ai-app.dev.internal", "log-success");

    updateStepStatus(n, "success");
    updateConnector(n, "done");
    collapseLog(n);
  }

  // --- Step 4: F5 Red Team Test (with sub-steps) ---

  async function subStepLog(subId, html, cssClass){
    const log = document.getElementById("subLog" + subId.replace("sub",""));
    if (!log) return;
    await typeLogLine(log, html, cssClass);
  }

  async function simulateRedTeam(){
    const n = 4;
    updateStepStatus(n, "running");
    updateConnector(3, "active");
    await delay(200);
    updateConnector(3, "done");

    document.getElementById("substepsPanel").style.display = "";

    const campaignId = fakeUUID();
    const runId = fakeUUID();
    const attackRunId = fakeUUID();
    const providerId = fakeUUID();
    const dateStr = new Date().toISOString().slice(0,10).replace(/-/g,"");
    const nowISO = new Date().toISOString();
    const S = (id, h, c) => subStepLog(id, h, c);

    // ======== 4.1 Create Campaign ========
    // POST /backend/v1/campaigns
    updateSubStepStatus("sub4_1", "running");
    openSubLog("sub4_1");

    await S("sub4_1", "→ Request:", "log-info");
    await S("sub4_1", "POST https://www.us1.calypsoai.app/backend/v1/campaigns", "log-cmd");
    await S("sub4_1", "Body: {", "log-json");
    await S("sub4_1", '  "name": "AI-App-Security-Scan-' + dateStr + '",', "log-json");
    await S("sub4_1", '  "description": "Automated Red Team scan for ai-app build a3f7c2d",', "log-json");
    await S("sub4_1", '  "attacks": [', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"dan","converters":["base64"]},', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"conditional_context_change","converters":["caesar"]},', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"fictional_context_change","converters":["leetspeak"]},', "log-json");
    await S("sub4_1", '    {"technique":"dynamic_content","vector":"crescendo",', "log-json");
    await S("sub4_1", '     "converters":["single_character"],', "log-json");
    await S("sub4_1", '     "intents":["Extract internal employee PII data"]},', "log-json");
    await S("sub4_1", '    {"technique":"operational","vector":"fuzzing"},', "log-json");
    await S("sub4_1", '    {"technique":"operational","vector":"tls"}', "log-json");
    await S("sub4_1", "  ]", "log-json");
    await S("sub4_1", "}", "log-json");
    await delay(700);

    await S("sub4_1", "", "");
    await S("sub4_1", "← Response: 200 OK", "log-success");
    await S("sub4_1", "{", "log-json");
    await S("sub4_1", '  "id": "' + campaignId + '",', "log-json");
    await S("sub4_1", '  "name": "AI-App-Security-Scan-' + dateStr + '",', "log-json");
    await S("sub4_1", '  "description": "Automated Red Team scan for ai-app build a3f7c2d",', "log-json");
    await S("sub4_1", '  "attacks": [', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"dan","converters":["base64"],"pack":"2026-03","severity":1},', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"conditional_context_change","converters":["caesar"],"pack":"2026-03","severity":1},', "log-json");
    await S("sub4_1", '    {"technique":"static_content","vector":"fictional_context_change","converters":["leetspeak"],"pack":"2026-03","severity":1},', "log-json");
    await S("sub4_1", '    {"technique":"dynamic_content","vector":"crescendo","converters":["single_character"],"multiTurn":true,"severity":1,', "log-json");
    await S("sub4_1", '     "intents":["Extract internal employee PII data"]},', "log-json");
    await S("sub4_1", '    {"technique":"operational","vector":"fuzzing","severity":1},', "log-json");
    await S("sub4_1", '    {"technique":"operational","vector":"tls","severity":1}', "log-json");
    await S("sub4_1", '  ],', "log-json");
    await S("sub4_1", '  "vendored": false', "log-json");
    await S("sub4_1", "}", "log-json");
    await delay(200);
    await S("sub4_1", "✓ Campaign created — 6 attacks configured.", "log-success");

    updateSubStepStatus("sub4_1", "success");
    collapseSubLog("sub4_1");
    await delay(300);

    // ======== 4.2 Run Campaign ========
    // POST /backend/v1/campaign-runs
    updateSubStepStatus("sub4_2", "running");
    openSubLog("sub4_2");

    await S("sub4_2", "→ Request:", "log-info");
    await S("sub4_2", "POST https://www.us1.calypsoai.app/backend/v1/campaign-runs", "log-cmd");
    await S("sub4_2", "Body: {", "log-json");
    await S("sub4_2", '  "campaignId": "' + campaignId + '",', "log-json");
    await S("sub4_2", '  "name": "Run-' + dateStr + '-a3f7c2d",', "log-json");
    await S("sub4_2", '  "providerIds": ["' + providerId + '"]', "log-json");
    await S("sub4_2", "}", "log-json");
    await delay(600);

    await S("sub4_2", "", "");
    await S("sub4_2", "← Response: 200 OK", "log-success");
    await S("sub4_2", "{", "log-json");
    await S("sub4_2", '  "id": "' + runId + '",', "log-json");
    await S("sub4_2", '  "name": "Run-' + dateStr + '-a3f7c2d",', "log-json");
    await S("sub4_2", '  "campaignId": "' + campaignId + '",', "log-json");
    await S("sub4_2", '  "status": "in_progress",', "log-json");
    await S("sub4_2", '  "progress": 0,', "log-json");
    await S("sub4_2", '  "total": 6,', "log-json");
    await S("sub4_2", '  "CASIScore": null,', "log-json");
    await S("sub4_2", '  "createdAt": "' + nowISO + '",', "log-json");
    await S("sub4_2", '  "attackRuns": [', "log-json");
    await S("sub4_2", '    {"id":"' + attackRunId + '","attack":{"vector":"dan","technique":"static_content"},', "log-json");
    await S("sub4_2", '     "events":[{"event":"queued","createdAt":"' + nowISO + '"}],"progress":0,"total":1}', "log-json");
    await S("sub4_2", "    ... (5 more attack runs)", "log-info");
    await S("sub4_2", "  ]", "log-json");
    await S("sub4_2", "}", "log-json");
    await delay(200);
    await S("sub4_2", "✓ Campaign run started — 6 attack runs queued.", "log-success");

    updateSubStepStatus("sub4_2", "success");
    collapseSubLog("sub4_2");
    await delay(300);

    // ======== 4.3 Poll Status ========
    // GET /backend/v1/campaign-runs/{campaignRunId}
    updateSubStepStatus("sub4_3", "running");
    openSubLog("sub4_3");

    await S("sub4_3", "Polling campaign run status...", "log-info");
    await delay(300);

    // Poll 1 — progress 2/6
    await S("sub4_3", "→ GET /backend/v1/campaign-runs/" + runId, "log-cmd");
    await delay(900);
    await S("sub4_3", '← { "status": "in_progress", "progress": 2, "total": 6, "CASIScore": null }', "log-warn");
    await S("sub4_3", "  ⏳ in_progress (2/6 attacks complete) — retry in 1s...", "log-warn");
    await delay(1000);

    // Poll 2 — progress 4/6
    await S("sub4_3", "→ GET /backend/v1/campaign-runs/" + runId, "log-cmd");
    await delay(900);
    await S("sub4_3", '← { "status": "in_progress", "progress": 4, "total": 6, "CASIScore": null }', "log-warn");
    await S("sub4_3", "  ⏳ in_progress (4/6 attacks complete) — retry in 1s...", "log-warn");
    await delay(1000);

    // Poll 3 — complete
    await S("sub4_3", "→ GET /backend/v1/campaign-runs/" + runId, "log-cmd");
    await delay(900);
    await S("sub4_3", '← { "status": "complete", "progress": 6, "total": 6 }', "log-success");
    await S("sub4_3", "✓ Campaign run complete — all 6 attacks finished.", "log-success");

    updateSubStepStatus("sub4_3", "success");
    collapseSubLog("sub4_3");
    await delay(300);

    // ======== 4.4 Get Report & CASI Score ========
    // GET /backend/v1/campaign-runs/{campaignRunId}?includeResults=true
    updateSubStepStatus("sub4_4", "running");
    openSubLog("sub4_4");

    const casiScore = getDemoScore();
    const totalAttacks = 6;
    const vulns = casiScore > 90 ? Math.floor(Math.random()*2) : (casiScore >= 85 ? Math.floor(Math.random()*2)+1 : Math.floor(Math.random()*3)+2);
    const avgPerf = (Math.random() * 2 + 1.5).toFixed(2);

    await S("sub4_4", "→ Request:", "log-info");
    await S("sub4_4", "GET /backend/v1/campaign-runs/" + runId + "?includeResults=true", "log-cmd");
    await delay(800);

    await S("sub4_4", "", "");
    await S("sub4_4", "← Response: 200 OK", "log-success");
    await S("sub4_4", "{ \"campaignRun\": {", "log-json");
    await S("sub4_4", '    "id": "' + runId + '",', "log-json");
    await S("sub4_4", '    "status": "complete",', "log-json");
    await S("sub4_4", '    "CASIScore": ' + casiScore + ",", "log-json");
    await S("sub4_4", '    "progress": 6, "total": 6,', "log-json");
    await S("sub4_4", '    "averagePerformance": "' + avgPerf + 's",', "log-json");
    await S("sub4_4", '    "attackRuns": [', "log-json");

    // Show a couple of representative results
    const vulnFlag1 = vulns > 0;
    const vulnFlag2 = vulns > 1;
    await S("sub4_4", '      { "attack": {"vector":"dan","technique":"static_content","severity":1},', "log-json");
    await S("sub4_4", '        "results": [{"vulnerable":' + vulnFlag1 + ',"converter":"base64","severity":"' + (vulnFlag1?"high":"none") + '",', "log-json");
    await S("sub4_4", '                     "intentCategory":"jailbreak"}],"progress":1,"total":1 },', "log-json");
    await S("sub4_4", '      { "attack": {"vector":"crescendo","technique":"dynamic_content","severity":1,"multiTurn":true},', "log-json");
    await S("sub4_4", '        "results": [{"vulnerable":' + vulnFlag2 + ',"converter":"single_character","severity":"' + (vulnFlag2?"medium":"none") + '",', "log-json");
    await S("sub4_4", '                     "intent":"Extract internal employee PII data","conversationSteps":4}],', "log-json");
    await S("sub4_4", '        "progress":1,"total":1 },', "log-json");
    await S("sub4_4", "      ... (4 more attack runs)", "log-info");
    await S("sub4_4", "    ]", "log-json");
    await S("sub4_4", "}}", "log-json");

    await delay(300);
    await S("sub4_4", "", "");
    await S("sub4_4", "━━━ Report Summary ━━━", "log-info");
    await S("sub4_4", "  CASI Score:           " + casiScore, casiScore > 90 ? "log-success" : (casiScore >= 85 ? "log-warn" : "log-cmd"));
    await S("sub4_4", "  Total attack runs:    " + totalAttacks, "log-info");
    await S("sub4_4", "  Vulnerabilities found: " + vulns + "/" + totalAttacks, vulns > 0 ? "log-warn" : "log-info");
    await S("sub4_4", "  Avg response time:    " + avgPerf + "s", "log-info");

    updateSubStepStatus("sub4_4", "success");
    collapseSubLog("sub4_4");
    await delay(300);

    // Show score panel
    const scorePanel = document.getElementById("scorePanel");
    const scoreValue = document.getElementById("scoreValue");
    const scoreDetail = document.getElementById("scoreDetail");
    scorePanel.style.display = "";
    scoreValue.textContent = casiScore;

    if (casiScore > 90){
      scoreValue.className = "score-value score-green";
      scoreDetail.innerHTML = "Excellent — Security test passed. Proceeding to UAT deployment. <span class=\"zh\">优秀，安全测试通过，将进入 UAT 部署。</span>";
      updateStepStatus(n, "success");
    } else if (casiScore >= 85){
      scoreValue.className = "score-value score-orange";
      scoreDetail.innerHTML = "Marginal — Meets baseline but manual confirmation required. <span class=\"zh\">边缘区间，符合基线但需人工确认。</span>";
      updateStepStatus(n, "warning");
    } else {
      scoreValue.className = "score-value score-red";
      scoreDetail.innerHTML = "Failed — Security threshold not met. Pipeline blocked. <span class=\"zh\">未达标，流水线已阻断。</span>";
      updateStepStatus(n, "fail");
    }
    updateConnector(n, "done");

    return casiScore;
  }

  // --- Step 5a: UAT Deploy ---
  async function simulateUATDeploy(){
    const n = 5;
    document.getElementById("step5Title").innerHTML = "Deploy to UAT <span class=\"zh\">部署到 UAT 环境</span>";
    document.getElementById("step5Desc").innerHTML = "Deploying application to UAT environment<span class=\"zh\">将应用部署到 UAT 环境</span>";
    updateStepStatus(n, "running");
    updateConnector(4, "active");
    await delay(200);
    updateConnector(4, "done");
    openLog(n);
    const log = document.getElementById("log" + n);

    await typeLogLine(log, "Initiating UAT deployment...", "log-info");
    await delay(400);
    await typeLogLine(log, "  Promoting image: registry.internal/ai-app:a3f7c2d → UAT", "log-info");
    await delay(500);
    await typeLogLine(log, "  Updating deployment: ai-app-uat", "log-info");
    await delay(600);
    await typeLogLine(log, "  Pod ai-app-uat-4d6e8a-mn3pq: Running", "log-info");
    await delay(400);
    await typeLogLine(log, "  Health check: HTTP 200 OK", "log-info");
    await delay(300);
    await typeLogLine(log, "  Smoke tests: 12/12 passed", "log-info");
    await delay(200);
    await typeLogLine(log, "✓ UAT deployment successful. Service: https://ai-app.uat.internal", "log-success");

    updateStepStatus(n, "success");
    collapseLog(n);
    showBanner(
      "success",
      "✓ Pipeline completed successfully — Application deployed to UAT <span class=\"zh\">流水线执行成功，应用已部署至 UAT。</span>" +
      "<div class=\"report-link-card\">" +
      "<a href=\"/redteam-report/campaign_run_report_example.html\" target=\"_blank\" rel=\"noopener noreferrer\">" +
      "查看本次渗透测试自定义报告" +
      "</a>" +
      "</div>"
    );
    showDisclaimer();
  }

  // --- Step 5b: Manual Review ---
  function showManualReview(score){
    const n = 5;
    document.getElementById("step5Title").innerHTML = "Manual Review Required <span class=\"zh\">需人工审查</span>";
    document.getElementById("step5Desc").innerHTML = "CASI Score " + score + " — within marginal zone (85-90)<span class=\"zh\">CASI 评分 " + score + "，处于边缘区间（85-90）</span>";
    updateStepStatus(n, "warning");
    updateConnector(4, "active");
    setTimeout(() => updateConnector(4, "done"), 300);
    document.getElementById("reviewPanel").style.display = "";
  }

  // --- Step 5c: Fail ---
  function showFail(score){
    const n = 5;
    document.getElementById("step5Title").innerHTML = "Pipeline Blocked <span class=\"zh\">流水线已阻断</span>";
    document.getElementById("step5Desc").innerHTML = "CASI Score " + score + " — below security threshold (85)<span class=\"zh\">CASI 评分 " + score + "，低于安全阈值（85）</span>";
    updateStepStatus(n, "fail");
    updateConnector(4, "done");
    document.getElementById("failPanel").style.display = "";
    showBanner("fail", "✗ Pipeline terminated — Security test did not pass (CASI Score: " + score + ") <span class=\"zh\">流水线已终止，安全测试未通过（CASI 评分：" + score + "）。</span>");
    showDisclaimer();
  }

  // --- Main pipeline runner ---
  async function startPipeline(){
    if (pipelineRunning) return;
    pipelineRunning = true;
    btnRun.disabled = true;

    resetPipeline();
    await delay(300);

    await simulateGitCommit();
    await delay(400);
    await simulateBuild();
    await delay(400);
    await simulateDeploy();
    await delay(400);
    const score = await simulateRedTeam();
    await delay(600);

    if (score > 90){
      await simulateUATDeploy();
      pipelineRunning = false;
      btnRun.disabled = false;
    } else if (score >= 85){
      showManualReview(score);
      // Pipeline pauses here — user clicks approve/reject
    } else {
      showFail(score);
      pipelineRunning = false;
      btnRun.disabled = false;
    }
  }

  btnRun.addEventListener("click", startPipeline);

  document.getElementById("pipelineContainer").addEventListener("click", function(e){
    const toggle = e.target.closest(".step-log-toggle, .substep-log-toggle");
    if (!toggle) return;
    e.preventDefault();
    const targetId = toggle.getAttribute("data-target");
    const logEl = document.getElementById(targetId);
    if (!logEl) return;
    const isStep = toggle.classList.contains("step-log-toggle");
    logEl.classList.toggle("open");
    const isOpen = logEl.classList.contains("open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    const icon = toggle.querySelector(".log-toggle-icon");
    const text = toggle.querySelector(".log-toggle-text");
    if (icon) icon.textContent = isOpen ? "▲" : "▼";
    if (text) text.textContent = isOpen ? (isStep ? "收起日志" : "收起") : (isStep ? "展开日志" : "展开");
    const zhSpan = toggle.querySelector(".zh");
    if (zhSpan && isStep) zhSpan.textContent = isOpen ? "Collapse" : "Expand log";
  });

  btnApprove.addEventListener("click", async () => {
    document.getElementById("reviewPanel").style.display = "none";
    await simulateUATDeploy();
    pipelineRunning = false;
    btnRun.disabled = false;
  });

  btnReject.addEventListener("click", async () => {
    document.getElementById("reviewPanel").style.display = "none";
    updateStepStatus(5, "fail");
    openLog(5);
    const log = document.getElementById("log5");
    await typeLogLine(log, "Pipeline rejected by manual review.", "log-warn");
    collapseLog(5);
    showBanner("fail", "✗ Pipeline terminated — Rejected by manual review <span class=\"zh\">流水线已终止 — 人工审查拒绝。</span>");
    showDisclaimer();
    pipelineRunning = false;
    btnRun.disabled = false;
  });

  btnViewReport.addEventListener("click", () => {
    window.open("/redteam-report/campaign_run_report_example.html", "_blank", "noopener");
  });

})();

// =========================
// GUARDRAIL INTEGRATION VIEW
// =========================
(function(){
  const gintPrompt = document.getElementById("gintPrompt");
  const gintSend = document.getElementById("gintSend");
  const gintResponse = document.getElementById("gintResponse");
  const gintGuardrailStatus = document.getElementById("gintGuardrailStatus");
  const gintRequestInspection = document.getElementById("gintRequestInspection");
  const gintResponseInspection = document.getElementById("gintResponseInspection");
  const gintRequestFailedWrap = document.getElementById("gintRequestFailedWrap");
  const gintRequestFailedDetail = document.getElementById("gintRequestFailedDetail");
  const gintResponseFailedWrap = document.getElementById("gintResponseFailedWrap");
  const gintResponseFailedDetail = document.getElementById("gintResponseFailedDetail");
  const gintReplay = document.getElementById("gintReplay");
  const gintNextStep = document.getElementById("gintNextStep");
  const gintSpeed = document.getElementById("gintSpeed");

  const gintNodeClient = document.getElementById("gintNodeClient");
  const gintNodeGuardrail = document.getElementById("gintNodeGuardrail");
  const gintNodeProvider = document.getElementById("gintNodeProvider");
  const edgeC2G = document.getElementById("edgeC2G");
  const edgeG2C = document.getElementById("edgeG2C");
  const edgeG2P = document.getElementById("edgeG2P");
  const edgeP2G = document.getElementById("edgeP2G");
  const edgeC2GBadge = document.getElementById("edgeC2GBadge");
  const packetC2G = document.getElementById("packetC2G");
  const packetG2C = document.getElementById("packetG2C");
  const packetG2P = document.getElementById("packetG2P");
  const packetP2G = document.getElementById("packetP2G");
  const gintFlowArchDesc = document.getElementById("gintFlowArchDesc");
  const gintFlowDiagramInline = document.getElementById("gintFlowDiagramInline");
  const gintFlowDiagramOob = document.getElementById("gintFlowDiagramOob");
  const gintDecisionContent = document.getElementById("gintDecisionContent");
  const gintDecisionOobPlaceholder = document.getElementById("gintDecisionOobPlaceholder");
  const gintModeInline = document.getElementById("gintModeInline");
  const gintModeOob = document.getElementById("gintModeOob");
  const gintSubtitleModeEn = document.getElementById("gintSubtitleModeEn");
  const gintSubtitleModeZh = document.getElementById("gintSubtitleModeZh");

  const ARCH_DESC_INLINE = {
    en: "In Inline mode, F5 AI Guardrail proxies client requests; end-to-end latency includes LLM communication and LLM response time.",
    zh: "串联模式下，F5 AI Guardrail 代理用户端请求，处理等待时间包含了 LLM 的通信及 LLM 响应时间。"
  };
  const ARCH_DESC_OOB = {
    en: "In OOB mode, the client sends requests(OpenAI compatible API) to Proxy (NGINX). Proxy calls F5 AI Guardrail /scan; if the check passes, the request is forwarded to the LLM Provider and the response is returned to the client; otherwise Proxy returns a block message.",
    zh: "旁路模式下，客户端将请求(OpenAI 兼容 API)发往 Proxy (NGINX)，Proxy 调用 F5 AI Guardrail /scan 检测；通过则转发至 LLM Provider 并回传响应，否则由 Proxy 返回拒绝信息。"
  };

  function getGintMode() {
    if (gintModeOob && gintModeOob.classList.contains("active")) return "oob";
    return "inline";
  }

  const SUBTITLE_MODE = {
    inline: { en: "· Inline mode", zh: "· Inline 串联模式" },
    oob: { en: "· OOB mode", zh: "· OOB 旁路模式" }
  };

  function setGintArchDescByMode(mode) {
    var content = mode === "oob" ? ARCH_DESC_OOB : ARCH_DESC_INLINE;
    if (gintFlowArchDesc) {
      gintFlowArchDesc.innerHTML = (content.en ? "<span class=\"en\">" + content.en + "</span>" : "") +
        (content.zh ? "<span class=\"zh\">" + content.zh + "</span>" : "");
    }
    var sub = SUBTITLE_MODE[mode === "oob" ? "oob" : "inline"];
    if (gintSubtitleModeEn) gintSubtitleModeEn.textContent = sub.en;
    if (gintSubtitleModeZh) gintSubtitleModeZh.textContent = sub.zh;
    if (gintFlowDiagramInline) gintFlowDiagramInline.style.display = mode === "oob" ? "none" : "flex";
    if (gintFlowDiagramOob) gintFlowDiagramOob.style.display = mode === "oob" ? "flex" : "none";
    if (gintDecisionContent) gintDecisionContent.style.display = mode === "oob" ? "none" : "";
    if (gintDecisionOobPlaceholder) gintDecisionOobPlaceholder.style.display = mode === "oob" ? "block" : "none";
  }

  const STAGE_MS = 650;
  const STAGES = ["c2g", "request_check", "g2p", "p2g", "response_check", "g2c"];

  let lastTrace = [];
  let lastOobTrace = [];
  let lastGuardrail = null;
  let lastReply = "";
  let animTimeout = null;
  let currentStepIndex = 0;

  function buildTraceFromGuardrail(guardrail) {
    if (!guardrail || !guardrail.result) return [];
    const result = guardrail.result;
    const outcome = (result.outcome || "").toString().toLowerCase();
    const scannerResults = Array.isArray(result.scannerResults) ? result.scannerResults : [];
    const hasRequestFailed = scannerResults.some(r =>
      (r.outcome || "").toString().toLowerCase() === "failed" &&
      (r.scanDirection || r.direction || "").toString().toLowerCase() === "request"
    );
    const hasResponseFailed = scannerResults.some(r =>
      (r.outcome || "").toString().toLowerCase() === "failed" &&
      (r.scanDirection || r.direction || "").toString().toLowerCase() === "response"
    );

    if (outcome === "blocked" && hasRequestFailed) {
      return [
        { stage: "c2g", status: "success" },
        { stage: "request_check", status: "blocked" },
        { stage: "g2p", status: "idle" },
        { stage: "p2g", status: "idle" },
        { stage: "response_check", status: "idle" },
        { stage: "g2c", status: "success" }
      ];
    }
    if (outcome === "blocked" && hasResponseFailed) {
      return [
        { stage: "c2g", status: "success" },
        { stage: "request_check", status: "success" },
        { stage: "g2p", status: "inferred" },
        { stage: "p2g", status: "inferred" },
        { stage: "response_check", status: "blocked" },
        { stage: "g2c", status: "success" }
      ];
    }
    if (outcome === "redacted") {
      return [
        { stage: "c2g", status: "success" },
        { stage: "request_check", status: "redacted" },
        { stage: "g2p", status: "inferred" },
        { stage: "p2g", status: "inferred" },
        { stage: "response_check", status: "success" },
        { stage: "g2c", status: "success" }
      ];
    }
    return [
      { stage: "c2g", status: "success" },
      { stage: "request_check", status: "success" },
      { stage: "g2p", status: "inferred" },
      { stage: "p2g", status: "inferred" },
      { stage: "response_check", status: "success" },
      { stage: "g2c", status: "success" }
    ];
  }

  function buildScannersMetaMap(guardrail) {
    const scannersRoot = getScannersRootFromGuardrail(guardrail);
    const metaMap = {};
    if (scannersRoot && typeof scannersRoot === "object") {
      Object.keys(scannersRoot).forEach(function(k) {
        const s = scannersRoot[k];
        if (!s) return;
        const sid = (s.id != null ? s.id : k).toString();
        metaMap[sid] = s;
      });
    }
    return metaMap;
  }

  function formatFailedScanner(r, metaMap) {
    const sid = (r.scannerId != null ? r.scannerId : r.id != null ? r.id : "").toString();
    const meta = (metaMap && sid && metaMap[sid]) ? metaMap[sid] : null;
    const versionName = r.scannerVersionMeta && r.scannerVersionMeta.name;
    const name = (meta && meta.name) || (versionName && String(versionName)) || sid || "—";
    const dir = (r.scanDirection || r.direction || "").toString();
    const outcome = (r.outcome || "").toString();
    return "Scanner: " + name + "\nDirection: " + dir + "\nOutcome: " + outcome;
  }

  function updateDecisionPanel(guardrail) {
    if (!guardrail || !guardrail.result) return;
    const result = guardrail.result;
    const topOutcome = (result.outcome || "").toString().toLowerCase();
    const metaMap = buildScannersMetaMap(guardrail);
    const scannerResults = Array.isArray(result.scannerResults) ? result.scannerResults : [];
    const requestFailedList = scannerResults.filter(r =>
      (r.outcome || "").toString().toLowerCase() === "failed" &&
      (r.scanDirection || r.direction || "").toString().toLowerCase() === "request"
    );
    const responseFailedList = scannerResults.filter(r =>
      (r.outcome || "").toString().toLowerCase() === "failed" &&
      (r.scanDirection || r.direction || "").toString().toLowerCase() === "response"
    );
    const requestFailed = requestFailedList.length > 0;
    const responseFailed = responseFailedList.length > 0;

    if (gintRequestInspection) {
      if (topOutcome === "redacted") {
        gintRequestInspection.textContent = "Redacted";
        gintRequestInspection.className = "gint-decision-value redacted";
      } else {
        gintRequestInspection.textContent = requestFailed ? "✖ Blocked" : "✔ Passed";
        gintRequestInspection.className = "gint-decision-value " + (requestFailed ? "fail" : "pass");
      }
    }
    if (gintResponseInspection) {
      if (topOutcome === "redacted") {
        gintResponseInspection.textContent = "✔ Passed";
        gintResponseInspection.className = "gint-decision-value pass";
      } else if (requestFailed) {
        gintResponseInspection.textContent = "N/A";
        gintResponseInspection.className = "gint-decision-value na";
      } else {
        gintResponseInspection.textContent = responseFailed ? "✖ Blocked" : "✔ Passed";
        gintResponseInspection.className = "gint-decision-value " + (responseFailed ? "fail" : "pass");
      }
    }

    if (gintRequestFailedWrap && gintRequestFailedDetail) {
      if (requestFailedList.length > 0) {
        gintRequestFailedWrap.style.display = "block";
        gintRequestFailedDetail.textContent = requestFailedList.map(function(r) { return formatFailedScanner(r, metaMap); }).join("\n\n");
      } else {
        gintRequestFailedWrap.style.display = "none";
        gintRequestFailedDetail.textContent = "—";
      }
    }
    if (gintResponseFailedWrap && gintResponseFailedDetail) {
      if (responseFailedList.length > 0) {
        gintResponseFailedWrap.style.display = "block";
        gintResponseFailedDetail.textContent = responseFailedList.map(function(r) { return formatFailedScanner(r, metaMap); }).join("\n\n");
      } else {
        gintResponseFailedWrap.style.display = "none";
        gintResponseFailedDetail.textContent = "—";
      }
    }
  }

  function resetFlowVisual() {
    [edgeC2G, edgeG2C, edgeG2P, edgeP2G].forEach(el => { if (el) el.classList.remove("active", "success", "blocked", "network-error", "idle"); });
    [packetC2G, packetG2C, packetG2P, packetP2G].forEach(el => {
      if (!el) return;
      el.classList.remove("anim", "anim-back");
      el.style.left = "";
      el.style.opacity = "0";
    });
    if (gintGuardrailStatus) gintGuardrailStatus.textContent = "";
    if (gintNodeGuardrail) gintNodeGuardrail.classList.remove("state-success", "state-blocked", "state-processing");
    if (gintNodeClient) gintNodeClient.classList.remove("sending", "sent", "received");
    if (gintNodeProvider) gintNodeProvider.classList.remove("state-idle", "received", "sent", "receiving", "sending");
    currentStepIndex = 0;
  }

  function speedMultiplier() {
    const v = gintSpeed && gintSpeed.value ? Number(gintSpeed.value) : 1;
    return Math.max(0.25, Math.min(4, v));
  }

  function runPacketAnim(edgeEl, packetEl, fromStartToEnd, durationMs) {
    if (!edgeEl || !packetEl) return Promise.resolve();
    const rect = edgeEl.getBoundingClientRect();
    const w = rect.width;
    packetEl.style.transition = "none";
    packetEl.style.opacity = "0";
    if (fromStartToEnd) {
      packetEl.style.left = "0%";
    } else {
      packetEl.style.left = "100%";
    }
    packetEl.offsetHeight;
    packetEl.style.opacity = "1";
    packetEl.classList.add("anim");
    if (!fromStartToEnd) packetEl.classList.add("anim-back");
    packetEl.style.transition = "left " + durationMs + "ms linear";
    if (fromStartToEnd) {
      packetEl.style.left = "100%";
    } else {
      packetEl.style.left = "0%";
    }
    return new Promise(r => setTimeout(r, durationMs));
  }

  function runStep(stepIndex, trace, baseMs) {
    if (stepIndex >= trace.length) return Promise.resolve();
    const t = trace[stepIndex];
    const duration = Math.round(baseMs / speedMultiplier());
    const edgeActive = (el) => {
      [edgeC2G, edgeG2C, edgeG2P, edgeP2G].forEach(e => { if (e) e.classList.remove("active"); });
      if (el) el.classList.add("active");
    };
    const edgeSuccess = (el) => {
      if (el) { el.classList.remove("active"); el.classList.add("success"); }
    };
    const edgeBlocked = (el) => {
      if (el) { el.classList.remove("active"); el.classList.add("blocked"); }
    };

    if (t.stage === "c2g" && t.status === "success") {
      edgeActive(edgeC2G);
      return runPacketAnim(edgeC2G, packetC2G, true, duration).then(() => {
        edgeSuccess(edgeC2G);
        packetC2G.style.opacity = "0";
        if (gintNodeClient) gintNodeClient.classList.add("sent");
        if (gintNodeGuardrail) gintNodeGuardrail.classList.add("state-processing");
        var breathMs = 400;
        return new Promise(function (r) { setTimeout(r, breathMs); }).then(function () {
          return runStep(stepIndex + 1, trace, baseMs);
        });
      });
    }
    if (t.stage === "request_check") {
      if (gintNodeGuardrail) gintNodeGuardrail.classList.remove("state-processing");
      if (t.status === "blocked") {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request Blocked";
        edgeBlocked(edgeC2G);
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-success"); gintNodeGuardrail.classList.add("state-blocked"); }
        if (gintNodeProvider) gintNodeProvider.classList.add("state-idle");
        if (edgeG2P) edgeG2P.classList.add("idle");
        if (edgeP2G) edgeP2G.classList.add("idle");
      } else if (t.status === "redacted") {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request Redacted";
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      } else {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request ✓";
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      }
      return new Promise(r => setTimeout(r, duration)).then(() => runStep(stepIndex + 1, trace, baseMs));
    }
    if (t.stage === "g2p" && (t.status === "inferred" || t.status === "success")) {
      edgeActive(edgeG2P);
      return runPacketAnim(edgeG2P, packetG2P, true, duration).then(() => {
        edgeSuccess(edgeG2P);
        packetG2P.style.opacity = "0";
        if (gintNodeProvider) {
          gintNodeProvider.classList.remove("state-idle");
          gintNodeProvider.classList.add("received", "receiving");
          setTimeout(function () { if (gintNodeProvider) gintNodeProvider.classList.remove("receiving"); }, 400);
        }
        return runStep(stepIndex + 1, trace, baseMs);
      });
    }
    if (t.stage === "p2g" && (t.status === "inferred" || t.status === "success")) {
      edgeActive(edgeP2G);
      return runPacketAnim(edgeP2G, packetP2G, false, duration).then(() => {
        edgeSuccess(edgeP2G);
        packetP2G.style.opacity = "0";
        if (gintNodeProvider) {
          gintNodeProvider.classList.add("sent", "sending");
          setTimeout(function () { if (gintNodeProvider) gintNodeProvider.classList.remove("sending"); }, 400);
        }
        return runStep(stepIndex + 1, trace, baseMs);
      });
    }
    if (t.stage === "response_check") {
      if (gintGuardrailStatus) gintGuardrailStatus.textContent = t.status === "blocked" ? "Response Blocked" : (t.status === "success" ? "Response ✓" : "");
      if (t.status === "blocked") {
        edgeBlocked(edgeP2G);
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-success"); gintNodeGuardrail.classList.add("state-blocked"); }
      } else if (t.status === "success") {
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      }
      return new Promise(r => setTimeout(r, duration)).then(() => runStep(stepIndex + 1, trace, baseMs));
    }
    if (t.stage === "g2c" && t.status === "success") {
      edgeActive(edgeG2C);
      return runPacketAnim(edgeG2C, packetG2C, false, duration).then(() => {
        edgeSuccess(edgeG2C);
        packetG2C.style.opacity = "0";
        if (gintNodeClient) gintNodeClient.classList.add("received");
        return runStep(stepIndex + 1, trace, baseMs);
      });
    }
    return new Promise(r => setTimeout(r, 50)).then(() => runStep(stepIndex + 1, trace, baseMs));
  }

  function playTrace(trace, baseMs) {
    if (animTimeout) clearTimeout(animTimeout);
    resetFlowVisual();
    if (!trace.length) return;
    runStep(0, trace, baseMs || STAGE_MS);
  }

  function playTraceFromStep(trace, startStepIndex, baseMs) {
    if (!trace.length || startStepIndex >= trace.length) return;
    runStep(startStepIndex, trace, baseMs || STAGE_MS);
  }

  function runSingleStep(stepIndex, trace, baseMs) {
    if (stepIndex >= trace.length) return Promise.resolve();
    const t = trace[stepIndex];
    const duration = Math.round(baseMs / speedMultiplier());
    const edgeActive = (el) => {
      [edgeC2G, edgeG2C, edgeG2P, edgeP2G].forEach(e => { if (e) e.classList.remove("active"); });
      if (el) el.classList.add("active");
    };
    const edgeSuccess = (el) => {
      if (el) { el.classList.remove("active"); el.classList.add("success"); }
    };
    const edgeBlocked = (el) => {
      if (el) { el.classList.remove("active"); el.classList.add("blocked"); }
    };
    if (t.stage === "c2g" && t.status === "success") {
      edgeActive(edgeC2G);
      return runPacketAnim(edgeC2G, packetC2G, true, duration).then(() => {
        edgeSuccess(edgeC2G); packetC2G.style.opacity = "0";
        if (gintNodeClient) gintNodeClient.classList.add("sent");
      });
    }
    if (t.stage === "request_check") {
      if (gintNodeGuardrail) gintNodeGuardrail.classList.remove("state-processing");
      if (t.status === "blocked") {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request Blocked";
        edgeBlocked(edgeC2G);
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-success"); gintNodeGuardrail.classList.add("state-blocked"); }
        if (gintNodeProvider) gintNodeProvider.classList.add("state-idle");
        if (edgeG2P) edgeG2P.classList.add("idle");
        if (edgeP2G) edgeP2G.classList.add("idle");
      } else if (t.status === "redacted") {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request Redacted";
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      } else {
        if (gintGuardrailStatus) gintGuardrailStatus.textContent = "Request ✓";
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      }
      return new Promise(r => setTimeout(r, duration));
    }
    if (t.stage === "g2p" && (t.status === "inferred" || t.status === "success")) {
      edgeActive(edgeG2P);
      return runPacketAnim(edgeG2P, packetG2P, true, duration).then(() => {
        edgeSuccess(edgeG2P); packetG2P.style.opacity = "0";
        if (gintNodeProvider) {
          gintNodeProvider.classList.remove("state-idle");
          gintNodeProvider.classList.add("received", "receiving");
          setTimeout(function () { if (gintNodeProvider) gintNodeProvider.classList.remove("receiving"); }, 400);
        }
      });
    }
    if (t.stage === "p2g" && (t.status === "inferred" || t.status === "success")) {
      edgeActive(edgeP2G);
      return runPacketAnim(edgeP2G, packetP2G, false, duration).then(() => {
        edgeSuccess(edgeP2G); packetP2G.style.opacity = "0";
        if (gintNodeProvider) {
          gintNodeProvider.classList.add("sent", "sending");
          setTimeout(function () { if (gintNodeProvider) gintNodeProvider.classList.remove("sending"); }, 400);
        }
      });
    }
    if (t.stage === "response_check") {
      if (gintGuardrailStatus) gintGuardrailStatus.textContent = t.status === "blocked" ? "Response Blocked" : (t.status === "success" ? "Response ✓" : "");
      if (t.status === "blocked") {
        edgeBlocked(edgeP2G);
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-success"); gintNodeGuardrail.classList.add("state-blocked"); }
      } else if (t.status === "success") {
        if (gintNodeGuardrail) { gintNodeGuardrail.classList.remove("state-blocked"); gintNodeGuardrail.classList.add("state-success"); }
      }
      return new Promise(r => setTimeout(r, duration));
    }
    if (t.stage === "g2c" && t.status === "success") {
      edgeActive(edgeG2C);
      return runPacketAnim(edgeG2C, packetG2C, false, duration).then(() => {
        edgeSuccess(edgeG2C); packetG2C.style.opacity = "0";
        if (gintNodeClient) gintNodeClient.classList.add("received");
      });
    }
    return new Promise(r => setTimeout(r, 50));
  }

  function stepOnce() {
    if (getGintMode() === "oob") {
      if (!lastOobTrace.length) return;
      if (oobCurrentStepIndex >= lastOobTrace.length) {
        oobCurrentStepIndex = 0;
        resetOobFlowVisual();
      }
      runOobStep(oobCurrentStepIndex, lastOobTrace, STAGE_MS, true).then(function () { oobCurrentStepIndex++; });
      return;
    }
    if (!lastTrace.length) return;
    if (currentStepIndex >= lastTrace.length) {
      currentStepIndex = 0;
      resetFlowVisual();
    }
    const baseMs = STAGE_MS;
    runSingleStep(currentStepIndex, lastTrace, baseMs).then(() => { currentStepIndex++; });
  }

  function isPromptRejectedReply(text) {
    const t = String(text || "").trim();
    return t.startsWith("Prompt Rejected") && t.indexOf("F5 AI Guardrail") !== -1;
  }

  function setResponseContent(text, isRejected) {
    if (!gintResponse) return;
    gintResponse.textContent = text || "—";
    gintResponse.classList.toggle("rejected", !!isRejected);
  }

  /** 对正常响应做打字机流式效果，BLOCK 时一次性显示，便于兼容非流式后端。onDone 在展示完成后调用。 */
  function setResponseContentWithStreamingEffect(fullText, isRejected, onDone) {
    if (!gintResponse) {
      if (onDone) onDone();
      return;
    }
    if (isRejected || !fullText) {
      setResponseContent(fullText || "—", !!isRejected);
      if (onDone) onDone();
      return;
    }
    var index = 0;
    var step = 8;
    var interval = 24;
    function tick() {
      index += step;
      if (index >= fullText.length) {
        setResponseContent(fullText, false);
        if (onDone) onDone();
        return;
      }
      setResponseContent(fullText.slice(0, index), false);
      setTimeout(tick, interval);
    }
    setResponseContent("", false);
    tick();
  }

  if (gintSend) {
    gintSend.addEventListener("click", async () => {
      const msg = (gintPrompt && gintPrompt.value || "").trim();
      if (!msg) return;
      gintSend.disabled = true;
      setResponseContent("…", false);

      if (getGintMode() === "oob") {
        resetOobFlowVisual();
        if (oobNodeClient) {
          oobNodeClient.classList.remove("sending");
          oobNodeClient.offsetHeight;
          oobNodeClient.classList.add("sending");
          setTimeout(function () { if (oobNodeClient) oobNodeClient.classList.remove("sending"); }, 600);
        }
        var duration = Math.round(STAGE_MS / speedMultiplier());
        var oobEdges = [oobEdgeC2P, oobEdgeP2C, oobEdgeGuardrail, oobEdgeP2Prov, oobEdgeProv2P];
        oobEdges.forEach(function (e) { if (e) e.classList.remove("active", "success", "blocked", "network-error", "result-blocked"); });
        if (oobEdgeC2P) oobEdgeC2P.classList.add("active");
        var c2pPromise = runOobPacketAnim(oobEdgeC2P, oobPacketC2P, true, duration);
        c2pPromise.then(function () {
          if (oobNodeProxy) oobNodeProxy.classList.add("state-processing");
        });
        try {
          var res = await authFetch("/api/oob-chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg, stream: false })
          });
          await c2pPromise;
          if (oobEdgeC2P) { oobEdgeC2P.classList.remove("active"); oobEdgeC2P.classList.add("success"); }
          if (oobPacketC2P) oobPacketC2P.style.opacity = "0";
          if (oobNodeClient) oobNodeClient.classList.add("sent");
          if (oobNodeProxy) oobNodeProxy.classList.add("state-processing");
          var contentType = (res.headers.get("Content-Type") || "").toLowerCase();
          if (contentType.indexOf("application/json") !== -1) {
            var body = await res.json().catch(function () { return { detail: "Invalid response" }; });
            if (!res.ok) {
              setResponseContent(getOobResponseText(body) || "Request failed", false);
              if (oobEdgeC2P) { oobEdgeC2P.classList.remove("success"); oobEdgeC2P.classList.add("network-error"); }
            } else {
              lastReply = getOobResponseText(body);
              var blocked = isOobBlockedResponse(body);
              var oobTrace = buildOobTrace(blocked);
              lastOobTrace = oobTrace;
              setResponseContent(lastReply || "—", blocked);
              setTimeout(function () {
                oobCurrentStepIndex = 1;
                var playPromise = playOobTrace(oobTrace, STAGE_MS, 1);
                if (playPromise) playPromise.then(function () { oobCurrentStepIndex = lastOobTrace.length; });
              }, 400);
            }
          } else if (contentType.indexOf("text/event-stream") !== -1) {
            var accumulated = "";
            var readCount = 0;
            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var buf = "";
            for (;;) {
              var chunk = await reader.read();
              if (chunk.done) break;
              readCount++;
              buf += decoder.decode(chunk.value, { stream: true });
              var events = buf.split(/\n\n/);
              buf = events.pop() || "";
              for (var i = 0; i < events.length; i++) {
                var line = events[i].split("\n").find(function (l) { return l.indexOf("data:") === 0; });
                if (!line) continue;
                var payload = line.replace(/^data:\s*/, "").trim();
                if (payload === "[DONE]") continue;
                try {
                  var obj = JSON.parse(payload);
                  var choice = obj.choices && obj.choices[0];
                  var delta = choice && choice.delta;
                  var content = delta && delta.content;
                  if (typeof content === "string") {
                    accumulated += content;
                    setResponseContent(accumulated || "…", false);
                  }
                } catch (err) {}
              }
            }
            lastReply = accumulated || "—";
            var oobTrace = buildOobTrace(false);
            lastOobTrace = oobTrace;
            function runTrace() {
              setTimeout(function () {
                oobCurrentStepIndex = 1;
                var playPromise = playOobTrace(oobTrace, STAGE_MS, 1);
                if (playPromise) playPromise.then(function () { oobCurrentStepIndex = lastOobTrace.length; });
              }, 400);
            }
            if (readCount <= 1 && lastReply) {
              setResponseContentWithStreamingEffect(lastReply, false, runTrace);
            } else {
              setResponseContent(lastReply || "—", false);
              runTrace();
            }
          } else {
            setResponseContent("Unsupported response type", false);
            if (oobEdgeC2P) { oobEdgeC2P.classList.remove("success"); oobEdgeC2P.classList.add("network-error"); }
          }
        } catch (e) {
          await c2pPromise;
          if (oobEdgeC2P) { oobEdgeC2P.classList.remove("active"); oobEdgeC2P.classList.add("network-error"); }
          if (oobPacketC2P) oobPacketC2P.style.opacity = "0";
          setResponseContent("Error: " + (e && e.message || "Request failed"), false);
        }
        gintSend.disabled = false;
        return;
      }

      resetFlowVisual();
      if (gintRequestInspection) { gintRequestInspection.textContent = "—"; gintRequestInspection.className = "gint-decision-value"; }
      if (gintResponseInspection) { gintResponseInspection.textContent = "—"; gintResponseInspection.className = "gint-decision-value"; }
      if (gintRequestFailedWrap) { gintRequestFailedWrap.style.display = "none"; gintRequestFailedDetail && (gintRequestFailedDetail.textContent = "—"); }
      if (gintResponseFailedWrap) { gintResponseFailedWrap.style.display = "none"; gintResponseFailedDetail && (gintResponseFailedDetail.textContent = "—"); }

      if (gintNodeClient) {
        gintNodeClient.classList.remove("sending");
        gintNodeClient.offsetHeight;
        gintNodeClient.classList.add("sending");
        setTimeout(function () { if (gintNodeClient) gintNodeClient.classList.remove("sending"); }, 600);
      }

      var duration = Math.round(STAGE_MS / speedMultiplier());
      [edgeC2G, edgeG2C, edgeG2P, edgeP2G].forEach(e => e && e.classList.remove("active", "success", "blocked", "network-error"));
      edgeC2G && edgeC2G.classList.add("active");
      var c2gAnimPromise = runPacketAnim(edgeC2G, packetC2G, true, duration);
      c2gAnimPromise.then(function () {
        if (gintNodeGuardrail) gintNodeGuardrail.classList.add("state-processing");
      });

      var fetchPromise = authFetch("/api/guardrail-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      }).then(res => {
        if (res.ok) return res.json();
        return res.json().then(d => { throw { httpError: true, message: d.detail || "Request failed" }; });
      });

      try {
        const data = await fetchPromise;
        await c2gAnimPromise;
        if (edgeC2G) { edgeC2G.classList.remove("active"); edgeC2G.classList.add("success"); }
        if (packetC2G) packetC2G.style.opacity = "0";
        if (gintNodeClient) gintNodeClient.classList.add("sent");
        if (gintNodeGuardrail) gintNodeGuardrail.classList.add("state-processing");

        lastReply = data.reply || "";
        lastGuardrail = data.guardrail && data.guardrail.result ? data.guardrail : null;
        lastTrace = buildTraceFromGuardrail(lastGuardrail);

        setResponseContent(lastReply || "—", isPromptRejectedReply(lastReply));
        updateDecisionPanel(lastGuardrail);
        await new Promise(function (r) { setTimeout(r, 400); });
        playTraceFromStep(lastTrace, 1, STAGE_MS);
      } catch (e) {
        await c2gAnimPromise;
        var isNetworkError = !e || !e.httpError;
        if (edgeC2G && isNetworkError) { edgeC2G.classList.remove("active"); edgeC2G.classList.add("network-error"); }
        else if (edgeC2G) { edgeC2G.classList.remove("active"); edgeC2G.classList.add("success"); }
        if (packetC2G) packetC2G.style.opacity = "0";
        setResponseContent("Error: " + (e && e.message || "Request failed"), false);
      } finally {
        gintSend.disabled = false;
      }
    });
  }

  if (gintReplay) gintReplay.addEventListener("click", function () {
    if (getGintMode() === "oob" && lastOobTrace.length) {
      oobCurrentStepIndex = 0;
      var p = playOobTrace(lastOobTrace);
      if (p) p.then(function () { oobCurrentStepIndex = lastOobTrace.length; });
    } else {
      playTrace(lastTrace);
    }
  });
  if (gintNextStep) gintNextStep.addEventListener("click", stepOnce);

  setGintArchDescByMode("inline");
  if (gintModeInline) {
    gintModeInline.addEventListener("click", function () {
      if (gintModeInline.disabled) return;
      gintModeInline.classList.add("active");
      if (gintModeOob) gintModeOob.classList.remove("active");
      setGintArchDescByMode("inline");
    });
  }
  if (gintModeOob) {
    gintModeOob.addEventListener("click", function () {
      if (gintModeOob.disabled) return;
      gintModeOob.classList.add("active");
      if (gintModeInline) gintModeInline.classList.remove("active");
      setGintArchDescByMode("oob");
    });
  }

  // ---------- OOB 旁路模式：动画节点与边
  const oobNodeClient = document.getElementById("oobNodeClient");
  const oobNodeProxy = document.getElementById("oobNodeProxy");
  const oobNodeGuardrail = document.getElementById("oobNodeGuardrail");
  const oobNodeProvider = document.getElementById("oobNodeProvider");
  const oobEdgeC2P = document.getElementById("oobEdgeC2P");
  const oobEdgeP2C = document.getElementById("oobEdgeP2C");
  const oobEdgeGuardrail = document.getElementById("oobEdgeGuardrail");
  const oobEdgeP2Prov = document.getElementById("oobEdgeP2Prov");
  const oobEdgeProv2P = document.getElementById("oobEdgeProv2P");
  const oobPacketC2P = document.getElementById("oobPacketC2P");
  const oobPacketP2C = document.getElementById("oobPacketP2C");
  const oobPacketG2P = document.getElementById("oobPacketG2P");
  const oobPacketP2Prov = document.getElementById("oobPacketP2Prov");
  const oobPacketProv2P = document.getElementById("oobPacketProv2P");
  const oobGuardrailStatus = document.getElementById("oobGuardrailStatus");
  const oobProxyStatus = document.getElementById("oobProxyStatus");
  const oobBlockBubble = document.getElementById("oobBlockBubble");
  let oobCurrentStepIndex = 0;

  function isOobBlockedResponse(body) {
    if (!body || typeof body !== "object") return false;
    var id = (body.id || "").toString();
    if (/chatcmpl-error-/.test(id)) return true;
    try {
      var choices = body.choices;
      if (Array.isArray(choices) && choices.length > 0) {
        var content = (choices[0].message && choices[0].message.content) || "";
        if (/Request blocked by F5 AI Guardrails/i.test(content)) return true;
        if (/Request blocked due to sensitive data detected/i.test(content)) return true;
      }
    } catch (e) {}
    return false;
  }

  function getOobResponseText(body) {
    if (!body || typeof body !== "object") return "";
    try {
      var choices = body.choices;
      if (Array.isArray(choices) && choices.length > 0 && choices[0].message)
        return (choices[0].message.content || "").toString();
    } catch (e) {}
    return body.detail ? String(body.detail) : JSON.stringify(body);
  }

  function buildOobTrace(blocked) {
    if (blocked) {
      return [
        { stage: "c2p", status: "success" },
        { stage: "p2g", status: "success" },
        { stage: "scan_check", status: "blocked" },
        { stage: "g2p", status: "blocked" },
        { stage: "p2c", status: "success" }
      ];
    }
    return [
      { stage: "c2p", status: "success" },
      { stage: "p2g", status: "success" },
      { stage: "scan_check", status: "success" },
      { stage: "p2prov", status: "success" },
      { stage: "prov2p", status: "success" },
      { stage: "p2c", status: "success" }
    ];
  }

  function resetOobFlowVisual() {
    [oobEdgeC2P, oobEdgeP2C, oobEdgeGuardrail, oobEdgeP2Prov, oobEdgeProv2P].forEach(function (el) {
      if (el) el.classList.remove("active", "success", "blocked", "network-error", "idle", "gint-edge-scan", "result-blocked");
    });
    [oobPacketC2P, oobPacketP2C, oobPacketG2P, oobPacketP2Prov, oobPacketProv2P].forEach(function (el) {
      if (!el) return;
      el.classList.remove("anim", "anim-back");
      el.style.left = "";
      el.style.top = "";
      el.style.opacity = "0";
    });
    if (oobGuardrailStatus) oobGuardrailStatus.textContent = "";
    if (oobProxyStatus) oobProxyStatus.textContent = "";
    if (oobNodeGuardrail) oobNodeGuardrail.classList.remove("state-success", "state-blocked", "state-processing");
    if (oobNodeProxy) oobNodeProxy.classList.remove("state-processing", "state-success");
    if (oobNodeClient) oobNodeClient.classList.remove("sending", "sent", "received");
    if (oobNodeProvider) oobNodeProvider.classList.remove("state-idle", "received", "sent", "receiving", "sending");
    if (oobBlockBubble) oobBlockBubble.classList.remove("visible");
  }

  function resetOobFlowVisualFromProxy() {
    [oobEdgeGuardrail, oobEdgeP2Prov, oobEdgeProv2P, oobEdgeP2C].forEach(function (el) {
      if (el) el.classList.remove("active", "success", "blocked", "network-error", "idle", "gint-edge-scan", "result-blocked");
    });
    [oobPacketG2P, oobPacketP2Prov, oobPacketProv2P, oobPacketP2C].forEach(function (el) {
      if (!el) return;
      el.classList.remove("anim", "anim-back");
      el.style.left = "";
      el.style.top = "";
      el.style.opacity = "0";
    });
    if (oobGuardrailStatus) oobGuardrailStatus.textContent = "";
    if (oobNodeGuardrail) oobNodeGuardrail.classList.remove("state-success", "state-blocked", "state-processing");
    if (oobNodeProvider) oobNodeProvider.classList.remove("state-idle", "received", "sent", "receiving", "sending");
    if (oobBlockBubble) oobBlockBubble.classList.remove("visible");
  }

  function runOobPacketAnim(edgeEl, packetEl, fromStartToEnd, durationMs) {
    if (!edgeEl || !packetEl) return Promise.resolve();
    var isVertical = packetEl.classList.contains("gint-packet-vertical");
    packetEl.style.transition = "none";
    packetEl.style.opacity = "0";
    if (isVertical) {
      packetEl.style.left = "";
      packetEl.style.top = fromStartToEnd ? "0%" : "100%";
    } else {
      packetEl.style.top = "";
      packetEl.style.left = fromStartToEnd ? "0%" : "100%";
    }
    packetEl.offsetHeight;
    packetEl.style.opacity = "1";
    packetEl.classList.add("anim");
    if (!fromStartToEnd) packetEl.classList.add("anim-back");
    var prop = isVertical ? "top" : "left";
    packetEl.style.transition = prop + " " + durationMs + "ms linear";
    if (isVertical)
      packetEl.style.top = fromStartToEnd ? "100%" : "0%";
    else
      packetEl.style.left = fromStartToEnd ? "100%" : "0%";
    return new Promise(function (r) { setTimeout(r, durationMs); });
  }

  function runOobStep(stepIndex, trace, baseMs, singleStep) {
    if (stepIndex >= trace.length) return Promise.resolve();
    var t = trace[stepIndex];
    var duration = Math.round(baseMs / speedMultiplier());
    var next = function () {
      return singleStep ? Promise.resolve() : runOobStep(stepIndex + 1, trace, baseMs, singleStep);
    };
    var allEdges = [oobEdgeC2P, oobEdgeP2C, oobEdgeGuardrail, oobEdgeP2Prov, oobEdgeProv2P];
    var edgeActive = function (el) {
      allEdges.forEach(function (e) {
        if (e) e.classList.remove("active", "gint-edge-scan");
      });
      if (el) el.classList.add("active");
    };
    var edgeSuccess = function (el) {
      if (el) { el.classList.remove("active"); el.classList.add("success"); }
    };
    var edgeBlocked = function (el) {
      if (el) { el.classList.remove("active"); el.classList.add("blocked"); }
    };

    if (t.stage === "c2p" && t.status === "success") {
      edgeActive(oobEdgeC2P);
      return runOobPacketAnim(oobEdgeC2P, oobPacketC2P, true, duration).then(function () {
        edgeSuccess(oobEdgeC2P);
        oobPacketC2P.style.opacity = "0";
        if (oobNodeClient) oobNodeClient.classList.add("sent");
        if (oobNodeProxy) oobNodeProxy.classList.add("state-processing");
        return new Promise(function (r) { setTimeout(r, 400); }).then(next);
      });
    }
    if (t.stage === "p2g" && t.status === "success") {
      edgeActive(oobEdgeGuardrail);
      if (oobNodeGuardrail) oobNodeGuardrail.classList.add("state-processing");
      return new Promise(function (r) { setTimeout(r, duration); }).then(function () {
        if (oobEdgeGuardrail) oobEdgeGuardrail.classList.remove("active");
        return new Promise(function (r) { setTimeout(r, 400); }).then(next);
      });
    }
    if (t.stage === "scan_check") {
      if (oobNodeGuardrail) oobNodeGuardrail.classList.remove("state-processing");
      if (oobGuardrailStatus) oobGuardrailStatus.textContent = t.status === "blocked" ? "Request Blocked" : "Request ✓";
      if (t.status === "blocked") {
        if (oobNodeGuardrail) { oobNodeGuardrail.classList.remove("state-success"); oobNodeGuardrail.classList.add("state-blocked"); }
        if (oobNodeProvider) oobNodeProvider.classList.add("state-idle");
        if (oobEdgeP2Prov) oobEdgeP2Prov.classList.add("idle");
        if (oobEdgeProv2P) oobEdgeProv2P.classList.add("idle");
        if (oobBlockBubble) { oobBlockBubble.textContent = "Request blocked by F5 AI Guardrails"; oobBlockBubble.classList.add("visible"); }
      } else {
        if (oobNodeGuardrail) oobNodeGuardrail.classList.add("state-success");
        if (oobEdgeGuardrail) {
          oobEdgeGuardrail.classList.remove("active");
          oobEdgeGuardrail.classList.add("success");
        }
        if (oobBlockBubble) oobBlockBubble.classList.remove("visible");
      }
      return new Promise(function (r) { setTimeout(r, duration); }).then(next);
    }
    if (t.stage === "g2p") {
      if (t.status === "blocked") {
        if (oobEdgeGuardrail) {
          oobEdgeGuardrail.classList.remove("active");
          oobEdgeGuardrail.classList.add("result-blocked");
        }
        return new Promise(function (r) { setTimeout(r, duration); }).then(next);
      }
      return runOobPacketAnim(oobEdgeGuardrail, oobPacketG2P, true, duration).then(function () {
        oobPacketG2P.style.opacity = "0";
        if (oobEdgeGuardrail) {
          oobEdgeGuardrail.classList.remove("active");
          oobEdgeGuardrail.classList.add("success");
        }
        return new Promise(function (r) { setTimeout(r, 400); }).then(next);
      });
    }
    if (t.stage === "p2prov" && t.status === "success") {
      edgeActive(oobEdgeP2Prov);
      return runOobPacketAnim(oobEdgeP2Prov, oobPacketP2Prov, true, duration).then(function () {
        edgeSuccess(oobEdgeP2Prov);
        oobPacketP2Prov.style.opacity = "0";
        if (oobNodeProvider) {
          oobNodeProvider.classList.remove("state-idle");
          oobNodeProvider.classList.add("received", "receiving");
          setTimeout(function () { if (oobNodeProvider) oobNodeProvider.classList.remove("receiving"); }, 400);
        }
        return next();
      });
    }
    if (t.stage === "prov2p" && t.status === "success") {
      edgeActive(oobEdgeProv2P);
      return runOobPacketAnim(oobEdgeProv2P, oobPacketProv2P, false, duration).then(function () {
        edgeSuccess(oobEdgeProv2P);
        oobPacketProv2P.style.opacity = "0";
        if (oobNodeProvider) {
          oobNodeProvider.classList.add("sent", "sending");
          setTimeout(function () { if (oobNodeProvider) oobNodeProvider.classList.remove("sending"); }, 400);
        }
        return next();
      });
    }
    if (t.stage === "p2c" && t.status === "success") {
      edgeActive(oobEdgeP2C);
      return runOobPacketAnim(oobEdgeP2C, oobPacketP2C, false, duration).then(function () {
        edgeSuccess(oobEdgeP2C);
        oobPacketP2C.style.opacity = "0";
        if (oobNodeClient) oobNodeClient.classList.add("received");
        if (oobNodeProxy) { oobNodeProxy.classList.remove("state-processing"); oobNodeProxy.classList.add("state-success"); }
        return Promise.resolve();
      });
    }
    return new Promise(function (r) { setTimeout(r, 50); }).then(next);
  }

  function playOobTrace(trace, baseMs, startFromStep) {
    if (!trace.length) return;
    var fromStep = startFromStep > 0 ? startFromStep : 0;
    if (fromStep > 0) {
      resetOobFlowVisualFromProxy();
    } else {
      resetOobFlowVisual();
      oobCurrentStepIndex = 0;
    }
    return runOobStep(fromStep, trace, baseMs || STAGE_MS);
  }

  setGintArchDescByMode(getGintMode());
})();