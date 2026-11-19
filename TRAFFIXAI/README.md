# TRAFFIX AI
### Predictive Spillback-Aware Signal Control for Lower Congestion and Emissions

A modular, software-only intelligent traffic management system built for college-level simulation, presentation, and evaluation using Eclipse SUMO, TraCI, Python, Flask, and Chart.js.

---

## 1. Project Overview & Main Objective
In urban corridors with closely spaced signalised intersections (e.g., 200m–400m apart), conventional fixed-time and isolated actuated traffic signals suffer from **traffic spillback**: a queue forming at a downstream bottleneck intersection extends backward until it physically blocks the upstream intersection, triggering widespread gridlock.

**TRAFFIX AI** addresses this problem using predictive traffic flow dynamics and cooperative signal control:
1. Simulates a 3-intersection arterial corridor (`J1` — `J2` — `J3`) with heterogeneous traffic classes (**cars**, **motorcycles**, **buses**, and **trucks**).
2. Estimates live spatial queue lengths in meters and monitors downstream road storage capacity.
3. Predicts short-term queue growth over **10-second, 20-second, and 30-second horizons**.
4. Evaluates the **Spillback Risk Index (SRI $\in [0, 1]$)** on inter-intersection storage links.
5. Dynamically triggers **Upstream Gating (Metering)** and **Bottleneck Flushing** while strictly enforcing **minimum green** ($10\text{s}$) and **maximum green** ($55\text{s}$) safeguards.
6. Analyzes real-time fuel consumption and emissions ($CO_2$, $CO$, $NO_x$, $PM_x$) using SUMO HBEFA3 emission models.
7. Provides a modern interactive web dashboard and an empirical comparison between fixed-time control and TRAFFIX AI.

---

## 2. Technology Stack
- **Traffic Simulation**: Eclipse SUMO (v1.28.0 64-bit binaries: `sumo.exe`, `netconvert.exe`)
- **Simulation Interface**: TraCI (Traffic Control Interface) and `sumolib`
- **Backend Server**: Python 3.15, Flask, Flask-Cors
- **Numerical Processing**: NumPy
- **Frontend Dashboard**: HTML5, Modern CSS, JavaScript (ES6+), Chart.js (v4.4)

---

## 3. Project Directory Structure & Major Files

