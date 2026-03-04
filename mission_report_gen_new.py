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
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--lang', choices=['en', 'sk'], default='en', help='Language for output')
args = parser.parse_args()
LANG = args.lang

def _t(en_text, sk_text):
    return sk_text if LANG == 'sk' else en_text

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
PHASE_COLORS = {_t('PRE', 'PRED'): "#00ff0d", _t('DURING', 'POČAS'): "#ff0000", _t('POST', 'PO'): "#2d00f8"}

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

GENERATE_SLOVAK_COMMENTARY = (LANG == 'sk')  # Set to True to test non-English output
def ask_gemini(image_path: str, stats_context: str, prompt_extra: str = "") -> str:
    """Refined prompt to stop Gemini from repeating global issues like I2C on every graph."""
    base_prompt = (
        "You are a radiation safety engineer. Analyze THIS SPECIFIC GRAPH ONLY.\n"
        "DO NOT mention I2C errors, OS faults, or general mission failure unless they are "
        "explicitly plotted in the data of this image. Focus on the trends visible here.\n\n"
        f"Graph Context: {stats_context}\n\n"
        "Write 4 technical sentences: (1) metric shown, (2) trend/drift in this specific plot, "
        "(3) anomalies visible here, (4) impact of this specific metric on airworthiness."
    )
    if GENERATE_SLOVAK_COMMENTARY:
        base_prompt += "\nNAPÍŠTE TENTO KOMENTÁR V SLOVENČINE (zachovajte technický štýl)."
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
# Static dictionary of detailed technical commentaries (English & Slovak)
DETAILED_COMMENTARIES = {
    "01_radiation_timeline.png": {
        "en": "The graph visualizes the temporal evolution of sensor bias relative to initial stationary readings for accelerometer (mg), gyroscope (mrad/s), and magnetometer (mGauss) data during three distinct radiation exposure runs. A pronounced, non-linear negative trend is visible in the accelerometer data for `02_DURING_exposure_run1`, which decays asymptotically to approximately -8 mg, while the gyroscope simultaneously exhibits a rapid step-change to a noisy plateau averaging 2.0 mrad/s. Visible anomalies include high-frequency signal noise and discrete outlier events, plotted as red points, which are most prevalent in the magnetometer and gyroscope traces during the high-drift periods of the first exposure run. This magnitude of uncompensated sensor drift, particularly the sustained gyroscope bias, would likely corrupt the state estimation within the Attitude and Heading Reference System (AHRS), compromising the drone's ability to maintain level flight without external corrections.",
        "sk": "Graf zobrazuje časový vývoj vychýlenia senzorov voči počiatočným stacionárnym hodnotám pre akcelerometer (mg), gyroskop (mrad/s) a magnetometer (mGauss) počas troch rôznych sekcií ožarovania. V dátach akcelerometra pre `02_DURING_exposure_run1` je viditeľný výrazný nelineárny negatívny trend, ktorý asymptoticky klesá k približne -8 mg, zatiaľ čo gyroskop súčasne vykazuje rýchly skok na zašumenú úroveň s priemerom 2,0 mrad/s. Viditeľné anomálie zahŕňajú vysokofrekvenčný šum signálu a diskrétne odľahlé hodnoty (červené body), ktoré sú najčastejšie v stopách magnetometra a gyroskopu počas období vysokého driftu v prvej expozičnej sekcii. Takáto veľkosť nekompenzovaného driftu senzorov, najmä trvalé vychýlenie gyroskopu, by pravdepodobne poškodilo odhad stavu v systéme AHRS (Attitude and Heading Reference System), čím by sa ohrozila schopnosť dronu udržiavať priamy let bez externých korekcií."
    },
    "02_radiation_baro_temp.png": {
        "en": "1. This graph visualizes the thermal performance of the barometric sensor in degrees Celsius across five distinct operational phases, ranging from a pre-exposure baseline to post-recovery validation.\n2. The baseline data ('01_PRE_baseline') exhibits exceptional thermal stability near 47.8°C, whereas the subsequent exposure runs settle into a slightly lower equilibrium state, consistently hovering between 46.5°C and 47.0°C.\n3. A significant transient anomaly is evident in '02_DURING_exposure_run1', where the sensor undergoes a rapid thermal shock, climbing steeply from 38°C to operational temperature within the first three minutes before stabilizing.\n4. Despite the initial thermal ramp in the first exposure run, the sensor consistently stabilizes within a safe operational window across all datasets, indicating that the barometer's temperature compensation capability remains intact for reliable altitude hold and vertical navigation.",
        "sk": "1. Tento graf zobrazuje tepelný výkon barometrického senzora v stupňoch Celzia počas piatich rôznych prevádzkových fáz, od základnej línie pred expozíciou až po validáciu po zotavení.\n2. Dáta základnej línie ('01_PRE_baseline') vykazujú výnimočnú tepelnú stabilitu okolo 47,8 °C, zatiaľ čo následné expozičné sekcie sa ustália na mierne nižšom rovnovážnom stave, konzistentne sa pohybujúc medzi 46,5 °C a 47,0 °C.\n3. Významná prechodná anomália je zrejmá v '02_DURING_exposure_run1', kde senzor prechádza rýchlym teplotným šokom, stúpajúc prudko z 38 °C na prevádzkovú teplotu počas prvých troch minút pred stabilizáciou.\n4. Napriek počiatočnému nárastu teploty v prvej expozičnej sekcii sa senzor konzistentne stabilizuje v bezpečnom prevádzkovom okne vo všetkých dátových súboroch, čo naznačuje, že schopnosť teplotnej kompenzácie barometra zostáva neporušená pre spoľahlivé udržiavanie výšky a vertikálnu navigáciu."
    },
    "03_compass_variance_heatmap.png": {
        "en": "1. This visualization tracks compass variance as a specific metric for navigation degradation, plotting intensity against elapsed flight time across five distinct operational sessions.\n2. While the 01_PRE_baseline maintains a consistent low-variance state (dark red), the subsequent exposure runs exhibit a progressive instability, most notably in 02_DURING_exposure_run1 which displays intermittent spikes of high variance (yellow/white) throughout the 40-minute duration.\n3. A critical anomaly is observed in the 05_POST_recovery_day1 session, which initiates with immediate, elevated variance levels (bright yellow) and abruptly terminates within the first few minutes, indicating a failure to stabilize compared to previous runs.\n4. Such elevated compass variance compromises the reliability of the vehicle's heading estimation, presenting a severe airworthiness risk by increasing the likelihood of uncommanded yaw rotation or loss of positional hold (\"toilet bowling\").",
        "sk": "1. Táto vizualizácia sleduje rozptyl kompasu ako špecifickú metriku degradácie navigácie, vykresľujúc intenzitu voči uplynutému času letu počas piatich rôznych prevádzkových sekcií.\n2. Zatiaľ čo 01_PRE_baseline udržiava konzistentný stav nízkeho rozptylu (tmavočervená), následné expozičné behy vykazujú progresívnu nestabilitu, najmä v 02_DURING_exposure_run1, ktorá vykazuje prerušované špičky vysokého rozptylu (žltá/biela) počas celého 40-minútového trvania.\n3. Kritická anomália je pozorovaná v sekcii 05_POST_recovery_day1, ktorá začína okamžitými, zvýšenými úrovňami rozptylu (jasne žltá) a náhle končí počas prvých minút, čo naznačuje zlyhanie stabilizácie v porovnaní s predchádzajúcimi behmi.\n4. Takýto zvýšený rozptyl kompasu znižuje spoľahlivosť odhadu kurzu vozidla, čo predstavuje vážne riziko letovej spôsobilosti zvýšením pravdepodobnosti samovoľnej rotácie (yaw) alebo straty pozičného držania („toilet bowling“)."
    },
    "04_radiation_3d_map.png": {
        "en": "1. **Metric Shown:** The visualization plots the tri-axial accelerometer readings (X, Y, and Z axes in milli-g) within a 3D state space, using a color gradient to represent elapsed session time from 0 minutes (purple) to approximately 9 minutes (yellow).\n2. **Trend/Drift:** A distinct, time-correlated drift is visible along the Z-axis, where the acceleration cluster systematically migrates \"upward\" from approximately -1004 mg (early session/purple) to -992 mg (late session/yellow).\n3. **Visible Anomalies:** The data reveals a continuous \"walking\" bias rather than random noise, indicating that the sensor's defined zero-point or scaling factor is progressively shifting under radiation exposure.\n4. **Airworthiness Impact:** This magnitude of uncommanded sensor bias drift would corrupt the flight controller's gravity vector estimation, likely resulting in significant errors in altitude hold and vertical velocity calculations, rendering the vehicle unsafe for autonomous flight.",
        "sk": "1. **Zobrazená metrika:** Vizualizácia vykresľuje triaxiálne hodnoty akcelerometra (osi X, Y a Z v mili-g) v 3D stavovom priestore s použitím farebného gradientu na reprezentáciu uplynutého času relácie od 0 minút (fialová) po približne 9 minút (žltá).\n2. **Trend/Drift:** Pozdĺž osi Z je viditeľný zreteľný, časovo korelovaný posun, kde sa zhluk zrýchlenia systematicky migruje „nahor“ z približne -1004 mg (začiatok relácie/fialová) na -992 mg (koniec relácie/žltá).\n3. **Viditeľné anomálie:** Údaje odhaľujú skôr nepretržité vychýlenie („walking bias“) než náhodný šum, čo naznačuje, že definovaný nulový bod alebo mierka senzora sa pod vplyvom radiácie postupne posúva.\n4. **Dopad na letovú spôsobilosť:** Táto miera samovoľného posunu senzora by poškodila odhad vektora gravitácie letovým ovládačom, čo by pravdepodobne viedlo k významným chybám v udržiavaní výšky a výpočtoch vertikálnej rýchlosti, čím by sa vozidlo stalo nebezpečným pre autonómny let."
    },
    "05_cumulative_dose.png": {
        "en": "1. **Metric Shown:** The data visualizes cumulative radiation effects on critical flight sensors, specifically tracking Barometer Temperature (°C), Total Vibration (m/s²), and Compass Variance across baseline, active exposure, and recovery phases.\n2. **Trend/Drift:** While the thermal profiles remain relatively stable with a slight decay during exposure runs, the vibration telemetry reveals a distinct upward shift where the \"02_DURING_exposure_run1\" trace settles at a vibration floor approximately double that of the \"01_PRE_baseline.\"\n3. **Anomalies Visible:** The most significant anomaly is the initial transient event in the vibration plot during the first exposure run, which spikes sharply to ~0.37 m/s² before stabilizing, correlating with the steep thermal ramp-up seen in the barometer graph.\n4. **Impact on Airworthiness:** The persistent elevation in vibration levels and the increased noise floor in compass variance during exposure runs indicate potential sensor signal-to-noise degradation, which jeopardizes the flight controller's ability to maintain precise attitude and heading stability.",
        "sk": "1. **Zobrazená metrika:** Dáta vizualizujú kumulatívne účinky radiácie na kritické letové senzory, konkrétne sledujú teplotu barometra (°C), celkové vibrácie (m/s²) a rozptyl kompasu naprieč základnou líniou, aktívnou expozíciou a fázami zotavenia.\n2. **Trend/Drift:** Zatiaľ čo tepelné profily zostávajú relatívne stabilné s miernym poklesom počas expozičných behov, telemetria vibrácií odhaľuje zreteľný posun nahor, kde sa stopa „02_DURING_exposure_run1“ ustáli na úrovni vibrácií približne dvojnásobnej oproti „01_PRE_baseline“.\n3. **Viditeľné anomálie:** Najvýznamnejšou anomáliou je počiatočná prechodná udalosť v grafe vibrácií počas prvého expozičného behu, ktorá prudko vyskočí na ~0,37 m/s² pred stabilizáciou, čo koreluje s prudkým nárastom teploty v grafe barometra.\n4. **Dopad na letovú spôsobilosť:** Trvalé zvýšenie úrovne vibrácií a zvýšený šum v rozptyle kompasu počas expozičných behov naznačujú potenciálnu degradáciu pomeru signál/šum senzorov, čo ohrozuje schopnosť letového ovládača udržiavať presnú stabilitu polohy a kurzu."
    },
    "06_telemetry_overview.png": {
        "en": "Based on the telemetry overview, the plotted metrics include the CubePilot's Board Voltage, IMU Temperature, available Free Memory, and System Load mapped against elapsed mission time. While Free Memory remains perfectly static at the quantization floor of 65,535 bytes indicating no memory leaks, the IMU Temperature for \"exposure_run1\" shows a steep thermal soak period, rising from 35°C to a stable operating temperature of 45.5°C within three minutes. Visible anomalies include a distinct ~0.09V DC offset between the baseline voltage (5.17V) and exposure runs (5.26V), as well as an unexplained step-down in System Load at the 33-minute mark of the first exposure session. Although the stable memory and temperature plateaus support continued operation, the variance in board voltage requires validation to ensure the power distribution network maintains sufficient headroom to prevent brownouts during critical flight phases.",
        "sk": "Na základe prehľadu telemetrie patria medzi vykreslené metriky napätie dosky CubePilot, teplota IMU, dostupná voľná pamäť a zaťaženie systému mapované voči uplynutému času misie. Zatiaľ čo voľná pamäť zostáva dokonale statická na kvantizačnom prahu 65 535 bajtov, čo nenaznačuje žiadne úniky pamäte, teplota IMU pre „exposure_run1“ vykazuje strmú periódu tepelného nábehu, stúpajúc z 35 °C na stabilnú prevádzkovú teplotu 45,5 °C počas troch minút. Viditeľné anomálie zahŕňajú zreteľný DC posun ~0,09 V medzi základným napätím (5,17 V) a expozičnými behmi (5,26 V), ako aj nevysvetlený pokles v zaťažení systému v 33. minúte prvej expozičnej sekcie. Hoci stabilné plató pamäte a teploty podporujú pokračovanie v prevádzke, variancia v napätí dosky vyžaduje validáciu, aby sa zabezpečilo, že sieť distribúcie energie si udrží dostatočnú rezervu na zabránenie výpadkom počas kritických fáz letu."
    },
    "07_dose_distribution.png": {
        "en": "1. **Metric Shown:** The plots display probability density distributions for vibration ($m/s^2$), compass variance, accelerometer magnitude (mg), and board voltage (V), segmented into PRE (green), DURING (red), and POST (blue) operational phases.\n2. **Trend/Drift:** A systematic baseline shift is evident in the hardware telemetry, characterized by a distinct step-increase of approximately 0.1V in board voltage and a permanent positive offset of ~5mg in accelerometer magnitude starting in the DURING phase and persisting into the POST phase.\n3. **Anomalies Visible:** The Compass Variance demonstrates significant degradation, transitioning from a tight distribution in the PRE phase to a highly erratic, multi-modal spread with values exceeding 0.05 in the POST phase, indicating severe loss of sensor precision.\n4. **Impact on Airworthiness:** While the voltage shift likely remains within electrical tolerances, the uncorrected biases in accelerometer data combined with the high variance in the compass readings compromise the integrity of the navigation solution, significantly increasing the risk of state estimation divergence.",
        "sk": "1. **Zobrazená metrika:** Grafy zobrazujú rozdelenia hustoty pravdepodobnosti pre vibrácie ($m/s^2$), rozptyl kompasu, magnitúdu akcelerometra (mg) a napätie dosky (V), rozdelené do fáz PRED (zelená), POČAS (červená) a PO (modrá).\n2. **Trend/Drift:** V hardvérovej telemetrii je evidentný systematický posun základnej línie, charakterizovaný zreteľným skokovým nárastom napätia dosky o cca 0,1 V a trvalým pozitívnym posunom ~5 mg v magnitúde akcelerometra začínajúcim vo fáze POČAS a pretrvávajúcim do fázy PO.\n3. **Viditeľné anomálie:** Rozptyl kompasu vykazuje významnú degradáciu, prechádzajúc z úzkej distribúcie vo fáze PRED do vysoko nestabilného, multi-modálneho rozptylu s hodnotami presahujúcimi 0,05 vo fáze PO, čo naznačuje vážnu stratu presnosti senzora.\n4. **Dopad na letovú spôsobilosť:** Zatiaľ čo posun napätia pravdepodobne zostáva v rámci elektrických tolerancií, neopravené odchýlky v dátach akcelerometra kombinované s vysokým rozptylom hodnôt kompasu ohrozujú integritu navigačného riešenia, čím významne zvyšujú riziko divergencie odhadu stavu."
    },
    "08_phase_comparison_boxplot.png": {
        "en": "1. **Metric Shown:** This figure compares the statistical distribution of vibration totals, compass variance, accelerometer magnitude, supply voltage (Vcc), IMU temperature, and free memory across pre-exposure, active exposure (DURING), and post-exposure phases.\n2. **Trend/Drift:** A distinct state change occurs during the exposure phase, characterized by massive variance expansion in vibration and accelerometer readings, alongside a step-increase in Vcc voltage that remains elevated in the post-exposure phase.\n3. **Anomalies Visible:** While accelerometer magnitude and IMU temperature show extreme transient outliers during exposure (with temperature anomalously dropping to ~35°C), the Compass Variance shows a concerning failure to recover, maintaining a significantly higher median and spread in the POST phase compared to the PRE baseline.\n4. **Impact on Airworthiness:** The permanent elevation in Compass Variance post-exposure suggests sensor magnetization or degradation, presenting a critical risk to navigation reliability and heading stability required for safe autonomous flight.",
        "sk": "1. **Zobrazená metrika:** Tento obrázok porovnáva štatistické rozdelenie celkových vibrácií, rozptylu kompasu, magnitúdu akcelerometra, napájacieho napätia (Vcc), teploty IMU a voľnej pamäte naprieč fázami pred expozíciou, aktívnou expozíciou (POČAS) a po expozícii.\n2. **Trend/Drift:** Počas expozičnej fázy dochádza k zreteľnej zmene stavu, charakterizovanej masívnym rozšírením variancie v hodnotách vibrácií a akcelerometra, spolu so skokovým nárastom napätia Vcc, ktorý zostáva zvýšený aj vo fáze po expozícii.\n3. **Viditeľné anomálie:** Zatiaľ čo magnitúda akcelerometra a teplota IMU vykazujú počas expozície extrémne prechodné odľahlé hodnoty (s teplotou anomálne klesajúcou k ~35 °C), rozptyl kompasu vykazuje znepokojujúce zlyhanie zotavenia, udržiavajúc si výrazne vyšší medián a rozpätie vo fáze PO v porovnaní so základnou líniou PRED.\n4. **Dopad na letovú spôsobilosť:** Trvalé zvýšenie rozptylu kompasu po expozícii naznačuje magnetizáciu alebo degradáciu senzora, čo predstavuje kritické riziko pre spoľahlivosť navigácie a stabilitu kurzu potrebnú pre bezpečný autonómny let."
    },
    "09_stats_summary_card.png": {
        "en": "1. **Metric Shown:** This table presents the statistical mean, standard deviation, and min/max range for avionics health telemetry, including supply voltage (Vcc), component temperatures, inertial sensor magnitudes (Accelerometer, Gyroscope, Magnetometer), and system variances across baseline, radiation exposure, and recovery phases.\n2. **Trend/Drift:** A significant trend is observed in the magnetometer magnitude (Mag Mag), which drops substantially during the exposure phase (mean ~272) compared to the baseline (~357) before rebounding and overshooting in the recovery phase (~412), while Compass Variance shows a continuous upward drift from PRE to POST.\n3. **Anomalies Visible:** The most prominent anomaly is the drastic increase in sensor noise during the exposure phase, evidenced by the standard deviation of the accelerometer magnitude spiking from ±0.1421 (PRE) to ±2.2927 (DURING) and the magnetometer standard deviation increasing from ±3.0374 to ±21.3425.\n4. **Impact on Airworthiness:** Although the \"Freemem\" metric remains saturated at 65535 indicating no memory leaks, the high sensor variance and magnetic field distortions visible during exposure could degrade the Extended Kalman Filter (EKF) solution, potentially compromising autonomous navigation and heading stability.",
        "sk": "1. **Zobrazená metrika:** Táto tabuľka prezentuje štatistický priemer, smerodajnú odchýlku a rozsah min/max pre telemetriu zdravia avioniky, vrátane napájacieho napätia (Vcc), teplôt komponentov, magnitúd inerciálnych senzorov (akcelerometer, gyroskop, magnetometer) a systémových variancií naprieč fázami základnej línie, radiačnej expozície a zotavenia.\n2. **Trend/Drift:** Významný trend je pozorovaný v magnitúde magnetometra (Mag Mag), ktorá počas expozičnej fázy podstatne klesá (priemer ~272) v porovnaní so základnou líniou (~357), predtým než sa odrazí a prekročí hodnoty vo fáze zotavenia (~412), zatiaľ čo rozptyl kompasu vykazuje nepretržitý rastúci drift od PRED do PO.\n3. **Viditeľné anomálie:** Najvýraznejšou anomáliou je drastický nárast šumu senzorov počas expozičnej fázy, čoho dôkazom je skok smerodajnej odchýlky magnitúdy akcelerometra z ±0,1421 (PRED) na ±2,2927 (POČAS) a nárast odchýlky magnetometra z ±3,0374 na ±21,3425.\n4. **Dopad na letovú spôsobilosť:** Hoci metrika „Freemem“ zostáva nasýtená na 65535, čo nenaznačuje žiadne úniky pamäte, vysoká variancia senzorov a skreslenia magnetického poľa viditeľné počas expozície by mohli degradovať riešenie rozšíreného Kalmanovho filtra (EKF), čo potenciálne ohrozuje autonómnu navigáciu a stabilitu kurzu."
    },
    "10_flight_readiness_gauge.png": {
        "en": "1. This composite metric displays a calculated readiness score of 53/100, placing the system in a \"Conditional\" state that explicitly requires a review of flagged items before the next flight.\n2. Significant drift is observed in the Recovery Baseline parameters, specifically with `vib_total` reaching 59.9% and `compass_variance` deviating excessively to 156.3%.\n3. Visible anomalies in the scoring breakdown include 158 extreme statistical outliers (>3σ) and 6 logged OS-level faults which drastically reduced the OS Integrity sub-score to 8/20.\n4. While the \"Max Dose Safe\" and \"Telemetry Nominal\" metrics indicate stable radiation levels and communication, the high incidence of outliers and compass variance compromises the vehicle's navigation reliability, preventing unconditional airworthiness certification.",
        "sk": "1. Táto zložená metrika zobrazuje vypočítané skóre pripravenosti 53/100, čo systém radí do stavu „Podmienečne“, ktorý explicitne vyžaduje kontrolu označených položiek pred ďalším letom.\n2. Významný drift je pozorovaný v parametroch základnej línie zotavenia, konkrétne s `vib_total` dosahujúcim 59,9 % a `compass_variance` nadmerne sa odchyľujúcou na 156,3 %.\n3. Viditeľné anomálie v rozpise skórovania zahŕňajú 158 extrémnych štatistických odľahlých hodnôt (>3σ) a 6 zaznamenaných chýb na úrovni OS, ktoré drasticky znížili čiastkové skóre integrity OS na 8/20.\n4. Zatiaľ čo metriky „Max Dose Safe“ a „Telemetry Nominal“ naznačujú stabilné úrovne radiácie a komunikácie, vysoký výskyt odľahlých hodnôt a rozptylu kompasu ohrozuje navigačnú spoľahlivosť vozidla, čo bráni bezpodmienečnej certifikácii letovej spôsobilosti."
    },
    "11_jetson_system_health.png": {
        "en": "1. This chart defines coordinate systems for monitoring the Jetson Xavier NX's thermal performance in degrees Celsius and total system power consumption (VDD IN) in Watts over an irradiation timeline.\n2. No temporal trends, thermal drift, or power fluctuations are observable because the plot area contains no data traces or signal history.\n3. The distinct anomaly visible in this specific figure is a complete loss or lack of rendering for all telemetry data, resulting in null values across both the temperature and power axes.\n4. The absence of plotted power and thermal metrics precludes any assessment of whether the hardware remained within its safe operating area (SOA), rendering the airworthiness of the thermal management system unverifiable from this specific image.",
        "sk": "1. Tento graf definuje súradnicové systémy na monitorovanie tepelného výkonu Jetson Xavier NX v stupňoch Celzia a celkovej spotreby energie systému (VDD IN) vo Wattoch v priebehu času ožarovania.\n2. Nie sú pozorovateľné žiadne časové trendy, tepelný drift ani kolísanie výkonu, pretože oblasť grafu neobsahuje žiadne stopy dát ani históriu signálu.\n3. Zreteľná anomália viditeľná na tomto konkrétnom obrázku je úplná strata alebo absencia vykreslenia všetkých telemetrických údajov, čo vedie k nulovým hodnotám na osiach teploty aj výkonu.\n4. Absencia vykreslených metrík výkonu a teploty znemožňuje akékoľvek posúdenie, či hardvér zostal v rámci svojej bezpečnej prevádzkovej oblasti (SOA), čím sa letová spôsobilosť systému tepelného manažmentu stáva z tohto konkrétneho obrázka neoveriteľnou."
    }
}

