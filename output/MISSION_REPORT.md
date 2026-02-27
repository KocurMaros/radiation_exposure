# Drone Radiation Mission Safety Report

**Generated:** 2026-02-27 15:58:07
**Exposure Duration:** 50.4 min | **Total Data Points:** 8,398
**Platform:** CubePilot autopilot + Jetson Xavier NX (stationary)
**FLIGHT READINESS VERDICT:** ⚠️ CONDITIONAL — Review flagged items before next flight
**Score:** 53/100

---

## Executive Summary

Tu je manažérske zhrnutie v slovenčine:

Dron je uzemnený so skóre 53/100 primárne kvôli závažnej logickej degradácii systému, hoci fyzicky radiačnú záťaž prežil bez poškodenia pamäte. Analýza logov odhalila kritickú nestabilitu na zbernici PCIe (opakované AER udalosti), čo signalizuje prerušovanú komunikáciu medzi procesorom Jetson a kľúčovými perifériami. Tento stav je ďalej zhoršený vysokým počtom extrémnych odchýlok (>3σ) a neprijateľnou varianciou kompasu (156 %), čo naznačuje výraznú korupciu senzorických dát. Hoci základná telemetria vyzerá nominálne, operačný systém vykazuje chyby integrity, ktoré v kombinácii s nestabilným hardvérovým rozhraním znemožňujú bezpečné riadenie letu. Zariadenie teda zlyhalo na úrovni spoľahlivosti výpočtových procesov, nie na úrovni deštrukcie napájania či hardvéru.

---

## Phase Statistics — PRE / DURING / POST

| Metric | PRE (Baseline) | DURING (Exposure) | POST (Recovery) |
|---|---|---|---|
| Vcc V | 5.1673 ± 0.0011 | 5.2601 ± 0.0038 | 5.2618 ± 0.0010 |
| Imu Temp C | 44.9925 ± 0.0350 | 45.0592 ± 0.7843 | 45.3154 ± 0.0199 |
| Baro Temp C | 47.7528 ± 0.0113 | 46.6426 ± 0.6869 | 47.0098 ± 0.0175 |
| Acc Mag | 987.8836 ± 0.1421 | 994.0001 ± 2.2927 | 992.4494 ± 0.1265 |
| Gyro Mag | 1.0620 ± 0.0807 | 1.8884 ± 0.8337 | 3.3430 ± 0.1111 |
| Mag Mag | 357.1598 ± 3.0374 | 271.9362 ± 21.3425 | 412.4026 ± 3.2249 |
| Vib Total | 0.1077 ± 0.0071 | 0.1841 ± 0.0385 | 0.1722 ± 0.0040 |
| Compass Variance | 0.0138 ± 0.0033 | 0.0194 ± 0.0061 | 0.0355 ± 0.0079 |
| Pos Horiz Variance | 0.0005 ± 0.0003 | 0.0008 ± 0.0010 | 0.0006 ± 0.0003 |
| Freemem | 65535.0000 ± 0.0000 | 65535.0000 ± 0.0000 | 65535.0000 ± 0.0000 |


---
## Sensor drift over elapsed time during radiation exposure sessions
![01_radiation_timeline.png](01_radiation_timeline.png)

**AI Commentary:** Based on the provided graph and specific constraints, here is the technical analysis:

The graph visualizes the temporal evolution of sensor bias relative to initial stationary readings for accelerometer (mg), gyroscope (mrad/s), and magnetometer (mGauss) data during three distinct radiation exposure runs. A pronounced, non-linear negative trend is visible in the accelerometer data for `02_DURING_exposure_run1`, which decays asymptotically to approximately -8 mg, while the gyroscope simultaneously exhibits a rapid step-change to a noisy plateau averaging 2.0 mrad/s. Visible anomalies include high-frequency signal noise and discrete outlier events, plotted as red points, which are most prevalent in the magnetometer and gyroscope traces during the high-drift periods of the first exposure run. This magnitude of uncompensated sensor drift, particularly the sustained gyroscope bias, would likely corrupt the state estimation within the Attitude and Heading Reference System (AHRS), compromising the drone's ability to maintain level flight without external corrections.

