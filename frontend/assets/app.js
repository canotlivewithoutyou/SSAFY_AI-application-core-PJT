const API_BASE = window.PLANNER_API_BASE ?? "http://localhost:8000/api/v1";
const sessionId =
  localStorage.getItem("planner-session-id") ??
  (globalThis.crypto?.randomUUID?.() ?? `session-${Date.now()}`);

localStorage.setItem("planner-session-id", sessionId);

const elements = {
  landingView: document.querySelector("#landing-view"),
  plannerView: document.querySelector("#planner-view"),
  plansView: document.querySelector("#plans-view"),
  appFooter: document.querySelector("#app-footer"),
  messages: document.querySelector("#messages"),
  form: document.querySelector("#chat-form"),
  message: document.querySelector("#message"),
  send: document.querySelector("#send-button"),
  progressPanel: document.querySelector("#progress-panel"),
  progressSummary: document.querySelector("#progress-summary"),
  progressSteps: [...document.querySelectorAll("#progress-steps li")],
  emptyResult: document.querySelector("#empty-result"),
  recommendation: document.querySelector("#recommendation"),
  recommendationContext: document.querySelector("#recommendation-context"),
  recommendationType: document.querySelector("#recommendation-type"),
  recommendationName: document.querySelector("#recommendation-name"),
  recommendationAddress: document.querySelector("#recommendation-address"),
  recommendationDuration: document.querySelector("#recommendation-duration"),
  recommendationArrival: document.querySelector("#recommendation-arrival"),
  recommendationClose: document.querySelector("#recommendation-close"),
  recommendationReason: document.querySelector("#recommendation-reason"),
  savePlan: document.querySelector("#save-plan"),
  focusSearch: document.querySelector("#focus-search"),
  tracePanel: document.querySelector("#trace-panel"),
  traceToggle: document.querySelector("#trace-toggle"),
  traceSummary: document.querySelector("#trace-summary"),
  traceContent: document.querySelector("#trace-content"),
  plans: document.querySelector("#plans"),
  refreshPlans: document.querySelector("#refresh-plans"),
  planDialog: document.querySelector("#plan-dialog"),
  dialogTitle: document.querySelector("#dialog-title"),
  dialogType: document.querySelector("#dialog-type"),
  detailList: document.querySelector("#plan-detail-list"),
  editToggle: document.querySelector("#edit-plan-toggle"),
  deletePlan: document.querySelector("#delete-plan"),
  editForm: document.querySelector("#edit-plan-form"),
  editName: document.querySelector("#edit-name"),
  editDeparture: document.querySelector("#edit-departure"),
  editReason: document.querySelector("#edit-reason"),
  cancelEdit: document.querySelector("#cancel-edit"),
  toast: document.querySelector("#toast"),
};

let latestResponse = null;
let currentPlan = null;
let requestSequence = 0;
let toastTimer = null;

