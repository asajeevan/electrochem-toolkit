#!/bin/sh
# Cyclara.app/Contents/MacOS/Cyclara: start the bundled Python on electrochem.studio.
# The interpreter is Contents/MacOS/cyclara-python, inside the bundle, so macOS attributes
# the process to Cyclara.app: the Dock icon, the application menu and the name all read
# Cyclara. -I keeps a user's own Python settings and packages out of the way.
here="$(cd "$(dirname "$0")/.." && pwd)"
exec "$here/MacOS/cyclara-python" -I -X utf8 -m electrochem.studio "$@"
