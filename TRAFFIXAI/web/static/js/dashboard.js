/**
 * TRAFFIX AI - Technical Live Dashboard & 2D Vehicle Canvas Visualizer
 * Streams real-time TraCI telemetry, draws moving vehicles on HTML5 canvas,
 * updates junction traffic lights, storage occupancy, and Chart.js graphs.
 */

let pollInterval = null;
let isPolling = false;

// Canvas & Context
let canvas = null;
let ctx = null;
let cachedVehicles = [];
let cachedJunctions = {};
let hoveredVehicle = null;

// Chart.js instances
let queueChart = null;
let emissionsChart = null;
let perfChart = null;

document.addEventListener("DOMContentLoaded", () => {
  initCanvas();
  initCharts();
  fetchStatus();
  startPolling();
});

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(fetchStatus, 400); // 2.5 Hz refresh for smooth vehicle movement
  isPolling = true;
}

function stopPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = null;
  isPolling = false;
}

// =============================================================================
// TELEMETRY FETCH & DASHBOARD UPDATE
// =============================================================================

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

function renderDashboard(data) {
  if (!data || !data.network) return;

  // 1. KPI Counters
  document.getElementById("metric-clock").innerText = data.simulation_time || 0;
  document.getElementById("metric-active-vehs").innerText = data.network.active_vehicles || 0;
  document.getElementById("metric-avg-speed").innerText = data.network.average_speed_kmh || "0.0";
  document.getElementById("metric-waiting-time").innerText = (data.network.total_waiting_time_s || 0).toLocaleString();
  document.getElementById("metric-co2").innerText = data.emissions_cumulative ? data.emissions_cumulative.co2_kg : "0.00";
  document.getElementById("metric-fuel").innerText = data.emissions_cumulative ? data.emissions_cumulative.fuel_liters : "0.00";
  document.getElementById("metric-throughput").innerText = data.network.total_completed_vehicles || 0;

  // Status Badge
  const badge = document.getElementById("sim-status-badge");
  if (data.is_paused) {
    badge.className = "status-badge status-paused";
    badge.innerText = "⏸ PAUSED";
  } else {
    badge.className = "status-badge status-running";
    badge.innerText = "● LIVE SIMULATING";
  }

  // Active Density & Controller Dropdowns sync
  const selCtrl = document.getElementById("select-controller");
  if (selCtrl && data.controller_type) selCtrl.value = data.controller_type;

  const selDensity = document.getElementById("select-density");
  if (selDensity && data.density_level) selDensity.value = data.density_level;

  // 2. Junction Rigs & Explainability Reasons
  const junctions = data.junctions || {};
  cachedJunctions = junctions;

  ["J1", "J2", "J3"].forEach(jid => {
    const jdata = junctions[jid] || {};
    const phase = jdata.phase_id || 0;
    const phaseName = jdata.phase_name || "CORRIDOR_GREEN";
    const elapsed = jdata.time_in_phase || 0;
    const action = jdata.last_action || "";

    const rBulb = document.getElementById(`${jid.toLowerCase()}-bulb-red`);
    const yBulb = document.getElementById(`${jid.toLowerCase()}-bulb-yellow`);
    const gBulb = document.getElementById(`${jid.toLowerCase()}-bulb-green`);

    [rBulb, yBulb, gBulb].forEach(b => { if (b) b.classList.remove("active"); });

    if (phase === 0) {
      if (gBulb) gBulb.classList.add("active");
    } else if (phase === 1 || phase === 3) {
      if (yBulb) yBulb.classList.add("active");
    } else if (phase === 2) {
      if (rBulb) rBulb.classList.add("active");
    }

    const pNameElem = document.getElementById(`${jid.toLowerCase()}-phase-name`);
    if (pNameElem) pNameElem.innerText = phaseName;

    const tPhaseElem = document.getElementById(`${jid.toLowerCase()}-time-in-phase`);
    if (tPhaseElem) tPhaseElem.innerText = elapsed;

    const actElem = document.getElementById(`${jid.toLowerCase()}-action-text`);
    if (actElem) actElem.innerText = action;

    const gBadge = document.getElementById(`${jid.toLowerCase()}-gating-badge`);
    if (gBadge) {
      if (jdata.emergency_active) {
        gBadge.innerText = "EMERGENCY PRIORITY";
        gBadge.style.backgroundColor = "rgba(239, 68, 68, 0.3)";
        gBadge.style.color = "#fca5a5";
      } else if (jdata.gating_active) {
        gBadge.innerText = "GATING UPSTREAM";
        gBadge.style.backgroundColor = "rgba(239, 68, 68, 0.25)";
        gBadge.style.color = "var(--signal-red)";
      } else if (jdata.flushing_active) {
        gBadge.innerText = "FLUSHING BOTTLENECK";
        gBadge.style.backgroundColor = "rgba(8, 145, 178, 0.25)";
        gBadge.style.color = "#67e8f9";
      } else {
        gBadge.innerText = "NORMAL";
        gBadge.style.backgroundColor = "rgba(99, 102, 241, 0.15)";
        gBadge.style.color = "#818cf8";
      }
    }
  });

  // Decision Explainability Log
  const explainElem = document.getElementById("ai-decision-text");
  if (explainElem) {
    const r1 = junctions.J1 ? `[J1] ${junctions.J1.reason}` : "";
    const r2 = junctions.J2 ? `[J2] ${junctions.J2.reason}` : "";
    const r3 = junctions.J3 ? `[J3] ${junctions.J3.reason}` : "";
    explainElem.innerText = `${r1}\n${r2}\n${r3}`;
  }

  // 3. Storage & Spillback Risk Monitoring (J1->J2 & J2->J3)
  const spill = data.spillback_reports || {};
  updateStorageCard("j1-j2", spill["J1_to_J2"]);
  updateStorageCard("j2-j3", spill["J2_to_J3"]);

  // 4. Update 2D Canvas with Moving Vehicles
  cachedVehicles = data.vehicles || [];
  drawCorridorCanvas();

  // 5. Update Charts
  updateCharts(data.history || {});
}

