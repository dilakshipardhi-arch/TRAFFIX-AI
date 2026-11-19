/**
 * TRAFFIX AI - Comparative Performance Evaluation JavaScript
 * Loads empirical benchmark data, renders comparative KPI cards,
 * side-by-side grouped bar charts, and time-series delay progression curves.
 */

let chartTraffic = null;
let chartEmissions = null;
let chartTimeseries = null;
let masterData = {};

document.addEventListener("DOMContentLoaded", () => {
  loadBenchmarkData();
});

async function loadBenchmarkData() {
  try {
    const res = await fetch("/api/benchmark/results");
    if (!res.ok) {
      console.warn("No benchmark data found yet. Run benchmark to generate.");
      return;
    }
    masterData = await res.json();
    renderComparison(masterData);
  } catch (err) {
    console.error("Error loading benchmark results:", err);
  }
}

function renderComparison(data) {
  const selDensity = document.getElementById("benchmark-density").value;
  let targetSummary = data.summary || {};
  let targetTimeseries = data.timeseries || {};

  // Check if all_densities has this tier
  if (data.all_densities && data.all_densities[selDensity]) {
    targetSummary = data.all_densities[selDensity];
  }

  const sum = targetSummary;
  const f = sum.fixed_time || {};
  const p = sum.proposed_controller || {};
  const imp = sum.improvements || {};
  const ts = targetTimeseries;

  const tsElem = document.getElementById("benchmark-timestamp");
  if (tsElem) {
    tsElem.innerText = `Scenario: ${(sum.density_level || selDensity).toUpperCase()} • Last benchmark: ${sum.benchmark_date || "N/A"} (${sum.duration_seconds || 0}s)`;
  }

  // 1. KPI Percentage Cards
  setElemText("imp-delay", `-${imp.waiting_time_reduction_pct || 0}%`);
  setElemText("imp-speed", `+${imp.speed_increase_pct || 0}%`);
  setElemText("imp-throughput", `+${imp.throughput_increase_pct || 0}%`);
  setElemText("imp-co2", `-${imp.co2_reduction_pct || 0}%`);
  setElemText("imp-fuel", `-${imp.fuel_savings_pct || 0}%`);

  // 2. Table Rows
  setElemText("tbl-f-delay", `${(f.total_waiting_time_s || 0).toLocaleString()} s`);
  setElemText("tbl-p-delay", `${(p.total_waiting_time_s || 0).toLocaleString()} s`);
  setElemText("tbl-diff-delay", `-${imp.waiting_time_reduction_pct || 0}%`);

  setElemText("tbl-f-tp", `${f.total_throughput_vehs || 0} vehs`);
  setElemText("tbl-p-tp", `${p.total_throughput_vehs || 0} vehs`);
  setElemText("tbl-diff-tp", `+${imp.throughput_increase_pct || 0}%`);

  setElemText("tbl-f-speed", `${f.average_speed_kmh || 0} km/h`);
  setElemText("tbl-p-speed", `${p.average_speed_kmh || 0} km/h`);
  setElemText("tbl-diff-speed", `+${imp.speed_increase_pct || 0}%`);

  setElemText("tbl-f-queue", `${f.max_queue_observed_m || 0} m`);
  setElemText("tbl-p-queue", `${p.max_queue_observed_m || 0} m`);
  setElemText("tbl-diff-queue", `${imp.queue_reduction_pct || 0}%`);

  setElemText("tbl-f-fuel", `${f.cumulative_fuel_liters || 0} L`);
  setElemText("tbl-p-fuel", `${p.cumulative_fuel_liters || 0} L`);
  setElemText("tbl-diff-fuel", `-${imp.fuel_savings_pct || 0}%`);

  setElemText("tbl-f-co2", `${f.cumulative_co2_kg || 0} kg`);
  setElemText("tbl-p-co2", `${p.cumulative_co2_kg || 0} kg`);
  setElemText("tbl-diff-co2", `-${imp.co2_reduction_pct || 0}%`);

  setElemText("tbl-f-nox", `${f.cumulative_nox_g || 0} g`);
  setElemText("tbl-p-nox", `${p.cumulative_nox_g || 0} g`);

  const noxDiff = f.cumulative_nox_g > 0 ? ((f.cumulative_nox_g - p.cumulative_nox_g) / f.cumulative_nox_g * 100).toFixed(1) : 0;
  setElemText("tbl-diff-nox", `-${noxDiff}%`);

  // 3. Render Charts
  renderBarCharts(f, p);
  renderTimeseriesChart(ts);
}