const toolLabels = {
  search_place: "출발지 확인",
  search_nearby_institutions: "주변 후보 조회",
  get_institution_detail: "운영시간 확인",
  get_driving_route: "자동차 경로 계산",
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `요청을 완료하지 못했습니다. (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).filter(Boolean).join(" · ") || message;
      }
    } catch (_) {
      // Keep a safe generic message when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function showToast(message, type = "success") {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `toast ${type === "success" ? "" : type}`.trim();
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4200);
}

function addMessage(role, text, { error = false } = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = [
    "message",
    role === "user" ? "user-message" : "assistant-message",
    error ? "error-message" : "",
  ].filter(Boolean).join(" ");
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "나" : "열려있DOC";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  wrapper.append(label, paragraph);
  elements.messages.append(wrapper);
  wrapper.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function formatDateTime(value, options = {}) {
  if (!value) return "확인 필요";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "확인 필요";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...options,
  }).format(parsed);
}

function formatTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function formatDuration(seconds) {
  if (!Number.isFinite(Number(seconds))) return "확인 필요";
  const total = Math.max(0, Number(seconds));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  if (minutes && remainder) return `${minutes}분 ${remainder}초`;
  return minutes ? `${minutes}분` : `${remainder}초`;
}

function seoulDateKey(value) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function toDatetimeLocal(value) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(value));
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

function setEmptyResult(title, copy) {
  elements.emptyResult.hidden = false;
  elements.emptyResult.querySelector("strong").textContent = title;
  elements.emptyResult.querySelector("p").textContent = copy;
}

const stepTools = {
  place: "search_place",
  nearby: "search_nearby_institutions",
  hours: "get_institution_detail",
  route: "get_driving_route",
};

const stageLabels = {
  analyze_request: "요청 분석",
  build_plan: "실행 계획",
  execute_tools: "Tool 실행",
  judge_constraints: "조건 판단",
  replan: "재계획",
  generate_response: "응답 생성",
};

elements.progressSteps.forEach((step) => {
  const small = step.querySelector("small");
  if (small) step.dataset.defaultNote = small.textContent;
});

function setStepNote(step, text) {
  const small = step.querySelector("small");
  if (small) small.textContent = text ?? step.dataset.defaultNote ?? "";
}

function resetProgress() {
  elements.progressPanel?.removeAttribute("aria-busy");
  elements.progressSteps.forEach((step) => {
    step.classList.remove("active", "complete", "failed", "recovered");
    setStepNote(step);
  });
}

// While the request runs we only show a neutral state. Stage completion is
// rendered afterwards from the events the backend actually recorded.
function startProgress() {
  resetProgress();
  elements.progressPanel?.setAttribute("aria-busy", "true");
  elements.recommendation.hidden = true;
  elements.tracePanel.hidden = true;
  elements.traceContent.replaceChildren();
  setEmptyResult("요청을 처리하고 있어요.", "처리가 끝나면 실제로 실행된 단계와 Tool 기록을 보여 드립니다.");
  elements.progressSummary.textContent = "처리 중입니다. 완료 후 실제 실행 기록으로 단계를 표시합니다.";
}

async function fetchRunTrace(response) {
  if (!response.request_id) return null;
  try {
    const trace = await api(
      `/logs/sessions/${encodeURIComponent(response.session_id)}?request_id=${encodeURIComponent(response.request_id)}`,
    );
    // Guard against rendering another run's events.
    if (trace?.request_id !== response.request_id) return null;
    return trace.summary ?? null;
  } catch (_) {
    return null;
  }
}

function toolName(name) {
  return toolLabels[name] ?? name;
}

function finishProgress(response, summary) {
  resetProgress();
  if (!summary) {
    elements.progressSummary.textContent = "실행 기록을 불러오지 못해 단계 표시를 생략했습니다.";
    return;
  }
  const tools = summary.tools ?? [];
  elements.progressSteps.forEach((step) => {
    const key = step.dataset.step;
    if (key === "done") {
      if (summary.selected) {
        step.classList.add("complete");
        setStepNote(step, "조건 충족 후보 선택");
      } else if (response.status === "failed") {
        step.classList.add("failed");
        setStepNote(step, summary.stop_reason || "후보 확정 실패");
      }
      return;
    }
    const calls = tools.filter((call) => call.tool === stepTools[key]);
    if (!calls.length) return; // Not executed in this request.
    const failures = calls.filter((call) => !call.ok);
    const succeeded = calls.some((call) => call.ok);
    const cachedCount = calls.filter((call) => call.cached).length;
    const calledCount = calls.length - cachedCount;
    if (succeeded) {
      step.classList.add("complete");
      if (failures.length) step.classList.add("recovered");
      const usage = [calledCount ? `호출 ${calledCount}회` : "", cachedCount ? `캐시 ${cachedCount}회` : ""]
        .filter(Boolean)
        .join(" · ");
      setStepNote(
        step,
        failures.length ? `실패 ${failures.length}회 후 성공 · ${usage}` : `성공 · ${usage}`,
      );
    } else {
      step.classList.add("failed");
      setStepNote(step, `실패: ${failures.at(-1)?.error_message || failures.at(-1)?.error_code || "사유 미제공"}`);
    }
  });

  const executed = summary.tool_call_count + summary.cache_hit_count;
  if (response.status === "setup_required") {
    elements.progressSummary.textContent = "환경변수 설정이 필요해 Tool을 실행하지 않았습니다.";
  } else if (executed === 0) {
    elements.progressSummary.textContent = "Tool 호출 없이 응답했습니다.";
  } else if (summary.selected) {
    elements.progressSummary.textContent = "도착 시점에도 운영하는 후보를 찾았습니다.";
  } else if (response.status === "needs_input") {
    elements.progressSummary.textContent = "추가 조건을 기다리고 있습니다.";
  } else {
    elements.progressSummary.textContent = "확인 결과를 안내했습니다.";
  }
}

function recommendationInterval(recommendation) {
  const intervals = recommendation.opening_intervals ?? [];
  const arrival = new Date(recommendation.expected_arrival_at).getTime();
  return intervals.find((interval) => {
    const start = new Date(interval.start).getTime();
    const end = new Date(interval.end).getTime();
    return start <= arrival && arrival < end;
  }) ?? intervals[0] ?? null;
}

function renderRecommendation(response) {
  const recommendation = response.recommendation;
  if (!recommendation) return;
  const request = response.request_context ?? {};
  const interval = recommendationInterval(recommendation);
  const origin = request.origin_name || request.origin_query || "출발지";
  elements.recommendationContext.textContent =
    `${origin} · ${formatDateTime(request.departure_at)} 출발${request.departure_was_defaulted ? " (지금 출발)" : ""}`;
  elements.recommendationType.textContent = request.institution_type === "hospital" ? "병원" : "약국";
  elements.recommendationName.textContent = recommendation.name || "기관명 확인 필요";
  elements.recommendationAddress.textContent = recommendation.address || "주소 확인 필요";
  elements.recommendationDuration.textContent = formatDuration(recommendation.duration_seconds);
  elements.recommendationArrival.textContent = formatTime(recommendation.expected_arrival_at);
  elements.recommendationClose.textContent = interval ? formatTime(interval.end) : "확인 필요";
  elements.recommendationReason.textContent =
    recommendation.selection_reason || "이동시간 상한 이내이며 공개 운영 종료 전에 도착할 것으로 예상돼요.";
  elements.savePlan.disabled = false;
  elements.savePlan.textContent = "방문 계획 저장";
  elements.emptyResult.hidden = true;
  elements.recommendation.hidden = false;
}

function traceItem(entry) {
  const item = document.createElement("li");
  item.className = `trace-item trace-${entry.kind}`;
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  switch (entry.kind) {
    case "decision":
      title.textContent = entry.decision_maker === "llm" ? "LLM 판단" : "규칙 기반 판단";
      detail.textContent = entry.reason || "";
      break;
    case "tool": {
      const status = entry.cached ? (entry.ok ? "캐시 재사용" : "캐시된 실패") : entry.ok ? "성공" : "실패";
      if (!entry.ok) item.classList.add("failed");
      title.textContent = `Tool ${entry.order}. ${toolName(entry.tool)} · ${status}`;
      const parts = [];
      if (entry.duration_ms != null) parts.push(`${entry.duration_ms}ms`);
      if (!entry.ok) parts.push(entry.error_message || entry.error_code || "사유 미제공");
      detail.textContent = parts.join(" · ");
      break;
    }
    case "candidate_excluded":
      title.textContent = `후보 제외: ${entry.name || entry.institution_id || "후보"}`;
      detail.textContent = [entry.reason, entry.stop_reason ? `종료: ${entry.stop_reason}` : ""]
        .filter(Boolean)
        .join(" · ");
      break;
    case "replan":
      title.textContent = `재계획 ${entry.replan_count}회차${entry.limit ? ` (상한 ${entry.limit}회)` : ""}`;
      detail.textContent = "직전 후보를 제외하고 다음 후보를 확인합니다.";
      break;
    case "candidate_selected":
      title.textContent = `후보 선택: ${entry.name || entry.institution_id || "후보"}`;
      detail.textContent = entry.reason || "";
      break;
    case "setup_required":
      title.textContent = "환경변수 설정 필요";
      detail.textContent = `${(entry.missing_settings ?? []).join(", ")} 값을 .env에 설정한 뒤 서버를 다시 시작해 주세요.`;
      break;
    default:
      title.textContent = entry.kind;
  }
  item.append(title);
  if (detail.textContent) item.append(detail);
  return item;
}

function renderTrace(response, summary) {
  elements.traceContent.hidden = true;
  elements.traceToggle.setAttribute("aria-expanded", "false");
  if (!summary) {
    // Fallback: show only what the response itself reports, labelled as such.
    const calls = response.tool_calls ?? [];
    elements.tracePanel.hidden = calls.length === 0;
    elements.traceSummary.textContent = `Tool ${calls.length}회 · 실행 로그 조회 실패`;
    const list = document.createElement("ol");
    list.className = "trace-list";
    calls.forEach((raw, index) => {
      const [name, suffix] = raw.split(":");
      const item = document.createElement("li");
      item.textContent = `${index + 1}. ${toolName(name)}${suffix === "cache" ? " (캐시 재사용)" : ""}`;
      list.append(item);
    });
    elements.traceContent.replaceChildren(list);
    return;
  }

  const timeline = summary.timeline ?? [];
  elements.tracePanel.hidden = timeline.length === 0 && (summary.stages ?? []).length === 0;
  const parts = [`Tool ${summary.tool_call_count}회`];
  if (summary.cache_hit_count) parts.push(`캐시 ${summary.cache_hit_count}회`);
  if (summary.failed_tool_count) parts.push(`실패 ${summary.failed_tool_count}회`);
  if (summary.replan_count) parts.push(`재계획 ${summary.replan_count}회`);
  if (summary.excluded_count) parts.push(`제외 ${summary.excluded_count}곳`);
  elements.traceSummary.textContent = parts.join(" · ");

  const children = [];
  const stages = summary.stages ?? [];
  if (stages.length) {
    const stageLine = document.createElement("p");
    stageLine.className = "trace-stages";
    stageLine.textContent = "실행 단계: " + stages
      .map((stage) => `${stageLabels[stage.stage] ?? stage.stage}${stage.status === "completed" ? "" : "(실패)"}`)
      .join(" → ");
    children.push(stageLine);
  }
  const list = document.createElement("ol");
  list.className = "trace-list trace-timeline";
  timeline.forEach((entry) => list.append(traceItem(entry)));
  children.push(list);
  elements.traceContent.replaceChildren(...children);
}

function requiredNumber(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} 좌표를 확인할 수 없어 저장하지 못했습니다.`);
  return number;
}

