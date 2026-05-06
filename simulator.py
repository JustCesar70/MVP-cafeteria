import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883

zonas = {}

zonas["Cad_Fria"] = [
    "refrig_a",
    "refrig_b",
    "cong_a",
    "cong_b"
]

zonas["Bar_Serv"] = [
    "cal_a",
    "cal_b",
    "cal_c",
    "frio_a",
    "frio_b",
    "frio_c"
]

# --- MODELO DE TEMPERATURA ---
# Cada equipo tiene: temperatura objetivo, rango aceptable, y fuerza de corrección

perfiles = {
    "refrig": {"objetivo": 4.0,   "tolerancia": 1.5,  "correccion": 0.3, "ruido": 0.1},
    "cong":   {"objetivo": -20.0, "tolerancia": 2.0,  "correccion": 0.4, "ruido": 0.05},
    "cal":    {"objetivo": 65.0,  "tolerancia": 3.0,  "correccion": 0.5, "ruido": 0.2},
    "frio":   {"objetivo": 6.0,   "tolerancia": 1.0,  "correccion": 0.3, "ruido": 0.1},
}

def get_perfil(equipo):
    for key in perfiles:
        if key in equipo:
            return perfiles[key]
    return {"objetivo": 20.0, "tolerancia": 2.0, "correccion": 0.2, "ruido": 0.1}

# Inicializar temperaturas en el valor objetivo de cada equipo
temperaturas = {}
for zona in zonas:
    for equipo in zonas[zona]:
        perfil = get_perfil(equipo)
        # Arrancan con una pequeña variación aleatoria realista
        temperaturas[equipo] = round(perfil["objetivo"] + random.uniform(-0.5, 0.5), 2)

def actualizar_temperatura(equipo):
    """
    Modelo Ornstein-Uhlenbeck: la temperatura es atraída hacia el objetivo
    con una fuerza proporcional a cuánto se desvía, más ruido gaussiano pequeño.
    Esto simula el termostato del equipo actuando continuamente.
    """
    perfil = get_perfil(equipo)
    objetivo    = perfil["objetivo"]
    correccion  = perfil["correccion"]
    ruido       = perfil["ruido"]
    tolerancia  = perfil["tolerancia"]

    temp_actual = temperaturas[equipo]
    desviacion  = objetivo - temp_actual

    # Fuerza de corrección proporcional a la desviación (termostato)
    # Si está muy lejos del objetivo, corrige más fuerte
    correccion_dinamica = correccion * (1 + abs(desviacion) / tolerancia)

    nueva_temp = temp_actual + correccion_dinamica * desviacion + random.gauss(0, ruido)

    temperaturas[equipo] = round(nueva_temp, 2)

# --- MQTT ---

client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Conectado al broker MQTT: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"Desconectado del broker MQTT: {rc}")

client.on_connect = on_connect
client.on_disconnect = on_disconnect

client.reconnect_delay_set(min_delay=1, max_delay=30)
client.connect(BROKER, PORT, 60)
client.loop_start()

while True:
    try:
        for zona in list(zonas.keys()):
            for equipo in zonas[zona]:
                actualizar_temperatura(equipo)

                topic = f"cafeteria/{zona}/{equipo}/temperatura"
                result = client.publish(topic, str(temperaturas[equipo]))

                if result.rc == 0:
                    print(f"[{datetime.now()}] {topic}: {temperaturas[equipo]}")
                else:
                    print(f"Error publicando en {topic}")

        time.sleep(5)

    except Exception as e:
        print("Error:", e)
        time.sleep(5)