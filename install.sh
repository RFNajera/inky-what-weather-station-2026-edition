#!/usr/bin/env bash
#
# install.sh - one-shot installer for the Inky wHAT weather station on
#              Debian 13 "trixie" (Raspberry Pi Zero 2 W).
#
# What it does:
#   1. Installs system packages (Python venv, build deps, fonts, SPI tools).
#   2. Enables the SPI + I2C interfaces and the spi0-0cs overlay.
#   3. Creates a Python virtual environment and installs Pillow + inky.
#   4. Installs a systemd *user* timer that refreshes the screen every 30 min.
#   5. Sets up headless Wi-Fi provisioning (Comitup) + a setup-mode screen.
#   6. Does a first render so the display shows weather right away.
#
# Run it from inside the project folder as the normal user (NOT root):
#       cd ~/inky-what-weather-station-2026-edition && ./install.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_DIR/venv"

if [[ $EUID -eq 0 ]]; then
    echo "Please run as your normal user (it will sudo when needed), not as root."
    exit 1
fi

# Hotspot name shown when the station can't find a known Wi-Fi network.
SETUP_SSID="WeatherStation-Setup"

echo "==> 1/6  Installing system packages (needs sudo) ..."
sudo apt-get update
sudo apt-get install -y \
    python3 python3-venv python3-pip python3-dev \
    libopenjp2-7 libjpeg-dev zlib1g-dev \
    fonts-dejavu-core \
    i2c-tools git

echo "==> 2/6  Enabling SPI and I2C ..."
# Prefer raspi-config when present (non-interactive flags).
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_spi 0   # 0 = enable
    sudo raspi-config nonint do_i2c 0
fi

# Make sure the overlays are in the firmware config regardless.
CONFIG=/boot/firmware/config.txt
[[ -f "$CONFIG" ]] || CONFIG=/boot/config.txt   # very old layouts
add_line() { grep -qxF "$1" "$CONFIG" || echo "$1" | sudo tee -a "$CONFIG" >/dev/null; }
add_line "dtparam=spi=on"
add_line "dtparam=i2c_arm=on"
# The Inky driver needs a single chip-select line on SPI0.
add_line "dtoverlay=spi0-0cs"

echo "==> 3/6  Creating Python virtual environment ..."
# --system-site-packages lets the venv see any apt-installed GPIO libs,
# which avoids common RPi.GPIO/gpiod build headaches on the Zero 2 W.
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
# The [rpi] extra pulls in the hardware backends (gpiod/spidev/etc.).
"$VENV/bin/pip" install "Pillow" "inky[rpi]"

echo "==> 4/6  Installing the systemd user timer (every 30 min) ..."
mkdir -p "$HOME/.config/systemd/user"
cp "$PROJECT_DIR/inky-weather.service" "$HOME/.config/systemd/user/"
cp "$PROJECT_DIR/inky-weather.timer"   "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now inky-weather.timer
# Let user services run even when you're not logged in (headless Pi).
sudo loginctl enable-linger "$USER"

echo "==> 5/6  Setting up headless Wi-Fi provisioning (Comitup) ..."
# Comitup brings up a 'WeatherStation-Setup' hotspot whenever the Pi can't
# reach a known network, so you can add new Wi-Fi from your phone - no screen
# or keyboard needed. It requires NetworkManager, which is the default on
# Raspberry Pi OS / Debian trixie.
if ! command -v nmcli >/dev/null 2>&1; then
    sudo apt-get install -y network-manager
fi
# Comitup ships in Debian; fall back to the maintainer's repo if it's missing.
if ! sudo apt-get install -y comitup 2>/dev/null; then
    echo "   comitup not in apt; adding the maintainer package repo ..."
    sudo apt-get install -y wget
    wget -qO /tmp/davesteele.gpg \
        https://davesteele.github.io/key-366150CE.pub.txt || true
    sudo apt-get install -y \
        "$(wget -qO- https://davesteele.github.io/comitup/latest.package || true)" \
        || echo "   NOTE: install comitup manually - see davesteele.github.io/comitup"
fi

# --- Hotspot password (stored ONLY on this device, never in the repo) -------
# Generate a simple, memorable phrase like "sunny-cloud-42" the first time,
# then reuse it on future runs so the password stays stable. The phrase lives
# in PASSWORD_FILE, which is .gitignored and never committed.
PASSWORD_FILE="$PROJECT_DIR/wifi_password.txt"
if [[ ! -s "$PASSWORD_FILE" ]]; then
    ADJ=(sunny cloudy rainy windy frosty stormy misty breezy snowy hazy)
    NOUN=(cloud storm breeze meadow river summit harbor comet ember willow)
    a=${ADJ[$RANDOM % ${#ADJ[@]}]}
    n=${NOUN[$RANDOM % ${#NOUN[@]}]}
    num=$(( RANDOM % 90 + 10 ))          # two digits
    # WPA passwords must be 8-63 chars; "adjective-noun-NN" satisfies this.
    echo "${a}-${n}-${num}" > "$PASSWORD_FILE"
    chmod 600 "$PASSWORD_FILE"
    echo "   Generated a new hotspot password (saved locally, not in git)."
fi
AP_PASSWORD="$(cat "$PASSWORD_FILE")"

# Write Comitup config: our friendly hotspot name, a password so the hotspot
# is secured, and a callback that drives the display.
sudo tee /etc/comitup.conf >/dev/null <<EOF
# Managed by the Inky wHAT weather station installer.
ap_name: $SETUP_SSID
ap_password: $AP_PASSWORD
external_callback: /usr/local/bin/comitup-callback
service_name: comitup
EOF
sudo chmod 600 /etc/comitup.conf   # keep the password readable only by root

# Install the callback with this project's path baked in, then make it runnable.
sudo cp "$PROJECT_DIR/comitup-callback.sh" /usr/local/bin/comitup-callback
sudo sed -i "s|__PROJECT_DIR__|$PROJECT_DIR|" /usr/local/bin/comitup-callback
sudo sed -i "s|^SETUP_SSID=.*|SETUP_SSID=\"$SETUP_SSID\"|" /usr/local/bin/comitup-callback
sudo chmod +x /usr/local/bin/comitup-callback

# NetworkManager must own wifi for Comitup to work. Enable the services.
sudo systemctl enable NetworkManager 2>/dev/null || true
sudo systemctl enable comitup comitup-web 2>/dev/null || true

echo "==> 6/6  First render ..."
# This may fail if SPI was just enabled and a reboot is still pending -
# that's fine, the timer will catch it after you reboot.
"$VENV/bin/python" "$PROJECT_DIR/weather.py" || \
    echo "   (First render failed - this is normal before the first reboot.)"

echo
echo "Done!  If this was the first time enabling SPI/I2C, reboot now:"
echo "    sudo reboot"
echo
echo "Useful commands:"
echo "    systemctl --user list-timers inky-weather.timer   # next weather run"
echo "    systemctl --user start inky-weather.service        # update now"
echo "    journalctl --user -u inky-weather.service -n 30    # weather logs"
echo
echo "Wi-Fi setup (when moved to a new network):"
echo "    The station auto-opens a '$SETUP_SSID' hotspot when it can't"
echo "    connect. Join it from your phone and follow the on-screen steps."
echo "    Hotspot password (also shown on the display): $AP_PASSWORD"
echo "    It is stored locally in wifi_password.txt and is NOT in git."
echo "    Preview the setup screen: python3 setup_screen.py --preview"
echo "    Comitup logs: sudo journalctl -u comitup -n 30"
