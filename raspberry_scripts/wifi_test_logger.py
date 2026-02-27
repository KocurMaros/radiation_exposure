#!/usr/bin/env python3
"""
Simple UDP text logger for WiFi connectivity test messages from RPi3.
Receives plain text messages via UDP and logs to a file.

Usage on PC:
    python3 wifi_test_logger.py --port 14551 --log-dir wifi_logs
"""

import socket
import os
import sys
import argparse
from datetime import datetime
from threading import Thread, Event


class UDPTextLogger:
    """
    Listens on a UDP port, receives plain text messages, and logs to a timestamped file.
    """
    def __init__(self, port, log_base_dir):
        self.port = port
        self.log_base_dir = log_base_dir
        self._stop_event = Event()
        self._thread = None
        self.log_dir = os.path.join(log_base_dir, datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.log_file = None
        self.msg_count = 0
        
    def start(self):
        """Start the logger background thread."""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Log directory created: {self.log_dir}")
        except OSError as e:
            print(f"ERROR creating log directory {self.log_dir}: {e}", file=sys.stderr)
            return
        
        log_path = os.path.join(self.log_dir, "wifi_connectivity.log")
        try:
            self.log_file = open(log_path, 'w')
            print(f"Log file: {log_path}")
        except OSError as e:
            print(f"ERROR opening log file: {e}", file=sys.stderr)
            return
        
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop the logger and close the file."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.log_file:
            self.log_file.close()
        print(f"\nLogger stopped. {self.msg_count} messages logged.")
        print(f"Log saved to: {os.path.join(self.log_dir, 'wifi_connectivity.log')}")
        
    def _run(self):
        """Main UDP listening loop."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(('0.0.0.0', self.port))
            print(f"Listening on UDP port {self.port}...")
            print("Waiting for WiFi connectivity test messages from RPi3...")
            print("="*70)
            
            while not self._stop_event.is_set():
                try:
                    sock.settimeout(1.0)
                    data, addr = sock.recvfrom(1024)
                    message = data.decode('utf-8', errors='ignore').strip()
                    
                    if message:
                        timestamp = datetime.now().isoformat(sep=' ', timespec='milliseconds')
                        log_line = f"[{timestamp}] {addr[0]}:{addr[1]} - {message}"
                        
                        print(log_line)
                        if self.log_file:
                            self.log_file.write(log_line + '\n')
                            self.log_file.flush()
                        
                        self.msg_count += 1
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error receiving data: {e}", file=sys.stderr)
                    
        except OSError as e:
            print(f"Socket error: {e}", file=sys.stderr)
        finally:
            sock.close()


def main():
    parser = argparse.ArgumentParser(description='WiFi Connectivity Test UDP Logger')
    parser.add_argument('--port', type=int, default=14551, help='UDP port to listen on (default: 14551)')
    parser.add_argument('--log-dir', default='wifi_logs', help='Base directory for logs')
    args = parser.parse_args()
    
    print("="*70)
    print("       WiFi Connectivity Test Logger (UDP Text)")
    print("="*70)
    print(f"Listening on: 0.0.0.0:{args.port}")
    print(f"Log directory: {args.log_dir}")
    print("="*70)
    print()
    
    logger = UDPTextLogger(args.port, args.log_dir)
    
    try:
        logger.start()
        while logger._thread and logger._thread.is_alive():
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nUser requested stop (Ctrl+C). Stopping logger...")
    finally:
        logger.stop()


if __name__ == '__main__':
    main()