---
## Barometric temperature increase over elapsed time
![02_radiation_baro_temp.png](02_radiation_baro_temp.png)

**AI Commentary:** Based on the barometric temperature telemetry presented in this plot, here is the technical analysis:

1.  This graph visualizes the thermal performance of the barometric sensor in degrees Celsius across five distinct operational phases, ranging from a pre-exposure baseline to post-recovery validation.
2.  The baseline data ('01_PRE_baseline') exhibits exceptional thermal stability near 47.8°C, whereas the subsequent exposure runs settle into a slightly lower equilibrium state, consistently hovering between 46.5°C and 47.0°C.
3.  A significant transient anomaly is evident in '02_DURING_exposure_run1', where the sensor undergoes a rapid thermal shock, climbing steeply from 38°C to operational temperature within the first three minutes before stabilizing.
4.  Despite the initial thermal ramp in the first exposure run, the sensor consistently stabilizes within a safe operational window across all datasets, indicating that the barometer's temperature compensation capability remains intact for reliable altitude hold and vertical navigation.

---
## Navigation degradation heatmap — compass variance by session
![03_compass_variance_heatmap.png](03_compass_variance_heatmap.png)

**AI Commentary:** Based on the provided heatmap, here is the radiation safety engineering analysis:

1.  This visualization tracks compass variance as a specific metric for navigation degradation, plotting intensity against elapsed flight time across five distinct operational sessions.
2.  While the 01_PRE_baseline maintains a consistent low-variance state (dark red), the subsequent exposure runs exhibit a progressive instability, most notably in 02_DURING_exposure_run1 which displays intermittent spikes of high variance (yellow/white) throughout the 40-minute duration.
3.  A critical anomaly is observed in the 05_POST_recovery_day1 session, which initiates with immediate, elevated variance levels (bright yellow) and abruptly terminates within the first few minutes, indicating a failure to stabilize compared to previous runs.
4.  Such elevated compass variance compromises the reliability of the vehicle's heading estimation, presenting a severe airworthiness risk by increasing the likelihood of uncommanded yaw rotation or loss of positional hold ("toilet bowling").

---
## 3D accelerometer state-space showing drift during exposure
![04_radiation_3d_map.png](04_radiation_3d_map.png)

**AI Commentary:** Based on the provided 3D accelerometer state-space graph, here is the technical analysis:

1.  **Metric Shown:** The visualization plots the tri-axial accelerometer readings (X, Y, and Z axes in milli-g) within a 3D state space, using a color gradient to represent elapsed session time from 0 minutes (purple) to approximately 9 minutes (yellow).
2.  **Trend/Drift:** A distinct, time-correlated drift is visible along the Z-axis, where the acceleration cluster systematically migrates "upward" from approximately -1004 mg (early session/purple) to -992 mg (late session/yellow).
3.  **Visible Anomalies:** The data reveals a continuous "walking" bias rather than random noise, indicating that the sensor's defined zero-point or scaling factor is progressively shifting under radiation exposure.
4.  **Airworthiness Impact:** This magnitude of uncommanded sensor bias drift would corrupt the flight controller's gravity vector estimation, likely resulting in significant errors in altitude hold and vertical velocity calculations, rendering the vehicle unsafe for autonomous flight.

---
## Cumulative effects: temperature, vibration, compass over time
![05_cumulative_dose.png](05_cumulative_dose.png)

**AI Commentary:** Based on the provided telemetry graph analyzing progressive degradation indicators:

