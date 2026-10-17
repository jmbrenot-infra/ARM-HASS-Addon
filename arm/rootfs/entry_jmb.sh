#!/bin/bash
# Entry point (jmbrenot-infra fork): start the disc watcher when `auto_rip` is enabled,
# then hand over to the upstream add-on start script.

AUTO_RIP=$(python3 -c 'import json; print(str(json.load(open("/data/options.json")).get("auto_rip", True)).lower())' 2>/dev/null || echo true)
if [ "$AUTO_RIP" = "true" ]; then
    echo "[INFO] auto_rip enabled: starting disc watcher"
    /usr/local/bin/arm_disc_watcher.sh &
else
    echo "[INFO] auto_rip disabled: use the web UI Manual start"
fi
exec /run.sh
