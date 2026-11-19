"""
TRAFFIX AI - Web Dashboard Backend (Flask)
Provides REST APIs for real-time simulation control, live TraCI telemetry streaming,
HTML5 canvas vehicle positioning, OpenCV vision detection, and empirical evaluations.
"""

import os
import sys
import json
import time
import threading
from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulation.sumo_runner import SumoSimulation
from controllers.fixed_controller import FixedTimeController
from controllers.spillback_controller import SpillbackAwareController
from core.metrics_collector import MetricsCollector
from core.queue_estimator import QueueEstimator
from core.queue_predictor import QueuePredictor
from core.spillback_detector import SpillbackDetector
from core.benchmark_runner import run_comparison_benchmark, get_scenario_route_file
from core.camera_detector import camera_stream

app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "web", "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "web", "static")
)
CORS(app)


class SimulationManager:
    """Manages background simulation stepping, scenario density, and vehicle positioning."""

    def __init__(self):
        self.lock = threading.RLock()
        self.sim: SumoSimulation = None
        self.collector: MetricsCollector = None
        self.estimator: QueueEstimator = None
        self.predictor: QueuePredictor = None
        self.detector: SpillbackDetector = None
        self.controller = None

        self.controller_type = "spillback_aware"
        self.density_level = "medium"
        self.is_running = False
        self.is_paused = False
        self.sim_speed = 1.0
        self.step_delay = 0.2

        self.latest_telemetry = {}
        self.history_buffer = {
            "time": [],
            "queue_j1_j2": [],
            "pred_10s": [],
            "pred_20s": [],
            "pred_30s": [],
            "sri_j1_j2": [],
            "co2_rate": [],
            "fuel_rate": [],
            "avg_speed": [],
            "waiting_time": [],
        }

        self._thread = None
        self._stop_event = threading.Event()
        self.critical_edges = ["W_to_J1", "J1_to_J2", "J2_to_J3", "J3_to_E", "N1_to_J1", "N2_to_J2", "N3_to_J3"]

    def init_simulation(self, controller_type="spillback_aware", density_level="medium"):
        with self.lock:
            self._close_existing()
            self.controller_type = controller_type
            self.density_level = density_level

            cfg_file = "traffix_ai.sumocfg" if controller_type == "spillback_aware" else "fixed_time.sumocfg"
            cfg_path = os.path.join(PROJECT_ROOT, "simulation", "configs", cfg_file)
            route_path = get_scenario_route_file(self.density_level)

            self.sim = SumoSimulation(sumocfg_path=cfg_path, gui=False, step_length=1.0, route_file=route_path)
            self.sim.start()

            self.collector = MetricsCollector(self.sim.traci)
            self.estimator = QueueEstimator(self.sim.traci)
            self.predictor = QueuePredictor(self.sim.traci)
            self.detector = SpillbackDetector()

            if self.controller_type == "fixed_time":
                self.controller = FixedTimeController(self.sim.traci)
            else:
                self.controller = SpillbackAwareController(self.sim.traci)

            self._reset_history()
            self.is_running = True
            self.is_paused = False
            self._perform_step_locked()

    def _close_existing(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
        with self.lock:
            if self.sim:
                try:
                    self.sim.close()
                except Exception:
                    pass
                self.sim = None
            self.is_running = False

    def _reset_history(self):
        for k in self.history_buffer:
            self.history_buffer[k] = []

    def start_loop(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self.is_running and not self.is_paused:
                with self.lock:
                    if self.sim and self.sim.is_running():
                        self._perform_step_locked()
                    else:
                        self.is_running = False
            time.sleep(self.step_delay)

    def _perform_step_locked(self):
        if not self.sim:
            return

        self.sim.step()
        sim_time = self.sim.get_time()

        # 1. Collect live metrics
        metrics = self.collector.collect_step_metrics()

        # 2. Estimate Queues
        queues = self.estimator.estimate_all_queues(self.critical_edges)

        # 3. Predict Queues
        predictions = self.predictor.predict_all(queues)

        # 4. Detect Spillback
        spillback_rep = self.detector.assess_all_links(queues, predictions)

        # 5. Controller Step
        decisions = self.controller.step(
            current_time=sim_time,
            queue_estimates=queues,
            queue_predictions=predictions,
            spillback_reports=spillback_rep
        )

        # 6. Extract Individual Vehicle Coordinates for 2D Canvas Visualization
        active_vehicles_data = []
        try:
            for vid in self.sim.traci.vehicle.getIDList():
                x, y = self.sim.traci.vehicle.getPosition(vid)
                spd = self.sim.traci.vehicle.getSpeed(vid)
                ang = self.sim.traci.vehicle.getAngle(vid)
                vtype = self.sim.traci.vehicle.getTypeID(vid)
                lane = self.sim.traci.vehicle.getLaneID(vid)
                edge = self.sim.traci.vehicle.getRoadID(vid)
                active_vehicles_data.append({
                    "id": vid,
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "speed_kmh": round(spd * 3.6, 1),
                    "angle": round(ang, 1),
                    "type": vtype,
                    "lane": lane,
                    "edge": edge,
                    "is_queued": spd <= 1.0,
                })
        except Exception:
            pass

        # Update History Buffer
        q_j1_j2 = queues.get("J1_to_J2", {}).get("max_queue_length_m", 0.0)
        p_j1_j2 = predictions.get("J1_to_J2", {}).get("predictions", {})
        sri_j1_j2 = spillback_rep.get("J1_to_J2", {}).get("sri", 0.0)

        self.history_buffer["time"].append(int(sim_time))
        self.history_buffer["queue_j1_j2"].append(round(q_j1_j2, 1))
        self.history_buffer["pred_10s"].append(round(p_j1_j2.get("10s", {}).get("predicted_queue_m", q_j1_j2), 1))
        self.history_buffer["pred_20s"].append(round(p_j1_j2.get("20s", {}).get("predicted_queue_m", q_j1_j2), 1))
        self.history_buffer["pred_30s"].append(round(p_j1_j2.get("30s", {}).get("predicted_queue_m", q_j1_j2), 1))
        self.history_buffer["sri_j1_j2"].append(round(sri_j1_j2, 3))
        self.history_buffer["co2_rate"].append(metrics["emissions_step"]["co2_g"])
        self.history_buffer["fuel_rate"].append(metrics["emissions_step"]["fuel_ml"])
        self.history_buffer["avg_speed"].append(metrics["network"]["average_speed_kmh"])
        self.history_buffer["waiting_time"].append(metrics["network"]["total_waiting_time_s"])

        max_pts = 120
        if len(self.history_buffer["time"]) > max_pts:
            for k in self.history_buffer:
                self.history_buffer[k] = self.history_buffer[k][-max_pts:]

        # Junction display data
        junction_display = {}
        for jid in ["J1", "J2", "J3"]:
            jstate = self.controller.get_junction_state(jid)
            junction_display[jid] = {
                "phase_id": jstate.get("current_phase", 0),
                "phase_name": jstate.get("phase_name", "CORRIDOR_GREEN"),
                "time_in_phase": jstate.get("time_in_phase", 0),
                "last_action": decisions.get(jid, {}).get("action", "NORMAL"),
                "reason": decisions.get(jid, {}).get("reason", "Adaptive control active."),
                "gating_active": decisions.get(jid, {}).get("gating_active", False),
                "flushing_active": decisions.get(jid, {}).get("flushing_active", False),
                "emergency_active": decisions.get(jid, {}).get("emergency_active", False),
            }

        self.latest_telemetry = {
            "simulation_time": int(sim_time),
            "controller_type": self.controller_type,
            "density_level": self.density_level,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "network": metrics["network"],
            "emissions_step": metrics["emissions_step"],
            "emissions_cumulative": metrics["emissions_cumulative"],
            "junctions": junction_display,
            "queues": queues,
            "predictions": predictions,
            "spillback_reports": spillback_rep,
            "vehicles": active_vehicles_data,
            "history": self.history_buffer,
        }

    def inject_emergency_vehicle(self, approach="W_to_J1"):
        """Injects an ambulance into the simulation."""
        with self.lock:
            if not self.sim or not self.sim.is_running():
                return False
            vid = f"ambulance_{int(time.time() * 10) % 10000}"
            route_id = "r_WE" if "W" in approach else "r_NS_1"
            try:
                self.sim.traci.vehicle.add(
                    vehID=vid,
                    routeID=route_id,
                    typeID="emergency",
                    depart="now",
                    departLane="best",
                    departSpeed="max"
                )
                print(f"[TRAFFIX AI] Emergency vehicle {vid} injected on {approach}.")
                return True
            except Exception as e:
                print(f"[TRAFFIX AI] Emergency injection error: {e}")
                return False

    def toggle_incident_blockage(self, link_id="J1_to_J2"):
        """Toggles an incident blockage on an inter-intersection link."""
        with self.lock:
            if not self.detector:
                return False
            curr = self.detector.blocked_links.get(link_id, False)
            new_state = not curr
            self.detector.set_link_blockage(link_id, new_state)
            print(f"[TRAFFIX AI] Incident blockage on {link_id} set to: {new_state}")
            return new_state

    def single_step(self):
        with self.lock:
            if not self.sim:
                self.init_simulation(self.controller_type, self.density_level)
            self._perform_step_locked()
            return self.latest_telemetry

    def pause(self):
        self.is_paused = not self.is_paused
        return self.is_paused

    def reset(self):
        with self.lock:
            self.init_simulation(self.controller_type, self.density_level)
        return True


mgr = SimulationManager()


# =============================================================================
# WEB & API ROUTES
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/comparison")
def comparison():
    return render_template("comparison.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    if not mgr.sim:
        mgr.init_simulation(mgr.controller_type, mgr.density_level)
        mgr.start_loop()
    return jsonify(mgr.latest_telemetry)


@app.route("/api/start", methods=["POST"])
def start_simulation():
    data = request.get_json() or {}
    ctrl_type = data.get("controller_type", mgr.controller_type)
    density = data.get("density_level", mgr.density_level)
    speed = float(data.get("speed", 1.0))

    mgr.step_delay = max(0.02, 0.2 / max(0.1, speed))

    if not mgr.sim or mgr.controller_type != ctrl_type or mgr.density_level != density:
        mgr.init_simulation(ctrl_type, density)
    else:
        mgr.is_paused = False

    mgr.start_loop()
    return jsonify({"status": "started", "controller": ctrl_type, "density": density, "speed": speed})


@app.route("/api/pause", methods=["POST"])
def pause_simulation():
    is_paused = mgr.pause()
    return jsonify({"is_paused": is_paused})


@app.route("/api/step", methods=["POST"])
def step_simulation():
    mgr.is_paused = True
    telemetry = mgr.single_step()
    return jsonify(telemetry)


@app.route("/api/reset", methods=["POST"])
def reset_simulation():
    data = request.get_json() or {}
    ctrl_type = data.get("controller_type", mgr.controller_type)
    density = data.get("density_level", mgr.density_level)
    mgr.init_simulation(ctrl_type, density)
    return jsonify({"status": "reset", "controller": ctrl_type, "density": density})


@app.route("/api/emergency/inject", methods=["POST"])
def inject_emergency():
    data = request.get_json() or {}
    approach = data.get("approach", "W_to_J1")
    success = mgr.inject_emergency_vehicle(approach)
    return jsonify({"success": success, "approach": approach})


@app.route("/api/incident/toggle", methods=["POST"])
def toggle_incident():
    data = request.get_json() or {}
    link_id = data.get("link_id", "J1_to_J2")
    state = mgr.toggle_incident_blockage(link_id)
    return jsonify({"link_id": link_id, "is_blocked": state})


@app.route("/api/benchmark/results", methods=["GET"])
def get_benchmark_results():
    summary_path = os.path.join(PROJECT_ROOT, "data", "results", "comparison_summary.json")
    timeseries_path = os.path.join(PROJECT_ROOT, "data", "results", "comparison_timeseries.json")
    all_path = os.path.join(PROJECT_ROOT, "data", "results", "comparison_all_densities.json")

    if not os.path.isfile(summary_path):
        return jsonify({"error": "No benchmark results found. Run benchmark first."}), 404

    with open(summary_path, "r") as f:
        summary_data = json.load(f)

    timeseries_data = {}
    if os.path.isfile(timeseries_path):
        with open(timeseries_path, "r") as f:
            timeseries_data = json.load(f)

    all_densities = {}
    if os.path.isfile(all_path):
        with open(all_path, "r") as f:
            all_densities = json.load(f)

    return jsonify({
        "summary": summary_data,
        "timeseries": timeseries_data,
        "all_densities": all_densities
    })


@app.route("/api/benchmark/run", methods=["POST"])
def trigger_benchmark():
    data = request.get_json() or {}
    duration = int(data.get("duration", 300))
    density = data.get("density_level", "medium")

    def run_bg():
        try:
            print(f"[API] Starting background benchmark for {duration}s ({density.upper()})...")
            run_comparison_benchmark(duration, density)
        except Exception as e:
            print(f"[API] Benchmark error: {e}")

    th = threading.Thread(target=run_bg, daemon=True)
    th.start()
    return jsonify({"status": "running", "duration": duration, "density": density})


# =============================================================================
# COMPUTER VISION CAMERA STREAM ROUTES (OPENCV)
# =============================================================================

def gen_camera_frames():
    """Generates continuous MJPEG frames from the OpenCV camera detector."""
    while True:
        frame_bytes, _ = camera_stream.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.04) # ~25 FPS streaming


@app.route("/api/vision/feed")
def vision_feed():
    """Video streaming route for OpenCV camera detection view."""
    return Response(gen_camera_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/api/vision/status", methods=["GET"])
def vision_status():
    """Returns real-time vehicle counts and lane occupancy from camera vision."""
    return jsonify(camera_stream.current_metrics or {"mode": "OPENCV_CAMERA_DETECTION", "active_vehicles": 0})


@app.route("/api/vision/source", methods=["POST"])
def vision_set_source():
    data = request.get_json() or {}
    source = data.get("source", "synthetic")
    camera_stream.set_source(source)
    return jsonify({"source": source})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[TRAFFIX AI] Starting Flask Server on http://localhost:{port}...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
