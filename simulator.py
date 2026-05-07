import random
import time
import threading
from datetime import datetime

import paho.mqtt.client as mqtt

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

BROKER = "localhost"
PORT   = 1883

zonas = {
    "Cad_Fria": ["refrig_a", "refrig_b", "cong_a", "cong_b"],
    "Bar_Serv": ["cal_a", "cal_b", "cal_c", "frio_a", "frio_b", "frio_c"],
}

perfiles = {
    "refrig": {"objetivo": 4.0,   "tolerancia": 1.5, "correccion": 0.3, "ruido": 0.1},
    "cong":   {"objetivo": -20.0, "tolerancia": 2.0, "correccion": 0.4, "ruido": 0.05},
    "cal":    {"objetivo": 65.0,  "tolerancia": 3.0, "correccion": 0.5, "ruido": 0.2},
    "frio":   {"objetivo": 6.0,   "tolerancia": 1.0, "correccion": 0.3, "ruido": 0.1},
}

# ─────────────────────────────────────────────
# ESTADO
# ─────────────────────────────────────────────

temperaturas    = {}
eventos_activos = {}   # equipo -> {tipo, duracion_restante, intensidad}
lock            = threading.Lock()  # protege eventos_activos entre hilos


def get_perfil(equipo: str) -> dict:
    for key in perfiles:
        if key in equipo:
            return perfiles[key]
    return {"objetivo": 20.0, "tolerancia": 2.0, "correccion": 0.2, "ruido": 0.1}


# Inicializar temperaturas cerca del objetivo
for zona in zonas:
    for equipo in zonas[zona]:
        p = get_perfil(equipo)
        temperaturas[equipo] = round(p["objetivo"] + random.uniform(-0.5, 0.5), 2)


# ─────────────────────────────────────────────
# MODELO DE TEMPERATURA
# ─────────────────────────────────────────────

def aplicar_evento(equipo: str) -> float:
    """
    Durante un evento el equipo pierde su capacidad de mantener temperatura
    y deriva HACIA el ambiente (20 °C), independientemente de si el equipo
    es frío o caliente.
    """
    with lock:
        if equipo not in eventos_activos:
            return 0.0

        evento     = eventos_activos[equipo]
        intensidad = evento["intensidad"]

        # La deriva siempre es hacia 20 °C (ambiente).
        # Si el equipo está a -20 °C → delta positivo (sube).
        # Si el equipo está a  65 °C → delta negativo (baja).
        # El signo es automático.
        TEMP_AMBIENTE = 20.0
        delta = (TEMP_AMBIENTE - temperaturas[equipo]) * 0.06 * intensidad

        evento["duracion_restante"] -= 1
        if evento["duracion_restante"] <= 0:
            print(f"\n✅  [{datetime.now().strftime('%H:%M:%S')}] "
                  f"Evento '{evento['tipo']}' terminado en {equipo}. Recuperando...\n")
            del eventos_activos[equipo]

        return delta


def actualizar_temperatura(equipo: str) -> None:
    p          = get_perfil(equipo)
    objetivo   = p["objetivo"]
    correccion = p["correccion"]
    ruido      = p["ruido"]

    temp_actual = temperaturas[equipo]
    desviacion  = objetivo - temp_actual

    with lock:
        hay_evento = equipo in eventos_activos

    if hay_evento:
        # Durante el evento el termostato está prácticamente apagado.
        # Solo aplicamos el delta del evento + ruido pequeño.
        delta_evento  = aplicar_evento(equipo)
        delta_normal  = random.gauss(0, ruido)
    else:
        # Recuperación suave: la corrección está limitada para evitar
        # oscilaciones cuando la temperatura está muy lejos del objetivo.
        MAX_CORRECCION = 1.5  # °C por ciclo como máximo
        correccion_raw = correccion * desviacion
        correccion_limitada = max(-MAX_CORRECCION, min(MAX_CORRECCION, correccion_raw))

        delta_normal = correccion_limitada + random.gauss(0, ruido)
        delta_evento = 0.0

    temperaturas[equipo] = round(temp_actual + delta_normal + delta_evento, 2)


