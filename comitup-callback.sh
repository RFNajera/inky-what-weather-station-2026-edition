#!/usr/bin/env bash
#
# comitup-callback.sh - Comitup external_callback for the weather station.
#
# Comitup runs this script on every Wi-Fi state change, passing one argument:
#     HOTSPOT     - no known network reachable; the setup hotspot is now up
#     CONNECTING  - attempting to join a network
#     CONNECTED   - joined a network and online
#
# We use it to drive the Inky wHAT:
#   * HOTSPOT   -> show the "Wi-Fi SETUP MODE" instruction screen
#   * CONNECTED -> re-render the normal weather display
#
# The installer copies this to /usr/local/bin/comitup-callback and points
# comitup.conf's `external_callback` at it. It runs as root (Comitup's user),
# so we invoke the project's venv Python by absolute path.

set -u

# ---- Edit these two lines only if you move the project or change the SSID ---
PROJECT_DIR="__PROJECT_DIR__"           # filled in by install.sh
SETUP_SSID="WeatherStation-Setup"       # must match comitup.conf ap_name
# -----------------------------------------------------------------------------

PY="$PROJECT_DIR/venv/bin/python"
STATE="${1:-}"

# The setup screen reads the (local, git-ignored) hotspot password itself from
# $PROJECT_DIR/wifi_password.txt, so we don't need to pass it here.

log() { logger -t inky-weather-wifi "$*"; echo "$*"; }

case "$STATE" in
    HOTSPOT)
        log "Entered HOTSPOT mode - showing setup screen"
        "$PY" "$PROJECT_DIR/setup_screen.py" --ssid "$SETUP_SSID" \
            || log "setup_screen render failed"
        ;;
    CONNECTED)
        log "CONNECTED - refreshing weather"
        # Give DNS/routing a couple seconds to settle before hitting the APIs.
        sleep 3
        "$PY" "$PROJECT_DIR/weather.py" \
            || log "weather render failed"
        ;;
    CONNECTING|*)
        # Nothing to draw for CONNECTING; leave the current screen as-is.
        log "State: $STATE (no display change)"
        ;;
esac

exit 0
