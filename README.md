# Radiation exposure experiment scripts

TODO: 

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