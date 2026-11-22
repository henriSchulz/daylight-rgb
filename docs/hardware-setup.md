# Hardware and network setup

## The display

The project was developed with an RGB Technology colour LED sign:

| Item | Tested device |
|---|---|
| Controller | product "Ko5G", hardware "GIGG", firmware 01.25 |
| Resolution | 288 x 16 px, 8-bit RGB |
| Physical layout | three separate panels driven by three ports: 128, 64 and 96 px wide |
| Modules | board type 4 (32 x 16 px, four 16 x 8 address fragments each) |
| Storage | SD card, 916 MB |
| Interfaces | 100 Mbit Ethernet, Wi-Fi (access point or client), web interface |
| Sensors | temperature, ambient light |

Other sizes and panel arrangements should work as long as the controller speaks the same protocol: all
geometry is read from the device configuration (`python -m ko5g status`).

## Connecting a computer

The controller has a fixed IP address and no DHCP server on its Ethernet port. Connect it directly to a
computer (a USB Ethernet adapter is fine) or to a switch, and give the computer a static address in the
same subnet.

macOS example (replace the service name and addresses with yours):

```sh
networksetup -listallnetworkservices          # find the adapter, e.g. "USB 10/100/1000 LAN"
sudo networksetup -setmanual "<service>" <computer-ip> <netmask>
```

`<computer-ip>` is a free address in the display's subnet (e.g. the display's address with a different
last number) and `<netmask>` usually `255.255.255.0`.

Leave the router field empty so that the computer keeps using its normal connection for the internet.

Check the connection:

```sh
ping <display-ip>
nc -z <display-ip> 2101 && echo "data port open"
```

If you don't know the display's address, look at the label or documentation of the installation, or ask
the installer. The controller also offers its own Wi-Fi access point; its settings are shown in the web
interface.

## Web interface

`http://<display-ip>/` (HTTP Basic authentication; the credentials are set by the installer). It shows
network settings, status (clock, temperature, ambient light, firmware) and the current mode, and lets you
change network settings, the password and the firmware. This project only reads from it (see
[protocol.md §10](protocol.md#10-web-interface-port-80)).

## Software

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export KO5G_HOST=<display-ip>
.venv/bin/python -m ko5g status
```

`status` prints the size, the panels and the current composition. If it works, the setup is complete.