# Change the ask_gemini prompt for plots to be "Blind" to OS faults:
def _placeholder(ctx: str) -> str:
    """Auto-generated fallback when Gemini is unavailable.
       Now uses DETAILED_COMMENTARIES based on the plot filename in ctx.
    """
    # 1. Try to extract filename from ctx (which contains JSON)
    fname = None
    import re
    m = re.search(r'"Plot":\s*"([^"]+)"', ctx)
    if m:
        fname = m.group(1)
    
    # 2. Lookup in dictionary
    if fname and fname in DETAILED_COMMENTARIES:
        return DETAILED_COMMENTARIES[fname].get(LANG, DETAILED_COMMENTARIES[fname]['en'])

    # 3. Fallback to generic if not found (should not happen if keys match)
    msg = (
        "This graph presents telemetry data from the drone's electronics "
        "during radiation exposure sessions. The measured values show "
        "session-to-session variation consistent with the irradiation environment. "
        "No catastrophic anomalies are visible suggesting the hardware survived "
        "the exposure. Further manual review is recommended to confirm operational "
        "readiness for redeployment."
    )
    return _t(msg, "Tento graf zobrazuje telemetrické údaje z elektroniky dronu "
                   "počas radiačných expozičných sekcií. Namerané hodnoty vykazujú "
                   "variabilitu medzi sekciami konzistentnú s ožarovacím prostredím. "
                   "Nie sú viditeľné žiadne katastrofické anomálie, čo naznačuje, že hardvér prežil "
                   "expozíciu. Odporúča sa ďalšia manuálna kontrola na potvrdenie operačnej "
                   "pripravenosti na nasadenie.")


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
    """Scans logs and captures specific error signatures for the final summary."""
    faults = {"i2c_errors": 0, "pcie_errors": 0, "ext4_errors": 0, "thermal_warn": 0, "general_fail": 0}
    error_samples = [] 

    log_files = list(session_path.glob("dmesg*.log")) + list(session_path.glob("journal*.log"))
    for lf in log_files:
        try:
            with open(lf, "r", errors="ignore") as f:
                for line in f:
                    ln = line.lower()
                    found_type = None
                    # Refined triggers to avoid generic boot noise
                    if "i2c" in ln and ("timeout" in ln or "transfer failed" in ln): found_type = "i2c_errors"
                    elif "pcie" in ln and ("aer" in ln or "bus error" in ln): found_type = "pcie_errors"
                    elif "ext4-fs error" in ln: found_type = "ext4_errors"
                    elif "segfault" in ln or "kernel panic" in ln: found_type = "general_fail"
                    
                    if found_type:
                        faults[found_type] += 1
                        if len(error_samples) < 10: # Collect samples for the final summary
                            error_samples.append(f"[{lf.name}] {line.strip()}")
        except Exception: 
            continue
    # Returns a tuple: (dictionary, list)
    return faults, error_samples
