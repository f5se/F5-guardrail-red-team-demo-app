const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const btnSend = document.getElementById("btnSend");
const btnClear = document.getElementById("btnClear");
const chatTitleEl = document.getElementById("chatTitle");
const modeBadgeEl = document.getElementById("modeBadge");
const kbSkillBadgeEl = document.getElementById("kbSkillBadge");
const navButtons = Array.from(document.querySelectorAll(".navBtn"));

const chatView = document.getElementById("chatView");
const settingsView = document.getElementById("settingsView");
const toggleMultiTurnEl = document.getElementById("toggleMultiTurn");
const toggleAgentSkillEl = document.getElementById("toggleAgentSkill");
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

    el.className = "engineStatus " + (s === "PASS" ? "pass" : "block");

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

function setActiveView(view){
  activeView = view;
  navButtons.forEach(b => b.classList.toggle("active", b.dataset.view === view));

  if (view === "CHAT"){
    chatTitleEl.textContent = "AI Chatbot";
    chatView.style.display = "";
    settingsView.style.display = "none";
    inputEl.focus();
  } else {
    chatTitleEl.textContent = "Settings";
    chatView.style.display = "none";
    settingsView.style.display = "";
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