# ─────────────────────────────────────────────
# MQTT — publicación de temperaturas
# ─────────────────────────────────────────────

pub_client = mqtt.Client(client_id="simulador_pub")

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Conectado al broker (rc={rc})")

def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc})")

pub_client.on_connect    = on_connect
pub_client.on_disconnect = on_disconnect
pub_client.reconnect_delay_set(min_delay=1, max_delay=30)
pub_client.connect(BROKER, PORT, 60)
pub_client.loop_start()


# ─────────────────────────────────────────────
# MQTT — escucha de eventos manuales
# ─────────────────────────────────────────────
#
#  Para disparar un evento publica en:
#
#    cafeteria/evento/<equipo>
#
#  con un payload JSON como:
#    {"tipo": "puerta_abierta", "duracion": 10, "intensidad": 2.5}
#
#  o simplemente vacío / cualquier texto para usar los valores por defecto.
#
#  Ejemplos con mosquitto_pub:
#    mosquitto_pub -t "cafeteria/evento/refrig_a" -m '{"tipo":"fallo_compresor","duracion":8,"intensidad":2.0}'
#    mosquitto_pub -t "cafeteria/evento/cal_b"    -m '{}'
#
# ─────────────────────────────────────────────

import json

TIPOS_EVENTO = ["fallo_compresor", "puerta_abierta", "sobrecarga"]

# Lista plana de todos los equipos para validar
todos_los_equipos = [e for equipos in zonas.values() for e in equipos]


def on_evento(client, userdata, msg):
    equipo = msg.topic.split("/")[-1]

    if equipo not in todos_los_equipos:
        print(f"\n⛔  Equipo desconocido: '{equipo}'. "
              f"Equipos válidos: {todos_los_equipos}\n")
        return

    # Parsear payload (opcional)
    try:
        params = json.loads(msg.payload.decode()) if msg.payload else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        params = {}

    tipo       = params.get("tipo",       random.choice(TIPOS_EVENTO))
    duracion   = int(params.get("duracion",   random.randint(6, 14)))
    intensidad = float(params.get("intensidad", random.uniform(1.5, 3.0)))

    with lock:
        eventos_activos[equipo] = {
            "tipo":              tipo,
            "duracion_restante": duracion,
            "intensidad":        intensidad,
        }

    print(f"\n🚨  [{datetime.now().strftime('%H:%M:%S')}] "
          f"EVENTO MANUAL → equipo={equipo} | tipo={tipo} | "
          f"duración={duracion} ciclos | intensidad={intensidad:.1f}\n")


sub_client = mqtt.Client(client_id="simulador_sub")
sub_client.on_message = on_evento
sub_client.connect(BROKER, PORT, 60)
sub_client.subscribe("cafeteria/evento/+")
sub_client.loop_start()

print("=" * 60)
print("  Simulador arrancado")
print("  Para disparar un evento manual:")
print('  mosquitto_pub -t "cafeteria/evento/<equipo>" -m \'{}\'')
print(f"  Equipos disponibles: {todos_los_equipos}")
print("=" * 60)


# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

while True:
    try:
        for zona, equipos in zonas.items():
            for equipo in equipos:
                actualizar_temperatura(equipo)

                topic  = f"cafeteria/{zona}/{equipo}/temperatura"
                result = pub_client.publish(topic, str(temperaturas[equipo]))

                estado = "🚨 EVENTO" if equipo in eventos_activos else "   "
                if result.rc == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {estado} {topic}: {temperaturas[equipo]}")
                else:
                    print(f"Error publicando en {topic}")

        time.sleep(5)

    except KeyboardInterrupt:
        print("\nSimulador detenido.")
        pub_client.loop_stop()
        sub_client.loop_stop()
        break

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