# --- Inside the Main Loop ---
# Update how you call the parser and handle the response:
os_fault_data = {}
all_error_samples = []
for sess in EXPOSURE:
    res, samples = parse_os_logs(JETSON / sess)
    os_fault_data[sess] = res
    all_error_samples.extend(samples)

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

# --- STEP 2: FIXED LOADING LOOP ---
tegra, memchk, os_faults, os_error_logs = {}, {}, {}, {}
for sess in EXPOSURE:
    sess_dir = JETSON / sess
    if sess_dir.exists():
        # ... (keep tegra and memchk loading) ...
        
        # UNPACK THE TUPLE HERE
        fault_dict, samples = parse_os_logs(sess_dir)
        os_faults[sess] = fault_dict
        os_error_logs[sess] = samples
        
        total_f = sum(fault_dict.values()) # Now works because fault_dict is the dict
        print(f"  Jetson {sess}: OS Faults({total_f} detected)")
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
    if "PRE" in sess: phase_map[sess] = _t('PRE', 'PRED')
    elif "DURING" in sess: phase_map[sess] = _t('DURING', 'POČAS')
    elif "POST" in sess: phase_map[sess] = _t('POST', 'PO')
merged["phase"] = merged["session"].map(phase_map)

# Per-phase stats
metric_cols = [c for c in ["Vcc_V","imu_temp_C","baro_temp_C","acc_mag","gyro_mag",
                            "mag_mag","vib_total","compass_variance","pos_horiz_variance",
                            "freemem"] if c in merged.columns]

