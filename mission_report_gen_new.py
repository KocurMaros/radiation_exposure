#!/usr/bin/env python3
"""
=======================================================================
  DRONE RADIATION MISSION SAFETY REPORT GENERATOR
=======================================================================
Analyzes MAVLink + Jetson telemetry from a drone system exposed to
ionizing radiation, generates 11 publication-quality plots, calls
Gemini LLM for intelligent commentary on each, computes a Flight
Readiness Score, and assembles a complete markdown + self-contained
HTML report.

Platform : CubePilot autopilot + Jetson Xavier NX  (stationary)
Exposure : 3 sessions at an irradiation facility, 2025-12-14/15
Post-exp : sessions 4th-8th recorded days/weeks later
"""

import os, sys, re, io, json, time, base64, warnings, textwrap
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib import cm
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")

# ────────────────────────────────────────────────────────────
# PATHS
# ────────────────────────────────────────────────────────────
ROOT    = Path("/home/frajer/Projects/radiation_exposure")
BASE    = ROOT / "merania"
MAVLINK = BASE / "mavlink"
JETSON  = BASE / "jetson"
OUTPUT  = ROOT / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

PRE        = ["01_PRE_baseline"]
EXPOSURE   = ["02_DURING_exposure_run1", "03_DURING_exposure_run2", "04_DURING_exposure_run3"]
POST       = ["05_POST_recovery_day1", "06_POST_recovery_day2", "07_POST_recovery_dayX"]

ALL_SESS   = PRE + EXPOSURE + POST

COLORS = {
    "01_PRE_baseline": "#00ff00",
    "02_DURING_exposure_run1": "#ff0000",
    "03_DURING_exposure_run2": "#e67e22",
    "04_DURING_exposure_run3": "#f1c40f",
    "05_POST_recovery_day1": "#00ff95",
    "06_POST_recovery_day2": "#00e1ff",
    "07_POST_recovery_dayX": "#003cff",
}
PHASE_COLORS = {"PRE": "#00ff0d", "DURING": "#ff0000", "POST": "#2d00f8"}

DPI = 300
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "#fafafa",
    "axes.grid": True, "grid.alpha": 0.3, "font.size": 9,
    "savefig.dpi": DPI, "savefig.bbox": "tight",
})

# ────────────────────────────────────────────────────────────
# GEMINI SETUP
# ────────────────────────────────────────────────────────────
GEMINI_OK = False
try:
    import google.generativeai as genai
    from PIL import Image
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel("gemini-3-pro-preview")
        GEMINI_OK = True
        print("[✓] Gemini API configured")
    else:
        print("[!] GEMINI_API_KEY not set – will use auto-generated placeholder text")
except Exception as e:
    print(f"[!] Gemini init error: {e} – will use placeholder text")

GENERATE_SLOVAK_COMMENTARY = True  # Set to True to test non-English output
def ask_gemini(image_path: str, stats_context: str, prompt_extra: str = "") -> str:
    """Send image + stats to Gemini; return commentary string."""
    base_prompt = (
        "You are a radiation safety engineer analysing drone telemetry from a single "
        "stationary drone exposed to ionizing radiation inside an irradiation facility. "
        "There is NO external radiation sensor — the graphs show the cumulative EFFECTS of radiation "
        "on the drone's COTS electronics (sensor drift, EKF degradation, voltage changes, etc.).\n\n"
        "CRITICAL EXPERIMENTAL CONTEXT:\n"
        "- The radiation dose rate was 3 Sieverts per hour.\n"
        "- Each active exposure run (1st, 2nd, 3rd) was designed to be 30 minutes of beam time (approx 1.5 Sieverts per run), "
        "plus setup and cooldown time.\n"
        "- All exposure logs MUST span at least 30 minutes. If a log is shorter, it indicates an early system crash or incomplete dataset.\n\n"
        f"Given this graph and targeted context:\n{stats_context}\n\n"
        "Write a concise, highly analytical 4 to 5 sentence technical summary structured as follows:\n"
        "(1) Briefly state what the graph shows.\n"
        "(2) Compare the sequential exposure runs (1st vs 2nd vs 3rd) against each other to identify any cumulative degradation or worsening trends over time.\n"
        "(3) State any anomalies, explicitly reporting if any exposure measurement falls short of the mandatory 30-minute duration.\n"
        "(4) Conclude what these specific metrics mean for the drone's immediate airworthiness and hardware survivability.\n"
    )
    if GENERATE_SLOVAK_COMMENTARY:
        base_prompt += "(5) Napíšte tento komentár v slovenčine, zachovávajúc technickú presnosť a analytický tón.)\n\n"
    base_prompt += f"{prompt_extra}" 
    # base_prompt = (
    #     "You are a radiation safety engineer analysing drone telemetry from a "
    #     "stationary drone exposed to ionizing radiation inside a reactor/irradiation "
    #     "facility. There is NO external radiation sensor — the graphs show the "
    #     "EFFECTS of radiation on the drone electronics (sensor drift, EKF degradation, "
    #     "voltage changes, etc.). "
    #     f"Given this graph and targeted context:\n{stats_context}\n\n"
    #     "Write a concise 4-sentence technical summary: (1) what the graph shows, "
    #     "(2) what trend or pattern is visible, (3) any anomalies or concerns, and "
    #     "(4) what this means for the drone's airworthiness after radiation exposure. "
    #     f"{prompt_extra}"
    # )
    if not GEMINI_OK:
        return _placeholder(stats_context)
    try:
        img = Image.open(image_path)
        resp = gemini_model.generate_content([img, base_prompt])
        time.sleep(1.0)          # respect free-tier rate limits
        return resp.text.strip()
    except Exception as e:
        print(f"    Gemini call failed ({e}), using placeholder")
        return _placeholder(stats_context)