function planPayloadFromResponse(response) {
  if (response.plan_draft) return response.plan_draft;
  const recommendation = response.recommendation;
  const request = response.request_context;
  if (!recommendation || !request?.departure_at || !recommendation.expected_arrival_at) {
    throw new Error("저장할 추천 정보가 충분하지 않습니다. 다시 검색해 주세요.");
  }
  const interval = recommendationInterval(recommendation);
  return {
    institution_type: request.institution_type,
    institution_id: recommendation.institution_id || null,
    institution_name: recommendation.name,
    institution_address: recommendation.address,
    visit_date: seoulDateKey(recommendation.expected_arrival_at),
    origin_name: request.origin_name || request.origin_query,
    origin_longitude: requiredNumber(request.origin_longitude, "출발지"),
    origin_latitude: requiredNumber(request.origin_latitude, "출발지"),
    destination_longitude: requiredNumber(recommendation.longitude, "기관"),
    destination_latitude: requiredNumber(recommendation.latitude, "기관"),
    departure_at: request.departure_at,
    expected_arrival_at: recommendation.expected_arrival_at,
    travel_duration_seconds: Number(recommendation.duration_seconds),
    operation_start: interval?.start ?? null,
    operation_end: interval?.end ?? null,
    selection_reason: recommendation.selection_reason || "도착 시점 운영시간과 이동시간 조건을 충족함",
  };
}