function updateStorageCard(prefix, rep) {
  if (!rep) return;
  const q = rep.current_queue_m || 0.0;
  const avail = rep.remaining_storage_m || 225.0;
  const availPct = rep.remaining_storage_pct || 100.0;
  const sri = rep.sri || 0.0;
  const alert = rep.alert_level || "LOW";

  const qElem = document.getElementById(`${prefix}-queue`);
  if (qElem) qElem.innerText = q.toFixed(1);

  const availElem = document.getElementById(`${prefix}-avail`);
  if (availElem) availElem.innerText = avail.toFixed(1);

  const pctElem = document.getElementById(`${prefix}-avail-pct`);
  if (pctElem) pctElem.innerText = `${availPct.toFixed(0)}%`;

  const occPct = Math.max(4, Math.min(100, 100 - availPct));
  const fill = document.getElementById(`${prefix}-storage-fill`);
  if (fill) {
    fill.style.width = `${occPct}%`;
    if (sri >= 0.85 || rep.is_blocked) {
      fill.style.backgroundColor = "var(--signal-red)";
    } else if (sri >= 0.65) {
      fill.style.backgroundColor = "#fb923c";
    } else if (sri >= 0.35) {
      fill.style.backgroundColor = "var(--signal-yellow)";
    } else {
      fill.style.backgroundColor = "var(--signal-green)";
    }
  }

  const badge = document.getElementById(`${prefix}-risk-badge`);
  if (badge) {
    const alertLabel = rep.is_blocked ? "INCIDENT BLOCKED (SRI 1.00)" : `${alert} (SRI ${sri.toFixed(2)})`;
    badge.innerText = alertLabel;
    badge.className = `alert-badge badge-${alert.toLowerCase()}`;
  }
}

// =============================================================================
// INTERACTIVE 2D CORRIDOR VEHICLE CANVAS
// =============================================================================

function initCanvas() {
  canvas = document.getElementById("corridor-canvas");
  if (!canvas) return;
  ctx = canvas.getContext("2d");

  // Handle canvas coordinate resizing
  function resizeCanvas() {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    drawCorridorCanvas();
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  // Mouse move hover detection
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    hoveredVehicle = null;
    for (const v of cachedVehicles) {
      const vx = mapX(v.x);
      const vy = mapY(v.y);
      if (Math.hypot(mx - vx, my - vy) < 14) {
        hoveredVehicle = v;
        break;
      }
    }
    drawCorridorCanvas();
  });
}

// Mapping SUMO coordinates [0, 1000] and [0, 400] to Canvas dimensions
function mapX(sumoX) {
  const pad = 45;
  const w = canvas.width - pad * 2;
  return pad + (sumoX / 1000.0) * w;
}

function mapY(sumoY) {
  const pad = 35;
  const h = canvas.height - pad * 2;
  return (canvas.height - pad) - (sumoY / 400.0) * h;
}