function setElemText(id, text) {
  const elem = document.getElementById(id);
  if (elem) elem.innerText = text;
}

function renderBarCharts(f, p) {
  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#94a3b8", font: { size: 10 } } }
    },
    scales: {
      x: { ticks: { color: "#94a3b8" }, grid: { color: "#243452" } },
      y: { ticks: { color: "#94a3b8" }, grid: { color: "#243452" } }
    }
  };

  // Chart 1: Traffic Efficiency Bar
  const ctxTraffic = document.getElementById("chart-comp-traffic").getContext("2d");
  if (chartTraffic) chartTraffic.destroy();

  chartTraffic = new Chart(ctxTraffic, {
    type: "bar",
    data: {
      labels: ["Waiting Time (s)", "Throughput (vehs)", "Avg Speed (km/h)"],
      datasets: [
        {
          label: "Fixed-Time Baseline",
          data: [f.total_waiting_time_s || 0, f.total_throughput_vehs || 0, f.average_speed_kmh || 0],
          backgroundColor: "#f43f5e",
          borderRadius: 4,
        },
        {
          label: "TRAFFIX AI Proposed",
          data: [p.total_waiting_time_s || 0, p.total_throughput_vehs || 0, p.average_speed_kmh || 0],
          backgroundColor: "#2563eb",
          borderRadius: 4,
        }
      ]
    },
    options: chartOpts
  });

  // Chart 2: Emissions Bar
  const ctxEmiss = document.getElementById("chart-comp-emissions").getContext("2d");
  if (chartEmissions) chartEmissions.destroy();

  chartEmissions = new Chart(ctxEmiss, {
    type: "bar",
    data: {
      labels: ["CO2 (kg)", "Fuel (L)", "NOx (g)"],
      datasets: [
        {
          label: "Fixed-Time Baseline",
          data: [f.cumulative_co2_kg || 0, f.cumulative_fuel_liters || 0, f.cumulative_nox_g || 0],
          backgroundColor: "#f59e0b",
          borderRadius: 4,
        },
        {
          label: "TRAFFIX AI Proposed",
          data: [p.cumulative_co2_kg || 0, p.cumulative_fuel_liters || 0, p.cumulative_nox_g || 0],
          backgroundColor: "#10b981",
          borderRadius: 4,
        }
      ]
    },
    options: chartOpts
  });
}

function renderTimeseriesChart(ts) {
  const fTs = ts.fixed_time || {};
  const pTs = ts.proposed_controller || {};

  const timeLabels = (fTs.time || pTs.time || []).map(t => `${t}s`);

  const ctxTs = document.getElementById("chart-comp-timeseries").getContext("2d");
  if (chartTimeseries) chartTimeseries.destroy();

  chartTimeseries = new Chart(ctxTs, {
    type: "line",
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: "Fixed-Time Delay (s)",
          data: fTs.waiting_time || [],
          borderColor: "#f43f5e",
          backgroundColor: "rgba(244, 63, 94, 0.08)",
          fill: true,
          borderWidth: 1.8,
          tension: 0.25,
        },
        {
          label: "TRAFFIX AI Delay (s)",
          data: pTs.waiting_time || [],
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.08)",
          fill: true,
          borderWidth: 1.8,
          tension: 0.25,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#94a3b8", font: { size: 10 } } }
      },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 12 }, grid: { color: "#243452" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "#243452" } }
      }
    }
  });
}

async function runBenchmark() {
  const dur = document.getElementById("benchmark-duration").value;
  const density = document.getElementById("benchmark-density").value;
  const btn = document.getElementById("btn-run-benchmark");
  btn.disabled = true;
  btn.innerText = `⏳ Running SUMO (${density.toUpperCase()})...`;

  try {
    await fetch("/api/benchmark/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration: parseInt(dur), density_level: density })
    });

    let attempts = 0;
    const poller = setInterval(async () => {
      attempts++;
      const res = await fetch("/api/benchmark/results");
      if (res.ok) {
        const data = await res.json();
        if (data.summary && data.summary.density_level === density && data.summary.duration_seconds === parseInt(dur)) {
          clearInterval(poller);
          btn.disabled = false;
          btn.innerText = "⚡ Run Benchmark";
          masterData = data;
          renderComparison(data);
          return;
        }
      }
      if (attempts > 50) {
        clearInterval(poller);
        btn.disabled = false;
        btn.innerText = "⚡ Run Benchmark";
      }
    }, 1800);

  } catch (err) {
    console.error("Benchmark launch error:", err);
    btn.disabled = false;
    btn.innerText = "⚡ Run Benchmark";
  }
}