1.  **Metric Shown:** The data visualizes cumulative radiation effects on critical flight sensors, specifically tracking Barometer Temperature (°C), Total Vibration (m/s²), and Compass Variance across baseline, active exposure, and recovery phases.
2.  **Trend/Drift:** While the thermal profiles remain relatively stable with a slight decay during exposure runs, the vibration telemetry reveals a distinct upward shift where the "02_DURING_exposure_run1" trace settles at a vibration floor approximately double that of the "01_PRE_baseline."
3.  **Anomalies Visible:** The most significant anomaly is the initial transient event in the vibration plot during the first exposure run, which spikes sharply to ~0.37 m/s² before stabilizing, correlating with the steep thermal ramp-up seen in the barometer graph.
4.  **Impact on Airworthiness:** The persistent elevation in vibration levels and the increased noise floor in compass variance during exposure runs indicate potential sensor signal-to-noise degradation, which jeopardizes the flight controller's ability to maintain precise attitude and heading stability.

---
## Multi-panel telemetry: voltage, temp, free memory, load
![06_telemetry_overview.png](06_telemetry_overview.png)

**AI Commentary:** Based on the telemetry overview, the plotted metrics include the CubePilot's Board Voltage, IMU Temperature, available Free Memory, and System Load mapped against elapsed mission time. While Free Memory remains perfectly static at the quantization floor of 65,535 bytes indicating no memory leaks, the IMU Temperature for "exposure_run1" shows a steep thermal soak period, rising from 35°C to a stable operating temperature of 45.5°C within three minutes. Visible anomalies include a distinct ~0.09V DC offset between the baseline voltage (5.17V) and exposure runs (5.26V), as well as an unexplained step-down in System Load at the 33-minute mark of the first exposure session. Although the stable memory and temperature plateaus support continued operation, the variance in board voltage requires validation to ensure the power distribution network maintains sufficient headroom to prevent brownouts during critical flight phases.

---
## Distribution histograms comparing PRE/DURING/POST phases
![07_dose_distribution.png](07_dose_distribution.png)

**AI Commentary:** Based on the provided histograms comparing sensor distributions across operational phases:

1.  **Metric Shown:** The plots display probability density distributions for vibration ($m/s^2$), compass variance, accelerometer magnitude (mg), and board voltage (V), segmented into PRE (green), DURING (red), and POST (blue) operational phases.
2.  **Trend/Drift:** A systematic baseline shift is evident in the hardware telemetry, characterized by a distinct step-increase of approximately 0.1V in board voltage and a permanent positive offset of ~5mg in accelerometer magnitude starting in the DURING phase and persisting into the POST phase.
3.  **Anomalies Visible:** The Compass Variance demonstrates significant degradation, transitioning from a tight distribution in the PRE phase to a highly erratic, multi-modal spread with values exceeding 0.05 in the POST phase, indicating severe loss of sensor precision.
4.  **Impact on Airworthiness:** While the voltage shift likely remains within electrical tolerances, the uncorrected biases in accelerometer data combined with the high variance in the compass readings compromise the integrity of the navigation solution, significantly increasing the risk of state estimation divergence.

---
## Box-plot comparison of key metrics across phases
![08_phase_comparison_boxplot.png](08_phase_comparison_boxplot.png)

**AI Commentary:** Based on the provided box-plot analysis of telemetry data:

1.  **Metric Shown:** This figure compares the statistical distribution of vibration totals, compass variance, accelerometer magnitude, supply voltage (Vcc), IMU temperature, and free memory across pre-exposure, active exposure (DURING), and post-exposure phases.
2.  **Trend/Drift:** A distinct state change occurs during the exposure phase, characterized by massive variance expansion in vibration and accelerometer readings, alongside a step-increase in Vcc voltage that remains elevated in the post-exposure phase.
3.  **Anomalies Visible:** While accelerometer magnitude and IMU temperature show extreme transient outliers during exposure (with temperature anomalously dropping to ~35°C), the Compass Variance shows a concerning failure to recover, maintaining a significantly higher median and spread in the POST phase compared to the PRE baseline.
4.  **Impact on Airworthiness:** The permanent elevation in Compass Variance post-exposure suggests sensor magnetization or degradation, presenting a critical risk to navigation reliability and heading stability required for safe autonomous flight.

