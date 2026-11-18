const API_BASE = window.PLANNER_API_BASE ?? "http://localhost:8000/api/v1";
const sessionId =
  localStorage.getItem("planner-session-id") ??
  (globalThis.crypto?.randomUUID?.() ?? `session-${Date.now()}`);

localStorage.setItem("planner-session-id", sessionId);

const statusElement = document.querySelector("#api-status");
const integrationList = document.querySelector("#integration-list");
const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message");
const sendButton = document.querySelector("#send-button");
const plansContainer = document.querySelector("#plans");
const refreshButton = document.querySelector("#refresh-plans");

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `요청 실패 (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch (_) {
      // Keep the safe generic message for a non-JSON upstream response.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function addMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "나" : "플래너";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  wrapper.append(label, paragraph);
  messages.append(wrapper);
  wrapper.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function integrationItem(label, ready) {
  const item = document.createElement("li");
  const mark = document.createElement("span");
  mark.className = `check ${ready ? "ready" : "pending"}`;
  mark.textContent = ready ? "✓" : "·";
  item.append(mark, document.createTextNode(`${label} ${ready ? "연결됨" : "연결 전"}`));
  return item;
}

async function loadHealth() {
  try {
    const health = await api("/health");
    statusElement.className = "status status-ready";
    statusElement.textContent = "API 연결됨";
    integrationList.replaceChildren(
      integrationItem("SQLite", health.database === "ready"),
      integrationItem("LLM", health.integrations.llm),
      integrationItem("카카오", health.integrations.kakao),
      integrationItem("의료기관 데이터", health.integrations.medical_data),
    );
  } catch (error) {
    statusElement.className = "status status-error";
    statusElement.textContent = "API 연결 안 됨";
    integrationList.replaceChildren(integrationItem("백엔드", false));
  }
}

function formatKoreanDate(value) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Seoul",
  }).format(new Date(value));
}

async function removePlan(planId) {
  if (!window.confirm("이 방문 계획을 삭제할까요?")) return;
  try {
    await api(`/plans/${planId}`, { method: "DELETE" });
    await loadPlans();
  } catch (error) {
    addMessage("assistant", error.message);
  }
}

function planCard(plan) {
  const article = document.createElement("article");
  article.className = "plan-card";

  const heading = document.createElement("div");
  const type = document.createElement("span");
  type.className = "plan-type";
  type.textContent = plan.institution_type === "hospital" ? "병원" : "약국";
  const title = document.createElement("h3");
  title.textContent = plan.institution_name;
  const address = document.createElement("p");
  address.textContent = plan.institution_address;
  heading.append(type, title, address);

  const time = document.createElement("dl");
  const pairs = [
    ["출발", formatKoreanDate(plan.departure_at)],
    ["도착 예상", formatKoreanDate(plan.expected_arrival_at)],
    ["주행시간", `${Math.floor(plan.travel_duration_seconds / 60)}분 ${plan.travel_duration_seconds % 60}초`],
  ];
  for (const [term, description] of pairs) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = description;
    time.append(dt, dd);
  }

  const remove = document.createElement("button");
  remove.className = "danger-button";
  remove.type = "button";
  remove.textContent = "삭제";
  remove.addEventListener("click", () => removePlan(plan.id));
  article.append(heading, time, remove);
  return article;
}

async function loadPlans() {
  refreshButton.disabled = true;
  try {
    const plans = await api("/plans");
    if (plans.length === 0) {
      plansContainer.className = "plans-empty";
      plansContainer.textContent = "저장된 방문 계획이 없습니다.";
      return;
    }
    plansContainer.className = "plans-grid";
    plansContainer.replaceChildren(...plans.map(planCard));
  } catch (error) {
    plansContainer.className = "plans-empty error-copy";
    plansContainer.textContent = error.message;
  } finally {
    refreshButton.disabled = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;

  addMessage("user", message);
  messageInput.value = "";
  sendButton.disabled = true;
  sendButton.textContent = "확인 중";
  try {
    const response = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    addMessage("assistant", response.answer);
  } catch (error) {
    addMessage("assistant", error.message);
  } finally {
    sendButton.disabled = false;
    sendButton.textContent = "보내기";
    messageInput.focus();
  }
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

refreshButton.addEventListener("click", loadPlans);

loadHealth();
loadPlans();

