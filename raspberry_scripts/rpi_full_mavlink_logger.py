#!/usr/bin/env python3
"""
Raspberry Pi MAVLink logger that:
- Connects directly to the Cube via serial (default /dev/ttyACM0 @ 921600 baud).
- Requests *all* known MAVLink message IDs at a fixed rate (via MAV_CMD_SET_MESSAGE_INTERVAL).
- Also requests the generic MAV_DATA_STREAM_ALL as a fallback.
- Logs every received message to CSV files under mavlink_logs/<timestamp>/, one file per message type.
- Flushes every write so data is preserved even if power/network drops.

Run on the RPi:
    python3 rpi_full_mavlink_logger.py --device /dev/ttyACM0 --baud 921600 --rate-hz 10

You can change --rate-hz to request a different per-message rate. The script will keep
running until stopped with Ctrl+C.
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime
from typing import Dict, Tuple, List
from pymavlink import mavutil


def discover_message_ids() -> List[Tuple[str, int]]:
    """Collect all MAVLink message IDs exposed by pymavlink (ardupilotmega dialect)."""
    msg_ids: List[Tuple[str, int]] = []
    for name in dir(mavutil.mavlink):
        if not name.startswith("MAVLINK_MSG_ID_"):
            continue
        try:
            msg_id = int(getattr(mavutil.mavlink, name))
        except Exception:
            continue
        msg_name = name.replace("MAVLINK_MSG_ID_", "")
        msg_ids.append((msg_name, msg_id))
    # Deduplicate and sort by ID for deterministic ordering
    unique = {}
    for msg_name, msg_id in msg_ids:
        unique[msg_id] = msg_name
    return [(name, msg_id) for msg_id, name in sorted(unique.items(), key=lambda x: x[0])]


class RpiMavlinkLogger:
    def __init__(self, device: str, baud: int, log_base_dir: str, rate_hz: float) -> None:
        self.device = device
        self.baud = baud
        self.rate_hz = rate_hz
        self.log_base_dir = log_base_dir
        self.log_dir = os.path.join(log_base_dir, datetime.now().strftime("%Y%m%d_%H%M%S"))

        self._mav = None
        self._csv_writers: Dict[str, csv.DictWriter] = {}
        self._csv_files: Dict[str, any] = {}
        self.common_fieldnames = ["SystemTime_ISO", "MsgType", "FC_Time_us"]

    def _open_connection(self) -> None:
        print(f"Connecting to {self.device} @ {self.baud} ...")
        self._mav = mavutil.mavlink_connection(
            self.device,
            baud=self.baud,
            dialect="ardupilotmega",
        )
        self._mav.wait_heartbeat(timeout=20)
        print(f"Heartbeat from system {self._mav.target_system} component {self._mav.target_component}")

    def _request_all_intervals(self) -> None:
        interval_us = int(1_000_000 / self.rate_hz) if self.rate_hz > 0 else 0
        print(f"Requesting per-message intervals for all known IDs at {self.rate_hz} Hz (interval {interval_us} us)")
        all_ids = discover_message_ids()
        for msg_name, msg_id in all_ids:
            try:
                self._mav.mav.command_long_send(
                    self._mav.target_system,
                    self._mav.target_component,
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                    0,
                    msg_id,
                    interval_us,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
                # Non-blocking ack check; many autopilots may not ACK every ID
                ack = self._mav.recv_match(type="COMMAND_ACK", blocking=False, timeout=0)
                if ack and ack.command == mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL and ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    print(f"  {msg_name:<25} id={msg_id:<4} -> result {ack.result}")
            except Exception as exc:
                # Keep going even if some IDs are not supported
                print(f"  {msg_name:<25} id={msg_id:<4} -> error {exc}")
                continue
        print("Finished sending interval requests.")

        # Generic stream request as a safety net
        try:
            self._mav.mav.request_data_stream_send(
                self._mav.target_system,
                self._mav.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                int(max(self.rate_hz, 1)),
                1,
            )
            print("Requested MAV_DATA_STREAM_ALL as fallback.")
        except Exception as exc:
            print(f"Warning: failed to request MAV_DATA_STREAM_ALL ({exc})")

    def _prepare_logging(self) -> None:
        os.makedirs(self.log_dir, exist_ok=True)
        print(f"Logging to: {self.log_dir}")

    def _create_writer(self, msg_type: str, row: dict) -> None:
        fieldnames = self.common_fieldnames + sorted([k for k in row.keys() if k not in self.common_fieldnames])
        file_path = os.path.join(self.log_dir, f"{msg_type}.csv")
        print(f"   -> Creating log file: {msg_type}.csv")
        f = open(file_path, "w", newline="")
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        self._csv_files[msg_type] = f
        self._csv_writers[msg_type] = writer

    def _log_message(self, msg) -> None:
        msg_type = msg.get_type()
        if msg_type == "BAD_DATA":
            return
        data = msg.to_dict()
        row = {
            "SystemTime_ISO": datetime.now().isoformat(sep=" ", timespec="milliseconds"),
            "MsgType": msg_type,
            "FC_Time_us": data.pop("time_usec", data.pop("time_boot_ms", 0)),
        }
        for key in list(data.keys()):
            if key in ["magic", "timestamp", "crc", "msgid", "wire_len", "hash", "header"]:
                data.pop(key, None)
        row.update(data)

        if msg_type not in self._csv_writers:
            self._create_writer(msg_type, row)

        writer = self._csv_writers[msg_type]
        writer.writerow(row)
        # Flush every write to satisfy "save after every read" requirement
        self._csv_files[msg_type].flush()

    def run(self) -> None:
        self._prepare_logging()
        self._open_connection()
        self._request_all_intervals()

        print("Starting log loop. Press Ctrl+C to stop.")
        try:
            while True:
                msg = self._mav.recv_match(blocking=True, timeout=1.0)
                if msg is not None:
                    self._log_message(msg)
        except KeyboardInterrupt:
            print("\nStopping (Ctrl+C)")
        finally:
            for f in self._csv_files.values():
                try:
                    f.close()
                except Exception:
                    pass
            if self._mav:
                try:
                    self._mav.close()
                except Exception:
                    pass
            print(f"Logs saved under {self.log_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Raspberry Pi MAVLink full logger")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Serial device for Cube (default: /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=921600, help="Baud rate (default: 921600)")
    parser.add_argument("--log-dir", default="mavlink_logs", help="Base log directory (default: mavlink_logs)")
    parser.add_argument("--rate-hz", type=float, default=10.0, help="Requested per-message rate in Hz (default: 10)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = RpiMavlinkLogger(args.device, args.baud, args.log_dir, args.rate_hz)
    logger.run()


if __name__ == "__main__":
    main()
