"use strict";

const state = { incidents: [], selected: null, investigation: null, token: null, principal: null };
const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const formatTime = (value) => new Intl.DateTimeFormat(undefined, {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"}).format(new Date(value));

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) openAuthDialog();
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function openAuthDialog() {
  const dialog = byId("auth-dialog");
  if (!dialog.open) dialog.showModal();
}

async function loadIdentity() {
  try {
    state.principal = await api("/api/v1/auth/me");
    byId("connect-button").textContent = state.principal.authenticated ? state.principal.principal : "Local mode";
  } catch (_) {
    state.principal = null;
  }
}

async function loadIncidents() {
  try {
    state.incidents = await api("/api/v1/incidents");
    byId("system-status").textContent = "API online";
    byId("open-count").textContent = state.incidents.filter((item) => !["closed", "mitigated"].includes(item.status)).length;
    renderIncidentList();
    if (!state.selected && state.incidents.length) await selectIncident(state.incidents[0].id);
  } catch (error) { byId("system-status").textContent = "API unavailable"; toast(error.message); }
}

function renderIncidentList() {
  const list = byId("incident-list");
  if (!state.incidents.length) { list.innerHTML = '<div class="empty-state">No incidents yet.</div>'; return; }
  list.innerHTML = state.incidents.map((incident) => `
    <button class="incident-item ${state.selected?.id === incident.id ? "active" : ""}" data-incident="${incident.id}" type="button">
      <strong>${escapeHtml(incident.title)}</strong><small>${escapeHtml(incident.affected_service || "Service unknown")}</small>
      <span class="incident-meta"><span>${escapeHtml(incident.severity.toUpperCase())}</span><span>${formatTime(incident.created_at)}</span></span>
    </button>`).join("");
  list.querySelectorAll("[data-incident]").forEach((button) => button.addEventListener("click", () => selectIncident(button.dataset.incident)));
}

async function selectIncident(id) {
  try {
    const detail = await api(`/api/v1/incidents/${id}`);
    state.selected = detail.incident; state.investigation = detail.latest_investigation;
    renderIncidentList(); renderIncident(); renderInvestigation();
  } catch (error) { toast(error.message); }
}

function renderIncident() {
  const incident = state.selected;
  byId("incident-severity").textContent = incident.severity.toUpperCase();
  byId("incident-status").textContent = incident.status.toUpperCase();
  byId("incident-title").textContent = incident.title;
  byId("incident-summary").textContent = incident.summary || `${incident.affected_service || "Unknown service"} · ${formatTime(incident.window.start)} → ${formatTime(incident.window.end)}`;
  byId("investigate-button").disabled = false;
}

function renderInvestigation() {
  const run = state.investigation;
  byId("top-confidence").textContent = run?.hypotheses?.length ? `${Math.round(run.hypotheses[0].confidence * 100)}%` : "—";
  byId("evidence-count").textContent = run?.evidence?.length ?? "—";
  byId("agent-mode").textContent = run ? run.mode.replace("_", " ") : "—";
  renderHypotheses(run?.hypotheses || [], run?.evidence || []);
  renderEvidence(run?.evidence || []); renderGraph(run?.graph); renderAgents(run?.agent_runs || []);
  if (run) loadTimeline(); else byId("timeline-list").innerHTML = "No timeline available.";
  loadRemediation();
}

function renderHypotheses(hypotheses, evidence) {
  const target = byId("hypothesis-list");
  if (!hypotheses.length) { target.className = "hypothesis-list empty-state"; target.textContent = "Run an investigation to generate grounded hypotheses."; return; }
  const ledger = Object.fromEntries(evidence.map((item) => [item.id, item])); target.className = "hypothesis-list";
  target.innerHTML = hypotheses.map((item) => {
    const score = item.causal_score || {};
    return `<article class="hypothesis-card"><div class="hypothesis-top"><div><p class="eyebrow">#${item.rank} · ${escapeHtml(item.status.toUpperCase())}</p><h3>${escapeHtml(item.root_cause_service)} — ${escapeHtml(item.failure_mode)}</h3></div><span class="confidence">${Math.round(item.confidence * 100)}%</span></div><p>${escapeHtml(item.description)}</p><div class="score-track"><i style="width:${item.confidence * 100}%"></i></div><div class="causal-grid"><div>Anomaly<b>${percent(score.anomaly_strength)}</b></div><div>Temporal<b>${percent(score.temporal_precedence)}</b></div><div>Criticality<b>${percent(score.trace_criticality)}</b></div><div>Graph fit<b>${percent(score.graph_consistency)}</b></div></div><div class="evidence-chips">${item.evidence_for.map((id) => `<span class="chip" title="${escapeHtml(ledger[id]?.observation || id)}">${escapeHtml(ledger[id]?.source || "evidence")} · ${id.slice(0,8)}</span>`).join("")}</div></article>`;
  }).join("");
}

function renderEvidence(evidence) {
  const target = byId("evidence-list"); if (!evidence.length) { target.className = "evidence-list empty-state"; target.textContent = "No evidence available."; return; }
  target.className = "evidence-list"; target.innerHTML = evidence.map((item) => `<article class="evidence-row"><div><span class="badge neutral">${escapeHtml(item.source.toUpperCase())}</span></div><div><strong>${escapeHtml(item.service || "global")}</strong><br><small>${escapeHtml(item.signal)}</small></div><p>${escapeHtml(item.observation)}<br><small>${escapeHtml(item.query_reference)}</small></p><small class="${item.origin === "historical_prior" ? "origin-prior" : ""}">${escapeHtml(item.origin)}<br>${Math.round(item.confidence * 100)}%</small></article>`).join("");
}

function renderGraph(graph) {
  const target = byId("graph-container"); if (!graph?.nodes?.length) { target.className = "graph-container empty-state"; target.textContent = "No trace graph available."; return; }
  target.className = "graph-container"; const width = 900, height = 480, radius = 190, cx = 450, cy = 240;
  const points = Object.fromEntries(graph.nodes.map((node, index) => { const angle = (index / graph.nodes.length) * Math.PI * 2 - Math.PI / 2; return [node.service, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius}]; }));
  const edges = graph.edges.map((edge) => `<line class="graph-edge" x1="${points[edge.caller]?.x}" y1="${points[edge.caller]?.y}" x2="${points[edge.callee]?.x}" y2="${points[edge.callee]?.y}"><title>${escapeHtml(edge.caller)} → ${escapeHtml(edge.callee)} · p95 ${edge.p95_latency_ms.toFixed(1)} ms</title></line>`).join("");
  const nodes = graph.nodes.map((node) => `<g class="graph-node" transform="translate(${points[node.service].x} ${points[node.service].y})"><circle r="30"><title>${escapeHtml(node.service)} · ${node.error_count} errors</title></circle><text y="48">${escapeHtml(node.service)}</text></g>`).join("");
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trace-derived service dependency graph"><defs><marker id="arrow" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#3b4b58"></path></marker></defs>${edges}${nodes}</svg>`;
}

async function loadTimeline() { try { const items = await api(`/api/v1/incidents/${state.selected.id}/timeline`); const target = byId("timeline-list"); target.className = "timeline"; target.innerHTML = items.map((item) => `<article class="timeline-item"><time>${formatTime(item.timestamp)}</time><h3>${escapeHtml(item.title)}</h3></article>`).join("") || "No timeline available."; } catch (_) { byId("timeline-list").textContent = "No timeline available."; } }
function renderAgents(runs) { const target = byId("agent-list"); if (!runs.length) { target.className = "agent-list empty-state"; target.textContent = "No agent run available."; return; } target.className = "agent-list"; target.innerHTML = runs.map((run) => `<article class="agent-row"><span class="badge ${run.status === "completed" ? "good" : ""}">${escapeHtml(run.status)}</span><strong>${escapeHtml(run.agent_id.replaceAll("_", " "))}</strong><p>${escapeHtml((run.notes || []).join(" ") || "Completed assigned evidence task.")}</p><small>${duration(run.started_at, run.completed_at)}</small></article>`).join(""); }
async function loadRemediation() { const target = byId("remediation-panel"); if (!state.selected) { target.textContent = "No remediation plan available."; return; } try { const plan = await api(`/api/v1/incidents/${state.selected.id}/remediation`); renderRemediation(plan); } catch (_) { target.className = "empty-state"; target.textContent = "No remediation plan available."; } }
function renderRemediation(plan) { state.remediationId = plan.id; const target = byId("remediation-panel"); target.className = "hypothesis-list"; target.innerHTML = `<article class="hypothesis-card"><p class="eyebrow">LEVEL ${plan.risk_level} · ${escapeHtml(plan.status.toUpperCase())}</p><h3>${escapeHtml(plan.action_type.replaceAll("_", " "))}</h3><p>${escapeHtml(plan.rationale)}</p><div class="evidence-chips">${plan.evidence_ids.map((id) => `<span class="chip">${id.slice(0,8)}</span>`).join("")}</div>${plan.status === "proposed" ? `<button class="button primary" id="approve-remediation" type="button">Approve action</button> <button class="button" id="reject-remediation" type="button">Reject</button>` : ""}</article>`; byId("approve-remediation")?.addEventListener("click", () => decideRemediation("approve")); byId("reject-remediation")?.addEventListener("click", () => decideRemediation("reject")); }
async function decideRemediation(decision) { const actor = state.principal?.authenticated ? state.principal.principal : window.prompt("Operator identity (email or on-call handle)"); if (!actor) return; const reason = window.prompt(`Reason to ${decision} this remediation`); if (!reason) return; try { const plan = await api(`/api/v1/incidents/${state.selected.id}/${decision}-remediation`, {method:"POST", body: JSON.stringify({plan_id: state.remediationId, actor, reason})}); renderRemediation(plan); toast(`Remediation ${decision}d`); } catch (error) { toast(error.message); } }

async function investigate() { if (!state.selected) return; const button = byId("investigate-button"); button.disabled = true; button.textContent = "Agents collecting evidence…"; try { state.investigation = await api(`/api/v1/incidents/${state.selected.id}/investigate`, {method:"POST", body:JSON.stringify({mode:"multi_agent"})}); renderInvestigation(); await loadIncidents(); toast("Investigation completed"); } catch (error) { toast(error.message); } finally { button.disabled = false; button.textContent = "Run investigation"; } }
async function createIncident(form) { const data = new FormData(form), end = new Date(), start = new Date(end.getTime() - Number(data.get("minutes")) * 60000); const payload = {title:data.get("title"), summary:data.get("summary"), affected_service:data.get("affected_service") || null, severity:data.get("severity"), incident_start:start.toISOString(), incident_end:end.toISOString()}; try { const incident = await api("/api/v1/incidents", {method:"POST", body:JSON.stringify(payload)}); byId("incident-dialog").close(); await loadIncidents(); await selectIncident(incident.id); toast("Incident created"); } catch (error) { toast(error.message); } }
function percent(value) { return `${Math.round((value || 0) * 100)}%`; } function duration(start, end) { return `${Math.max(0, new Date(end) - new Date(start))} ms`; }
function toast(message) { const target = byId("toast"); target.textContent = message; target.classList.add("visible"); setTimeout(() => target.classList.remove("visible"), 3200); }

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab)); document.querySelectorAll(".tab-view").forEach((view) => view.classList.toggle("hidden", view.id !== `view-${tab.dataset.tab}`)); }));
const incidentDialog = byId("incident-dialog");
const incidentForm = byId("incident-form");
function closeIncidentDialog() { incidentDialog.close("cancel"); }

byId("refresh-button").addEventListener("click", loadIncidents);
byId("investigate-button").addEventListener("click", investigate);
byId("new-incident-button").addEventListener("click", () => {
  incidentForm.reset();
  incidentDialog.showModal();
});
byId("close-incident-dialog").addEventListener("click", closeIncidentDialog);
byId("cancel-incident-dialog").addEventListener("click", closeIncidentDialog);
incidentForm.addEventListener("submit", (event) => {
  event.preventDefault();
  createIncident(event.currentTarget);
});
byId("connect-button").addEventListener("click", openAuthDialog);
byId("cancel-auth-dialog").addEventListener("click", () => byId("auth-dialog").close("cancel"));
byId("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = new FormData(event.currentTarget).get("token");
  await loadIdentity();
  if (!state.principal?.authenticated) {
    state.token = null;
    toast("Authentication failed");
    return;
  }
  byId("auth-dialog").close("connected");
  event.currentTarget.reset();
  await loadIncidents();
});
setInterval(() => { byId("utc-clock").textContent = new Date().toISOString().slice(11, 19) + " UTC"; }, 1000);
loadIdentity();
loadIncidents();
