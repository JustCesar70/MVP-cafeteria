from flask import Flask, request, jsonify
from flask_cors import CORS
import paho.mqtt.client as mqtt
import json
import csv
import os
from datetime import datetime, timezone, timedelta
 
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
 
# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
 
BROKER = "localhost"
PORT   = 1883
 
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "iIqFGbh9O5YPfs7lXJb-MHxPjMHddeXM8T_zH7zYDLQjONnNoTm7AOXGbq9rYQsfAXUHwIMPfnezICctOT48TA=="
INFLUX_ORG    = "Chuuk"
INFLUX_BUCKET = "Temperaturas"
 
LOG_FILE = "alertas.csv"
OFFSET   = timedelta(hours=-6)   # UTC-6 México Centro — ajusta si es necesario
 
# ─────────────────────────────────────────────
# CLIENTES
# ─────────────────────────────────────────────
 
app = Flask(__name__)
CORS(app)
 
mqtt_client = mqtt.Client(client_id="api_eventos")
mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()
 
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)
 
 
# ─────────────────────────────────────────────
# REGISTRO CSV
# ─────────────────────────────────────────────
 
def registrar_en_csv(estado, zona, equipo, nombre, valor):
    """Añade una fila al CSV de alertas con hora local."""
    hora_local = datetime.now(timezone.utc).astimezone(timezone(OFFSET))
    existe     = os.path.isfile(LOG_FILE)
 
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["fecha_hora", "estado", "zona", "equipo", "alerta", "valor_C"])
        writer.writerow([
            hora_local.strftime("%Y-%m-%d %H:%M:%S"),
            estado,
            zona,
            equipo,
            nombre,
            f"{valor:.2f}",
        ])
 
 
# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────
 
@app.route("/evento", methods=["POST"])
def disparar_evento():
    """Publica un evento en MQTT para que el simulador lo procese."""
    data   = request.get_json(force=True)
    equipo = data.get("equipo")
 
    if not equipo:
        return jsonify({"error": "Falta el campo 'equipo'"}), 400
 
    payload = {
        "tipo":       data.get("tipo",       "fallo_compresor"),
        "duracion":   data.get("duracion",   10),
        "intensidad": data.get("intensidad", 2.5),
    }
 
    topic = f"cafeteria/evento/{equipo}"
    mqtt_client.publish(topic, json.dumps(payload))
 
    print(f"[EVENTO] {equipo} → {payload}")
    return jsonify({"ok": True, "equipo": equipo, "payload": payload})
 
 
@app.route("/webhook-alerta", methods=["POST"])
def webhook_alerta():
    """
    Recibe el webhook de Grafana cuando una alerta cambia de estado.
    Guarda el registro en CSV (siempre) y en InfluxDB (si está disponible).
    """
    data = request.get_json(force=True)
 
    for alert in data.get("alerts", []):
        estado = alert.get("status", "unknown")
        labels = alert.get("labels", {})
        equipo = labels.get("equipo", "desconocido")
        zona   = labels.get("zona",   "desconocida")
        nombre = labels.get("alertname", "sin_nombre")
 
        valor = 0.0
        for v in (alert.get("values") or {}).values():
            try:
                valor = float(v)
            except (TypeError, ValueError):
                valor = 0.0
            break
 
        # ── Guardar en CSV ──────────────────────
        try:
            registrar_en_csv(estado, zona, equipo, nombre, valor)
        except Exception as e:
            print(f"[CSV] Error escribiendo log: {e}")
 
        # ── Guardar en InfluxDB ─────────────────
        try:
            point = (
                Point("alertas")
                .tag("equipo", equipo)
                .tag("zona",   zona)
                .tag("estado", estado)
                .tag("nombre", nombre)
                .field("valor", valor)
            )
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        except Exception as e:
            print(f"[INFLUX] Error guardando alerta: {e}")
 
        print(f"[WEBHOOK] {estado.upper():8} | zona={zona} | equipo={equipo} | {valor:.2f}°C")
 
    return jsonify({"ok": True})
 
 
@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})
 
 
# ─────────────────────────────────────────────
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)