async function saveLatestPlan() {
  if (!latestResponse?.recommendation) return;
  elements.savePlan.disabled = true;
  elements.savePlan.textContent = "저장 중";
  try {
    const result = await api("/plans", {
      method: "POST",
      body: JSON.stringify(planPayloadFromResponse(latestResponse)),
    });
    elements.savePlan.textContent = "저장 완료";
    const message = result.warnings?.length
      ? `계획을 저장했습니다. ${result.warnings.join(" ")}`
      : "방문 계획을 저장했습니다.";
    showToast(message, result.warnings?.length ? "warning" : "success");
    await loadPlans();
  } catch (error) {
    elements.savePlan.disabled = false;
    elements.savePlan.textContent = "방문 계획 저장";
    showToast(error.message, "error");
  }
}

function setView(view) {
  const showLanding = view === "landing";
  const showPlanner = view === "planner";
  const showPlans = view === "plans";
  elements.landingView.hidden = !showLanding;
  elements.plannerView.hidden = !showPlanner;
  elements.plansView.hidden = !showPlans;
  elements.appFooter.hidden = showLanding;
  document.body.dataset.view = view;

  if (showPlans) {
    history.replaceState(null, "", "#plans");
    loadPlans();
  } else if (showPlanner) {
    history.replaceState(null, "", "#planner");
  } else {
    history.replaceState(null, "", "#landing");
  }

  if (!showPlans) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function overlapMap(plans) {
  const overlaps = new Map(plans.map((plan) => [plan.id, new Set()]));
  for (let left = 0; left < plans.length; left += 1) {
    for (let right = left + 1; right < plans.length; right += 1) {
      const first = plans[left];
      const second = plans[right];
      if (first.visit_date !== second.visit_date) continue;
      if (
        new Date(first.departure_at) < new Date(second.expected_arrival_at) &&
        new Date(first.expected_arrival_at) > new Date(second.departure_at)
      ) {
        overlaps.get(first.id).add(second.id);
        overlaps.get(second.id).add(first.id);
      }
    }
  }
  return overlaps;
}

function planTime(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "plan-time";
  const term = document.createElement("span");
  term.textContent = label;
  const time = document.createElement("strong");
  time.textContent = value;
  wrapper.append(term, time);
  return wrapper;
}

async function removePlan(planId) {
  if (!window.confirm("이 방문 계획을 삭제할까요? 삭제한 계획은 복구할 수 없습니다.")) return;
  try {
    await api(`/plans/${planId}`, { method: "DELETE" });
    if (elements.planDialog.open) elements.planDialog.close();
    showToast("방문 계획을 삭제했습니다.");
    await loadPlans();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function planRow(plan, overlappingIds) {
  const row = document.createElement("article");
  row.className = `plan-row${overlappingIds.size ? " overlapping" : ""}`;

  const institution = document.createElement("div");
  institution.className = "plan-institution";
  const name = document.createElement("strong");
  name.textContent = plan.institution_name;
  const meta = document.createElement("span");
  meta.textContent = `${plan.institution_type === "hospital" ? "병원" : "약국"} · ${plan.institution_address}`;
  institution.append(name, meta);

  const actions = document.createElement("div");
  actions.className = "plan-row-actions";
  const detail = document.createElement("button");
  detail.className = "detail-button";
  detail.type = "button";
  detail.textContent = "상세";
  detail.addEventListener("click", () => openPlan(plan.id));
  const remove = document.createElement("button");
  remove.className = "row-delete-button";
  remove.type = "button";
  remove.textContent = "삭제";
  remove.addEventListener("click", () => removePlan(plan.id));
  actions.append(detail, remove);

  row.append(
    institution,
    planTime("출발", formatTime(plan.departure_at)),
    planTime("도착", formatTime(plan.expected_arrival_at)),
    planTime("소요", formatDuration(plan.travel_duration_seconds)),
    actions,
  );
  if (overlappingIds.size) {
    const warning = document.createElement("p");
    warning.className = "overlap-warning";
    warning.textContent = `같은 날짜에 시간이 겹치는 계획 ${[...overlappingIds].map((id) => `#${id}`).join(", ")}이 있어요. 계획은 그대로 유지됩니다.`;
    row.append(warning);
  }
  return row;
}

function planDateLabel(dateKey) {
  const date = new Date(`${dateKey}T00:00:00+09:00`);
  return {
    date: new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric" }).format(date),
    weekday: new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", weekday: "long" }).format(date),
  };
}

function renderPlans(plans) {
  if (plans.length === 0) {
    elements.plans.className = "plans-empty";
    elements.plans.textContent = "저장된 방문 계획이 없습니다. 추천 결과에서 ‘방문 계획 저장’을 눌러 주세요.";
    return;
  }
  const overlaps = overlapMap(plans);
  const groups = new Map();
  plans.forEach((plan) => {
    if (!groups.has(plan.visit_date)) groups.set(plan.visit_date, []);
    groups.get(plan.visit_date).push(plan);
  });
  const container = document.createElement("div");
  container.className = "plan-groups";
  [...groups.entries()].forEach(([dateKey, groupPlans]) => {
    const section = document.createElement("section");
    section.className = "plan-group";
    const date = document.createElement("div");
    date.className = "plan-date";
    const label = planDateLabel(dateKey);
    const strong = document.createElement("strong");
    strong.textContent = label.date;
    const weekday = document.createElement("span");
    weekday.textContent = label.weekday;
    date.append(strong, weekday);
    const list = document.createElement("div");
    list.className = "plan-list";
    list.replaceChildren(...groupPlans.map((plan) => planRow(plan, overlaps.get(plan.id))));
    section.append(date, list);
    container.append(section);
  });
  elements.plans.className = "";
  elements.plans.replaceChildren(container);
}

async function loadPlans() {
  elements.refreshPlans.disabled = true;
  try {
    renderPlans(await api("/plans"));
  } catch (error) {
    elements.plans.className = "plans-empty";
    elements.plans.textContent = error.message;
  } finally {
    elements.refreshPlans.disabled = false;
  }
}

function detailPair(term, description) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = description;
  return [dt, dd];
}

async function openPlan(planId) {
  try {
    const plan = await api(`/plans/${planId}`);
    currentPlan = plan;
    elements.dialogType.textContent = plan.institution_type === "hospital" ? "병원" : "약국";
    elements.dialogTitle.textContent = plan.institution_name;
    const details = [
      ["주소", plan.institution_address],
      ["출발지", plan.origin_name],
      ["출발", formatDateTime(plan.departure_at)],
      ["도착 예상", formatDateTime(plan.expected_arrival_at)],
      ["주행시간", formatDuration(plan.travel_duration_seconds)],
      ["운영시간", plan.operation_start ? `${formatDateTime(plan.operation_start)} ~ ${formatTime(plan.operation_end)}` : "확인 필요"],
      ["선택 근거", plan.selection_reason],
      ["생성 일시", formatDateTime(plan.created_at)],
    ];
    elements.detailList.replaceChildren(...details.flatMap(([term, value]) => detailPair(term, value)));
    elements.editForm.hidden = true;
    elements.editName.value = plan.institution_name;
    elements.editDeparture.value = toDatetimeLocal(plan.departure_at);
    elements.editDeparture.min = `${plan.visit_date}T00:00`;
    elements.editDeparture.max = `${plan.visit_date}T23:59`;
    elements.editReason.value = plan.selection_reason;
    if (typeof elements.planDialog.showModal === "function") {
      elements.planDialog.showModal();
    } else {
      elements.planDialog.setAttribute("open", "");
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function updateCurrentPlan(event) {
  event.preventDefault();
  if (!currentPlan) return;
  const departureAt = `${elements.editDeparture.value}:00+09:00`;
  const expectedArrival = new Date(
    new Date(departureAt).getTime() + Number(currentPlan.travel_duration_seconds) * 1000,
  ).toISOString();
  try {
    const result = await api(`/plans/${currentPlan.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        institution_name: elements.editName.value.trim(),
        departure_at: departureAt,
        expected_arrival_at: expectedArrival,
        visit_date: seoulDateKey(expectedArrival),
        selection_reason: elements.editReason.value.trim(),
      }),
    });
    currentPlan = result.plan;
    elements.planDialog.close();
    await loadPlans();
    showToast(
      result.warnings?.length ? `계획을 수정했습니다. ${result.warnings.join(" ")}` : "방문 계획을 수정했습니다.",
      result.warnings?.length ? "warning" : "success",
    );
  } catch (error) {
    showToast(error.message, "error");
  }
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.message.value.trim();
  if (!message) return;
  addMessage("user", message);
  elements.message.value = "";
  elements.send.disabled = true;
  elements.send.textContent = "확인 중";
  const sequence = ++requestSequence;
  startProgress();
  try {
    const response = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    const summary = await fetchRunTrace(response);
    if (sequence !== requestSequence) return; // A newer request owns the screen.
    latestResponse = response;
    finishProgress(response, summary);
    addMessage("assistant", response.answer, { error: response.status === "failed" || response.status === "setup_required" });
    renderTrace(response, summary);
    if (response.recommendation) {
      renderRecommendation(response);
    } else if (response.status === "setup_required") {
      const names = (response.missing_settings ?? []).join(", ");
      setEmptyResult(
        "환경변수 설정이 필요해요.",
        `${names || "필요한 환경변수"}를 .env에 설정하고 서버를 다시 시작해 주세요. 키 값은 화면과 로그에 표시하지 않습니다.`,
      );
    } else {
      const title = response.status === "needs_input"
        ? "조건을 조금 더 알려 주세요."
        : response.status === "completed"
          ? "안내를 확인해 주세요."
          : "추천 결과를 확정하지 못했습니다.";
      setEmptyResult(title, response.answer);
    }
  } catch (error) {
    if (sequence !== requestSequence) return;
    resetProgress();
    elements.progressSummary.textContent = "요청 처리 중 오류가 발생했습니다. 실행 단계는 확인되지 않았습니다.";
    addMessage("assistant", "요청을 처리하지 못했습니다. 서버 연결을 확인하고 다시 시도해 주세요.", { error: true });
    setEmptyResult("요청을 완료하지 못했습니다.", error.message);
  } finally {
    elements.send.disabled = false;
    elements.send.innerHTML = '<span class="search-icon" aria-hidden="true"></span> 열린 곳 찾기';
    elements.message.focus();
  }
});

elements.message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    setView(button.dataset.view);
    const scrollTarget = button.dataset.scroll;
    if (scrollTarget) {
      window.requestAnimationFrame(() => {
        document.querySelector(`#${scrollTarget}`)?.scrollIntoView({ behavior: "smooth" });
      });
    }
  });
});
elements.savePlan.addEventListener("click", saveLatestPlan);
elements.focusSearch.addEventListener("click", () => {
  elements.message.focus();
  elements.message.scrollIntoView({ behavior: "smooth", block: "center" });
});
elements.traceToggle.addEventListener("click", () => {
  const expanded = elements.traceToggle.getAttribute("aria-expanded") === "true";
  elements.traceToggle.setAttribute("aria-expanded", String(!expanded));
  elements.traceContent.hidden = expanded;
});
elements.refreshPlans.addEventListener("click", loadPlans);
elements.editToggle.addEventListener("click", () => {
  elements.editForm.hidden = false;
  elements.editName.focus();
});
elements.cancelEdit.addEventListener("click", () => {
  elements.editForm.hidden = true;
});
elements.deletePlan.addEventListener("click", () => {
  if (currentPlan) removePlan(currentPlan.id);
});
elements.editForm.addEventListener("submit", updateCurrentPlan);
elements.planDialog.addEventListener("close", () => {
  currentPlan = null;
  elements.editForm.hidden = true;
});

loadPlans();
const initialView =
  window.location.hash === "#plans"
    ? "plans"
    : window.location.hash === "#planner"
      ? "planner"
      : "landing";
setView(initialView);