def _placeholder(ctx: str) -> str:
    """Auto-generated fallback when Gemini is unavailable."""
    return (
        "This graph presents telemetry data from the drone's electronics "
        "during radiation exposure sessions. The measured values show "
        "session-to-session variation consistent with the irradiation environment. "
        "No catastrophic anomalies are visible suggesting the hardware survived "
        "the exposure. Further manual review is recommended to confirm operational "
        "readiness for redeployment."
    )


# ================================================================
#  STEP 1 — DATA DISCOVERY
# ================================================================
print("\n" + "=" * 70)
print("  STEP 1 — DATA DISCOVERY")
print("=" * 70)

file_inventory = []

def scan_dir(root, label):
    if not root.exists(): return
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".csv", ".log", ".txt", ".bin", ".bak"):
            rel = p.relative_to(ROOT)
            size_kb = p.stat().st_size / 1024
            file_inventory.append({
                "path": str(rel), "category": label,
                "format": p.suffix.lower(), "size_kb": round(size_kb, 1),
            })

scan_dir(MAVLINK, "MAVLink")
scan_dir(JETSON,  "Jetson")
scan_dir(BASE / "cube", "CubePilot")

print(f"  Found {len(file_inventory)} files")
for cat in ["MAVLink", "Jetson", "CubePilot"]:
    n = sum(1 for f in file_inventory if f["category"] == cat)
    sz = sum(f["size_kb"] for f in file_inventory if f["category"] == cat)
    print(f"    {cat:12s}: {n:4d} files, {sz/1024:.1f} MB total")


# ================================================================
#  STEP 2 — DATA PARSING & ALIGNMENT
# ================================================================
print("\n" + "=" * 70)
print("  STEP 2 — DATA PARSING & ALIGNMENT")
print("=" * 70)

def load_csv(session, msg):
    p = MAVLINK / session / f"{msg}.csv"
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, parse_dates=["SystemTime_ISO"])
    except Exception:
        return None

