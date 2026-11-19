"""
TRAFFIX AI - SUMO Simulation Runner
Manages TraCI connection lifecycle, SUMO binary detection, and step-by-step execution.
"""

import os
import sys
import shutil

# Ensure user site-packages are accessible in sys.path
import site
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.insert(0, user_site)

# Ensure SUMO_HOME is set
user_site_sumo = os.path.expanduser(r"~\AppData\Roaming\Python\Python315\site-packages\sumo")
if os.path.isdir(user_site_sumo) and not os.environ.get("SUMO_HOME"):
    os.environ["SUMO_HOME"] = user_site_sumo

import traci
import sumolib


def get_sumo_binary(gui=False):
    """Find the path to sumo or sumo-gui executable."""
    bin_name = "sumo-gui" if gui else "sumo"
    if os.name == "nt":
        bin_name += ".exe"

    # 1. Direct Python Scripts location
    py_scripts = os.path.expanduser(rf"~\AppData\Roaming\Python\Python315\Scripts\{bin_name}")
    if os.path.isfile(py_scripts):
        return py_scripts

    # 2. Check PATH
    which_bin = shutil.which(bin_name)
    if which_bin and os.path.isfile(which_bin):
        return which_bin

    # 3. Check SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        cand = os.path.join(sumo_home, "bin", bin_name)
        if os.path.isfile(cand):
            return cand

    # 4. Check typical Windows install paths
    win_paths = [
        rf"C:\Program Files (x86)\Eclipse\Sumo\bin\{bin_name}",
        rf"C:\Program Files\Eclipse\Sumo\bin\{bin_name}",
        os.path.expanduser(rf"~\AppData\Local\Programs\Sumo\bin\{bin_name}"),
    ]
    for wp in win_paths:
        if os.path.isfile(wp):
            return wp

    raise FileNotFoundError(
        f"Could not locate '{bin_name}'! Ensure Eclipse SUMO is installed or SUMO_HOME is set."
    )


class SumoSimulation:
    """Encapsulates a live SUMO TraCI simulation session."""

    def __init__(self, sumocfg_path, gui=False, step_length=1.0, route_file=None):
        self.sumocfg_path = os.path.abspath(sumocfg_path)
        self.gui = gui
        self.step_length = step_length
        self.route_file = route_file
        self._running = False
        self._traci = traci

    def start(self):
        """Start the SUMO process and connect via TraCI."""
        if self._running:
            return

        sumo_bin = get_sumo_binary(self.gui)
        sumo_cmd = [
            sumo_bin,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--no-warnings", "true",
            "--duration-log.disable", "true",
            "--no-step-log", "true",
        ]

        if self.route_file and os.path.isfile(self.route_file):
            sumo_cmd.extend(["-r", os.path.abspath(self.route_file)])

        if self.gui:
            sumo_cmd.extend(["--start", "true", "--quit-on-end", "true"])

        self._traci.start(sumo_cmd)
        self._running = True

    def step(self):
        """Advance the simulation by one step."""
        if not self._running:
            raise RuntimeError("Simulation is not running. Call start() first.")
        self._traci.simulationStep()
        return self._traci.simulation.getTime()

    def get_time(self):
        """Return current simulation clock in seconds."""
        if not self._running:
            return 0.0
        return self._traci.simulation.getTime()

    def is_running(self):
        """Check if simulation is currently active and has remaining vehicles."""
        if not self._running:
            return False
        return self._traci.simulation.getMinExpectedNumber() > 0

    def close(self):
        """Gracefully close TraCI connection."""
        if self._running:
            try:
                self._traci.close()
            except Exception:
                pass
            self._running = False

    @property
    def traci(self):
        """Direct access to TraCI API."""
        return self._traci