function drawCorridorCanvas() {
  if (!ctx || !canvas) return;

  const cw = canvas.width;
  const ch = canvas.height;

  // Background
  ctx.fillStyle = "#070b14";
  ctx.fillRect(0, 0, cw, ch);

  // 1. Draw Road Network
  const corridorY = mapY(200.0);
  const roadHeight = 44; // 2 lanes in each direction

  // Main Arterial Road (West-to-East)
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(35, corridorY - roadHeight / 2, cw - 70, roadHeight);

  // Double Yellow Centerline
  ctx.strokeStyle = "#eab308";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(35, corridorY - 1.5);
  ctx.lineTo(cw - 35, corridorY - 1.5);
  ctx.moveTo(35, corridorY + 1.5);
  ctx.lineTo(cw - 35, corridorY + 1.5);
  ctx.stroke();

  // White Dashed Lane Dividers (Corridor)
  ctx.strokeStyle = "#94a3b8";
  ctx.lineWidth = 1;
  ctx.setLineDash([8, 8]);
  ctx.beginPath();
  ctx.moveTo(35, corridorY - roadHeight / 4);
  ctx.lineTo(cw - 35, corridorY - roadHeight / 4);
  ctx.moveTo(35, corridorY + roadHeight / 4);
  ctx.lineTo(cw - 35, corridorY + roadHeight / 4);
  ctx.stroke();
  ctx.setLineDash([]);

  // Draw 3 Cross Streets at J1 (x=250), J2 (x=500), J3 (x=750)
  const junctionsX = [
    { id: "J1", x: mapX(250.0), name: "Junction 1" },
    { id: "J2", x: mapX(500.0), name: "Junction 2 (Bottleneck)" },
    { id: "J3", x: mapX(750.0), name: "Junction 3" },
  ];

  const crossWidth = 32;

  junctionsX.forEach(j => {
    // Cross street road asphalt
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(j.x - crossWidth / 2, 25, crossWidth, ch - 50);

    // Cross street center dashed line
    ctx.strokeStyle = "#eab308";
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 6]);
    ctx.beginPath();
    ctx.moveTo(j.x, 25);
    ctx.lineTo(j.x, ch - 25);
    ctx.stroke();
    ctx.setLineDash([]);

    // Stop lines at junction
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    // West approach stop line
    ctx.moveTo(j.x - crossWidth / 2 - 2, corridorY);
    ctx.lineTo(j.x - crossWidth / 2 - 2, corridorY + roadHeight / 2);
    // East approach stop line
    ctx.moveTo(j.x + crossWidth / 2 + 2, corridorY - roadHeight / 2);
    ctx.lineTo(j.x + crossWidth / 2 + 2, corridorY);
    ctx.stroke();

    // Intersection label
    ctx.fillStyle = "#64748b";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(j.name, j.x - 30, 20);

    // Draw Mini Traffic Light Heads for this junction
    const jstate = cachedJunctions[j.id] || {};
    const phase = jstate.phase_id || 0;
    let corrColor = "#10b981"; // green
    let crossColor = "#ef4444"; // red

    if (phase === 0) {
      corrColor = "#10b981"; crossColor = "#ef4444";
    } else if (phase === 1) {
      corrColor = "#f59e0b"; crossColor = "#ef4444";
    } else if (phase === 2) {
      corrColor = "#ef4444"; crossColor = "#10b981";
    } else if (phase === 3) {
      corrColor = "#ef4444"; crossColor = "#f59e0b";
    }

    // Corridor signal head lamp
    ctx.fillStyle = corrColor;
    ctx.beginPath();
    ctx.arc(j.x - 14, corridorY + 16, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowColor = corrColor;
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Cross street signal head lamp
    ctx.fillStyle = crossColor;
    ctx.beginPath();
    ctx.arc(j.x - 10, corridorY - 20, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowColor = crossColor;
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;
  });

  // Road Boundaries & Edge Labels
  ctx.fillStyle = "#475569";
  ctx.font = "11px -apple-system, sans-serif";
  ctx.fillText("West Inflow (W_to_J1)", 40, corridorY + 36);
  ctx.fillText("East Outflow (J3_to_E)", cw - 160, corridorY + 36);
  ctx.fillText("Inter-Storage J1->J2 (250m)", mapX(330), corridorY - 28);
  ctx.fillText("Inter-Storage J2->J3 (250m)", mapX(600), corridorY - 28);

  // 2. Render All Moving Vehicles
  cachedVehicles.forEach(v => {
    const vx = mapX(v.x);
    const vy = mapY(v.y);

    ctx.save();
    ctx.translate(vx, vy);

    // SUMO angle: 0 = North, 90 = East, 180 = South, 270 = West
    // Canvas rotation: 0 = East, clockwise
    const canvasRad = ((v.angle - 90) * Math.PI) / 180.0;
    ctx.rotate(canvasRad);

    let vWidth = 14;
    let vHeight = 7;
    let vColor = "#38bdf8"; // default car (cyan/blue)

    if (v.type === "motorcycle") {
      vWidth = 9; vHeight = 4.5; vColor = "#facc15"; // yellow
    } else if (v.type === "bus") {
      vWidth = 26; vHeight = 9.5; vColor = "#34d399"; // green
    } else if (v.type === "truck") {
      vWidth = 22; vHeight = 9.5; vColor = "#f87171"; // red
    } else if (v.type === "emergency") {
      vWidth = 18; vHeight = 8.5; vColor = "#ffffff"; // ambulance white
    }

    // Vehicle body
    ctx.fillStyle = vColor;
    ctx.fillRect(-vWidth / 2, -vHeight / 2, vWidth, vHeight);

    // Roof outline
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 0.8;
    ctx.strokeRect(-vWidth / 2, -vHeight / 2, vWidth, vHeight);

    // Front windshield marker
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(vWidth / 4, -vHeight / 2 + 1, 2, vHeight - 2);

    // If Queued / Stopped: Draw Red Brake Lights
    if (v.queued) {
      ctx.fillStyle = "#ef4444";
      ctx.fillRect(-vWidth / 2 - 1, -vHeight / 2 + 0.5, 2, 2);
      ctx.fillRect(-vWidth / 2 - 1, vHeight / 2 - 2.5, 2, 2);
    }

    // Flashing Emergency Beacon for Ambulance
    if (v.type === "emergency") {
      const flash = Math.floor(Date.now() / 150) % 2 === 0;
      ctx.fillStyle = flash ? "#ef4444" : "#3b82f6";
      ctx.beginPath();
      ctx.arc(0, 0, 3, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  });

  // 3. Draw Hover Tooltip if vehicle selected
  if (hoveredVehicle) {
    const hx = mapX(hoveredVehicle.x);
    const hy = mapY(hoveredVehicle.y);

    ctx.fillStyle = "rgba(15, 23, 42, 0.92)";
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1;

    const tipW = 150;
    const tipH = 50;
    const tx = Math.min(cw - tipW - 10, Math.max(10, hx - tipW / 2));
    const ty = Math.max(10, hy - tipH - 12);

    ctx.fillRect(tx, ty, tipW, tipH);
    ctx.strokeRect(tx, ty, tipW, tipH);

    ctx.fillStyle = "#f8fafc";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`ID: ${hoveredVehicle.id}`, tx + 8, ty + 15);
    ctx.fillText(`Type: ${hoveredVehicle.type.toUpperCase()}`, tx + 8, ty + 28);
    ctx.fillText(`Speed: ${hoveredVehicle.speed} km/h`, tx + 8, ty + 41);
  }
}

// =============================================================================
// CHART.JS INITIALIZATION & UPDATES
// =============================================================================

function initCharts() {
  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 200 },
    plugins: {
      legend: { labels: { color: "#94a3b8", font: { size: 10 } } }
    },
    scales: {
      x: { ticks: { color: "#64748b", maxTicksLimit: 7 }, grid: { color: "#1e293b" } },
      y: { ticks: { color: "#64748b" }, grid: { color: "#1e293b" } }
    }
  };

  // 1. Queue Length & Prediction Horizon Chart
  const ctxQueue = document.getElementById("chart-queue").getContext("2d");
  queueChart = new Chart(ctxQueue, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Actual Queue (m)", data: [], borderColor: "#38bdf8", backgroundColor: "rgba(56, 189, 248, 0.1)", fill: true, borderWidth: 2, tension: 0.2 },
        { label: "10s Prediction (m)", data: [], borderColor: "#06b6d4", borderDash: [4, 4], borderWidth: 1.5, tension: 0.2 },
        { label: "20s Prediction (m)", data: [], borderColor: "#f59e0b", borderDash: [4, 4], borderWidth: 1.5, tension: 0.2 },
        { label: "30s Prediction (m)", data: [], borderColor: "#ef4444", borderDash: [4, 4], borderWidth: 1.5, tension: 0.2 },
      ]
    },
    options: chartDefaults
  });

  // 2. Emissions Chart
  const ctxEmissions = document.getElementById("chart-emissions").getContext("2d");
  emissionsChart = new Chart(ctxEmissions, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "CO2 Rate (g/s)", data: [], borderColor: "#a855f7", backgroundColor: "rgba(168, 85, 247, 0.1)", fill: true, borderWidth: 2, tension: 0.2, yAxisID: "y" },
        { label: "Fuel Rate (ml/s)", data: [], borderColor: "#f97316", borderWidth: 2, tension: 0.2, yAxisID: "y1" },
      ]
    },
    options: {
      ...chartDefaults,
      scales: {
        ...chartDefaults.scales,
        y: { type: "linear", position: "left", ticks: { color: "#a855f7" }, grid: { color: "#1e293b" } },
        y1: { type: "linear", position: "right", ticks: { color: "#f97316" }, grid: { drawOnChartArea: false } }
      }
    }
  });

  // 3. Performance Chart
  const ctxPerf = document.getElementById("chart-performance").getContext("2d");
  perfChart = new Chart(ctxPerf, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Avg Speed (km/h)", data: [], borderColor: "#10b981", borderWidth: 2, tension: 0.2, yAxisID: "y" },
        { label: "Waiting Time (s)", data: [], borderColor: "#f43f5e", borderWidth: 2, tension: 0.2, yAxisID: "y1" },
      ]
    },
    options: {
      ...chartDefaults,
      scales: {
        ...chartDefaults.scales,
        y: { type: "linear", position: "left", ticks: { color: "#10b981" }, grid: { color: "#1e293b" } },
        y1: { type: "linear", position: "right", ticks: { color: "#f43f5e" }, grid: { drawOnChartArea: false } }
      }
    }
  });
}

