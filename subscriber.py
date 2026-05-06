import paho.mqtt.client as mqtt

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "iIqFGbh9O5YPfs7lXJb-MHxPjMHddeXM8T_zH7zYDLQjONnNoTm7AOXGbq9rYQsfAXUHwIMPfnezICctOT48TA=="
INFLUX_ORG = "Chuuk"
INFLUX_BUCKET = "Temperaturas"

client_db = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)

write_api = client_db.write_api(write_options=SYNCHRONOUS)

mqtt_client = mqtt.Client()

def on_message(client, userdata, msg):

    topic = msg.topic
    payload = msg.payload.decode()

    zona = topic.split("/")[1]
    equipo = topic.split("/")[2]

    temperatura = float(payload)

    point = (
    Point("temperaturas")
    .tag("zona", zona)
    .tag("equipo", equipo)
    .field("valor", temperatura)
)

    write_api.write(
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
        record=point
    )

    print(f"{equipo}: {temperatura}")

mqtt_client.on_message = on_message

mqtt_client.connect("localhost", 1883)

mqtt_client.subscribe("cafeteria/+/+/temperatura")

mqtt_client.loop_forever()