def parse_tegrastats(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                parts = line.split()
                ts = pd.to_datetime(f"{parts[0]} {parts[1]}", format="%m-%d-%Y %H:%M:%S")
                rec = {"timestamp": ts}
                m = re.search(r"RAM\s+(\d+)/(\d+)MB", line)
                if m: rec["ram_used_mb"] = int(m.group(1)); rec["ram_total_mb"] = int(m.group(2))
                m = re.search(r"CPU\s+\[([^\]]+)\]", line)
                if m:
                    cpus = [int(re.search(r"(\d+)%", c).group(1)) for c in m.group(1).split(",")
                            if c.strip() != "off" and re.search(r"\d+%", c)]
                    rec["cpu_avg_pct"] = np.mean(cpus) if cpus else 0
                for tn in ["AUX","CPU","GPU","AO","iwlwifi","PMIC"]:
                    m2 = re.search(rf"{tn}@([\d.]+)C", line)
                    if m2: rec[f"temp_{tn.lower()}_c"] = float(m2.group(1))
                m = re.search(r"thermal@([\d.]+)C", line)
                if m: rec["temp_thermal_c"] = float(m.group(1))
                for pw in ["VDD_IN","VDD_CPU_GPU_CV","VDD_SOC"]:
                    m2 = re.search(rf"{pw}\s+(\d+)mW/(\d+)mW", line)
                    if m2:
                        rec[f"pwr_{pw.lower()}_mw"] = int(m2.group(1))
                        rec[f"pwr_{pw.lower()}_avg_mw"] = int(m2.group(2))
                rows.append(rec)
            except Exception:
                continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()

def parse_memchk(path):
    rows = []
    with open(path) as f:
        for line in f:
            m = re.search(
                r"t=\s*([\d.]+)s\s+CHECK_ALL\s+blocks=(\d+)\s+errors=(\d+)\s+"
                r"free=([\d.]+)MB\s+\(([\d.]+)%\)", line)
            if m:
                rows.append({"time_s": float(m.group(1)), "blocks": int(m.group(2)),
                             "errors": int(m.group(3)), "free_mb": float(m.group(4)),
                             "free_pct": float(m.group(5))})
    return pd.DataFrame(rows) if rows else pd.DataFrame()

def parse_os_logs(session_path):
    """Scans dmesg and journal logs for radiation-induced hardware/OS faults."""
    faults = {"i2c_errors": 0, "pcie_errors": 0, "ext4_errors": 0, "thermal_warn": 0, "general_fail": 0}
    
    log_files = list(session_path.glob("dmesg*.log")) + list(session_path.glob("journal*.log"))
    for lf in log_files:
        try:
            with open(lf, "r", errors="ignore") as f:
                for line in f:
                    line_lower = line.lower()
                    if "i2c" in line_lower and ("timeout" in line_lower or "error" in line_lower): faults["i2c_errors"] += 1
                    if "pcie" in line_lower and ("aer" in line_lower or "error" in line_lower): faults["pcie_errors"] += 1
                    if "ext4-fs error" in line_lower: faults["ext4_errors"] += 1
                    if "thermal" in line_lower and ("trip" in line_lower or "throttle" in line_lower): faults["thermal_warn"] += 1
                    if "segfault" in line_lower or "kernel panic" in line_lower or "oops" in line_lower: faults["general_fail"] += 1
        except Exception:
            continue
    return faults

# --- Load MAVLink ---
msg_types = [
    "AHRS", "ATTITUDE", "EKF_STATUS_REPORT", "HEARTBEAT", "HWSTATUS", 
    "MEMINFO", "POWER_STATUS", "RAW_IMU", "SCALED_IMU", "SCALED_IMU2", 
    "SCALED_IMU3", "SCALED_PRESSURE", "SCALED_PRESSURE2", "SYS_STATUS", 
    "SYSTEM_TIME", "VIBRATION"
]

mavlink = {}
for sess in ALL_SESS:
    if not (MAVLINK / sess).is_dir(): continue
    mavlink[sess] = {}
    
    # Establish a "session zero time" using the earliest HWSTATUS or HEARTBEAT timestamp
    t0 = None
    for mt in ["HWSTATUS", "HEARTBEAT", "SYS_STATUS"]:
        df = load_csv(sess, mt)
        if df is not None and not df.empty:
            t0 = df["SystemTime_ISO"].min()
            break
            
    if t0 is None:
        print(f"  MAVLink {sess}: Failed to establish start time (missing HWSTATUS/HEARTBEAT). Skipping.")
        continue

    for mt in msg_types:
        df = load_csv(sess, mt)
        if df is not None and len(df) > 0:
            # Convert to elapsed seconds immediately
            df["elapsed_s"] = (df["SystemTime_ISO"] - t0).dt.total_seconds()
            # Filter out extreme outliers in time caused by clock jumps
            df = df[(df["elapsed_s"] >= 0) & (df["elapsed_s"] < 86400)] 
            mavlink[sess][mt] = df
            
    total = sum(len(v) for v in mavlink[sess].values())
    print(f"  MAVLink {sess}: {len(mavlink[sess])} msg types, {total:,} rows aligned from T=0")

# --- Load Jetson ---
tegra, memchk, os_faults = {}, {}, {}
for sess in EXPOSURE:
    sess_dir = JETSON / sess
    if sess_dir.exists():
        p_teg = sess_dir / "tegrastats_continuous.log"
        if p_teg.exists():
            tegra[sess] = parse_tegrastats(p_teg)
        
        p_mem = sess_dir / "mem_checksum.log"
        if p_mem.exists():
            memchk[sess] = parse_memchk(p_mem)
            
        os_faults[sess] = parse_os_logs(sess_dir)
        total_faults = sum(os_faults[sess].values())
        print(f"  Jetson {sess}: Tegra({len(tegra.get(sess, []))}), MemChk({len(memchk.get(sess, []))}), OS Faults({total_faults} detected)")

# --- Build merged 1-Hz telemetry using elapsed_s ---
def merge_session(sess):
    sd = mavlink.get(sess, {})
    if "HWSTATUS" not in sd: return pd.DataFrame()
    
    base = sd["HWSTATUS"][["elapsed_s","Vcc","I2Cerr"]].copy()
    base["Vcc_V"] = base["Vcc"] / 1000.0
    base["elapsed_s"] = base["elapsed_s"].round() # 1 Hz binning
    base = base.groupby("elapsed_s").agg({"Vcc_V":"mean","I2Cerr":"max"}).reset_index()
    base["session"] = sess
    base["is_exposure"] = sess in EXPOSURE

    def _merge(msg, cols, renames=None, transforms=None):
        if msg not in sd: return
        available_cols = [c for c in cols if c in sd[msg].columns]
        if not available_cols: return
        
        df = sd[msg][["elapsed_s"] + available_cols].copy()
        if renames:
            df.rename(columns=renames, inplace=True)
            available_cols = [renames.get(c, c) for c in available_cols]
            
        df["elapsed_s"] = df["elapsed_s"].round()
        agg = {c: "mean" for c in available_cols}
        df = df.groupby("elapsed_s").agg(agg).reset_index()
        
        if transforms:
            for k, fn in transforms.items(): 
                try: df[k] = fn(df)
                except KeyError: pass
            
        nonlocal base
        base = pd.merge_asof(base.sort_values("elapsed_s"),
                             df.sort_values("elapsed_s"),
                             on="elapsed_s", tolerance=2, direction="nearest")

    # Merge newly requested MAVLink messages
    _merge("ATTITUDE", ["roll", "pitch", "yaw"], transforms={
        "roll_deg": lambda d: np.degrees(d["roll"]),
        "pitch_deg": lambda d: np.degrees(d["pitch"]),
    })
    _merge("MEMINFO", ["freemem", "freemem32"])
    _merge("SYS_STATUS", ["load", "errors_count1"])
    
    _merge("SCALED_PRESSURE", ["press_abs","temperature"], 
           renames={"temperature":"baro_temp_cdeg"}, 
           transforms={"baro_temp_C": lambda d: d["baro_temp_cdeg"]/100})
           
    _merge("SCALED_IMU", ["xacc","yacc","zacc","xgyro","ygyro","zgyro","xmag","ymag","zmag","temperature"], 
           renames={"temperature":"imu_temp_cdeg"}, 
           transforms={
               "imu_temp_C": lambda d: d["imu_temp_cdeg"]/100,
               "acc_mag":  lambda d: np.sqrt(d["xacc"]**2+d["yacc"]**2+d["zacc"]**2),
               "gyro_mag": lambda d: np.sqrt(d["xgyro"]**2+d["ygyro"]**2+d["zgyro"]**2),
               "mag_mag":  lambda d: np.sqrt(d["xmag"]**2+d["ymag"]**2+d["zmag"]**2),
           })
           
    _merge("VIBRATION", ["vibration_x","vibration_y","vibration_z"], 
           transforms={"vib_total": lambda d: np.sqrt(d["vibration_x"]**2+d["vibration_y"]**2+d["vibration_z"]**2)})
           
    _merge("EKF_STATUS_REPORT", ["compass_variance","pos_horiz_variance","flags"], 
           renames={"flags":"ekf_flags"})

    return base

frames = [merge_session(s) for s in ALL_SESS]
frames = [f for f in frames if len(f) > 0]
merged = pd.concat(frames, ignore_index=True).sort_values(["session", "elapsed_s"]).reset_index(drop=True)

# Create elapsed_min for plotting (all start at 0)
merged["elapsed_min"] = merged["elapsed_s"] / 60.0

# Drift from initial per-session
for sess in EXPOSURE:
    m = merged["session"] == sess
    if not m.any(): continue
    for col in ["acc_mag","gyro_mag","mag_mag","imu_temp_C","baro_temp_C"]:
        if col in merged.columns and merged.loc[m, col].notna().any():
            init = merged.loc[m, col].dropna().iloc[:10].mean()
            merged.loc[m, f"{col}_drift"] = merged.loc[m, col] - init

print(f"\n  Merged dataset: {len(merged):,} rows × {merged.shape[1]} cols")

# ================================================================
#  STEP 3 — PHASE SEGMENTATION
# ================================================================
print("\n" + "=" * 70)
print("  STEP 3 — PHASE SEGMENTATION")
print("=" * 70)

# Phase assignment: 8th was recorded BEFORE exposure (pre-test baseline),
# 1st/2nd/3rd during exposure, 4th/5th/6th after.
phase_map = {}
for sess in ALL_SESS:
    if "PRE" in sess: phase_map[sess] = "PRE"
    elif "DURING" in sess: phase_map[sess] = "DURING"
    elif "POST" in sess: phase_map[sess] = "POST"
merged["phase"] = merged["session"].map(phase_map)

# Per-phase stats
metric_cols = [c for c in ["Vcc_V","imu_temp_C","baro_temp_C","acc_mag","gyro_mag",
                            "mag_mag","vib_total","compass_variance","pos_horiz_variance",
                            "freemem"] if c in merged.columns]

phase_stats = {}
for phase in ["PRE","DURING","POST"]:
    pm = merged["phase"] == phase
    if not pm.any():
        phase_stats[phase] = {}; continue
    dur = merged.loc[pm,"elapsed_min"].max() # Max elapsed min gives duration
    ps = {"duration_min": round(dur,1), "n_points": int(pm.sum())}
    for col in metric_cols:
        vals = merged.loc[pm, col].dropna()
        if len(vals) == 0: continue
        ps[f"{col}_mean"] = round(float(vals.mean()), 6)
        ps[f"{col}_median"] = round(float(vals.median()), 6)
        ps[f"{col}_std"]  = round(float(vals.std()), 6)
        ps[f"{col}_min"]  = round(float(vals.min()), 6)
        ps[f"{col}_max"]  = round(float(vals.max()), 6)
    phase_stats[phase] = ps

for ph, ps in phase_stats.items():
    print(f"  {ph}: {ps.get('duration_min','?')} min, {ps.get('n_points','?')} pts")


# ================================================================
#  STEP 4 — GENERATE 11 REPORT IMAGES
# ================================================================
print("\n" + "=" * 70)
print("  STEP 4 — GENERATING 11 REPORT IMAGES")
print("=" * 70)

commentary = {}

def _phase_legend_patches():
    return [mpatches.Patch(color=PHASE_COLORS[p], alpha=0.35, label=p) for p in ["PRE","DURING","POST"]]

# ──────────────── 01 RADIATION TIMELINE ────────────────
fname = "01_radiation_timeline.png"
print(f"  {fname}")
fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("Sensor Drift Timeline During Radiation Exposure\n"
             "(Deviation from initial reading — stationary drone, drift = radiation effect)",
             fontsize=13, fontweight="bold")

drift_cols = [("acc_mag_drift", "Accel Drift (mg)"),
              ("gyro_mag_drift", "Gyro Drift (mrad/s)"),
              ("mag_mag_drift",  "Mag Drift (mGauss)")]

for i, (col, ylabel) in enumerate(drift_cols):
    ax = axes[i]
    if col not in merged.columns:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel(ylabel); continue
    for sess in ALL_SESS:
        m = (merged["session"] == sess) & merged[col].notna()
        if not m.any(): continue
        # Use elapsed_min instead of absolute date
        ax.plot(merged.loc[m,"elapsed_min"], merged.loc[m, col],
                color=COLORS.get(sess,"gray"), alpha=0.75, linewidth=0.7, label=sess)
        
        vals = merged.loc[m, col]
        mu, sigma = vals.mean(), vals.std()
        anom = m & (merged[col].abs() > abs(mu) + 2*sigma)
        if anom.any():
            ax.scatter(merged.loc[anom,"elapsed_min"], merged.loc[anom, col],
                       c="red", s=8, zorder=5, label="_anom")
    ax.axhline(0, color="k", ls="--", alpha=0.3)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=7, loc="upper right", ncol=4)