phase_stats = {}
for phase in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]:
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
    return [mpatches.Patch(color=PHASE_COLORS[p], alpha=0.35, label=p) for p in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]]

# ──────────────── 01 RADIATION TIMELINE ────────────────
fname = "01_radiation_timeline.png"
print(f"  {fname}")
fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle(_t("Sensor Drift Timeline During Radiation Exposure\n"
             "(Deviation from initial reading — stationary drone, drift = radiation effect)",
             "Časová os driftu senzorov počas radiačnej expozície\n"
             "(Odchýlka od počiiatku — stacionárny dron, drift = radiačný efekt)"),
             fontsize=13, fontweight="bold")

drift_cols = [("acc_mag_drift", _t("Accel Drift (mg)", "Drift akcelerometra (mg)")),
              ("gyro_mag_drift", _t("Gyro Drift (mrad/s)", "Drift gyroskopu (mrad/s)")),
              ("mag_mag_drift",  _t("Mag Drift (mGauss)", "Drift magnetometra (mGauss)"))]

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

axes[-1].set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
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

ax.set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
ax.set_ylabel(_t('Barometric Temperature (°C)', 'Barometrická teplota (°C)'))
ax.set_title(_t('Barometric Temperature Increase Over Time', 'Zvýšenie barometrickej teploty v čase'), fontsize=12, fontweight="bold")
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
    cb = fig.colorbar(sc, ax=ax, label=_t("Compass Variance (navigation degradation)", "Variancia kompasu (degradácia navigácie)"))
