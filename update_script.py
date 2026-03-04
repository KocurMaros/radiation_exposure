import sys

with open('/home/frajer/Projects/radiation_exposure/analyze_radiation_exposure.py', 'r') as f:
    text = f.read()

# Make it support argparse
header = """import os
import re
import warnings
import argparse
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from datetime import datetime, timedelta
from scipy import stats

parser = argparse.ArgumentParser()
parser.add_argument('--lang', choices=['en', 'sk'], default='en', help='Language for output (en or sk)')
args = parser.parse_args()
LANG = args.lang

def _t(en_text, sk_text):
    return sk_text if LANG == 'sk' else en_text
"""
text = text.split("import os")[0] + header + text.split("from scipy import stats\n")[1]

# Define manual string replacements
# Use triple-quoted constants where there was a newline
replacements = [
    (
        "fig.suptitle('Sensor Drift During Radiation Exposure\\n(Deviation from initial readings — stationary drone)', \n             fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Sensor Drift During Radiation Exposure\\n(Deviation from initial readings — stationary drone)', 'Posun senzorov počas vystavenia radiácii\\n(Odchýlka od počiatočných hodnôt — stacionárny dron)'), fontsize=14, fontweight='bold')"
    ),
    ("'Accel Drift (mg)'", "_t('Accel Drift (mg)', 'Posun akcelerometra (mg)')"),
    ("'Accelerometer Magnitude Drift'", "_t('Accelerometer Magnitude Drift', 'Posun magnitúdy akcelerometra')"),
    ("'Gyro Drift (mrad/s)'", "_t('Gyro Drift (mrad/s)', 'Posun gyroskopu (mrad/s)')"),
    ("'Gyroscope Magnitude Drift'", "_t('Gyroscope Magnitude Drift', 'Posun magnitúdy gyroskopu')"),
    ("'Mag Drift (mGauss)'", "_t('Mag Drift (mGauss)', 'Posun magnetometra (mGauss)')"),
    ("'Magnetometer Magnitude Drift'", "_t('Magnetometer Magnitude Drift', 'Posun magnitúdy magnetometra')"),
    ("'Time (UTC)'", "_t('Time (UTC)', 'Čas (UTC)')"),
    
    (
        "label=f'{session} exposure'",
        "label=f\"{session} {_t('exposure', 'expozícia')}\""
    ),
    (
        "label=f'{session} {\"(exposure)\" if is_exp else \"(post)\"}'",
        "label=f\"{session} {'(expozícia)' if (LANG=='sk' and is_exp) else ('(po expozícii)' if LANG=='sk' and not is_exp else ('(exposure)' if is_exp else '(post)'))}\""
    ),

    ("'IMU Temperature (°C)'", "_t('IMU Temperature (°C)', 'Teplota IMU (°C)')"),
    ("'Barometric Relative Altitude (m)'", "_t('Barometric Relative Altitude (m)', 'Barometrická relatívna výška (m)')"),
    (
        "ax.set_title('Barometric Altitude Drift vs IMU Temperature\\n(Stationary drone — altitude should be constant)',\n            fontsize=13, fontweight='bold')",
        "ax.set_title(_t('Barometric Altitude Drift vs IMU Temperature\\n(Stationary drone — altitude should be constant)', 'Posun barometrickej výšky vs Teplota IMU\\n(Stacionárny dron — výška by mala byť konštantná)'), fontsize=13, fontweight='bold')"
    ),
    (
        "f'Trend (R²={r**2:.3f})'",
        "f\"{_t('Trend', 'Trend')} (R²={r**2:.3f})\""
    ),

    (
        "fig.suptitle('EKF Navigation Filter Health During Radiation Exposure\\n(Higher variance = degraded estimation quality)',\n            fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('EKF Navigation Filter Health During Radiation Exposure\\n(Higher variance = degraded estimation quality)', 'Stav navigačného filtra EKF počas vystavenia radiácii\\n(Vyššia variancia = zhoršená kvalita odhadu)'), fontsize=14, fontweight='bold')"
    ),
    (
        "ekf_labels = ['Compass Variance', 'Horizontal Position Variance', \n              'Vertical Position Variance', 'Velocity Variance']",
        "ekf_labels = [_t('Compass Variance', 'Variancia kompasu'), _t('Horizontal Position Variance', 'Variancia horiz. pozície'), _t('Vertical Position Variance', 'Variancia vertikálnej pozície'), _t('Velocity Variance', 'Variancia rýchlosti')]"
    ),
    ("'Variance'", "_t('Variance', 'Variancia')"),

    ("'X Accel (mg)'", "_t('X Accel (mg)', 'Zrýchlenie X (mg)')"),
    ("'Y Accel (mg)'", "_t('Y Accel (mg)', 'Zrýchlenie Y (mg)')"),
    ("'Z Accel (mg)'", "_t('Z Accel (mg)', 'Zrýchlenie Z (mg)')"),
    (
        "ax.set_title('3D Accelerometer State Space During Radiation Exposure\\n(Color = elapsed time in session)',\n            fontsize=13, fontweight='bold')",
        "ax.set_title(_t('3D Accelerometer State Space During Radiation Exposure\\n(Color = elapsed time in session)', '3D stavový priestor akcelerometra počas vystavenia radiácii\\n(Farba = uplynutý čas v sekcii)'), fontsize=13, fontweight='bold')"
    ),
    ("'Elapsed Time (min)'", "_t('Elapsed Time (min)', 'Uplynutý čas (min)')"),

    (
        "fig.suptitle('Cumulative Radiation Exposure Effects on Hardware\\n(Across all 3 exposure sessions)',\n            fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Cumulative Radiation Exposure Effects on Hardware\\n(Across all 3 exposure sessions)', 'Kumulatívne účinky radiácie na hardvér\\n(Naprieč všetkými 3 sekciami expozície)'), fontsize=14, fontweight='bold')"
    ),
    ("'Baro Temp (°C)'", "_t('Baro Temp (°C)', 'Teplota baro (°C)')"),
    ("'Barometric Sensor Temperature'", "_t('Barometric Sensor Temperature', 'Teplota barometrického senzora')"),
    ("'Vibration (m/s²)'", "_t('Vibration (m/s²)', 'Vibrácie (m/s²)')"),
    ("'Total Vibration Level'", "_t('Total Vibration Level', 'Celková úroveň vibrácií')"),
    ("'Compass Var.'", "_t('Compass Var.', 'Variancia kompasu')"),
    ("'Compass Variance (Navigation Degradation)'", "_t('Compass Variance (Navigation Degradation)', 'Variancia kompasu (Zhoršenie navigácie)')"),

    (
        "fig.suptitle('Telemetry Overview — All Sessions\\n(Red-shaded = exposure sessions, White = post-exposure)',\n            fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Telemetry Overview — All Sessions\\n(Red-shaded = exposure sessions, White = post-exposure)', 'Prehľad telemetrie — Všetky sekcie\\n(Červená = expozícia, Biela = po expozícii)'), fontsize=14, fontweight='bold')"
    ),
    ("'Voltage (V)'", "_t('Voltage (V)', 'Napätie (V)')"),
    ("'Board Voltage (Vcc)'", "_t('Board Voltage (Vcc)', 'Napätie dosky (Vcc)')"),
    ("'Temp (°C)'", "_t('Temp (°C)', 'Teplota (°C)')"),
    ("'Pressure (hPa)'", "_t('Pressure (hPa)', 'Tlak (hPa)')"),
    ("'Barometric Pressure'", "_t('Barometric Pressure', 'Barometrický tlak')"),
    ("'Rel. Alt (m)'", "_t('Rel. Alt (m)', 'Rel. výška (m)')"),
    ("'Barometric Relative Altitude (drift from home)'", "_t('Barometric Relative Altitude (drift from home)', 'Barometrická relatívna výška (odchýlka od domova)')"),

    (
        "fig.suptitle('Distribution of Vibration Readings — Exposure vs Post-Exposure',\n            fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Distribution of Vibration Readings — Exposure vs Post-Exposure', 'Distribúcia údajov o vibráciách — Expozícia vs Po expozícii'), fontsize=14, fontweight='bold')"
    ),
    ("'During Exposure'", "_t('During Exposure', 'Počas expozície')"),
    ("f'Exp μ={mean_exp:.4f}'", "f\"{_t('Exp', 'Exp')} μ={mean_exp:.4f}\""),
    ("f'Exp μ+2σ={mean_exp+2*std_exp:.4f}'", "f\"{_t('Exp', 'Exp')} μ+2σ={mean_exp+2*std_exp:.4f}\""),
    ("'Post-Exposure'", "_t('Post-Exposure', 'Po expozícii')"),
    ("f'Post μ={mean_post:.4f}'", "f\"{_t('Post', 'Post')} μ={mean_post:.4f}\""),
    ("'Density'", "_t('Density', 'Hustota')"),

    (
        "fig.suptitle('Anomaly Detection — Readings Exceeding μ ± 2σ Highlighted in Red\\n(Based on exposure session statistics)',\n            fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Anomaly Detection — Readings Exceeding μ ± 2σ Highlighted in Red\\n(Based on exposure session statistics)', 'Detekcia anomálií — Hodnoty nad μ ± 2σ zvýraznené červenou\\n(Založené na štatistikách expozície)'), fontsize=14, fontweight='bold')"
    ),
    (
        "anomaly_labels = ['Total Vibration (m/s²)', 'Compass Variance', 'Relative Altitude (m)']",
        "anomaly_labels = [_t('Total Vibration (m/s²)', 'Celkové vibrácie (m/s²)'), _t('Compass Variance', 'Variancia kompasu'), _t('Relative Altitude (m)', 'Relatívna výška (m)')]"
    ),

    (
        "fig.suptitle('Jetson Xavier NX Health During Radiation Exposure',\n                fontsize=14, fontweight='bold')",
        "fig.suptitle(_t('Jetson Xavier NX Health During Radiation Exposure', 'Zdravie Jetson Xavier NX počas vystavenia radiácii'), fontsize=14, fontweight='bold')"
    ),
    ("'RAM Used (MB)'", "_t('RAM Used (MB)', 'Využitá RAM (MB)')"),
    ("'RAM Usage'", "_t('RAM Usage', 'Využitie RAM')"),
    ("'CPU Load (%)'", "_t('CPU Load (%)', 'Záťaž CPU (%)')"),
    ("'Average CPU Utilization'", "_t('Average CPU Utilization', 'Priemerné využitie CPU')"),
    ("'Temperature (°C)'", "_t('Temperature (°C)', 'Teplota (°C)')"),
    ("'CPU/GPU Temperature'", "_t('CPU/GPU Temperature', 'Teplota CPU/GPU')"),
    ("'Power (mW)'", "_t('Power (mW)', 'Príkon (mW)')"),
    ("'Total Board Power (VDD_IN)'", "_t('Total Board Power (VDD_IN)', 'Celkový príkon dosky (VDD_IN)')"),

    (
        "is_exp = \"EXPOSURE\" if session in EXPOSURE_SESSIONS else \"POST\"",
        "is_exp_key = 'EXPOSURE' if session in EXPOSURE_SESSIONS else 'POST'\n    is_exp = _t('EXPOSURE', 'EXPOZÍCIA') if is_exp_key == 'EXPOSURE' else _t('POST', 'PO-EXPOZÍCII')"
    ),
    
    (
        "\"| {session} | {is_exp} | {t_min.strftime('%H:%M:%S')} | {t_max.strftime('%H:%M:%S')} | {dur:.1f} min | {n:,} |\"",
        "| {session} | {is_exp} | {t_min.strftime('%H:%M:%S')} | {t_max.strftime('%H:%M:%S')} | {dur:.1f} min | {n:,} |\""
    )
]