axes[-1].set_xlabel("Elapsed Time (Minutes)")
axes[0].legend(handles=_phase_legend_patches() + axes[0].get_legend_handles_labels()[0][:7],
               fontsize=7, loc="upper right", ncol=5)
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 02 RADIATION VS ALTITUDE (Baro Temp vs Time instead) ────────────────
fname = "02_radiation_baro_temp.png"
print(f"  {fname}")
fig, ax = plt.subplots(figsize=(12, 8))

for sess in ALL_SESS:
    m = (merged["session"] == sess) & merged["baro_temp_C"].notna()
    if not m.any(): continue
    ax.plot(merged.loc[m,"elapsed_min"], merged.loc[m,"baro_temp_C"],
               color=COLORS.get(sess,"gray"), alpha=0.75, label=sess)

ax.set_xlabel("Elapsed Time (Minutes)")
ax.set_ylabel("Barometric Temperature (°C)")
ax.set_title("Barometric Temperature Increase Over Time", fontsize=12, fontweight="bold")
ax.legend()
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 03 COMPASS HEATMAP ────────────────
fname = "03_compass_variance_heatmap.png"
print(f"  {fname}")
fig, ax = plt.subplots(figsize=(14, 6))

for sess in ALL_SESS:
    m = merged["session"] == sess
    if not m.any(): continue
    t = merged.loc[m, "elapsed_min"]
    cv = merged.loc[m, "compass_variance"] if "compass_variance" in merged.columns else None
    if cv is not None and cv.notna().any():
        sc = ax.scatter(t, [sess]*len(t), c=cv, cmap="hot", s=12, alpha=0.8,
                        norm=Normalize(vmin=0, vmax=merged["compass_variance"].quantile(0.99)))