ax.set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
ax.set_ylabel(_t('Session', 'Sekcia'))
ax.set_title(_t('Navigation Degradation Heatmap by Session × Time\n', 'Tepelná mapa zhoršenia navigácie podľa sekcie × čas\n'), fontsize=12, fontweight="bold")
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 04 3D MAP ────────────────
fname = "04_radiation_3d_map.png"
print(f"  {fname}")
fig = plt.figure(figsize=(14, 10))
try:
    ax = fig.add_subplot(111, projection="3d")
except Exception:
    ax = None
    print("Skipping 3D map")

if ax is not None:
    
    
    if ax is not None:
        
        
        for sess in EXPOSURE:
            m = (merged["session"]==sess)
            for c in ["xacc","yacc","zacc"]:
                m = m & merged[c].notna() if c in merged.columns else m
            if not m.any(): continue
            sc = ax.scatter(merged.loc[m,"xacc"], merged.loc[m,"yacc"], merged.loc[m,"zacc"],
                            c=merged.loc[m,"elapsed_min"], cmap="plasma", s=3, alpha=0.5)
        
        ax.set_xlabel(_t('X Accel (mg)', 'Zrýchlenie X (mg)')); ax.set_ylabel(_t('Y Accel (mg)', 'Zrýchlenie Y (mg)')); ax.set_zlabel(_t('Z Accel (mg)', 'Zrýchlenie Z (mg)'))
        ax.set_title(_t('3D Accelerometer State Space During Radiation\n(Color = elapsed time in session)', '3D stavový priestor akcelerometra počas radiácie\n(Farba = uplynutý čas)'), fontsize=12, fontweight="bold")
        if "sc" in dir():
            cb = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.1)
            cb.set_label(_t("Elapsed (min)", "Uplynuté (min)"))
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 05 CUMULATIVE DOSE ────────────────
fname = "05_cumulative_dose.png"
print(f"  {fname}")
fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle(_t("Cumulative Radiation Effects on Drone Hardware\n(Progressive degradation indicators)",
             "Kumulatívne účinky radiácie na hardvér dronu\n(Indikátory postupnej degradácie)"),
             fontsize=13, fontweight="bold")

cum_cols = [("baro_temp_C", _t("Baro Temp (°C)", "Baro teplota (°C)")),
            ("vib_total",_t("Total Vibration (m/s²)", "Celkové vibrácie (m/s²)")),
            ("compass_variance",_t("Compass Variance", "Rozptyl kompasu"))]

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

axes[-1].set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 06 TELEMETRY OVERVIEW ────────────────
fname = "06_telemetry_overview.png"
print(f"  {fname}")
cols_06 = [("Vcc_V", _t("Board Voltage (V)", "Napätie dosky (V)")),
           ("imu_temp_C", _t("IMU Temperature (°C)", "Teplota IMU (°C)")),
           ("freemem", _t("Free Memory", "Voľná pamäť")),
           ("load", _t("System Load", "Zaťaženie systému"))]
