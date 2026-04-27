# Radiation exposure experiment scripts

## Overview

Two scripts run on the Raspberry Pi as systemd services and log everything to a USB drive at `/mnt/log_usb/`:

| Script | What it logs | Output |
|---|---|---|
| `rpi_full_mavlink_logger.py` | All MAVLink messages from Cube via serial (`/dev/ttyACM0`) | `/mnt/log_usb/mavlink/<timestamp>/*.csv` |
| `jetson_logger.sh` | Jetson tegrastats, dmesg, journal snapshots, memory checksum guard via SSH (`192.168.55.1`) | `/mnt/log_usb/jetson/<timestamp>/` |

Both are grouped under `radiation-logging.target` and start automatically on boot.


## Requirements 

``` bash
sudo apt install sshpass
TODO: pymavlink, pyserial ...
```

## Deployment (first time on a new RPi)

```bash
# 1. Deploy scripts
sudo mkdir -p /opt/radiation_logging
sudo cp raspberry_scripts/rpi_full_mavlink_logger.py \
        raspberry_scripts/jetson_logger.sh \
        raspberry_scripts/mem_checksum_guard.py \
        /opt/radiation_logging/
sudo chmod +x /opt/radiation_logging/jetson_logger.sh

# 2. Install services
sudo cp raspberry_scripts/cube-mavlink-logger.service \
        raspberry_scripts/jetson-logger.service \
        raspberry_scripts/radiation-logging.target \
        /etc/systemd/system/
sudo systemctl daemon-reload

# 3. Enable (auto-starts on every boot)
sudo systemctl enable radiation-logging.target
```

## Starting / stopping

```bash
# Start both loggers
sudo systemctl start radiation-logging.target

# Stop both loggers
sudo systemctl stop radiation-logging.target

# Status of individual loggers
systemctl status cube-mavlink-logger jetson-logger
```

## Monitoring

```bash
# Live journal output from each service
journalctl -u cube-mavlink-logger -f
journalctl -u jetson-logger -f

# Jetson task-level events (retries, disconnects)
tail -f /mnt/log_usb/jetson/<session_ts>/supervisor.log
```

## Journal size on RPi

The RPi has limited storage (2 GB). To prevent the systemd journal from growing unbounded, add this to `/etc/systemd/journald.conf`:

```ini
SystemMaxUse=100M
```

Then restart the journal: `sudo systemctl restart systemd-journald`

All actual experiment data goes to the USB drive, not to the journal, so this cap has no effect on logged data.

## Troubleshooting

If the scripts wont run on a new drone, it is possible that they need sudo priviliges and you may need to add rules to visudo (don't add to main file): 

``` bash
sudo visudo -f /etc/sudoers.d/zz-jetson-logger

### Put this line in it
dcs_user ALL=(ALL:ALL) NOPASSWD: /bin/journalctl, /bin/dmesg, /usr/bin/tegrastats, /usr/bin/python3
### Put this line in it

sudo chown root:root /etc/sudoers.d/zz-jetson-logger
sudo chmod 440 /etc/sudoers.d/zz-jetson-logger
```

You can test if it works by running this on jetson:
``` bash
sudo -k
sudo -n /bin/journalctl --boot --no-pager | head
sudo -n /bin/dmesg | head
sudo -n /usr/bin/tegrastats --interval 1000
```


## Polish from GPT
``` bash
ssh-keygen -t ed25519
ssh-copy-id dcs_user@192.168.55.1
```