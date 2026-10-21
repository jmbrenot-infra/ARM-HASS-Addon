#!/bin/bash
# Entry point (jmbrenot-infra fork): start the disc watcher when `auto_rip` is enabled,
# then hand over to the upstream add-on start script.
#
# This stays alive as PID 1 and runs /run.sh as a background child instead of exec'ing
# into it, so a trap can forward SIGTERM/SIGINT to it. Supervisor sends its stop signal
# to PID 1; without a trap here that signal had no handler and the app was killed by the
# default action instead of shutting down cleanly (jmbrenot-infra/ARM-HASS-Addon#7).

# shellcheck disable=SC2317  # reachable via the trap below, not sequential flow
_term() {
    echo "[INFO] entry_jmb: caught SIGTERM, forwarding to ARM (pid ${run_pid})"
    kill -TERM "$run_pid" 2>/dev/null
}
trap _term SIGTERM

# shellcheck disable=SC2317  # reachable via the trap below, not sequential flow
_int() {
    echo "[INFO] entry_jmb: caught SIGINT, forwarding to ARM (pid ${run_pid})"
    kill -INT "$run_pid" 2>/dev/null
}
trap _int SIGINT

AUTO_RIP=$(python3 -c 'import json; print(str(json.load(open("/data/options.json")).get("auto_rip", True)).lower())' 2>/dev/null || echo true)
if [ "$AUTO_RIP" = "true" ]; then
    echo "[INFO] auto_rip enabled: starting disc watcher"
    /usr/local/bin/arm_disc_watcher.sh &
else
    echo "[INFO] auto_rip disabled: use the web UI Manual start"
fi

/run.sh &
run_pid=$!
wait "$run_pid"
exit_code=$?
echo "[INFO] entry_jmb: ARM web UI exited with code ${exit_code}"
exit "$exit_code"
