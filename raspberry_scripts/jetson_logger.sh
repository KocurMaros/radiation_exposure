#!/bin/bash
# jetson_logger.sh
#
# Runs on Raspberry Pi as a systemd service.
# Logs Jetson Xavier data via SSH over USB networking (192.168.55.1).
# All continuous tasks retry independently on any failure.
# Logs are saved to /mnt/log_usb/jetson/<session_timestamp>/.

# ── Configuration ──────────────────────────────────────────────────────────────
JETSON_USER="dcs_user"
JETSON_IP="192.168.55.1"
LOG_BASE_DIR="/mnt/log_usb/jetson"
MEMCHK_SCRIPT_LOCAL="/opt/radiation_logging/mem_checksum_guard.py"
MEMCHK_SCRIPT_REMOTE="/tmp/mem_checksum_guard.py"

TEGRASTAT_INTERVAL_MS=1000   # tegrastats polling interval (ms)
JOURNAL_INTERVAL_SEC=60      # how often to snapshot the Jetson journal
MEMCHK_SIZE_MB=64            # memory block size for checksum guard
MEMCHK_ALLOC_INTERVAL=30     # allocate a new block every N seconds
MEMCHK_CHECK_INTERVAL=60     # verify all blocks every N seconds
MEMCHK_MIN_FREE_PCT=80       # stop allocating if Jetson free memory < this %

RETRY_DELAY=10               # seconds between reconnect attempts

# SSH/SCP options shared by all remote calls
SSH_OPTS=(
    -o BatchMode=yes
    -o ConnectTimeout=10
    -o ServerAliveInterval=10
    -o ServerAliveCountMax=3
    -o StrictHostKeyChecking=accept-new
)

# ── Wait for USB log drive ─────────────────────────────────────────────────────
echo "Waiting for /mnt/log_usb to be ready..."
until mountpoint -q /mnt/log_usb 2>/dev/null && touch /mnt/log_usb/.write_test 2>/dev/null; do
    echo "  /mnt/log_usb not ready, retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
done
rm -f /mnt/log_usb/.write_test

# ── Session setup ─────────────────────────────────────────────────────────────
SESSION_TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${LOG_BASE_DIR}/${SESSION_TS}"
mkdir -p "${LOG_DIR}"
SUPERVISOR_LOG="${LOG_DIR}/supervisor.log"

log_sup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "${SUPERVISOR_LOG}"
}

log_sup "=== jetson_logger started (session: ${SESSION_TS}) ==="
log_sup "Target: ${JETSON_USER}@${JETSON_IP}"
log_sup "Log dir: ${LOG_DIR}"

# ── Child process tracking ────────────────────────────────────────────────────
declare -a CHILD_PIDS=()