function updateCharts(history) {
  if (!history || !history.time || history.time.length === 0) return;

  const labels = history.time.map(t => `${t}s`);

  if (queueChart) {
    queueChart.data.labels = labels;
    queueChart.data.datasets[0].data = history.queue_j1_j2 || [];
    queueChart.data.datasets[1].data = history.pred_10s || [];
    queueChart.data.datasets[2].data = history.pred_20s || [];
    queueChart.data.datasets[3].data = history.pred_30s || [];
    queueChart.update();
  }

  if (emissionsChart) {
    emissionsChart.data.labels = labels;
    emissionsChart.data.datasets[0].data = history.co2_rate || [];
    emissionsChart.data.datasets[1].data = history.fuel_rate || [];
    emissionsChart.update();
  }

  if (perfChart) {
    perfChart.data.labels = labels;
    perfChart.data.datasets[0].data = history.avg_speed || [];
    perfChart.data.datasets[1].data = history.waiting_time || [];
    perfChart.update();
  }
}

// =============================================================================
// USER CONTROLS & EVENT HANDLERS
// =============================================================================

async function startSim() {
  const ctrl = document.getElementById("select-controller").value;
  const density = document.getElementById("select-density").value;
  const spd = document.getElementById("select-speed").value;
  await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ controller_type: ctrl, density_level: density, speed: spd })
  });
  startPolling();
}