if "sc" in dir():
    cb = fig.colorbar(sc, ax=ax, label="Compass Variance (navigation degradation)")
ax.set_xlabel("Elapsed Time (Minutes)")
ax.set_ylabel("Session")
ax.set_title("Navigation Degradation Heatmap by Session × Time\n", fontsize=12, fontweight="bold")
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 04 3D MAP ────────────────
fname = "04_radiation_3d_map.png"
print(f"  {fname}")
fig = plt.figure(figsize=(14, 10))
ax = fig.add_subplot(111, projection="3d")

for sess in EXPOSURE:
    m = (merged["session"]==sess)
    for c in ["xacc","yacc","zacc"]:
        m = m & merged[c].notna() if c in merged.columns else m
    if not m.any(): continue
    sc = ax.scatter(merged.loc[m,"xacc"], merged.loc[m,"yacc"], merged.loc[m,"zacc"],
                    c=merged.loc[m,"elapsed_min"], cmap="plasma", s=3, alpha=0.5)

ax.set_xlabel("X Accel (mg)"); ax.set_ylabel("Y Accel (mg)"); ax.set_zlabel("Z Accel (mg)")
ax.set_title("3D Accelerometer State Space During Radiation\n(Color = elapsed time in session)", fontsize=12, fontweight="bold")
if "sc" in dir():
    cb = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.1)
    cb.set_label("Elapsed (min)")
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 05 CUMULATIVE DOSE ────────────────
fname = "05_cumulative_dose.png"
print(f"  {fname}")
fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("Cumulative Radiation Effects on Drone Hardware\n(Progressive degradation indicators)", fontsize=13, fontweight="bold")

cum_cols = [("baro_temp_C", "Baro Temp (°C)"), ("vib_total","Total Vibration (m/s²)"), ("compass_variance","Compass Variance")]

for i, (col, ylabel) in enumerate(cum_cols):
    ax = axes[i]
    if col not in merged.columns:
        ax.set_ylabel(ylabel); continue
    for sess in ALL_SESS:
        m = (merged["session"] == sess) & merged[col].notna()
        if not m.any(): continue
        ax.plot(merged.loc[m,"elapsed_min"], merged.loc[m,col],
                color=COLORS.get(sess,"gray"), alpha=0.7, lw=0.8, label=sess)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=7, ncol=4, loc="upper right")

axes[-1].set_xlabel("Elapsed Time (Minutes)")
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 06 TELEMETRY OVERVIEW ────────────────
fname = "06_telemetry_overview.png"
print(f"  {fname}")
cols_06 = [("Vcc_V","Board Voltage (V)"), ("imu_temp_C","IMU Temperature (°C)"), ("freemem","Free Memory"), ("load","System Load")]
fig, axes = plt.subplots(len(cols_06), 1, figsize=(14, 12), sharex=True)
fig.suptitle("Telemetry Overview — All Sessions\n", fontsize=13, fontweight="bold")

for i, (col, ylabel) in enumerate(cols_06):
    ax = axes[i]
    if col not in merged.columns:
        ax.set_ylabel(ylabel); continue
    for sess in ALL_SESS:
        m = (merged["session"]==sess) & merged[col].notna()
        if not m.any(): continue
        is_exp = sess in EXPOSURE
        ax.plot(merged.loc[m,"elapsed_min"], merged.loc[m,col],
                color=COLORS.get(sess,"gray"), alpha=0.8 if is_exp else 0.45,
                lw=0.9 if is_exp else 0.45, label=sess)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=6, ncol=4, loc="upper right")

axes[-1].set_xlabel("Elapsed Time (Minutes)")
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 07 DOSE DISTRIBUTION ────────────────
fname = "07_dose_distribution.png"
print(f"  {fname}")
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("Distribution of Key Sensor Readings — by Phase\n", fontsize=13, fontweight="bold")

dist_cols = [("vib_total","Vibration (m/s²)"), ("compass_variance","Compass Variance"),
             ("acc_mag","Accel Magnitude (mg)"), ("Vcc_V","Board Voltage (V)")]

for i, (col, xlabel) in enumerate(dist_cols):
    ax = axes.flat[i]
    if col not in merged.columns:
        ax.text(0.5,0.5,"No data",ha="center",va="center",transform=ax.transAxes); continue
    for phase in ["PRE","DURING","POST"]:
        vals = merged.loc[(merged["phase"]==phase) & merged[col].notna(), col]
        if len(vals) < 3: continue
        ax.hist(vals, bins=60, alpha=0.45, color=PHASE_COLORS[phase],
                label=f"{phase} (n={len(vals)})", density=True)
    ax.set_xlabel(xlabel); ax.set_ylabel("Density"); ax.legend(fontsize=7)

plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 08 PHASE COMPARISON BOXPLOT ────────────────
fname = "08_phase_comparison_boxplot.png"
print(f"  {fname}")
box_cols = [c for c in ["vib_total","compass_variance","acc_mag","Vcc_V", "imu_temp_C","freemem"] if c in merged.columns]
fig, axes = plt.subplots(1, len(box_cols), figsize=(3*len(box_cols), 7))
if len(box_cols) == 1: axes = [axes]
fig.suptitle("Phase Comparison — PRE vs DURING vs POST Exposure", fontsize=13, fontweight="bold")

