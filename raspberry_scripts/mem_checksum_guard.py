#!/usr/bin/env python3
"""
Continuous memory checksum guard for radiation testing.
Allocates memory blocks periodically and verifies their integrity.
"""
import os
import time
import hashlib
import random
import sys

# Configuration from environment
size_mb = int(os.environ.get('MEMCHK_SIZE_MB', '64'))
alloc_interval = int(os.environ.get('MEMCHK_ALLOC_INTERVAL', '30'))
check_interval = int(os.environ.get('MEMCHK_CHECK_INTERVAL', '60'))
min_free_pct = int(os.environ.get('MEMCHK_MIN_FREE_PCT', '80'))

blocks = []  # (timestamp, bytearray, initial_checksum)
block_id = 0
last_check = 0

def get_mem_info():
    """Return (free_mb, total_mb, free_pct)"""
    try:
        with open('/proc/meminfo') as f:
            lines = f.readlines()
        total = int([x for x in lines if 'MemTotal:' in x][0].split()[1]) / 1024
        avail = int([x for x in lines if 'MemAvailable:' in x][0].split()[1]) / 1024
        pct = (avail / total) * 100 if total > 0 else 0
        return avail, total, pct
    except:
        return 0, 0, 0

print("MEMCHK_START continuous mode, alloc_interval={}s check_interval={}s min_free={}%".format(
    alloc_interval, check_interval, min_free_pct))
sys.stdout.flush()

last_alloc = time.time()
start = time.time()

while True:
    now = time.time()
    elapsed = now - start
    
    # Allocate new block if interval passed and memory available
    if now - last_alloc >= alloc_interval:
        free_mb, total_mb, free_pct = get_mem_info()
        if free_pct >= min_free_pct:
            block_id += 1
            buf = bytearray(os.urandom(size_mb * 1024 * 1024))
            chk = hashlib.sha256(buf).hexdigest()
            blocks.append((now, buf, chk))
            print("t={:7.1f}s ALLOC block_id={} size={}MB free={:.1f}MB ({:.1f}%) blocks={} chk={}".format(
                elapsed, block_id, size_mb, free_mb, free_pct, len(blocks), chk))
            sys.stdout.flush()
            last_alloc = now
        else:
            print("t={:7.1f}s ALLOC_SKIP free={:.1f}MB ({:.1f}%) < {}%, blocks={}".format(
                elapsed, free_mb, free_pct, min_free_pct, len(blocks)))
            sys.stdout.flush()
            last_alloc = now
    
    # Check all blocks if interval passed
    if now - last_check >= check_interval:
        errors = 0
        for i, (ts, buf, orig) in enumerate(blocks):
            # Random access to keep memory active
            idx = random.randrange(0, len(buf) - 1024)
            _ = sum(buf[idx:idx+1024])
            
            current = hashlib.sha256(buf).hexdigest()
            status = "OK" if current == orig else "ERROR"
            if status != "OK":
                errors += 1
                print("t={:7.1f}s CHECK block={} age={:.1f}s status={} chk={}".format(
                    elapsed, i, now - ts, status, current))
                sys.stdout.flush()
        
        free_mb, total_mb, free_pct = get_mem_info()
        print("t={:7.1f}s CHECK_ALL blocks={} errors={} free={:.1f}MB ({:.1f}%)".format(
            elapsed, len(blocks), errors, free_mb, free_pct))
        sys.stdout.flush()
        last_check = now
    
    time.sleep(1)