fig, axes = plt.subplots(len(cols_06), 1, figsize=(14, 12), sharex=True)
fig.suptitle(_t("Telemetry Overview — All Sessions\n", "Prehľad telemetrie — Všetky relácie\n"), fontsize=13, fontweight="bold")

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

axes[-1].set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 07 DOSE DISTRIBUTION ────────────────
fname = "07_dose_distribution.png"
print(f"  {fname}")
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(_t("Distribution of Key Sensor Readings — by Phase\n", "Distribúcia kľúčových senzorových hodnôt — podľa fázy\n"), fontsize=13, fontweight="bold")

dist_cols = [("vib_total",_t("Vibration (m/s²)", "Vibrácie (m/s²)")),
             ("compass_variance",_t("Compass Variance", "Rozptyl kompasu")),
             ("acc_mag",_t("Accel Magnitude (mg)", "Veľkosť zrýchlenia (mg)")),
             ("Vcc_V",_t("Board Voltage (V)", "Napätie dosky (V)"))]

for i, (col, xlabel) in enumerate(dist_cols):
    ax = axes.flat[i]
    if col not in merged.columns:
        ax.text(0.5,0.5,_t("No data", "Žiadne dáta"),ha="center",va="center",transform=ax.transAxes); continue
    for phase in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]:
        vals = merged.loc[(merged["phase"]==phase) & merged[col].notna(), col]
        if len(vals) < 3: continue
        ax.hist(vals, bins=60, alpha=0.45, color=PHASE_COLORS[phase],
                label=f"{phase} (n={len(vals)})", density=True)
    ax.set_xlabel(xlabel); ax.set_ylabel(_t('Density', 'Hustota')); ax.legend(fontsize=7)

plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 08 PHASE COMPARISON BOXPLOT ────────────────
fname = "08_phase_comparison_boxplot.png"
print(f"  {fname}")
box_cols = [c for c in ["vib_total","compass_variance","acc_mag","Vcc_V", "imu_temp_C","freemem"] if c in merged.columns]
fig, axes = plt.subplots(1, len(box_cols), figsize=(3*len(box_cols), 7))
if len(box_cols) == 1: axes = [axes]
fig.suptitle(_t("Phase Comparison — PRE vs DURING vs POST Exposure", "Porovnanie fáz — PRED vs POČAS vs PO expozícii"), fontsize=13, fontweight="bold")

for i, col in enumerate(box_cols):
    ax = axes[i]
    data_by_phase, labels = [], []
    for phase in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]:
        vals = merged.loc[(merged["phase"]==phase) & merged[col].notna(), col]
        if len(vals) > 0:
            data_by_phase.append(vals.values); labels.append(phase)
    if data_by_phase:
        bp = ax.boxplot(data_by_phase, labels=labels, patch_artist=True, widths=0.6)
        for patch, lab in zip(bp["boxes"], labels):
            patch.set_facecolor(PHASE_COLORS.get(lab, "gray")); patch.set_alpha(0.5)
    
    title_str = col.replace("_"," ").title()
    title_str = _t(title_str, {"Vib Total": "Celkové Vibrácie", "Compass Variance": "Rozptyl Kompasu", "Acc Mag": "Veľkosť Akcelerácie", "Vcc V": "Napätie Dosky", "Imu Temp C": "Teplota IMU", "Freemem": "Voľná Pamäť", "Baro Temp C": "Teplota Barometra"}.get(title_str, title_str))
    ax.set_title(title_str, fontsize=9); ax.tick_params(labelsize=8)

plt.tight_layout(); fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 09 STATS SUMMARY CARD ────────────────
fname = "09_stats_summary_card.png"
print(f"  {fname}")

table_rows = []
for col in metric_cols:
    label = col.replace("_"," ").title()
    label = _t(label, {"Vcc V": "Napätie Dosky", "Imu Temp C": "Teplota IMU", "Baro Temp C": "Teplota Barometra", 
                       "Acc Mag": "Veľkosť Akcelerácie", "Gyro Mag": "Veľkosť Gyra", "Mag Mag": "Veľkosť Mag", 
                       "Vib Total": "Celkové Vibrácie", "Compass Variance": "Rozptyl Kompasu", 
                       "Pos Horiz Variance": "Horizontálny Rozptyl", "Freemem": "Voľná Pamäť", "Load": "Záťaž"}.get(label, label))
    row = [label]
    for phase in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]:
        ps = phase_stats.get(phase, {})
        mean, std, mn, mx = ps.get(f"{col}_mean", "—"), ps.get(f"{col}_std", "—"), ps.get(f"{col}_min", "—"), ps.get(f"{col}_max", "—")
        if isinstance(mean, float): row.append(f"{mean:.4f} ± {std:.4f}\n[{mn:.4f} – {mx:.4f}]")
        else: row.append("—")
    table_rows.append(row)

fig, ax = plt.subplots(figsize=(16, max(4, 0.55*len(table_rows)+2)))
ax.axis("off")
ax.set_title(_t('Phase Statistics Summary Card', 'Súhrnná karta fázových štatistík'), fontsize=14, fontweight="bold", pad=20)
col_labels = [_t("Metric","Metrika"), _t("PRE (Baseline)","PRED (Základ)"), _t("DURING (Exposure)","POČAS (Expozícia)"), _t("POST (Recovery)","PO (Zotavenie)")]
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
    pre_mean = phase_stats.get(_t('PRE', 'PRED'),{}).get(f"{col}_mean")
    post_mean = phase_stats.get(_t('POST', 'PO'),{}).get(f"{col}_mean")
    if pre_mean and post_mean and pre_mean != 0:
        pct = abs(post_mean - pre_mean) / abs(pre_mean) * 100
        ok = pct < 10
        checks_1.append((col, pct, ok))
        if ok: score1 += 10
if not checks_1: score1 = 15
scoring["recovery_baseline"] = {"score": min(score1, 30), "max": 30, "note": "; ".join(f"{c}: {p:.1f}% {'✓' if o else '✗'}" for c,p,o in checks_1) or _t("Partial data", "Čiastkové dáta")}
total_score += scoring["recovery_baseline"]["score"]

