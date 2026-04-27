# Raspberry Scripts Overview

## Script Reference Table

| Script | Runs on | What it does | Connects to | Output |
|---|---|---|---|---|
| `rpi_full_mavlink_logger.py` | **RPi** | Connects directly to Cube via serial, requests all MAVLink message IDs at a fixed rate, logs every message type to its own CSV file. Flushes every write — safe against power loss. | Cube via `/dev/ttyACM0` @ 921600 baud | `mavlink_logs/<timestamp>/*.csv` on RPi |
| `rpi4_script.sh` | **RPi** | Relays MAVLink from Cube via `mavproxy` to a PC over UDP port 14550. Also relays WiFi test UDP (port 14551) from RPi3 to PC via `socat`. Does **not** log locally — just forwards. | Cube via `/dev/ttyACM0`; forwards to PC at `10.11.1.17` | UDP stream to PC only |
| `set_message_intervals.py` | **RPi** | One-shot helper. Connects to Cube via serial and sends `MAV_CMD_SET_MESSAGE_INTERVAL` to fix per-message rates before starting mavproxy (BATTERY=1Hz, ATTITUDE=20Hz, IMU=50Hz). | Cube via `/dev/ttyACM0` | Console only (ACK results) |
| `cube_logger.py` | **PC** | Receives MAVLink UDP stream from RPi relay, logs every message type to its own CSV file. Requires `rpi4_script.sh` running on RPi first. | UDP port 14550 (from RPi relay) | `mavlink_logs/<timestamp>/*.csv` on PC |
| `mavlink_logger.sh` | **PC** | Wrapper script for `cube_logger.py`. Sets up Python venv, installs `pymavlink`, pings RPi to check connectivity, then launches `cube_logger.py`. | RPi at `192.168.88.15`; UDP port 14550 | Delegates to `cube_logger.py` |
| `jetson_logs.sh` | **PC** | Logs Jetson through RPi as SSH proxy (PC → RPi → Jetson). SSHes into RPi which then SSHes into Jetson. Runs tegrastats, dmesg follow, periodic journal snapshots, and memory checksum guard on Jetson. Saves logs **locally on PC**. | RPi at `192.168.88.15` → Jetson at `192.168.55.1` | `jetson_logs/<timestamp>/` on PC |
| `jetson_logs_pc.sh` | **PC** | Same as `jetson_logs.sh` but connects **directly** to Jetson without going through RPi (PC has direct USB/network link to Jetson). Saves logs **locally on PC**. | Jetson at `192.168.55.1` directly | `jetson_logs/<timestamp>/` on PC |
| `mem_checksum_guard.py` | **Jetson** | Allocates memory blocks periodically, computes SHA-256 checksums, and re-verifies them on a timer to detect radiation-induced bit flips. Config via env vars. Called by `jetson_logs.sh` / `jetson_logs_pc.sh`. | Local memory only | `mem_checksum.log` (streamed back to caller) |
| `rpi3_script.sh` | **RPi3** | Continuously pings Jetson over WiFi, collects WiFi metrics (signal, link quality, noise, bit rate, packet stats) and logs to CSV and text file. | Jetson at `192.168.55.1` via `wlan0` | `network_log/wifi_metrics_<timestamp>.csv` on RPi3 |
| `wifi_test_logger.py` | **PC** | Listens on UDP port 14551 for plain-text WiFi test messages sent by RPi3 (relayed via `rpi4_script.sh`). Logs messages to a timestamped file. | UDP port 14551 (from RPi relay) | `wifi_logs/<timestamp>/wifi_connectivity.log` on PC |

---

## Data Flow Summary

```
Cube (serial) ──► rpi_full_mavlink_logger.py  ──► CSV logs on RPi   [local logging]
Cube (serial) ──► rpi4_script.sh (mavproxy)   ──► UDP 14550 ──► cube_logger.py / mavlink_logger.sh on PC
Jetson        ──► jetson_logs.sh (via RPi SSH proxy)           ──► logs on PC
Jetson        ──► jetson_logs_pc.sh (direct)                   ──► logs on PC
Jetson memory ──► mem_checksum_guard.py (runs on Jetson)       ──► streamed into jetson_logs.sh
RPi3 WiFi     ──► rpi3_script.sh                               ──► CSV on RPi3
RPi3 WiFi     ──► rpi4_script.sh (socat relay) ──► UDP 14551 ──► wifi_test_logger.py on PC
```

---

## Which script to use for your setup

**Setup: PC ↔ RPi (ethernet), RPi ↔ Cube (serial), RPi ↔ Jetson (USB)**

| Goal | Run on RPi | Run on PC |
|---|---|---|
| Log Cube MAVLink locally on RPi | `rpi_full_mavlink_logger.py` | nothing |
| Log Cube MAVLink on PC (via relay) | `rpi4_script.sh` | `mavlink_logger.sh` |
| Log Jetson from PC (through RPi) | nothing | `jetson_logs.sh` |
| Log Jetson locally on RPi | `jetson_logs_pc.sh` (run on RPi, targets `192.168.55.1`) | nothing |
