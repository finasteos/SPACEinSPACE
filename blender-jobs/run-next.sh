#!/bin/bash
# Run APPROVED Blender jobs through the persistent B0 ambassador.
# Usage: ./blender-jobs/run-next.sh
# Designed to be triggered by launchd/cron.
#
# B1: no separate socket addon needed — the worker launches the persistent
# Blender ambassador itself (blender --background --python
# mcp_servers/blender_mcp_server.py) via create_blender_ambassador(). Only jobs
# a human has APPROVED (queue/approved/) are executed here; pending jobs wait.

cd "$(dirname "$0")/.." || exit 1

APPROVED=$(ls blender-jobs/queue/approved/*.md 2>/dev/null | wc -l | tr -d ' ')
if [ "$APPROVED" -eq 0 ]; then
    echo "No approved jobs. Approve some first:"
    echo "  python3 blender-jobs/worker.py list"
    echo "  python3 blender-jobs/worker.py approve <slug|all>"
    exit 0
fi

echo "Found $APPROVED approved job(s) — running via the persistent Blender ambassador."
python3 blender-jobs/worker.py run 2>&1
echo "---"
echo "Approved left: $(ls blender-jobs/queue/approved/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "Gallery: blender-jobs/gallery.md   Exports: blender-jobs/exports/"
