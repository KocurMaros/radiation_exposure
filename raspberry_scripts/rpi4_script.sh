#!/bin/bash
# filepath: /home/rpi/scripts/mavlink_relay.sh
# Forward MAVLink from the Cube to PC, and relay WiFi test UDP from RPi3 to PC.
# Enforces fixed per-message stream rates for consistent testing.

FC_DEV="/dev/ttyACM0"
FC_BAUD="921600"
PC_IP="10.11.1.17"
MAVLINK_PORT="14550"
WIFI_TEST_PORT="14551"
STREAM_RATE="20"  # Base streamrate fallback (Hz)

echo "=============================================="
echo "  MAVLink + WiFi Test Relay (RPi4)"
echo "=============================================="
echo "FC: ${FC_DEV} @ ${FC_BAUD}"
echo "Stream Rates: BAT=1Hz ATT=20Hz IMU=50Hz (via set_message_intervals.py)"
echo "MAVLink → PC: ${PC_IP}:${MAVLINK_PORT}"
echo "WiFi test UDP → PC: ${PC_IP}:${WIFI_TEST_PORT}"
echo "=============================================="

# Basic reachability checks
echo -n "Testing PC connection... "
if ping -c 1 -W 2 ${PC_IP} &>/dev/null; then
    echo "OK"
else
    echo "FAILED (will still start)"
fi

# Require socat for UDP relay
if ! command -v socat >/dev/null 2>&1; then
    echo "ERROR: socat is not installed. Install with: sudo apt install -y socat"
    exit 1
fi

# Stop any previous processes
pkill -f "mavproxy.py" 2>/dev/null
pkill -f "socat" 2>/dev/null
sleep 1


echo "Starting MAVLink relay (fixed per-message rates)..."
echo "Starting WiFi test UDP relay..."
echo "Press Ctrl+C to stop"
echo "=============================================="

# Pre-set message intervals directly on the FC (one-shot)
python3 /home/user/Projects/radiation_drone/set_message_intervals.py || echo "Warning: failed to set message intervals"

# Forward MAVLink from Cube to PC with fallback streamrate (auto-restart if it exits)
while true; do
    mavproxy.py \
        --master=${FC_DEV},${FC_BAUD} \
        --out=udpout:${PC_IP}:${MAVLINK_PORT} \
        --streamrate=${STREAM_RATE} \
        --state-basedir=/tmp \
        --daemon

    echo "mavproxy exited, retrying in 2s..."
    sleep 2
done &

# Relay WiFi test UDP from RPi3 (port 14551 local) to PC (port 14551)
# Listen on 0.0.0.0:14551, forward to PC:14551; suppress ICMP port unreachable noise
socat UDP-LISTEN:${WIFI_TEST_PORT},fork,reuseaddr UDP:${PC_IP}:${WIFI_TEST_PORT} 2>/dev/null &

wait