for src, dst in replacements:
    if src not in text:
        print(f"Warning: Could not find '{src[:30]}...'")
    text = text.replace(src, dst)


markdown_report_en = "report = f\"\"\"# Drone Radiation Exposure Analysis Report"
markdown_report_sk = """if LANG == 'sk':
    report = f\"\"\"# Správa o analýze vystavenia dronu radiácii

**Vygenerované:** {now}  
**Celková doba expozície:** {total_exposure_min:.1f} minút | **Dátové body:** {total_datapoints:,}  
**Platforma:** Autopilot CubePilot + Jetson Xavier NX na stacionárnom drone  
**Dátum experimentu:** 2025-12-14/15  
**Sekcie expozície:** 1st, 2nd, 3rd | **Sekcie po expozícii:** 4th, 5th, 6th, 8th

---

## Inventár dát

### Telemetria MAVLink (z CubePilot cez Raspberry Pi logger)
- **Typy správ:** GLOBAL_POSITION_INT, SYS_STATUS, VFR_HUD, HEARTBEAT, VIBRATION, SCALED_IMU, EKF_STATUS_REPORT, HWSTATUS, SCALED_PRESSURE, POWER_STATUS, RAW_IMU + ďalšie
- **Vzorkovacia frekvencia:** ~10 Hz (100 ms intervaly)
- **GPS:** Bez fixu (vo vnútri ožarovacej miestnosti) — lat/lon = 0

### Logy Jetson Xavier NX
- **tegrastats:** 1 Hz monitorovanie (RAM, CPU, GPU, teploty, výkon)
- **dmesg:** Kontinuálny kernel log
- **mem_checksum:** Kontroly integrity pamäte (alokácia + SHA256)
- **journal:** systemd journal každých ~60s

### Časová os (UTC)
| Sekcia | Typ | Štart | Koniec | Trvanie | Dátové body |
|---------|------|-------|-----|----------|-------------|
{chr(10).join(session_summaries)}

### Kľúčové zistenia
- **Bez externého dozimetra** — experiment sleduje ÚČINKY radiácie na elektroniku
- **Stacionárny dron** — senzory by mali ukazovať konštantné hodnoty
- **Kontrolné súčty pamäte:** {memchk_total_checks} kontrol, **{memchk_total_errors} chýb**

---
## Špecifické zistenia a grafy

## 1. Posun senzorov počas vystavenia radiácii
![radiation_vs_time](radiation_vs_time.png)

## 2. Posun barometrickej výšky vs Teplota IMU
![radiation_vs_altitude](radiation_vs_altitude.png)

## 3. Stav navigačného filtra EKF
![flight_path_radiation](flight_path_radiation.png)

## 4. 3D stavový priestor akcelerometra
![radiation_3d](radiation_3d.png)

## 5. Kumulatívne účinky radiácie na hardvér
![cumulative_dose](cumulative_dose.png)

## 6. Prehľad telemetrie — Všetky sekcie
![telemetry_overview](telemetry_overview.png)

## 7. Distribúcia údajov o vibráciách
![radiation_histogram](radiation_histogram.png)

## 8. Detekcia anomálií — Štatistické odchýlky
![anomaly_flagged](anomaly_flagged.png)

## Dodatok: Zdravie Jetson Xavier NX
![jetson_health](jetson_health.png)

---
## Súhrn zistení

| Metrika | Počas expozície | Po expozícii | Stav |
|--------|----------------|---------------|------------|
| Napätie dosky (Vcc) | {vcc_exp.mean():.3f} ± {vcc_exp.std():.4f} V | {vcc_post.mean():.3f} ± {vcc_post.std():.4f} V | {"Stabilné ✓" if abs(vcc_exp.mean() - vcc_post.mean()) < 0.05 else "Zmenené ⚠"} |
| Kontrola pamäte | {memchk_total_errors} chýb / {memchk_total_checks} kontrol | N/A | {"Bez bit-flipov ✓" if memchk_total_errors == 0 else f"{memchk_total_errors} bit-flipov ⚠"} |
| Jetson Systém | Operatívny | Operatívny | Žiadne pády ✓ |
\"\"\"
else:
    report = f\"\"\"# Drone Radiation Exposure Analysis Report"""

text = text.replace("report = f\"\"\"# Drone Radiation Exposure Analysis Report", markdown_report_sk)

with open('/home/frajer/Projects/radiation_exposure/analyze_radiation_exposure.py', 'w') as f:
    f.write(text)

print("Done")
