#!/bin/bash
# filepath: /home/user/Projects/radiation_drone/jetson_logs_test.sh
# Logs Jetson Xavier data directly from PC via USB (no Raspberry Pi)

# --- Configuration ---
JETSON_USER="dcs_user"
JETSON_IP="192.168.55.1"  # Jetson USB networking IP
LOG_BASE_DIR="jetson_logs"
TEGRASTAT_INTERVAL_MS=1000 # 1 second polling interval for tegrastats
JOURNAL_INTERVAL_SEC=60    # Periodic journal capture interval
MEMCHK_SIZE_MB=64          # Memory block size to allocate for checksum test
MEMCHK_ALLOC_INTERVAL=30   # Allocate new memory block every N seconds
MEMCHK_CHECK_INTERVAL=60   # Verify checksums every N seconds
MEMCHK_MIN_FREE_PCT=80     # Stop allocating if free memory drops below this %

# --- Local Setup ---
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${LOG_BASE_DIR}/${TIMESTAMP}"

echo "--- Jetson Direct Logger (USB) ---"
echo "Jetson: ${JETSON_USER}@${JETSON_IP}"
echo "Local Log Directory: ${LOG_DIR}"
echo "-----------------------------------"

mkdir -p "${LOG_DIR}"

# Array to hold PIDs of background SSH processes for cleanup
declare -a BG_PIDS

# --- Remote Command Definitions ---
# These commands will be executed on Jetson through RPI proxy

# Command 1: One-Time Dumps (Journal & Dmesg from last boot)
ONE_TIME_CMD=$(cat << 'EOF_CMD'
echo "--- START JOURNAL_BOOT $(date +%Y%m%d_%H%M%S) ---"
sudo journalctl --boot --no-pager
echo "--- START DMESG_BOOT $(date +%Y%m%d_%H%M%S) ---"
sudo dmesg
EOF_CMD
)

# Command 2: Continuous Tegrastats Stream
TEGRASTAT_CMD="sudo tegrastats --interval ${TEGRASTAT_INTERVAL_MS}"

# Command 3: Continuous Dmesg Follow
DMESG_CMD="sudo dmesg --follow"

# --- Cleanup Function ---
cleanup() {
    echo -e "\n--- Stopping Remote Logging Processes ---"
    # Kill the background SSH processes on the local host
    for pid in "${BG_PIDS[@]}"; do
        if kill "$pid" 2>/dev/null; then
            echo "Killed local PID: $pid"
        fi
    done
    wait
    echo "Cleanup complete. Data saved to ${LOG_DIR}"
    exit 0
}

# Set up the trap to run cleanup when script is interrupted (Ctrl+C)
trap cleanup SIGINT SIGTERM

# --- Test Connectivity ---
echo "Testing connectivity..."
echo -n "  - Testing PC -> Jetson... "
if ssh -n -o ConnectTimeout=5 "${JETSON_USER}@${JETSON_IP}" "echo OK" &>/dev/null; then
    echo "OK"
else
    echo "FAILED"
    echo "ERROR: Cannot connect to Jetson. Make sure:"
    echo "  1. Jetson USB cable is connected"
    echo "  2. SSH keys are set up: ssh-copy-id ${JETSON_USER}@${JETSON_IP}"
    exit 1
fi

# --- 1. Execute One-Time Dumps ---
echo -e "\n1. Capturing static boot logs..."
ssh -n "${JETSON_USER}@${JETSON_IP}" "${ONE_TIME_CMD}" > "${LOG_DIR}/initial_logs.txt" 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to run one-time logs."
    cleanup
fi
echo "   -> Saved to ${LOG_DIR}/initial_logs.txt"

# --- 2. Start Continuous Tegrastats Stream ---
echo "2. Starting continuous tegrastats stream (1Hz)..."
ssh "${JETSON_USER}@${JETSON_IP}" "${TEGRASTAT_CMD}" > "${LOG_DIR}/tegrastats_continuous.log" 2>&1 &
TEGRASTAT_PID=$!
BG_PIDS+=("$TEGRASTAT_PID")
echo "   -> Running in background with PID: ${TEGRASTAT_PID}"

# --- 3. Start Continuous Dmesg Stream ---
echo "3. Starting continuous kernel log stream..."
ssh -n "${JETSON_USER}@${JETSON_IP}" "${DMESG_CMD}" > "${LOG_DIR}/dmesg_continuous.log" 2>&1 &
DMESG_PID=$!
BG_PIDS+=("$DMESG_PID")
echo "   -> Running in background with PID: ${DMESG_PID}"

# --- 4. Periodic Journal Snapshots ---
echo "4. Starting periodic journal snapshots every ${JOURNAL_INTERVAL_SEC}s..."
(
  while true; do
    TS=$(date +%Y%m%d_%H%M%S)
    OUTFILE="${LOG_DIR}/journal_${TS}.log"
    echo "   -> Capturing journal to ${OUTFILE}"
    ssh -n "${JETSON_USER}@${JETSON_IP}" "sudo journalctl --no-pager --lines=100" > "${OUTFILE}" 2>&1
    sleep "${JOURNAL_INTERVAL_SEC}"
  done
) &
JOURNAL_PID=$!
BG_PIDS+=("$JOURNAL_PID")
echo "   -> Running in background with PID: ${JOURNAL_PID}"

# --- 5. Memory Checksum Guard ---
echo "5. Starting continuous memory checksum guard on Jetson..."
# Copy script directly to Jetson
scp -q mem_checksum_guard.py "${JETSON_USER}@${JETSON_IP}:/tmp/mem_checksum_guard.py"

# Run the script on Jetson
ssh -n "${JETSON_USER}@${JETSON_IP}" "export MEMCHK_SIZE_MB=${MEMCHK_SIZE_MB} MEMCHK_ALLOC_INTERVAL=${MEMCHK_ALLOC_INTERVAL} MEMCHK_CHECK_INTERVAL=${MEMCHK_CHECK_INTERVAL} MEMCHK_MIN_FREE_PCT=${MEMCHK_MIN_FREE_PCT}; python3 /tmp/mem_checksum_guard.py" > "${LOG_DIR}/mem_checksum.log" 2>&1 &
MEMCHK_PID=$!
BG_PIDS+=("$MEMCHK_PID")
echo "   -> Running in background with PID: ${MEMCHK_PID}"

# --- Keep Script Alive ---
echo -e "\n--- LOGGING IN PROGRESS ---"
echo "Logs are being saved to: ${LOG_DIR}"
echo "Press Ctrl+C to stop logging and save all files."
echo ""
echo "Monitoring:"
echo "  - Jetson tegrastats"
echo "  - Jetson kernel logs (dmesg)"
echo "  - Jetson journal snapshots every ${JOURNAL_INTERVAL_SEC}s"
echo "  - Jetson memory checksum guard (allocate ${MEMCHK_SIZE_MB}MB every ${MEMCHK_ALLOC_INTERVAL}s, check every ${MEMCHK_CHECK_INTERVAL}s, min free ${MEMCHK_MIN_FREE_PCT}%)"

# The 'wait' command blocks indefinitely until all background PIDs are terminated (handled by the trap).
wait