for i, col in enumerate(box_cols):
    ax = axes[i]
    data_by_phase, labels = [], []
    for phase in ["PRE","DURING","POST"]:
        vals = merged.loc[(merged["phase"]==phase) & merged[col].notna(), col]
        if len(vals) > 0:
            data_by_phase.append(vals.values); labels.append(phase)
    if data_by_phase:
        bp = ax.boxplot(data_by_phase, labels=labels, patch_artist=True, widths=0.6)
        for patch, lab in zip(bp["boxes"], labels):
            patch.set_facecolor(PHASE_COLORS.get(lab, "gray")); patch.set_alpha(0.5)
    ax.set_title(col.replace("_"," ").title(), fontsize=9); ax.tick_params(labelsize=8)

plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 09 STATS SUMMARY CARD ────────────────
fname = "09_stats_summary_card.png"
print(f"  {fname}")

table_rows = []
for col in metric_cols:
    row = [col.replace("_"," ").title()]
    for phase in ["PRE","DURING","POST"]:
        ps = phase_stats.get(phase, {})
        mean, std, mn, mx = ps.get(f"{col}_mean", "—"), ps.get(f"{col}_std", "—"), ps.get(f"{col}_min", "—"), ps.get(f"{col}_max", "—")
        if isinstance(mean, float): row.append(f"{mean:.4f} ± {std:.4f}\n[{mn:.4f} – {mx:.4f}]")
        else: row.append("—")
    table_rows.append(row)

fig, ax = plt.subplots(figsize=(16, max(4, 0.55*len(table_rows)+2)))
ax.axis("off")
ax.set_title("Phase Statistics Summary Card", fontsize=14, fontweight="bold", pad=20)
col_labels = ["Metric", "PRE (Baseline)", "DURING (Exposure)", "POST (Recovery)"]
table = ax.table(cellText=table_rows, colLabels=col_labels, loc="center", cellLoc="center", colColours=["#ddd","#aed6f1","#f5b7b1","#abebc6"])
table.auto_set_font_size(False); table.set_fontsize(8); table.scale(1.0, 1.6)
for (r, c), cell in table.get_celld().items():
    if r == 0: cell.set_text_props(fontweight="bold")
    cell.set_edgecolor("#ccc")
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 10 FLIGHT READINESS GAUGE ────────────────
fname = "10_flight_readiness_gauge.png"
print(f"  {fname}")

scoring, total_score = {}, 0

# 1. POST recovery within 10% of PRE baseline
score1, checks_1 = 0, []
for col in ["Vcc_V","vib_total","compass_variance"]:
    pre_mean = phase_stats.get("PRE",{}).get(f"{col}_mean")
    post_mean = phase_stats.get("POST",{}).get(f"{col}_mean")
    if pre_mean and post_mean and pre_mean != 0:
        pct = abs(post_mean - pre_mean) / abs(pre_mean) * 100
        ok = pct < 10
        checks_1.append((col, pct, ok))
        if ok: score1 += 10
if not checks_1: score1 = 15
scoring["recovery_baseline"] = {"score": min(score1, 30), "max": 30, "note": "; ".join(f"{c}: {p:.1f}% {'✓' if o else '✗'}" for c,p,o in checks_1) or "Partial data"}
total_score += scoring["recovery_baseline"]["score"]

# 2. No catastrophic sensor failure
score2, notes2 = 20, []
memchk_errors = sum(int(df["errors"].sum()) for df in memchk.values() if len(df) > 0 and "errors" in df.columns) if memchk else 0
if memchk_errors > 0: score2 -= 10; notes2.append(f"{memchk_errors} mem errors")
i2c_max = merged.loc[merged["is_exposure"],"I2Cerr"].max() if "I2Cerr" in merged.columns else 0
if i2c_max > 0: score2 -= 5; notes2.append(f"I2C errors: {i2c_max}")
scoring["max_dose_safe"] = {"score": max(score2,0), "max": 20, "note": "No failures" if not notes2 else "; ".join(notes2)}
total_score += scoring["max_dose_safe"]["score"]

# 3. No anomaly spikes > mean+3σ
score3, n_extreme = 20, 0
for col in ["vib_total","compass_variance"]:
    if col not in merged.columns: continue
    exp = merged.loc[merged["is_exposure"] & merged[col].notna(), col]
    if len(exp) == 0: continue
    mu, sig = exp.mean(), exp.std()
    n_extreme += ((exp > mu+3*sig) | (exp < mu-3*sig)).sum()
