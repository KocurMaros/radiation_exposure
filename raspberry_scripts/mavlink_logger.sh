#!/bin/bash
# filepath: /home/user/Projects/radiation_drone/start_relay_logging.sh
# Start MAVLink logging from RPI relay setup

echo "=============================================="
echo "  MAVLink Relay Logger (PC)"
echo "=============================================="
echo "PC IP: 10.11.1.18"
echo "Listening on port: 14550"
echo "Data flow: RPI #1 -> RPI #2 -> PC"
echo "=============================================="

RPI2_IP="192.168.88.15"
PC_PORT="14550"
LOG_DIR="mavlink_logs"

# Check if we're in the right directory
if [ ! -f "cube_logger.py" ]; then
    echo "ERROR: cube_logger.py not found!"
    echo "Please run from ~/Projects/radiation_drone"
    exit 1
fi

# Test connection to RPI #2
echo -n "Testing connection to RPI #2 (${RPI2_IP})... "
if ping -c 1 -W 2 ${RPI2_IP} &>/dev/null; then
    echo "OK"
else
    echo "FAILED"
    echo "ERROR: Cannot reach RPI #2"
    exit 1
fi

# Setup Python venv
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install pymavlink
else
    source venv/bin/activate
fi

# Verify pymavlink is installed
if ! python -c "import pymavlink" 2>/dev/null; then
    pip install pymavlink
fi

echo ""
echo "=============================================="
echo "Starting MAVLink logger..."
echo "Listening on port: ${PC_PORT}"
echo "Log directory: ${LOG_DIR}/"
echo "Press Ctrl+C to stop logging"
echo "=============================================="
echo ""

# Start the logger
python cube_logger.py --port ${PC_PORT} --log-dir ${LOG_DIR}

deactivate