---
## Numerical statistics table for all channels by phase
![09_stats_summary_card.png](09_stats_summary_card.png)

**AI Commentary:** Based on the statistical data presented in the summary card:

1.  **Metric Shown:** This table presents the statistical mean, standard deviation, and min/max range for avionics health telemetry, including supply voltage (Vcc), component temperatures, inertial sensor magnitudes (Accelerometer, Gyroscope, Magnetometer), and system variances across baseline, radiation exposure, and recovery phases.
2.  **Trend/Drift:** A significant trend is observed in the magnetometer magnitude (Mag Mag), which drops substantially during the exposure phase (mean ~272) compared to the baseline (~357) before rebounding and overshooting in the recovery phase (~412), while Compass Variance shows a continuous upward drift from PRE to POST.
3.  **Anomalies Visible:** The most prominent anomaly is the drastic increase in sensor noise during the exposure phase, evidenced by the standard deviation of the accelerometer magnitude spiking from ±0.1421 (PRE) to ±2.2927 (DURING) and the magnetometer standard deviation increasing from ±3.0374 to ±21.3425.
4.  **Impact on Airworthiness:** Although the "Freemem" metric remains saturated at 65535 indicating no memory leaks, the high sensor variance and magnetic field distortions visible during exposure could degrade the Extended Kalman Filter (EKF) solution, potentially compromising autonomous navigation and heading stability.

---
## Readiness gauge — score 53/100 — ⚠️ CONDITIONAL — Review flagged items before next flight
![10_flight_readiness_gauge.png](10_flight_readiness_gauge.png)

**AI Commentary:** Based on the provided Flight Readiness Assessment gauge and scoring breakdown:

1.  This composite metric displays a calculated readiness score of 53/100, placing the system in a "Conditional" state that explicitly requires a review of flagged items before the next flight.
2.  Significant drift is observed in the Recovery Baseline parameters, specifically with `vib_total` reaching 59.9% and `compass_variance` deviating excessively to 156.3%.
3.  Visible anomalies in the scoring breakdown include 158 extreme statistical outliers (>3σ) and 6 logged OS-level faults which drastically reduced the OS Integrity sub-score to 8/20.
4.  While the "Max Dose Safe" and "Telemetry Nominal" metrics indicate stable radiation levels and communication, the high incidence of outliers and compass variance compromises the vehicle's navigation reliability, preventing unconditional airworthiness certification.

---
## Jetson companion CPU/GPU temps and system power draw
![11_jetson_system_health.png](11_jetson_system_health.png)

**AI Commentary:** Based on the provided blank template graph, here is the technical analysis:

1.  This chart defines coordinate systems for monitoring the Jetson Xavier NX's thermal performance in degrees Celsius and total system power consumption (VDD IN) in Watts over an irradiation timeline.
2.  No temporal trends, thermal drift, or power fluctuations are observable because the plot area contains no data traces or signal history.
3.  The distinct anomaly visible in this specific figure is a complete loss or lack of rendering for all telemetry data, resulting in null values across both the temperature and power axes.
4.  The absence of plotted power and thermal metrics precludes any assessment of whether the hardware remained within its safe operating area (SOA), rendering the airworthiness of the thermal management system unverifiable from this specific image.

---


## Flight Readiness Breakdown

| Criterion | Points | Max | Notes |
|---|---|---|---|
| Recovery Baseline | 10 | 30 | Vcc_V: 1.8% ✓; vib_total: 59.9% ✗; compass_variance: 156.3% ✗ |
| Max Dose Safe | 20 | 20 | No failures |
| No 3Sigma Spikes | 5 | 20 | 158 extreme outliers (>3σ) |
| Os Integrity | 8 | 20 | 6 OS-level faults logged |
| Telemetry Nominal | 10 | 10 | Nominal |
| **TOTAL** | **53** | **100** | **⚠️ CONDITIONAL — Review flagged items before next flight** |

