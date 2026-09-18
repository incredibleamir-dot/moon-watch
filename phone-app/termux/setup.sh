#!/data/data/com.termux/files/usr/bin/sh
# Moon Watch Link - one-shot Termux setup.
# Run once inside Termux on the phone:
#     bash setup.sh
# Then start streaming:
#     python aim.py            # auto-finds the desktop on the LAN
#     python aim.py 192.168.1.10

set -e

pkg update -y
pkg install -y python termux-api

echo
echo "Setup complete."
echo
echo "IMPORTANT: 'termux-api' commands (sensors, GPS) need the"
echo "            'Termux:API' ANDROID APP, which exists only on F-Droid."
echo "            If termux-sensor says 'not yet available', your Termux is"
echo "            the Google Play build -> uninstall BOTH apps and install"
echo "            BOTH from https://f-droid.org (F-Droid)."
echo
echo "Next steps:"
echo "  1. Install the 'Termux:API' app from F-Droid, open it once."
echo "  2. First run of aim.py will ask for the LOCATION permission:"
echo "     that is what feeds GPS to the desktop sky map."
echo "  3. Start streaming:"
echo "       python aim.py"