# QUICKSTART — OpenNMS MQTT Monitoring Lab

Full step-by-step setup from a fresh clone to a live OpenNMS Geo Map with 30 simulated IoT sites.

---

## Prerequisites

- Docker + Docker Compose
- GitHub CLI (`gh auth login` completed)
- ~2 GB RAM for OpenNMS Horizon

---

## 1. Clone the repo

```bash
mkdir -p ~/git/open-nms-mqtt
gh repo clone mmorrow24work/open-nms-mqtt ~/git/open-nms-mqtt
cd ~/git/open-nms-mqtt
```

---

## 2. Start the stack

```bash
docker compose up -d
```

OpenNMS takes 2–3 minutes to initialise on first boot. Watch progress:

```bash
docker compose logs -f opennms
```

Wait until the log goes quiet and you can reach the UI.

Verify all containers are up (~3 min):

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | sort
```

Expected:

```
NAMES                        STATUS
mosquitto                    Up 3 minutes
opennms                      Up 3 minutes (healthy)
opennms-db                   Up 3 minutes
opennms-mqtt-sidecar         Up 3 minutes
iot-publisher                Up 3 minutes
```

---

## 3. Log in to OpenNMS

Open **http://localhost:8980** — `admin` / `admin`

---

## 4. Check the Geo Map

> **First login:** OpenNMS 36 prompts you to change the admin password on first login. Click **Skip** to dismiss it.

1. Navigate to **Maps → Geographical Map** (left sidebar pin icon), or go directly to:
   `http://localhost:8980/opennms/ui/index.html#/map`
2. Sites provisioned by the sidecar appear as node pins along the M6 corridor
3. Click a pin to open the node detail page

The sidecar creates one OpenNMS node per discovered site, setting `latitude` and `longitude` from the MQTT location messages.

---

## 5. Check events

Navigate to **Events → All Events** to see MQTT metric events arriving every 10 seconds.

Each event description contains the metric (`temp`, `humidity`, `power`), value, and site ID.

---

## 6. Monitor MQTT traffic

Subscribe to all lab topics directly:

```bash
docker exec -it mosquitto mosquitto_sub -t 'lab/#' -v
```

Or inspect a single metric:

```bash
docker exec -it mosquitto mosquitto_sub -t 'lab/temp/site1'
```

---

## 7. Tail sidecar logs

```bash
docker compose logs -f opennms-mqtt-sidecar
```

Expected output as sites are provisioned:

```
2026-06-04 10:00:01 INFO Waiting for OpenNMS API...
2026-06-04 10:02:30 INFO OpenNMS ready — version 33.0.0
2026-06-04 10:02:31 INFO Requisition MQTT-Sites already exists
2026-06-04 10:02:35 INFO === Provisioning site1 ===
2026-06-04 10:02:36 INFO   Added node site1 to requisition (52.2820, -1.5849)
2026-06-04 10:02:36 INFO   Triggered sync of MQTT-Sites
2026-06-04 10:02:36 INFO === site1 provisioned OK ===
```

---

## 8. Stop and clean up

```bash
# Stop containers
docker compose down

# Remove containers and volumes (deletes all OpenNMS data)
docker compose down -v
```

---

## Useful commands

```bash
# Tail sidecar logs
docker compose logs -f opennms-mqtt-sidecar

# Restart sidecar (e.g. after config change)
docker compose restart opennms-mqtt-sidecar

# Rebuild sidecar after code changes
docker compose up -d --build opennms-mqtt-sidecar

# Scale publishers (more simulated sites — each instance adds 15 sites)
docker compose up -d --scale iot-publisher-multi=2

# Take a screenshot (requires Playwright — see scripts/screenshot.py)
pip install playwright && playwright install chromium
python3 scripts/screenshot.py \
  "http://localhost:8980/opennms/ui/index.html#/map" \
  --user admin --password admin \
  --wait 8000 --name geomap
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| OpenNMS UI not reachable | Wait 2–3 min for first boot; check `docker compose logs opennms` |
| No nodes in Geo Map | Check sidecar logs — it may be waiting for OpenNMS to start |
| Sidecar `OpenNMS API not reachable` | OpenNMS still starting — sidecar retries for 5 min automatically |
| Events page empty | Sidecar sends events only after a site is provisioned; wait ~60s |
| Nodes have no map pin | Check asset fields: `latitude`/`longitude` must be set correctly |
| Publisher not publishing | Check `docker compose logs iot-publisher` for errors |
