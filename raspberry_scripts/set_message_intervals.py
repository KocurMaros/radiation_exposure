#!/usr/bin/env python3
"""
One-shot helper to request fixed MAVLink message intervals directly on the flight controller.
Run this before starting mavproxy to stabilize per-message rates.
"""
import sys
import time
from pymavlink import mavutil

# Configuration: adjust as needed
FC_DEV = "/dev/ttyACM0"
FC_BAUD = 921600
TARGETS = [
    ("BATTERY_STATUS", mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS, 1),
    ("ATTITUDE", mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, 20),
    ("SCALED_IMU", mavutil.mavlink.MAVLINK_MSG_ID_SCALED_IMU, 50),
    ("SCALED_IMU2", mavutil.mavlink.MAVLINK_MSG_ID_SCALED_IMU2, 50),
    ("SCALED_IMU3", mavutil.mavlink.MAVLINK_MSG_ID_SCALED_IMU3, 50),
]


def main():
    print(f"Connecting to FC {FC_DEV} @ {FC_BAUD} ...")
    mav = mavutil.mavlink_connection(FC_DEV, baud=FC_BAUD)
    mav.wait_heartbeat(timeout=15)
    print(f"Heartbeat from system {mav.target_system} component {mav.target_component}")

    for name, msg_id, rate_hz in TARGETS:
        interval_us = int(1_000_000 / rate_hz) if rate_hz > 0 else 0
        print(f"Request {name} ({msg_id}) at {rate_hz} Hz (interval {interval_us} us)")
        mav.mav.command_long_send(
            mav.target_system,
            mav.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            msg_id,
            interval_us,
            0, 0, 0, 0, 0,
        )
        # wait for ack
        ack = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
        if ack and ack.command == mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL:
            if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                print(f"  -> accepted")
            else:
                print(f"  -> result={ack.result}")
        else:
            print("  -> no ack")
        time.sleep(0.2)

    mav.close()
    print("Done sending intervals.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
