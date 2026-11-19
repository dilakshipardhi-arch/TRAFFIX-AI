"""
TRAFFIX AI - Network Build Script
Compiles the corridor network definitions (.nod.xml, .edg.xml, .con.xml)
into the SUMO road network XML (.net.xml) using netconvert.
"""

import os
import sys
import shutil
import subprocess

def find_netconvert():
    """Locate the netconvert executable from SUMO_HOME, python Scripts, or PATH."""
    user_site_sumo = os.path.expanduser(r"~\AppData\Roaming\Python\Python315\site-packages\sumo")
    if os.path.isdir(user_site_sumo) and not os.environ.get("SUMO_HOME"):
        os.environ["SUMO_HOME"] = user_site_sumo

    # 1. Direct path in Python Scripts
    py_scripts = os.path.expanduser(r"~\AppData\Roaming\Python\Python315\Scripts\netconvert.exe")
    if os.path.isfile(py_scripts):
        return py_scripts

    # 2. Check PATH
    which_nc = shutil.which("netconvert")
    if which_nc and os.path.isfile(which_nc):
        return which_nc

    # 3. Check SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        cand = os.path.join(sumo_home, "bin", "netconvert.exe" if os.name == "nt" else "netconvert")
        if os.path.isfile(cand):
            return cand

    # 4. Check typical Windows install paths
    win_paths = [
        r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe",
        r"C:\Program Files\Eclipse\Sumo\bin\netconvert.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Sumo\bin\netconvert.exe"),
    ]
    for wp in win_paths:
        if os.path.isfile(wp):
            return wp

    return None

def build_network():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    nod_file = os.path.join(current_dir, "corridor_3j.nod.xml")
    edg_file = os.path.join(current_dir, "corridor_3j.edg.xml")
    con_file = os.path.join(current_dir, "corridor_3j.con.xml")
    net_file = os.path.join(current_dir, "corridor_3j.net.xml")

    print("[TRAFFIX AI] Building corridor road network...")
    print(f"  Nodes: {nod_file}")
    print(f"  Edges: {edg_file}")
    print(f"  Connections: {con_file}")
    print(f"  Output: {net_file}")

    for f, name in [(nod_file, "Nodes"), (edg_file, "Edges"), (con_file, "Connections")]:
        if not os.path.exists(f):
            raise FileNotFoundError(f"Missing required definition file: {name} ({f})")

    netconvert_bin = find_netconvert()
    if not netconvert_bin:
        raise RuntimeError(
            "Could not find 'netconvert' executable! Please ensure Eclipse SUMO is installed "
            "or set SUMO_HOME to the SUMO directory."
        )

    print(f"[TRAFFIX AI] Using netconvert at: {netconvert_bin}")

    cmd = [
        netconvert_bin,
        "--node-files", nod_file,
        "--edge-files", edg_file,
        "--connection-files", con_file,
        "--output-file", net_file,
        "--tls.guess-signals", "true",
        "--tls.default-type", "static",
        "--check-lane-foes.all", "true",
        "--junctions.corner-detail", "5",
        "--offset.disable-normalization", "true"
    ]

    print("[TRAFFIX AI] Running netconvert command...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[TRAFFIX AI] netconvert failed with error:")
        print(res.stderr)
        raise RuntimeError(f"netconvert failed (code {res.returncode}): {res.stderr}")

    print("[TRAFFIX AI] Network compiled successfully!")
    print(f"  Generated: {net_file} ({os.path.getsize(net_file)} bytes)")
    return net_file

if __name__ == "__main__":
    build_network()
