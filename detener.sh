#!/bin/bash

# ─────────────────────────────────────────────
# detener.sh — Para toda la infraestructura
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$SCRIPT_DIR/logs"

echo ""
echo "⏹  Deteniendo servicios..."

for servicio in subscriber simulador api; do
    PID_FILE="$LOGS/$servicio.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "✓ $servicio detenido (PID $PID)"
        else
            echo "⚠  $servicio ya no estaba corriendo"
        fi
        rm "$PID_FILE"
    fi
done

echo ""
echo "⏹  Deteniendo Docker..."
docker compose down
echo "✓ Docker detenido"
echo ""