cleanup() {
    log_sup "=== SIGTERM received — stopping all tasks ==="
    for pid in "${CHILD_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Wait for subshells to exit (systemd will SIGKILL any stragglers via cgroup)
    wait 2>/dev/null || true
    log_sup "=== Shutdown complete ==="
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── Wait for initial SSH connection ───────────────────────────────────────────
log_sup "Waiting for Jetson SSH at ${JETSON_IP}..."
until ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" "true" 2>/dev/null; do
    log_sup "  SSH unavailable, retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
done
log_sup "Jetson SSH connected."

# ── One-time boot logs (journalctl + dmesg) ───────────────────────────────────
# Uses a temp file so no partial data lands in the final file on failure.
log_sup "Capturing initial boot logs (journalctl + dmesg)..."
while true; do
    BOOT_TMP="${LOG_DIR}/initial_logs.txt.tmp"
    > "${BOOT_TMP}"

    echo "--- START JOURNAL_BOOT $(date +%Y%m%d_%H%M%S) ---" >> "${BOOT_TMP}"
    if ! ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
            "sudo journalctl --boot --no-pager" >> "${BOOT_TMP}" 2>&1; then
        log_sup "  journalctl capture failed, retrying in ${RETRY_DELAY}s..."
        rm -f "${BOOT_TMP}"; sleep $RETRY_DELAY; continue
    fi

    echo "--- START DMESG_BOOT $(date +%Y%m%d_%H%M%S) ---" >> "${BOOT_TMP}"
    if ! ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
            "sudo dmesg" >> "${BOOT_TMP}" 2>&1; then
        log_sup "  dmesg capture failed, retrying in ${RETRY_DELAY}s..."
        rm -f "${BOOT_TMP}"; sleep $RETRY_DELAY; continue
    fi

    mv "${BOOT_TMP}" "${LOG_DIR}/initial_logs.txt"
    log_sup "Initial boot logs saved -> initial_logs.txt"
    break
done

# ── Copy mem_checksum_guard.py to Jetson ──────────────────────────────────────
log_sup "Copying mem_checksum_guard.py to Jetson..."
until scp -q "${SSH_OPTS[@]}" "${MEMCHK_SCRIPT_LOCAL}" \
        "${JETSON_USER}@${JETSON_IP}:${MEMCHK_SCRIPT_REMOTE}" 2>/dev/null; do
    log_sup "  scp failed, retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
done
log_sup "mem_checksum_guard.py copied."

# ── Continuous tasks ──────────────────────────────────────────────────────────
# Each task runs in its own background subshell with an inner retry loop.
# A task failure does not affect any other task.
# All output is appended to the same session log files across reconnects.

# Task 1: tegrastats stream
(
    while true; do
        log_sup "TASK[tegrastats] connecting..."
        ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
            "sudo tegrastats --interval ${TEGRASTAT_INTERVAL_MS}" \
            >> "${LOG_DIR}/tegrastats_continuous.log" 2>&1
        RC=$?
        log_sup "TASK[tegrastats] exited (${RC}), retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
    done
) &
CHILD_PIDS+=($!)

# Task 2: dmesg --follow
(
    while true; do
        log_sup "TASK[dmesg] connecting..."
        ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
            "sudo dmesg --follow" \
            >> "${LOG_DIR}/dmesg_continuous.log" 2>&1
        RC=$?
        log_sup "TASK[dmesg] exited (${RC}), retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
    done
) &
CHILD_PIDS+=($!)

# Task 3: Periodic journal snapshots
# Each snapshot is a separate timestamped file. Failed snapshots are discarded.
(
    while true; do
        SNAP_TS=$(date +%Y%m%d_%H%M%S)
        SNAP_FILE="${LOG_DIR}/journal_${SNAP_TS}.log"
        if ! ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
                "sudo journalctl --no-pager --lines=100" > "${SNAP_FILE}" 2>&1; then
            log_sup "TASK[journal] snapshot at ${SNAP_TS} failed"
            rm -f "${SNAP_FILE}"
        fi
        sleep "${JOURNAL_INTERVAL_SEC}"
    done
) &
CHILD_PIDS+=($!)

# Task 4: Memory checksum guard
# Re-copies the script on every reconnect in case /tmp was cleared (e.g. Jetson reboot).
(
    while true; do
        log_sup "TASK[memchk] connecting..."
        ssh -n "${SSH_OPTS[@]}" "${JETSON_USER}@${JETSON_IP}" \
            "export MEMCHK_SIZE_MB=${MEMCHK_SIZE_MB} \
                    MEMCHK_ALLOC_INTERVAL=${MEMCHK_ALLOC_INTERVAL} \
                    MEMCHK_CHECK_INTERVAL=${MEMCHK_CHECK_INTERVAL} \
                    MEMCHK_MIN_FREE_PCT=${MEMCHK_MIN_FREE_PCT}; \
             python3 ${MEMCHK_SCRIPT_REMOTE}" \
            >> "${LOG_DIR}/mem_checksum.log" 2>&1
        RC=$?
        log_sup "TASK[memchk] exited (${RC}), retrying in ${RETRY_DELAY}s..."
        # Re-copy script before next attempt (may have been purged from /tmp)
        scp -q "${SSH_OPTS[@]}" "${MEMCHK_SCRIPT_LOCAL}" \
            "${JETSON_USER}@${JETSON_IP}:${MEMCHK_SCRIPT_REMOTE}" 2>/dev/null || true
        sleep $RETRY_DELAY
    done
) &
CHILD_PIDS+=($!)

# ── Done ──────────────────────────────────────────────────────────────────────
log_sup "All 4 tasks started. Logging in progress."
log_sup "  tegrastats (${TEGRASTAT_INTERVAL_MS}ms)    -> tegrastats_continuous.log"
log_sup "  dmesg --follow               -> dmesg_continuous.log"
log_sup "  journal every ${JOURNAL_INTERVAL_SEC}s          -> journal_<timestamp>.log"
log_sup "  memchk (${MEMCHK_SIZE_MB}MB blocks)       -> mem_checksum.log"
log_sup "  supervisor events            -> supervisor.log"

# Block until SIGTERM (handled by trap above)
wait