async function pauseSim() {
  await fetch("/api/pause", { method: "POST" });
  fetchStatus();
}

async function stepSim() {
  const res = await fetch("/api/step", { method: "POST" });
  const data = await res.json();
  renderDashboard(data);
}

async function resetSim() {
  const ctrl = document.getElementById("select-controller").value;
  const density = document.getElementById("select-density").value;
  await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ controller_type: ctrl, density_level: density })
  });
  fetchStatus();
}

async function onControllerChange() {
  startSim();
}

async function onDensityChange() {
  resetSim();
}

async function onSpeedChange() {
  startSim();
}

async function injectEmergency() {
  const btn = document.getElementById("btn-emergency");
  btn.innerText = "🚨 Injecting Ambulance...";
  try {
    await fetch("/api/emergency/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approach: "W_to_J1" })
    });
    setTimeout(() => {
      btn.innerText = "🚑 Inject Ambulance";
    }, 1200);
  } catch (err) {
    console.error(err);
    btn.innerText = "🚑 Inject Ambulance";
  }
}

async function toggleIncidentBlockage() {
  const btn = document.getElementById("btn-incident");
  try {
    const res = await fetch("/api/incident/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ link_id: "J1_to_J2" })
    });
    const data = await res.json();
    if (data.is_blocked) {
      btn.innerText = "⚠️ Clear Blockage Incident";
      btn.style.backgroundColor = "#b91c1c";
    } else {
      btn.innerText = "⚠️ Simulate J1→J2 Blockage";
      btn.style.backgroundColor = "#d97706";
    }
  } catch (err) {
    console.error(err);
  }
}
