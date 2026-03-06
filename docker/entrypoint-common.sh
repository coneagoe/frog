#!/bin/bash
# Auto-detect CPU cores and set worker concurrency if not specified

# Add user to passwd if running as non-standard uid
if ! whoami &>/dev/null; then
    CURRENT_UID=$(id -u)
    CURRENT_GID=$(id -g)
    echo "airflow:x:${CURRENT_UID}:${CURRENT_GID}:airflow:/home/airflow:/bin/bash" >> /etc/passwd
    echo "Added user to passwd: uid=${CURRENT_UID}, gid=${CURRENT_GID}"
fi

# Detect CPU cores (fallback to 2 if detection fails)
CORES=$(nproc 2>/dev/null || echo "2")

# Set worker concurrency based on cores (leave half for system)
if [ -z "$WORKER_CONCURRENCY" ]; then
    export WORKER_CONCURRENCY=$((CORES > 2 ? CORES / 2 : 2))
    echo "Auto-detected ${CORES} cores, setting WORKER_CONCURRENCY=$WORKER_CONCURRENCY"
fi

# Set partition count based on cores (default to cores if not set)
if [ -z "$DOWNLOAD_PROCESS_COUNT" ]; then
    export DOWNLOAD_PROCESS_COUNT=$((CORES > 4 ? CORES : 4))
    echo "Auto-detected ${CORES} cores, setting DOWNLOAD_PROCESS_COUNT=$DOWNLOAD_PROCESS_COUNT"
fi

# Pass to Airflow config
export AIRFLOW__CELERY__WORKER_CONCURRENCY=$WORKER_CONCURRENCY

echo "Final config: WORKER_CONCURRENCY=$WORKER_CONCURRENCY, DOWNLOAD_PROCESS_COUNT=$DOWNLOAD_PROCESS_COUNT"

# Execute the original command
exec "$@"
