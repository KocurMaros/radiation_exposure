#!/bin/bash
# filepath: /home/rpi/scripts/wifi_connectivity_test.sh
# Test wireless connectivity to Jetson (10.42.0.1) and log metrics to CSV.

JETSON_IP="192.168.55.1"
WIFI_INTERFACE="wlan0"  # Change if using a different interface
LOG_DIR="./network_log"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CSV_FILE="${LOG_DIR}/wifi_metrics_${TIMESTAMP}.csv"
LOG_FILE="${LOG_DIR}/wifi_test_${TIMESTAMP}.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo "=============================================="
echo "  WiFi Connectivity Test (RPi3 → Jetson)"
echo "=============================================="
echo "Target (Jetson): ${JETSON_IP}"
echo "WiFi Interface: ${WIFI_INTERFACE}"
echo "CSV Log: ${CSV_FILE}"
echo "Text Log: ${LOG_FILE}"
echo "=============================================="
echo ""

# Detect WiFi interface if wlan0 doesn't exist
if ! ip link show "$WIFI_INTERFACE" &>/dev/null; then
    WIFI_INTERFACE=$(iw dev 2>/dev/null | awk '$1=="Interface"{print $2}' | head -1)
    if [ -z "$WIFI_INTERFACE" ]; then
        echo "WARNING: No WiFi interface detected, some metrics will be unavailable"
        WIFI_INTERFACE="unknown"
    else
        echo "Detected WiFi interface: ${WIFI_INTERFACE}"
    fi
fi

echo ""
echo "Starting WiFi connectivity tests..."
echo "Press Ctrl+C to stop"
echo "=============================================="

# Initialize CSV file with header
echo "timestamp,ping_count,ping_success,packet_loss_pct,ping_status,ping_latency_ms,signal_strength_dbm,link_quality,noise_level_dbm,bit_rate_mbps,frequency_ghz,ssid,tx_packets,rx_packets,tx_bytes,rx_bytes,tx_errors,rx_errors" > "$CSV_FILE"

# Function to get WiFi metrics
get_wifi_metrics() {
    local iw_output
    local iwconfig_output
    
    # Get signal strength and link quality using iw
    iw_output=$(iw dev "$WIFI_INTERFACE" link 2>/dev/null)
    iwconfig_output=$(iwconfig "$WIFI_INTERFACE" 2>/dev/null)
    
    # Signal strength (dBm)
    SIGNAL_DBM=$(echo "$iw_output" | grep -oP 'signal: \K-?\d+' 2>/dev/null || echo "N/A")
    
    # Frequency
    FREQUENCY=$(echo "$iw_output" | grep -oP 'freq: \K[\d.]+' 2>/dev/null || echo "N/A")
    if [ "$FREQUENCY" != "N/A" ]; then
        FREQUENCY=$(awk "BEGIN {printf \"%.3f\", $FREQUENCY/1000}")
    fi
    
    # SSID
    SSID=$(echo "$iw_output" | grep -oP 'SSID: \K.*' 2>/dev/null | head -1 || echo "N/A")
    [ -z "$SSID" ] && SSID="N/A"
    
    # Bit rate (Mbps)
    BIT_RATE=$(echo "$iw_output" | grep -oP 'tx bitrate: \K[\d.]+' 2>/dev/null || echo "N/A")
    
    # Link quality (from iwconfig, format: XX/70)
    LINK_QUALITY=$(echo "$iwconfig_output" | grep -oP 'Link Quality[=:]\K\d+/\d+' 2>/dev/null || echo "N/A")
    
    # Noise level (dBm)
    NOISE_LEVEL=$(echo "$iwconfig_output" | grep -oP 'Noise level[=:]\K-?\d+' 2>/dev/null || echo "N/A")
    
    # Get interface statistics
    if [ -d "/sys/class/net/$WIFI_INTERFACE/statistics" ]; then
        TX_PACKETS=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/tx_packets" 2>/dev/null || echo "N/A")
        RX_PACKETS=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/rx_packets" 2>/dev/null || echo "N/A")
        TX_BYTES=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/tx_bytes" 2>/dev/null || echo "N/A")
        RX_BYTES=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/rx_bytes" 2>/dev/null || echo "N/A")
        TX_ERRORS=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/tx_errors" 2>/dev/null || echo "N/A")
        RX_ERRORS=$(cat "/sys/class/net/$WIFI_INTERFACE/statistics/rx_errors" 2>/dev/null || echo "N/A")
    else
        TX_PACKETS="N/A"
        RX_PACKETS="N/A"
        TX_BYTES="N/A"
        RX_BYTES="N/A"
        TX_ERRORS="N/A"
        RX_ERRORS="N/A"
    fi
}

# Function to log result to console and text log
log_message() {
    local msg="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $msg" | tee -a "$LOG_FILE"
}

# Function to log metrics to CSV
log_csv() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${timestamp},${PING_COUNT},${PING_SUCCESS},${PKT_LOSS},${STATUS},${LATENCY},${SIGNAL_DBM},${LINK_QUALITY},${NOISE_LEVEL},${BIT_RATE},${FREQUENCY},${SSID},${TX_PACKETS},${RX_PACKETS},${TX_BYTES},${RX_BYTES},${TX_ERRORS},${RX_ERRORS}" >> "$CSV_FILE"
}

# Initial connectivity check
log_message "TEST_START: WiFi connectivity test to ${JETSON_IP}"

if ping -c 1 -W 2 ${JETSON_IP} &>/dev/null; then
    log_message "PING_OK: Device ${JETSON_IP} is reachable"
else
    log_message "PING_FAIL: Cannot reach ${JETSON_IP}"
    log_message "TEST_END: Initial ping failed"
    exit 1
fi

echo ""
echo "Running continuous tests (Ctrl+C to stop)..."
echo ""

# Continuous ping with comprehensive metrics
PING_COUNT=0
PING_SUCCESS=0
START_TIME=$(date +%s)

# Graceful exit handler
cleanup() {
    echo ""
    log_message "TEST_END: Total pings=$PING_COUNT Success=$PING_SUCCESS Loss=${PKT_LOSS}%"
    log_message "CSV log saved to: $CSV_FILE"
    exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
    # Get ping result with latency
    PING_OUTPUT=$(ping -c 1 -W 2 ${JETSON_IP} 2>/dev/null)
    if [ $? -eq 0 ]; then
        ((PING_SUCCESS++))
        STATUS="OK"
        # Extract latency from ping output
        LATENCY=$(echo "$PING_OUTPUT" | grep -oP 'time=\K[\d.]+' | head -1)
        [ -z "$LATENCY" ] && LATENCY="N/A"
    else
        STATUS="FAIL"
        LATENCY="N/A"
    fi
    
    ((PING_COUNT++))
    ELAPSED=$(($(date +%s) - START_TIME))
    PKT_LOSS=$((100 * (PING_COUNT - PING_SUCCESS) / PING_COUNT))
    
    # Get WiFi metrics
    get_wifi_metrics
    
    # Log to CSV
    log_csv
    
    # Console output
    MSG="Count=$PING_COUNT Loss=${PKT_LOSS}% Latency=${LATENCY}ms Signal=${SIGNAL_DBM}dBm Quality=${LINK_QUALITY} Rate=${BIT_RATE}Mbps"
    log_message "PING_STAT: $MSG"
    
    sleep 1
done