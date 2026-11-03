#!/bin/sh
# Runs the given Python script with the first working Python 3.9+: python3, then `py -3` (Windows launcher), then python.
# On Windows `python3`/`python` can be the Microsoft Store placeholder ("Python was not found"); it fails the probe and is skipped.
# The probe reads nothing from stdin, so the hook's JSON input still reaches the script.
for c in python3 "py -3" python; do
    if $c -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1; then
        exec $c "$@"
    fi
done
echo "now-kit: no working Python 3.9+ found (tried python3, py -3, python)" >&2
exit 1