```text
TRAFFIXAI/
├── simulation/                  # SUMO traffic network, routes, and configs
│   ├── networks/                # Nodes, edges, connections, and compiled network
│   │   ├── corridor_3j.nod.xml  # Coordinates for 3 signalized junctions (J1, J2, J3)
│   │   ├── corridor_3j.edg.xml  # Arterial & cross-street road links (250m spacing)
│   │   ├── corridor_3j.con.xml  # Lane-to-lane turning and through connections
│   │   ├── corridor_3j.net.xml  # Compiled SUMO road network (netconvert)
│   │   └── build_network.py     # Automated network compiler script
│   ├── routes/                  # Vehicle fleet and demand flows
│   │   ├── vtypes.add.xml       # Heterogeneous vehicle types with HBEFA3 emissions
│   │   └── corridor_flows.rou.xml # Corridor and cross-street flows (3600s demand)
│   ├── configs/                 # SUMO configuration files
│   │   ├── fixed_time.sumocfg   # Baseline simulation config
│   │   └── traffix_ai.sumocfg   # Controller-managed simulation config
│   └── sumo_runner.py           # TraCI session supervisor and step executor
│
├── controllers/                 # Traffic Signal Control logic
│   ├── __init__.py
│   ├── base_controller.py       # Abstract Base Controller interface
│   ├── fixed_controller.py      # Standard fixed-time 90s cycle baseline
│   └── spillback_controller.py  # Proposed Predictive Spillback-Aware Controller
│
├── core/                        # Core estimation, prediction, and benchmark engines
│   ├── __init__.py
│   ├── metrics_collector.py     # Live vehicle counts, speeds, fuel, and emissions
│   ├── queue_estimator.py       # Real-time spatial queue length (m) & lane occupancy
│   ├── queue_predictor.py       # Short-term (10s, 20s, 30s) queue progression model
│   ├── spillback_detector.py    # Downstream storage monitor & Spillback Risk Index (SRI)
│   └── benchmark_runner.py      # Automated back-to-back comparative evaluator
│
├── web/                         # Web Dashboard (Flask + HTML/CSS/JS + Chart.js)
│   ├── app.py                   # Flask REST API and simulation background manager
│   ├── templates/
│   │   ├── index.html           # Real-time traffic & signal monitoring dashboard
│   │   └── comparison.html      # Quantitative performance & emission benchmark view
│   └── static/
│       ├── css/style.css        # Professional technical dark-slate theme
│       └── js/
│           ├── dashboard.js     # Live telemetry, Chart.js plots, junction signals
│           └── comparison.js    # Comparative grouped bar and time-series charts
│
├── tests/                       # Automated Test Suite (17 Unit & Integration Tests)
│   ├── test_network.py          # Verifies XML definitions, geometries, and vehicle types
│   ├── test_simulation_run.py   # Verifies TraCI execution and vehicle insertion
│   ├── test_core_engine.py      # Tests prediction formulas and emission math
│   ├── test_controllers.py      # Tests signal safeguards and predictive gating
│   └── test_web_api.py          # Tests Flask REST endpoints and simulation stepping
│
├── data/results/                # Persistent empirical benchmark datasets
│   ├── comparison_summary.json  # Quantitative metrics and % improvements
│   └── comparison_timeseries.json # Step-by-step comparative progression data
│
├── requirements.txt             # Project Python dependencies
└── README.md                    # Project documentation
```

---

## 4. How to Run the Project

### Step 1: Run All Automated Verification Tests
Verify that all 17 tests across simulation, AI core, controllers, and web endpoints pass:
```bash
python -m unittest discover tests
```

### Step 2: Launch the Web Dashboard
Start the Flask application server:
```bash
python web/app.py
```
Open your browser and navigate to:
```text
http://localhost:5000
```
- **Live Dashboard (`/`)**: View real-time signal phase transitions (`J1`, `J2`, `J3`), downstream road storage progress bars, short-term queue predictions (10s, 20s, 30s), and live $CO_2$/fuel emission rates.
- **Evaluation & Benchmark (`/comparison`)**: View side-by-side empirical performance comparisons, percentage reductions, and trigger custom scenario benchmarks.

### Step 3: Run Standalone Benchmark Comparison
To run a back-to-back benchmark comparison (e.g., 300 seconds) directly from the command line:
```bash
python core/benchmark_runner.py 300
```

---

## 5. Empirical Benchmark Results (SUMO TraCI)

The following empirical results were measured under identical high-demand corridor flows:

| Evaluation Metric | Fixed-Time Control | Proposed TRAFFIX AI | Empirical Improvement |
| :--- | :---: | :---: | :---: |
| **Total Waiting Time / Delay** | $2,072.0\text{ s}$ | $110.0\text{ s}$ | **$-94.69\%$ reduction** |
| **Corridor Throughput** | $82\text{ vehicles}$ | $91\text{ vehicles}$ | **$+10.98\%$ increase** |
| **Average Network Speed** | $27.30\text{ km/h}$ | $29.93\text{ km/h}$ | **$+9.63\%$ increase** |
| **Fuel Consumed** | $14.701\text{ L}$ | $14.628\text{ L}$ | **Fuel savings achieved** |
| **$CO_2$ Emissions** | $34.236\text{ kg}$ | $34.070\text{ kg}$ | **Emission reduction achieved** |
| **$NO_x$ Emissions** | $102.07\text{ g}$ | $99.66\text{ g}$ | **$-2.36\%$ reduction** |
