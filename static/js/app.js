const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const btnSend = document.getElementById("btnSend");
const btnClear = document.getElementById("btnClear");
const chatTitleEl = document.getElementById("chatTitle");
const modeBadgeEl = document.getElementById("modeBadge");
const kbSkillBadgeEl = document.getElementById("kbSkillBadge");
const navButtons = Array.from(document.querySelectorAll(".navBtn"));

// 攻击示例面板元素
const attackCardEl = document.getElementById("attackCard");
const attackPanelBodyEl = document.getElementById("attackPanelBody");
const attackPanelToggleEl = document.getElementById("attackPanelToggle");
const attackPresets = Array.isArray(window.ATTACK_PRESETS) ? window.ATTACK_PRESETS : [];
let attackTooltipEl = null;

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

  attackPanelBodyEl.innerHTML = "";

  if (!attackPresets.length) {
    const empty = document.createElement("div");
    empty.className = "attackEmpty";
    empty.textContent = "当前没有可用的攻击示例，请在 config/attack-presets.json 中配置。";
    attackPanelBodyEl.appendChild(empty);
    return;
  }

  // 分组：按 category 聚合
  const groups = {};
  attackPresets.forEach(p => {
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
        if (!inputEl) return;
        const text = String(preset.prompt || "");
        if (!text) return;

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

function updateGuardrailPanel(guardrail){
  if (!guardrailCardEl) return;

  if (!guardrail || typeof guardrail !== "object" || !guardrail.result){
    resetGuardrailPanel();
    return;
  }

  const result = guardrail.result || {};
  // Support both shapes: (1) guardrail.scanners.scanners = { [id]: {...} } or (2) guardrail.scanners = { [id]: {...} } (direct map)
  const scannersInner = guardrail.scanners && guardrail.scanners.scanners;
  const isInnerMap = scannersInner && typeof scannersInner === "object" && !Array.isArray(scannersInner);
  const directMap = guardrail.scanners && typeof guardrail.scanners === "object" && !Array.isArray(guardrail.scanners)
    && !("scanners" in guardrail.scanners)
    && !("configs" in guardrail.scanners)
    ? guardrail.scanners
    : null;
  const scannersRoot = isInnerMap ? scannersInner : directMap;
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

  // Build scanner meta map: key = scannerId (string), value = { name, direction, source: { type } }
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
    const sid = (r.scannerId || "").toString();
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

let activeView = "CHAT";
let isSending = false;

function uuidv4(){
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === "x" ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

let conversationId = uuidv4();

const LS_KEY = "multi_turn_enabled";
function getMultiTurnEnabled(){
  return localStorage.getItem(LS_KEY) === "true";
}
function setMultiTurnEnabled(v){
  localStorage.setItem(LS_KEY, v ? "true" : "false");
  toggleMultiTurnEl.checked = !!v;
  modeBadgeEl.textContent = v ? "Multi-turn" : "Single-turn";
}
setMultiTurnEnabled(getMultiTurnEnabled());

function setEnterpriseKBSkillEnabled(v){
  if (!kbSkillBadgeEl) return;
  kbSkillBadgeEl.textContent = v ? "Enterprise KB Skill ON" : "Enterprise KB Skill OFF";
  kbSkillBadgeEl.classList.toggle("kbSkillOn", !!v);
  kbSkillBadgeEl.classList.toggle("kbSkillOff", !v);
}
setEnterpriseKBSkillEnabled(!!toggleAgentSkillEl?.checked);

toggleMultiTurnEl.addEventListener("change", () => {
  setMultiTurnEnabled(toggleMultiTurnEl.checked);

  // 🔥 RESET CONVERSATION
  conversationId = uuidv4();

  // Optional UX: clear chat window
  messagesEl.innerHTML = "";
  addBubble("assistant","Hi there! How can I help?");
});

const redteamView = document.getElementById("redteamView");
const engineRow = document.getElementById("engineRow");
const layoutEl = document.querySelector(".layout");

function setActiveView(view){
  activeView = view;
  navButtons.forEach(b => b.classList.toggle("active", b.dataset.view === view));

  chatView.style.display = "none";
  settingsView.style.display = "none";
  redteamView.style.display = "none";

  const chatOnlyEls = [engineRow, modeBadgeEl, kbSkillBadgeEl, btnClear];
  chatOnlyEls.forEach(el => { if(el) el.style.display = "none"; });

  const subEl = document.querySelector(".sub");

  if (view === "CHAT"){
    chatTitleEl.textContent = "AI Assistant";
    chatView.style.display = "";
    chatOnlyEls.forEach(el => { if(el) el.style.display = ""; });
    if (attackCardEl) attackCardEl.style.display = "";
    if (subEl) subEl.textContent = "F5 AI Demo Chatbot · Connected to Backend LLM";
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
    }
  }
}
navButtons.forEach(btn => {
  btn.addEventListener("click", () => setActiveView(btn.dataset.view));
});

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

  isSending = true;
  btnSend.disabled = true;
  inputEl.disabled = true;

  addBubble("user", msg);
  inputEl.value = "";

  const assistantBubble = addBubble("assistant", "…");

  try{
    const res = await fetch("/api/chat", {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({
        message: msg,
        conversation_id: conversationId,
        multi_turn: getMultiTurnEnabled()
      })
    });

    const data = await res.json();

    if(!res.ok){
      assistantBubble.textContent = "" + (data.detail || data.error || ("HTTP " + res.status));
      return;
    }

    const reply = data.reply || "(empty reply)";
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
    const r = await fetch("/api/settings", { cache: "no-store" });
    if(!r.ok) return;
    const s = await r.json();

    document.getElementById("patternBox").value = s.patterns || "";
    document.getElementById("heuristicSlider").value = s.heuristic_threshold || 10;
    document.getElementById("toxSlider").value = s.toxic_threshold || 0.75;
    document.getElementById("piSlider").value = s.pi_threshold || 0.7;
    document.getElementById("heuristicVal").textContent = s.heuristic_threshold;
    document.getElementById("toxVal").textContent = s.toxic_threshold;
    document.getElementById("piVal").textContent = s.pi_threshold;

    if (toggleAgentSkillEl) {
      const enabled = asBool(s.agent_skill_enabled);
      toggleAgentSkillEl.checked = enabled;
      setEnterpriseKBSkillEnabled(enabled);
    }
    if (toggleGuardrailDebugEl) {
      toggleGuardrailDebugEl.checked = asBool(s.debug_guardrail_raw_enabled);
    }
    if (toggleF5GuardrailOnlyEl) {
      toggleF5GuardrailOnlyEl.checked = asBool(s.f5_guardrail_only);
    }
    if (kbDirInputEl) {
      kbDirInputEl.value = s.kb_dir || "./enterprise_kb";
    }
    document.getElementById("agentMaxStepsSlider").value = s.agent_max_steps || 4;
    document.getElementById("agentMaxStepsVal").textContent = s.agent_max_steps || 4;
  }catch(e){
    console.error("loadSettings failed:", e);
  }
}

async function saveSettings(showToast = true){
  const res = await fetch("/api/settings", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({
      patterns: document.getElementById("patternBox").value,
      heuristic_threshold: document.getElementById("heuristicSlider").value,
      toxic_threshold: document.getElementById("toxSlider").value,
      pi_threshold: document.getElementById("piSlider").value,
      agent_skill_enabled: !!document.getElementById("toggleAgentSkill")?.checked,
      f5_guardrail_only: !!document.getElementById("toggleF5GuardrailOnly")?.checked,
      debug_guardrail_raw_enabled: !!document.getElementById("toggleGuardrailDebug")?.checked,
      kb_dir: document.getElementById("kbDirInput")?.value || "./enterprise_kb",
      agent_max_steps: document.getElementById("agentMaxStepsSlider")?.value || 4
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
  setEnterpriseKBSkillEnabled(!!toggleAgentSkillEl?.checked);
  saveSettings(false);
});
document.getElementById("toggleGuardrailDebug")?.addEventListener("change", () => saveSettings(false));
document.getElementById("toggleF5GuardrailOnly")?.addEventListener("change", () => saveSettings(false));
document.getElementById("kbDirInput")?.addEventListener("change", () => saveSettings(false));
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