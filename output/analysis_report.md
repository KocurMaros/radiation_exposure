# Drone Radiation Exposure Analysis Report
Generated: 2026-02-27 12:58:59
Flight Data points: 0

*Note: Based on log analysis, radiation sensor data was missing from the Jetson logs. Plots requiring radiation metrics have been generated as blank placeholders. Telemetry data from MAVLink has been plotted successfully.*

## 1. Radiation vs Time
![radiation_vs_time](radiation_vs_time.png)
This graph normally tracks the instantaneous radiation dose rate over the duration of the flight. Because radiation data was not logged, no trend is visible. Operationally, verifying the sensor's physical connection and software logging daemon (Python script) is required before the next flight.

## 2. Radiation vs Altitude
![radiation_vs_altitude](radiation_vs_altitude.png)
This scatter plot correlates radiation intensity with drone altitude (AGL). Typically, it helps identify if radiation plumes are concentrated at specific heights. Currently, the plot is empty due to missing sensor data.

## 3. Flight Path Radiation Map
![flight_path_radiation](flight_path_radiation.png)
This 2D GPS track shows the drone's ground path. Normally, the path is colored by a heatmap representing radiation intensity. The flight path was successfully extracted from MAVLink, showing the spatial coverage of the mission, but lacks the radiation overlay layer.

## 4. 3D Spatial Exposure Map
![radiation_3d](radiation_3d.png)
This 3D plot visualizes latitude, longitude, and altitude simultaneously. It provides a complete spatial understanding of the surveyed area. The physical flight envelope is visible, demonstrating successful GPS and Barometer logging from the CubeOrange+ autopilot.

## 5. Cumulative Dose
![cumulative_dose](cumulative_dose.png)
This graph represents the total accumulated radiation dose the drone absorbed over time. It is a critical metric for hardware degradation and maintenance cycles. Data is currently missing.

## 6. Telemetry Overview (Altitude, Speed, Battery)
![telemetry_overview](telemetry_overview.png)
This multi-panel graph displays the drone's physical health and flight dynamics. Altitude, groundspeed, and battery voltage are plotted against flight time. A steady decrease in battery voltage is expected, and the altitude profile clearly marks the takeoff, cruise, and landing phases.

## 7. Radiation Histogram
![radiation_histogram](radiation_histogram.png)
This histogram outlines the distribution of radiation readings. It helps identify the background radiation mean versus significant outlier spikes. Currently empty.

## 8. Anomaly Flagging
![anomaly_flagged](anomaly_flagged.png)
This graph highlights specific timestamps where radiation readings exceeded 2 standard deviations above the mean (95th percentile). Without data, no anomalies can be calculated.