if n_extreme > 50: score3 = max(0, score3 - min(20, n_extreme // 10))
scoring["no_3sigma_spikes"] = {"score": score3, "max": 20, "note": f"{n_extreme} extreme outliers (>3σ)"}
total_score += scoring["no_3sigma_spikes"]["score"]

# 4. OS/Journal Integrity (New!)
score4, notes4 = 20, []
total_os_faults = sum(sum(d.values()) for d in os_faults.values())
if total_os_faults > 0:
    score4 -= min(20, total_os_faults * 2)
    notes4.append(f"{total_os_faults} OS-level faults logged")
scoring["os_integrity"] = {"score": max(score4,0), "max": 20, "note": "Clean dmesg/journal" if not notes4 else "; ".join(notes4)}
total_score += scoring["os_integrity"]["score"]

# 5. Battery/telemetry nominal
score5, notes5 = 10, []
if "Vcc_V" in merged.columns:
    vcc_exp = merged.loc[merged["is_exposure"],"Vcc_V"].dropna()
    if len(vcc_exp) > 0 and vcc_exp.std() > 0.05: score5 -= 5; notes5.append(f"Vcc σ={vcc_exp.std():.4f}V")
scoring["telemetry_nominal"] = {"score": max(score5,0), "max": 10, "note": "Nominal" if not notes5 else "; ".join(notes5)}
total_score += scoring["telemetry_nominal"]["score"]

# Verdict
if total_score >= 80: verdict, verdict_color = "✅ READY — Drone cleared for re-entry into radiation zone", "#27ae60"
elif total_score >= 50: verdict, verdict_color = "⚠️ CONDITIONAL — Review flagged items before next flight", "#f39c12"
else: verdict, verdict_color = "❌ GROUNDED — Do not fly until maintenance and decontamination check", "#e74c3c"

# Draw gauge
fig, ax = plt.subplots(figsize=(10, 7))
ax.set_xlim(-1.3, 1.3); ax.set_ylim(-0.4, 1.4); ax.set_aspect("equal"); ax.axis("off")
theta = np.linspace(np.pi, 0, 300)
for i, t in enumerate(theta):
    frac = i / len(theta)
    c = plt.cm.RdYlGn(frac * 2) if frac < 0.5 else plt.cm.RdYlGn(0.5 + (frac - 0.5) * 1.0)
    ax.plot([1.05*np.cos(t)], [1.05*np.sin(t)], "s", color=c, markersize=8)
angle = np.pi * (1 - total_score / 100)
ax.annotate("", xy=(0.85*np.cos(angle), 0.85*np.sin(angle)), xytext=(0, 0), arrowprops=dict(arrowstyle="-|>", color="black", lw=2.5))
ax.plot(0, 0, "ko", markersize=10)
ax.text(0, 0.55, f"{total_score}", fontsize=52, fontweight="bold", ha="center", va="center", color=verdict_color)
ax.text(0, 0.35, "/ 100", fontsize=18, ha="center", va="center", color="#666")
ax.text(0, -0.15, verdict, fontsize=14, ha="center", va="center", fontweight="bold", color=verdict_color, bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor=verdict_color, lw=2))

y = -0.3
ax.text(-1.2, y, "Scoring Breakdown:", fontsize=10, fontweight="bold", va="top")
for name, info in scoring.items():
    y -= 0.075
    ax.text(-1.2, y, f"  {name.replace('_',' ').title()}: {info['score']}/{info['max']}  — {info['note']}", fontsize=8, va="top", fontfamily="monospace")
ax.set_title("Flight Readiness Assessment", fontsize=16, fontweight="bold", pad=10)
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 11 JETSON SYSTEM HEALTH ────────────────
fname = "11_jetson_system_health.png"
print(f"  {fname}")
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
fig.suptitle("Jetson Xavier NX Health During Irradiation\n(Metrics from Tegrastats)", fontsize=13, fontweight="bold")

for sess, t_df in tegra.items():
    if t_df.empty: continue
    t_df['elapsed_min'] = (t_df['timestamp'] - t_df['timestamp'].min()).dt.total_seconds() / 60.0
    axes[0].plot(t_df["elapsed_min"], t_df.get("temp_cpu_c", []), label=f"{sess} CPU", color=COLORS.get(sess))
    axes[0].plot(t_df["elapsed_min"], t_df.get("temp_gpu_c", []), linestyle="--", alpha=0.7, color=COLORS.get(sess))
    if "pwr_vdd_in_mw" in t_df.columns:
        axes[1].plot(t_df["elapsed_min"], t_df["pwr_vdd_in_mw"] / 1000.0, label=f"{sess} Power (W)", color=COLORS.get(sess))

axes[0].set_ylabel("Temperature (°C)")
axes[0].legend(fontsize=8, loc="upper right")
axes[1].set_ylabel("VDD IN Power (Watts)")
axes[1].set_xlabel("Elapsed Time (Minutes)")
axes[1].legend(fontsize=8, loc="upper right")
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ================================================================
#  STEP 5 — GEMINI COMMENTARY
# ================================================================
print("\n" + "=" * 70)
print("  STEP 5 — LLM COMMENTARY (Gemini)")
print("=" * 70)

def generate_ai_context(plot_file, merged_data, os_faults):
    """Generates highly specific, targeted JSON context for the LLM."""
    ctx = {"Plot": plot_file}
    
    if "timeline" in plot_file or "cumulative" in plot_file:
        ctx["Max Drift Observed"] = {
            "Accel": f"{merged_data.get('acc_mag_drift', pd.Series([0])).max():.2f} mg",
            "Gyro": f"{merged_data.get('gyro_mag_drift', pd.Series([0])).max():.2f} mrad/s"
        }
    elif "heatmap" in plot_file:
        ctx["Compass Variance Max"] = f"{merged_data.get('compass_variance', pd.Series([0])).max():.4f}"
    
    total_os_faults = {k: sum(d.get(k, 0) for d in os_faults.values()) for k in ["i2c_errors", "pcie_errors", "ext4_errors", "general_fail"]}
    ctx["Jetson OS Faults (Radiation Induced)"] = total_os_faults
    ctx["CubePilot Memory"] = f"Min Free Mem: {merged_data.get('freemem', pd.Series([0])).min()} bytes"
    
    return json.dumps(ctx, indent=2)

plot_files = [
    ("01_radiation_timeline.png",      "Sensor drift over elapsed time during radiation exposure sessions"),
    ("02_radiation_baro_temp.png",     "Barometric temperature increase over elapsed time"),
    ("03_compass_variance_heatmap.png","Navigation degradation heatmap — compass variance by session"),
    ("04_radiation_3d_map.png",        "3D accelerometer state-space showing drift during exposure"),
    ("05_cumulative_dose.png",         "Cumulative effects: temperature, vibration, compass over time"),
    ("06_telemetry_overview.png",      "Multi-panel telemetry: voltage, temp, free memory, load"),
    ("07_dose_distribution.png",       "Distribution histograms comparing PRE/DURING/POST phases"),
    ("08_phase_comparison_boxplot.png","Box-plot comparison of key metrics across phases"),
    ("09_stats_summary_card.png",      "Numerical statistics table for all channels by phase"),
    ("10_flight_readiness_gauge.png",  f"Readiness gauge — score {total_score}/100 — {verdict}"),
    ("11_jetson_system_health.png",    "Jetson companion CPU/GPU temps and system power draw"),
]

for pf, desc in plot_files:
    path = OUTPUT / pf
    stats_ctx = generate_ai_context(pf, merged, os_faults)
    print(f"  → {pf}")
    commentary[pf] = ask_gemini(str(path), f"Graph Description: {desc}\nTargeted Data:\n{stats_ctx}")
    print(f"    [{len(commentary[pf])} chars]")

# Final mission narrative
print("  → Mission safety narrative")
narrative_ctx = (
    f"Score: {total_score}/100. Verdict: {verdict}.\n"
    f"Scoring breakdown:\n" +
    "\n".join(f"  {k}: {v['score']}/{v['max']} — {v['note']}" for k,v in scoring.items()) +
    f"\nPhase durations: PRE={phase_stats.get('PRE',{}).get('duration_min','?')}min, "
    f"DURING={phase_stats.get('DURING',{}).get('duration_min','?')}min, "
    f"POST={phase_stats.get('POST',{}).get('duration_min','?')}min\n"
    f"Memory checksum errors: {memchk_errors}\n"
    f"Platform: CubePilot + Jetson Xavier NX, stationary in radiation facility"
)

if GEMINI_OK:
    try:
        resp = gemini_model.generate_content(
            f"You are a radiation safety officer writing the executive summary for a "
            f"drone radiation exposure test report. The drone was stationary (not flying) "
            f"inside a radiation facility. Based on this data:\n{narrative_ctx}\n\n"
            f"Write a single concise paragraph (5-7 sentences) suitable as the executive "
            f"summary of the mission safety report. Cover: what was tested, key findings, "
            f"whether the hardware survived, and the readiness verdict.")
        executive_summary = resp.text.strip()
    except Exception as e:
        print(f"    Gemini narrative failed: {e}")
        executive_summary = None
else:
    executive_summary = None

if not executive_summary:
    executive_summary = (
        f"This report documents a radiation exposure test of a CubePilot autopilot and "
        f"Jetson Xavier NX companion computer mounted on a stationary drone inside an "
        f"irradiation facility. The system achieved a Flight Readiness Score of {total_score}/100 — {verdict}."
    )

# ================================================================
#  STEP 6 & 7 — SAVE OUTPUTS
# ================================================================
print("\n" + "=" * 70)
print("  STEP 6 & 7 — ASSEMBLING MISSION REPORT")
print("=" * 70)
merged.to_csv(OUTPUT / "parsed_data_merged.csv", index=False)
print(f"  → {OUTPUT / 'parsed_data_merged.csv'} ({len(merged):,} rows)")

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
dur_min = phase_stats.get("DURING",{}).get("duration_min", "?")

stats_table_header = "| Metric | PRE (Baseline) | DURING (Exposure) | POST (Recovery) |\n|---|---|---|---|\n"
stats_table_rows = ""
for col in metric_cols:
    label = col.replace("_"," ").title()
    row = f"| {label} |"
    for phase in ["PRE","DURING","POST"]:
        ps = phase_stats.get(phase, {})
        mean, std = ps.get(f"{col}_mean"), ps.get(f"{col}_std")
        row += f" {mean:.4f} ± {std:.4f} |" if mean is not None else " — |"
    stats_table_rows += row + "\n"

scoring_table = "| Criterion | Points | Max | Notes |\n|---|---|---|---|\n"
for name, info in scoring.items():
    scoring_table += f"| {name.replace('_',' ').title()} | {info['score']} | {info['max']} | {info['note']} |\n"
scoring_table += f"| **TOTAL** | **{total_score}** | **100** | **{verdict}** |\n"

graph_sections = ""
for pf, title in plot_files:
    cmt = commentary.get(pf, "_No commentary available._")
    graph_sections += f"## {title}\n![{pf}]({pf})\n\n**AI Commentary:** {cmt}\n\n---\n"

md_report = f"""# Drone Radiation Mission Safety Report

**Generated:** {now}
**Exposure Duration:** {dur_min} min | **Total Data Points:** {len(merged):,}
**Platform:** CubePilot autopilot + Jetson Xavier NX (stationary)
**FLIGHT READINESS VERDICT:** {verdict}
**Score:** {total_score}/100

---

## Executive Summary

{executive_summary}

---

## Phase Statistics — PRE / DURING / POST

{stats_table_header}{stats_table_rows}

---
{graph_sections}

## Flight Readiness Breakdown

{scoring_table}
"""

with open(OUTPUT / "MISSION_REPORT.md", "w") as f: f.write(md_report)

import markdown as md_lib
def embed_images_in_html(html_body: str, base_dir: Path) -> str:
    import re as _re
    def _replace(match):
        src = match.group(1)
        img_path = base_dir / src
        if img_path.exists():
            with open(img_path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
            ext = img_path.suffix.lstrip(".")
            return f'src="data:image/{ext};base64,{b64}"'
        return match.group(0)
    return _re.sub(r'src="([^"]+\.png)"', _replace, html_body)

md_html = embed_images_in_html(md_lib.markdown(md_report, extensions=["tables", "fenced_code"]), OUTPUT)

html_doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Drone Radiation Mission Safety Report</title><style>body {{ font-family: sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1.5em; line-height: 1.6; }} img {{ max-width: 100%; height: auto; }} table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }} th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }} th {{ background: #f5f6fa; }}</style></head><body>{md_html}</body></html>"""
with open(OUTPUT / "MISSION_REPORT.html", "w") as f: f.write(html_doc)

print("\n  ✅  ALL STEPS COMPLETE")