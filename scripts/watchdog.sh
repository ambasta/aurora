#!/usr/bin/env bash
# Run a command in its own process group and stop the group if MemAvailable
# drops below AURORA_MEMORY_RESERVE_MIB (default 2048), so builds and tests can
# use every core without driving the host into the OOM killer.
set -uo pipefail
(( $# )) || { echo 'usage: scripts/watchdog.sh COMMAND [ARG...]' >&2; exit 2; }
reserve=${AURORA_MEMORY_RESERVE_MIB:-2048}
setsid "$@" &
child=$!
trap 'kill -TERM -- "-$child" 2>/dev/null' INT TERM
while kill -0 "$child" 2>/dev/null; do
    available=$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)
    if (( available < reserve )); then
        echo "watchdog: MemAvailable ${available} MiB is below ${reserve} MiB; stopping $1" >&2
        kill -TERM -- "-$child" 2>/dev/null
        for _ in 1 2 3 4; do kill -0 "$child" 2>/dev/null || break; sleep 0.5; done
        kill -KILL -- "-$child" 2>/dev/null
        wait "$child"
        exit 137
    fi
    sleep 0.5
done
wait "$child"