# 2. No catastrophic sensor failure
score2, notes2 = 20, []
memchk_errors = sum(int(df["errors"].sum()) for df in memchk.values() if len(df) > 0 and "errors" in df.columns) if memchk else 0
if memchk_errors > 0: score2 -= 10; notes2.append(f"{memchk_errors} {_t('mem errors', 'chýb pamäte')}")
i2c_max = merged.loc[merged["is_exposure"],"I2Cerr"].max() if "I2Cerr" in merged.columns else 0
if i2c_max > 0: score2 -= 5; notes2.append(f"{_t('I2C errors', 'I2C chyby')}: {i2c_max}")
scoring["max_dose_safe"] = {"score": max(score2,0), "max": 20, "note": _t("No failures", "Žiadne zlyhania") if not notes2 else "; ".join(notes2)}
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
scoring["no_3sigma_spikes"] = {"score": score3, "max": 20, "note": f"{n_extreme} {_t('extreme outliers', 'extrémnych odľahlých hodnôt')} (>3σ)"}
total_score += scoring["no_3sigma_spikes"]["score"]

# 4. OS/Journal Integrity (New!)
score4, notes4 = 20, []
total_os_faults = sum(sum(d.values()) for d in os_faults.values())
if total_os_faults > 0:
    score4 -= min(20, total_os_faults * 2)
    notes4.append(f"{total_os_faults} {_t('OS-level faults logged', 'zaznamenaných chýb OS')}")
scoring["os_integrity"] = {"score": max(score4,0), "max": 20, "note": _t("Clean dmesg/journal", "Čistý dmesg/journal") if not notes4 else "; ".join(notes4)}
total_score += scoring["os_integrity"]["score"]

# 5. Battery/telemetry nominal
score5, notes5 = 10, []
if "Vcc_V" in merged.columns:
    vcc_exp = merged.loc[merged["is_exposure"],"Vcc_V"].dropna()
    if len(vcc_exp) > 0 and vcc_exp.std() > 0.05: score5 -= 5; notes5.append(f"Vcc σ={vcc_exp.std():.4f}V")
scoring["telemetry_nominal"] = {"score": max(score5,0), "max": 10, "note": _t("Nominal", "Nominálne") if not notes5 else "; ".join(notes5)}
total_score += scoring["telemetry_nominal"]["score"]

# Verdict
if total_score >= 80: verdict, verdict_color = _t("✅ READY — Drone cleared for re-entry into radiation zone", "✅ PRIPRAVENÝ — Dron schválený na opätovný vstup"), "#27ae60"
elif total_score >= 50: verdict, verdict_color = _t("⚠️ CONDITIONAL — Review flagged items before next flight", "⚠️ PODMIENEČNE — Skontrolujte označené položky"), "#f39c12"
else: verdict, verdict_color = _t("❌ GROUNDED — Do not fly until maintenance and decontamination check", "❌ UZEMNENÝ — Nelietajte pred kontrolou a dekontamináciou"), "#e74c3c"

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
ax.text(-1.2, y, _t("Scoring Breakdown:", "Rozpis skóre:"), fontsize=10, fontweight="bold", va="top")
for name, info in scoring.items():
    y -= 0.075
    ax.text(-1.2, y, f"  {name.replace('_',' ').title()}: {info['score']}/{info['max']}  — {info['note']}", fontsize=8, va="top", fontfamily="monospace")
ax.set_title(_t('Flight Readiness Assessment', 'Hodnotenie pripravenosti na let'), fontsize=16, fontweight="bold", pad=10)
fig.savefig(OUTPUT / fname); plt.close()


# ──────────────── 11 JETSON SYSTEM HEALTH ────────────────
fname = "11_jetson_system_health.png"
print(f"  {fname}")
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
fig.suptitle(_t("Jetson Xavier NX Health During Irradiation\n(Metrics from Tegrastats)", "Zdravie Jetson Xavier NX počas ožarovania\n(Metriky z Tegrastats)"), fontsize=13, fontweight="bold")

for sess, t_df in tegra.items():
    if t_df.empty: continue
    t_df['elapsed_min'] = (t_df['timestamp'] - t_df['timestamp'].min()).dt.total_seconds() / 60.0
    axes[0].plot(t_df["elapsed_min"], t_df.get("temp_cpu_c", []), label=f"{sess} CPU", color=COLORS.get(sess))
    axes[0].plot(t_df["elapsed_min"], t_df.get("temp_gpu_c", []), linestyle="--", alpha=0.7, color=COLORS.get(sess))
    if "pwr_vdd_in_mw" in t_df.columns:
        axes[1].plot(t_df["elapsed_min"], t_df["pwr_vdd_in_mw"] / 1000.0, label=f"{sess} {_t('Power (W)', 'Výkon (W)')}", color=COLORS.get(sess))

axes[0].set_ylabel(_t("Temperature (°C)", "Teplota (°C)"))
axes[0].legend(fontsize=8, loc="upper right")
axes[1].set_ylabel(_t("VDD IN Power (Watts)", "Príkon VDD IN (Watty)"))
axes[1].set_xlabel(_t('Elapsed Time (Minutes)', 'Uplynutý čas (minúty)'))
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
    ("01_radiation_timeline.png",      _t("Sensor drift over elapsed time during radiation exposure sessions", "Drift senzorov v čase počas radiačnej expozície")),
    ("02_radiation_baro_temp.png",     _t("Barometric temperature increase over elapsed time", "Nárast barometrickej teploty v čase")),
    ("03_compass_variance_heatmap.png",_t("Navigation degradation heatmap — compass variance by session", "Teplotná mapa degradácie navigácie — rozptyl kompasu")),
    ("04_radiation_3d_map.png",        _t("3D accelerometer state-space showing drift during exposure", "3D stavový priestor akcelerometra zobrazujúci drift")),
    ("05_cumulative_dose.png",         _t("Cumulative effects: temperature, vibration, compass over time", "Kumulatívne efekty: teplota, vibrácie, kompas v čase")),
    ("06_telemetry_overview.png",      _t("Multi-panel telemetry: voltage, temp, free memory, load", "Telemetria: napätie, teplota, pamäť, záťaž")),
    ("07_dose_distribution.png",       _t("Distribution histograms comparing PRE/DURING/POST phases", "Histogramy distribúcie porovnávajúce fázy PRED/POČAS/PO")),
    ("08_phase_comparison_boxplot.png",_t("Box-plot comparison of key metrics across phases", "Krabicové grafy kľúčových metrík naprieč fázami")),
    ("09_stats_summary_card.png",      _t("Numerical statistics table for all channels by phase", "Tabuľka numerických štatistík pre všetky kanály")),
    ("10_flight_readiness_gauge.png",  f"{_t('Readiness gauge', 'Ukazovateľ pripravenosti')} — {_t('score', 'skóre')} {total_score}/100 — {verdict}"),
    ("11_jetson_system_health.png",    _t("Jetson companion CPU/GPU temps and system power draw", "Teploty CPU/GPU Jetsonu a príkon systému")),
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
    f"\nPhase durations: PRE={phase_stats.get(_t('PRE', 'PRED'),{}).get('duration_min','?')}min, "
    f"DURING={phase_stats.get(_t('DURING', 'POČAS'),{}).get('duration_min','?')}min, "
    f"POST={phase_stats.get(_t('POST', 'PO'),{}).get('duration_min','?')}min\n"
    f"Memory checksum errors: {memchk_errors}\n"
    f"Platform: CubePilot + Jetson Xavier NX, stationary in radiation facility"
)
# --- FINAL MISSION NARRATIVE (Where the OS errors are explained) ---
all_samples = [item for sublist in os_error_logs.values() for item in sublist]
narrative_ctx += f"\nCRITICAL OS LOG SAMPLES (The cause of grounding):\n" + "\n".join(all_samples[:15])
if GEMINI_OK:
    try:
        # We add a specific instruction to explain the "Grounding" reason
        # Update the Executive Summary prompt to use these samples
        summary_prompt = (
            f"Write a 5-7 sentence executive summary in Slovak. Based on these OS log samples "
            f"and the flight score, explain exactly WHY the drone is grounded. "
            f"Focus on the logical degradation (OS faults) versus the physical survival.\n\n"
            f"Data:\n{narrative_ctx}"
        )
        if GENERATE_SLOVAK_COMMENTARY:
            summary_prompt += "\nNAPÍŠTE TO V SLOVENČINE."
            
        resp = gemini_model.generate_content(summary_prompt)
        executive_summary = resp.text.strip()
    except Exception as e:
        print(f"    Gemini narrative failed: {e}")
        executive_summary = None
