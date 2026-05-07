#!/bin/bash

# ─────────────────────────────────────────────
# arrancar.sh — Levanta toda la infraestructura
# ─────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Sistema de Temperaturas MVP      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Docker Compose ──────────────────────────
echo "▶ Levantando contenedores Docker..."
docker compose up -d
echo "✓ Docker listo"
echo ""

# Esperar a que el broker MQTT y InfluxDB estén disponibles
echo "⏳ Esperando broker MQTT (localhost:1883)..."
until nc -z localhost 1883 2>/dev/null; do sleep 1; done
echo "✓ Broker MQTT disponible"

echo "⏳ Esperando InfluxDB (localhost:8086)..."
until nc -z localhost 8086 2>/dev/null; do sleep 1; done
echo "✓ InfluxDB disponible"
echo ""

# ── 2. Subscriber ──────────────────────────────
echo "▶ Iniciando subscriber..."
python3 "$SCRIPT_DIR/subscriber.py" > "$SCRIPT_DIR/logs/subscriber.log" 2>&1 &
SUB_PID=$!
echo "✓ Subscriber corriendo (PID $SUB_PID)"

# ── 3. Simulador ───────────────────────────────
echo "▶ Iniciando simulador..."
python3 "$SCRIPT_DIR/simulator.py" > "$SCRIPT_DIR/logs/simulador.log" 2>&1 &
SIM_PID=$!
echo "✓ Simulador corriendo (PID $SIM_PID)"

# ── 4. API de eventos ──────────────────────────
echo "▶ Iniciando API de eventos..."
python3 "$SCRIPT_DIR/api_eventos.py" > "$SCRIPT_DIR/logs/api.log" 2>&1 &
API_PID=$!
echo "✓ API corriendo en http://localhost:5050 (PID $API_PID)"

echo ""
echo "─────────────────────────────────────────"
echo "  Todo listo. Abre control.html en tu navegador."
echo "  Logs disponibles en ./logs/"
echo "─────────────────────────────────────────"
echo ""
echo "  PIDs activos:"
echo "    Subscriber : $SUB_PID"
echo "    Simulador  : $SIM_PID"
echo "    API        : $API_PID"
echo ""
echo "  Para detener todo: ./detener.sh"
echo ""

# Guardar PIDs para poder detener después
mkdir -p "$SCRIPT_DIR/logs"
echo "$SUB_PID" > "$SCRIPT_DIR/logs/subscriber.pid"
echo "$SIM_PID" > "$SCRIPT_DIR/logs/simulador.pid"
echo "$API_PID" > "$SCRIPT_DIR/logs/api.pid"

# Mantener el script vivo mostrando logs del simulador
tail -f "$SCRIPT_DIR/logs/simulador.log"
