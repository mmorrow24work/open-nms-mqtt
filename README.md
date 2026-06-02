# open-nms-mqtt

Docker Compose lab stack that integrates **OpenNMS Horizon** with an **MQTT broker** and a fleet of simulated IoT sensor sites distributed along the M6 motorway corridor (London → Newcastle).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          opennms-net                            │
│                                                                 │
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐  │
│  │ iot-publisher│────▶│  mosquitto   │◀────│opennms-mqtt-    │  │
│  │  (alpine)   │     │ (eclipse 2)  │     │    sidecar      │  │
│  └─────────────┘     └──────────────┘     └────────┬────────┘  │
│                                                     │           │
│                       ┌─────────────┐     ┌────────▼────────┐  │
│                       │ opennms-db  │◀────│    opennms      │  │
│                       │ (postgres)  │     │   (horizon)     │  │
│                       └─────────────┘     └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| Service | Image | Port |
|---|---|---|
| `opennms` | `opennms/horizon:latest` | `8980` (web), `8101` (karaf) |
| `db` | `postgres:15` | internal |
| `mosquitto` | `eclipse-mosquitto:2` | `1883` |
| `iot-publisher` | `alpine:3.20` | — |
| `opennms-mqtt-sidecar` | built from `./sidecar` | — |

## MQTT Topics

The publisher emits sensor readings every 10 seconds for 15 simulated sites:

| Topic | Payload | Example |
|---|---|---|
| `lab/temp/<site>` | float °C | `19.3` |
| `lab/humidity/<site>` | float % | `65.0` |
| `lab/power/<site>` | float W | `387.2` |
| `lab/location/<site>` | `lat,lon` | `52.4862,-1.8904` |
| `lab/discovery` | JSON LLD array | `[{"{#SITE}":"site1"},...]` |

Site positions are interpolated along the M6 route (London → Coventry → Birmingham → Manchester → Preston → Newcastle) so the OpenNMS Geo Map widget renders a realistic corridor.

## MQTT Sidecar

`sidecar/sidecar.py` connects to both MQTT and the OpenNMS REST API. On each new site discovered it:

1. Waits for the `lab/location/<site>` message to arrive (for accurate coordinates)
2. Creates a node in the `MQTT-Sites` OpenNMS requisition with `latitude` / `longitude` inventory fields
3. Triggers a requisition import so the node appears in the Geo Map immediately
4. Forwards subsequent `temp`, `humidity`, and `power` readings as OpenNMS events

## Prerequisites

- Docker Engine 24+
- Docker Compose v2
- ~2 GB RAM for OpenNMS

## Quick Start

```bash
git clone https://github.com/mmorrow24work/open-nms-mqtt.git
cd open-nms-mqtt
docker compose up -d
```

OpenNMS takes 2–3 minutes to initialise on first boot. Watch progress with:

```bash
docker compose logs -f opennms
```

Once you see `OpenNMS is starting up` complete, open the web UI:

```
http://localhost:8980
Username: admin
Password: admin
```

## Viewing the Geo Map

1. Log in to OpenNMS
2. Navigate to **Maps → Geo Map**
3. Sites provisioned by the sidecar appear as nodes along the M6 corridor
4. Node inventory (latitude/longitude) is populated automatically from MQTT location messages

## Monitoring MQTT Traffic

Subscribe to all lab topics directly from the host:

```bash
docker exec -it mosquitto mosquitto_sub -t 'lab/#' -v
```

Or inspect a single metric:

```bash
docker exec -it mosquitto mosquitto_sub -t 'lab/temp/site1'
```

## Configuration

All sidecar settings are environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `OPENNMS_URL` | `http://opennms:8980` | OpenNMS base URL |
| `OPENNMS_USER` | `admin` | API username |
| `OPENNMS_PASSWORD` | `admin` | API password |
| `OPENNMS_FOREIGN_SOURCE` | `MQTT-Sites` | Requisition name |
| `MQTT_BROKER` | `mosquitto` | Broker hostname |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_TOPIC` | `lab/#` | Subscription filter |

## Stopping and Cleaning Up

```bash
# Stop containers
docker compose down

# Remove containers and volumes (deletes all OpenNMS data)
docker compose down -v
```

## Related

- [mqtt2](https://github.com/mmorrow24work/mqtt2) — same sensor lab wired to Zabbix instead of OpenNMS