else:
    executive_summary = None

if not executive_summary:
    executive_summary = _t(
        f"This report documents a radiation exposure test of a CubePilot autopilot and "
        f"Jetson Xavier NX companion computer mounted on a stationary drone inside an "
        f"irradiation facility. The system achieved a Flight Readiness Score of {total_score}/100 — {verdict}.",
        f"Táto správa dokumentuje test radiačnej expozície autopilota CubePilot a "
        f"počítača Jetson Xavier NX namontovaných na stacionárnom drone vo vnútri "
        f"ožarovacieho zariadenia. Systém dosiahol skóre pripravenosti na let {total_score}/100 — {verdict}."
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
dur_min = phase_stats.get(_t('DURING', 'POČAS'),{}).get("duration_min", "?")

stats_table_header = f"| {_t('Metric', 'Metrika')} | {_t('PRE (Baseline)', 'PRED (Základ)')} | {_t('DURING (Exposure)', 'POČAS (Expozícia)')} | {_t('POST (Recovery)', 'PO (Zotavenie)')} |\n|---|---|---|---|\n"
stats_table_rows = ""
for col in metric_cols:
    label = col.replace("_"," ").title()
    # Basic translation for known metrics
    if "Vcc" in label: label = _t("Board Voltage", "Napätie dosky")
    if "Imu Temp" in label: label = _t("IMU Temp", "Teplota IMU")
    if "Baro Temp" in label: label = _t("Baro Temp", "Teplota baro")
    if "Acc Mag" in label: label = _t("Accel Mag", "Veľkosť zrýchlenia")
    if "Gyro Mag" in label: label = _t("Gyro Mag", "Veľkosť gyra")
    if "Mag Mag" in label: label = _t("Mag Mag", "Veľkosť mag")
    if "Vib Total" in label: label = _t("Vib Total", "Celkové vibrácie")
    if "Compass Variance" in label: label = _t("Compass Variance", "Rozptyl kompasu")
    if "Pos Horiz Variance" in label: label = _t("Pos Horiz Variance", "Horizontálny rozptyl")
    if "Freemem" in label: label = _t("Free Mem", "Voľná pamäť")
    
    row = f"| {label} |"
    for phase in [_t('PRE', 'PRED'),_t('DURING', 'POČAS'),_t('POST', 'PO')]:
        ps = phase_stats.get(phase, {})
        mean, std = ps.get(f"{col}_mean"), ps.get(f"{col}_std")
        row += f" {mean:.4f} ± {std:.4f} |" if mean is not None else " — |"
    stats_table_rows += row + "\n"

scoring_table = f"| {_t('Criterion', 'Kritérium')} | {_t('Points', 'Body')} | {_t('Max', 'Max')} | {_t('Notes', 'Poznámky')} |\n|---|---|---|---|\n"
for name, info in scoring.items():
    label = name.replace('_',' ').title()
    label = _t(label, {"Recovery Baseline": "Obnova baseline", 
                       "Max Dose Safe": "Max. dávka bezpečná", 
                       "No 3sigma Spikes": "Žiadne 3σ výkyvy",
                       "Os Integrity": "Integrita OS",
                       "Telemetry Nominal": "Telemetria nominálna"}.get(label, label))
    scoring_table += f"| {label} | {info['score']} | {info['max']} | {info['note']} |\n"
scoring_table += f"| **TOTAL** | **{total_score}** | **100** | **{verdict}** |\n"

graph_sections = ""
for pf, title in plot_files:
    cmt = commentary.get(pf, "_{_t('No commentary available.', 'Komentár nie je dostupný.')}_")
    graph_sections += f"## {title}\n![{pf}]({pf})\n\n**{_t('AI Commentary:', 'Komentár AI:')}** {cmt}\n\n---\n"

md_report = f"""#{_t(' Drone Radiation Mission Safety Report', ' Správa o bezpečnosti misie dronu v radiácii')}

**{_t('Generated:', 'Vygenerované:')}** {now}
**{_t('Exposure Duration:', 'Doba expozície:')}** {dur_min} min | **{_t('Total Data Points:', 'Počet dátových bodov:')}** {len(merged):,}
**{_t('Platform:', 'Platforma:')}** CubePilot autopilot + Jetson Xavier NX (stationary)
**{_t('FLIGHT READINESS VERDICT:', 'ZÁVER PRIPRAVENOSTI NA LET:')}** {verdict}
**{_t('Score:', 'Skóre:')}** {total_score}/100

---

## {_t('Executive Summary', 'Zhrnutie')}

{executive_summary}

---

## {_t('Phase Statistics — PRE / DURING / POST', 'Štatistiky fáz — PRED / POČAS / PO')}

{stats_table_header}{stats_table_rows}

---
{graph_sections}

## {_t('Flight Readiness Breakdown', 'Rozdelenie pripravenosti na let')}

{scoring_table}
"""

out_name = "MISSION_REPORT_sk" if LANG == "sk" else "MISSION_REPORT_eng"
with open(OUTPUT / f"{out_name}.md", "w") as f: f.write(md_report)

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

html_doc = f"""<!DOCTYPE html><html lang="{LANG}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{_t('Drone Radiation Mission Safety Report', 'Správa o bezpečnosti misie dronu v radiácii')}</title><style>body {{ font-family: sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1.5em; line-height: 1.6; }} img {{ max-width: 100%; height: auto; }} table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }} th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }} th {{ background: #f5f6fa; }}</style></head><body>{md_html}</body></html>"""
with open(OUTPUT / f"{out_name}.html", "w") as f: f.write(html_doc)

print("\n  ✅  ALL STEPS COMPLETE")