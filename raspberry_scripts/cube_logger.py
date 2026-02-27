#!/usr/bin/env python3
# filepath: /home/user/Projects/radiation_drone/cube_logger.py
"""
Network-based MAVLink logger for Orange Cube.
Receives ALL MAVLink messages from Raspberry Pi over UDP and logs to CSV files.

Usage on PC:
    python3 cube_logger.py
    python3 cube_logger.py --port 14550 --log-dir mavlink_logs

On Raspberry Pi, run:
    ./mavlink_forwarder.sh
"""

import time
import csv
import os
import sys
import argparse
from datetime import datetime
from threading import Thread, Event
from pymavlink import mavutil


class MavlinkNetworkLogger:
    """
    Connects to a MAVLink source over UDP, reads ALL messages, and logs each message type 
    to its own dedicated CSV file within a timestamped directory.
    """
    def __init__(self, connection_string, log_base_dir):
        self.connection_string = connection_string
        self.log_base_dir = log_base_dir
        
        # Runtime variables
        self._stop_event = Event()
        self._thread = None
        self._stats_thread = None
        self._mav = None
        self._csv_writers = {}  # {msg_type: csv.DictWriter}
        self._csv_files = {}    # {msg_type: file_object}
        self.log_dir = os.path.join(log_base_dir, datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        # Statistics
        self.msg_count = {}
        self.start_time = None
        self.last_stats_time = None
        
        # Standard fields for every log line
        self.common_fieldnames = ['SystemTime_ISO', 'MsgType', 'FC_Time_us']

    def start(self):
        """Start the logger background thread."""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Log directory created: {self.log_dir}")
        except OSError as e:
            print(f"ERROR creating log directory {self.log_dir}: {e}", file=sys.stderr)
            return

        self.start_time = time.time()
        self.last_stats_time = self.start_time
        
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        
        # Start statistics thread
        self._stats_thread = Thread(target=self._print_stats, daemon=True)
        self._stats_thread.start()

    def stop(self):
        """Stop the background thread and close all connections/files."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            
        # Close all open CSV files
        for f in self._csv_files.values():
            f.close()
        
        # Print final statistics
        print("\n" + "="*70)
        print("FINAL STATISTICS")
        print("="*70)
        self._print_message_stats()
        print(f"\nLogger stopped. {len(self._csv_files)} log files closed.")
        print(f"Logs saved to: {self.log_dir}")
        print("\nLog files created:")
        for msg_type in sorted(self._csv_files.keys()):
            count = self.msg_count.get(msg_type, 0)
            print(f"  {msg_type}.csv - {count} messages")

    def _run(self):
        """Main logging loop."""
        while not self._stop_event.is_set():
            try:
                print(f"Connecting to {self.connection_string}...")
                self._mav = mavutil.mavlink_connection(
                    self.connection_string,
                    dialect="ardupilotmega"
                )
                
                # Wait for a heartbeat to establish a connection
                print("Waiting for heartbeat...")
                self._mav.wait_heartbeat(timeout=30)
                print(f"✓ Heartbeat received from system {self._mav.target_system} component {self._mav.target_component}")
                print(f"✓ Starting logging to: {self.log_dir}")
                print("="*70)
                
                # Request all data streams at maximum rate
                self._mav.mav.request_data_stream_send(
                    self._mav.target_system, 
                    self._mav.target_component, 
                    mavutil.mavlink.MAV_DATA_STREAM_ALL, 
                    50,  # Request 50Hz for all streams
                    1    # Start streaming
                )
                
                # Main message logging loop - log EVERYTHING
                while not self._stop_event.is_set():
                    msg = self._mav.recv_match(blocking=False, timeout=0.1)
                    if msg is not None:
                        msg_type = msg.get_type()
                        # Log everything except BAD_DATA
                        if msg_type != 'BAD_DATA':
                            self._log_message(msg)
                            # Update statistics
                            self.msg_count[msg_type] = self.msg_count.get(msg_type, 0) + 1

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Connection Error: {e}", file=sys.stderr)
                # Brief pause before reconnect attempt
                for _ in range(3):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
            finally:
                if self._mav:
                    try:
                        self._mav.close()
                    except Exception:
                        pass
                    self._mav = None

    def _log_message(self, msg):
        """Processes a MAVLink message and writes it to the appropriate CSV."""
        msg_type = msg.get_type()
        data_dict = msg.to_dict()
        
        # 1. Prepare the row data
        row = {
            'SystemTime_ISO': datetime.now().isoformat(sep=' ', timespec='milliseconds'),
            'MsgType': msg_type,
            'FC_Time_us': data_dict.pop('time_usec', data_dict.pop('time_boot_ms', 0)) 
        }

        # Remove MAVLink protocol overhead fields for cleaner CSV
        for key in list(data_dict.keys()):
            if key in ['magic', 'timestamp', 'crc', 'msgid', 'wire_len', 'hash', 'header']:
                 data_dict.pop(key, None)
                 
        row.update(data_dict)

        # 2. Get or create the CSV writer for this message type
        if msg_type not in self._csv_writers:
            self._create_csv_writer(msg_type, row)
        
        # 3. Write the row
        self._csv_writers[msg_type].writerow(row)
        
        # Flush every 50 messages to balance performance and data safety
        if self.msg_count.get(msg_type, 0) % 50 == 0:
            self._csv_files[msg_type].flush()

    def _create_csv_writer(self, msg_type, row):
        """Creates a new CSV file and DictWriter for a new message type."""
        fieldnames = self.common_fieldnames + sorted([k for k in row.keys() if k not in self.common_fieldnames])
        
        file_path = os.path.join(self.log_dir, f"{msg_type}.csv")
        print(f"   -> Creating log file: {msg_type}.csv")
        
        f = open(file_path, 'w', newline='')
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        self._csv_files[msg_type] = f
        self._csv_writers[msg_type] = writer

    def _print_stats(self):
        """Periodically print statistics."""
        while not self._stop_event.is_set():
            time.sleep(5)  # Print stats every 5 seconds
            if self.msg_count:
                self._print_message_stats()

    def _print_message_stats(self):
        """Print current message statistics."""
        if not self.msg_count:
            return
        
        elapsed = time.time() - self.start_time
        total_msgs = sum(self.msg_count.values())
        rate = total_msgs / elapsed if elapsed > 0 else 0
        
        print(f"\n[Stats] Runtime: {elapsed:.1f}s | Total: {total_msgs} msgs | Rate: {rate:.1f} msg/s")
        print(f"Message types logged: {len(self.msg_count)}")
        
        # Show top 10 message types
        sorted_msgs = sorted(self.msg_count.items(), key=lambda x: x[1], reverse=True)
        print("Top message types:")
        for msg_type, count in sorted_msgs[:10]:
            msg_rate = count / elapsed if elapsed > 0 else 0
            print(f"  {msg_type:<25} {count:>7} msgs  ({msg_rate:>6.1f} Hz)")
        
        if len(sorted_msgs) > 10:
            print(f"  ... and {len(sorted_msgs) - 10} more message types")


def main():
    parser = argparse.ArgumentParser(description='Network-based MAVLink Logger - Logs ALL messages')
    parser.add_argument('--port', type=int, default=14550, help='UDP port to listen on (default: 14550)')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--log-dir', default='mavlink_logs', help='Base directory for logs')
    args = parser.parse_args()
    
    connection_string = f"udpin:{args.host}:{args.port}"
    
    print("="*70)
    print("       MAVLink Network Logger (ALL Messages)")
    print("="*70)
    print(f"Listening on: {args.host}:{args.port}")
    print(f"Log directory: {args.log_dir}")
    print(f"Waiting for MAVLink data from Raspberry Pi...")
    print("="*70)
    
    logger = MavlinkNetworkLogger(connection_string, args.log_dir)
    
    try:
        logger.start()
        # Keep the main thread alive until user stops the script (Ctrl+C)
        while logger._thread and logger._thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nUser requested stop (Ctrl+C). Stopping logger...")
    finally:
        logger.stop()


if __name__ == '__main__':
    main()