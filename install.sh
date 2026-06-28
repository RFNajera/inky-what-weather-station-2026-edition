#!/usr/bin/env bash
#
# install.sh - one-shot installer for the Inky wHAT weather station on
#              Debian 13 "trixie" (Raspberry Pi Zero 2 W).
#
# What it does:
#   1. Installs system packages (Python venv, build deps, fonts, SPI tools).
#   2. Enables the SPI + I2C interfaces and the spi0-0cs overlay.
#   3. Creates a Python virtual environment and installs Pillow + inky.
#   4. Installs a systemd *user* timer that refreshes the screen every hour.
#   5. Does a first render so the display shows weather right away.
#
# Run it from inside the project folder as the normal user (NOT root):
#       cd ~/inky-weather && ./install.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_DIR/venv"

if [[ $EUID -eq 0 ]]; then
    echo "Please run as your normal user (it will sudo when needed), not as root."
    exit 1
fi

echo "==> 1/5  Installing system packages (needs sudo) ..."
sudo apt-get update
sudo apt-get install -y \
    python3 python3-venv python3-pip python3-dev \
    libopenjp2-7 libjpeg-dev zlib1g-dev \
    fonts-dejavu-core \
    i2c-tools git

echo "==> 2/5  Enabling SPI and I2C ..."
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

echo "==> 3/5  Creating Python virtual environment ..."
# --system-site-packages lets the venv see any apt-installed GPIO libs,
# which avoids common RPi.GPIO/gpiod build headaches on the Zero 2 W.
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
# The [rpi] extra pulls in the hardware backends (gpiod/spidev/etc.).
"$VENV/bin/pip" install "Pillow" "inky[rpi]"

echo "==> 4/5  Installing the hourly systemd user timer ..."
mkdir -p "$HOME/.config/systemd/user"
cp "$PROJECT_DIR/inky-weather.service" "$HOME/.config/systemd/user/"
cp "$PROJECT_DIR/inky-weather.timer"   "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now inky-weather.timer
# Let user services run even when you're not logged in (headless Pi).
sudo loginctl enable-linger "$USER"

echo "==> 5/5  First render ..."
# This may fail if SPI was just enabled and a reboot is still pending -
# that's fine, the timer will catch it after you reboot.
"$VENV/bin/python" "$PROJECT_DIR/weather.py" || \
    echo "   (First render failed - this is normal before the first reboot.)"

echo
echo "Done!  If this was the first time enabling SPI/I2C, reboot now:"
echo "    sudo reboot"
echo
echo "Useful commands:"
echo "    systemctl --user list-timers inky-weather.timer   # next run"
echo "    systemctl --user start inky-weather.service        # update now"
echo "    journalctl --user -u inky-weather.service -n 30    # logs"
