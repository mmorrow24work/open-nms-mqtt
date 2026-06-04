# QUICKSTART — OpenNMS MQTT Monitoring Lab (Claude edition)

Full step-by-step setup from a fresh clone to a live OpenNMS Geo Map and Events view with simulated IoT sites.
All API examples use the OpenNMS REST API with basic auth — no token setup required.

> **OpenNMS startup note:** Horizon is a JVM application. On first boot it initialises the database schema before serving HTTP. Allow 2–3 minutes before attempting to log in or call the REST API.

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

The sidecar will restart a few times while waiting for OpenNMS to become healthy — this is expected.

To run multiple IoT publishers (more simulated sites — each instance covers 15 sites):

```bash
docker compose up -d --scale iot-publisher-multi=2
```

---

## 3. Log in to OpenNMS

Open **http://localhost:8980** — `admin` / `admin`

> **First login:** OpenNMS 36 shows a "Change Password" dialog on first login. Click **Skip** to dismiss it and proceed to the dashboard.

---

## 4. Verify the REST API

Once the UI is reachable, confirm the REST API is responding:

```bash
curl -s -u admin:admin http://localhost:8980/opennms/rest/info | python3 -m json.tool
```

Expected response includes `"version": "..."` and `"packageDescription": "OpenNMS"`.

---

## 5. Check the requisition

The sidecar creates the `MQTT-Sites` requisition automatically. Verify it exists:

```bash
curl -s -u admin:admin \
  http://localhost:8980/opennms/rest/requisitions/MQTT-Sites \
  -H 'Accept: application/json' | python3 -m json.tool | head -30
```

If the sidecar has provisioned sites, you'll see node entries with `latitude` and `longitude` asset fields.

To list all provisioned nodes:

```bash
curl -s -u admin:admin \
  "http://localhost:8980/opennms/rest/nodes?foreignSource=MQTT-Sites&limit=100" \
  -H 'Accept: application/json' | python3 -c "
import sys, json
data = json.load(sys.stdin)
nodes = data.get('node', [])
if isinstance(nodes, dict): nodes = [nodes]
for n in nodes:
    print(f\"  {n.get('foreignId','?'):12s}  id={n.get('id','?')}\")
print(f'Total: {len(nodes)}')
"
```

---

## 6. Manually create or re-provision a node (optional)

If you want to manually provision a site via the REST API:

```bash
curl -s -u admin:admin -X POST \
  http://localhost:8980/opennms/rest/requisitions/MQTT-Sites/nodes \
  -H 'Content-Type: application/xml' \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<node xmlns="http://xmlns.opennms.org/xsd/config/model-import"
  node-label="site1"
  foreign-id="site1">
  <interface ip-addr="127.0.0.1" snmp-primary="N" status="1">
    <monitored-service service-name="ICMP"/>
  </interface>
  <asset name="latitude" value="52.2820"/>
  <asset name="longitude" value="-1.5849"/>
  <asset name="description" value="MQTT Sensor Site"/>
  <asset name="building" value="IoT Lab"/>
</node>'

# Trigger the import
curl -s -u admin:admin -X PUT \
  "http://localhost:8980/opennms/rest/requisitions/MQTT-Sites/import?rescanExisting=false"
```

---

## 7. View the Geo Map

1. Navigate to **Maps → Geographical Map** (left sidebar pin icon) or go directly to:
   `http://localhost:8980/opennms/ui/index.html#/map`
2. Site nodes appear as pins along the M6 corridor
3. Click a pin to open the node detail page

The Geo Map reads the `latitude` and `longitude` asset fields set by the sidecar. If pins are missing, check that the sidecar has completed provisioning and the requisition import has run.

---

## 8. View events

Navigate to **Events → All Events** to see MQTT metric events.

To query events via the REST API:

```bash
curl -s -u admin:admin \
  "http://localhost:8980/opennms/rest/events?limit=10&orderBy=eventTime&order=desc" \
  -H 'Accept: application/json' | python3 -c "
import sys, json
data = json.load(sys.stdin)
events = data.get('event', [])
if isinstance(events, dict): events = [events]
for e in events:
    print(f\"  [{e.get('eventTime','?')}] {e.get('eventDescr','?')[:80]}\")
"
```

---

## 9. Monitor MQTT traffic

```bash
# Subscribe to all lab topics
docker exec mosquitto mosquitto_sub -h localhost -t 'lab/#' -v

# Tail sidecar provisioning logs
docker compose logs -f opennms-mqtt-sidecar
```

---

## 10. Take screenshots with `scripts/screenshot.py`

`scripts/screenshot.py` uses [Playwright](https://playwright.dev/python/) to capture any OpenNMS page as a PNG. Pass `--user` and `--password` to log in first (required for authenticated pages).

```bash
# Install Playwright (once)
pip install playwright && playwright install chromium

# Geo Map screenshot (OpenNMS 36 URL)
python3 scripts/screenshot.py \
  "http://localhost:8980/opennms/ui/index.html#/map" \
  --user admin --password admin \
  --wait 8000 \
  --name geomap

# Node list
python3 scripts/screenshot.py \
  "http://localhost:8980/opennms/element/nodeList.htm" \
  --user admin --password admin \
  --name nodes

# Events page
python3 scripts/screenshot.py \
  "http://localhost:8980/opennms/event/list" \
  --user admin --password admin \
  --name events

# Wider viewport for maps
python3 scripts/screenshot.py \
  "http://localhost:8980/opennms/map/index.jsp" \
  --user admin --password admin \
  --wait 5000 --width 1600 --height 900 \
  --name geomap_wide
```

| Flag | Default | Description |
|---|---|---|
| `--user` | — | OpenNMS username; triggers login flow |
| `--password` | — | OpenNMS password |
| `--wait` | `5000` | Extra ms to wait after page load |
| `--name` | timestamp | Output filename stem (saved to `docs/screenshots/<name>.png`) |
| `--base-url` | `http://localhost:8980` | OpenNMS base URL |
| `--width` | `1280` | Viewport width in pixels |
| `--height` | `900` | Viewport height in pixels |

Screenshots are saved to `docs/screenshots/` at the repo root.

---

## Useful commands

```bash
# Tail sidecar provisioning logs
docker compose logs -f opennms-mqtt-sidecar

# Restart sidecar (e.g. after config change)
docker compose restart opennms-mqtt-sidecar

# Rebuild sidecar after code changes
docker compose up -d --build opennms-mqtt-sidecar

# Scale publishers (more IoT sites — each instance adds 15 sites)
docker compose up -d --scale iot-publisher-multi=2

# Stop everything
docker compose down

# Stop and remove volumes (full reset)
docker compose down -v
```

---

## Configuration reference

All sidecar settings are environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `OPENNMS_URL` | `http://opennms:8980` | OpenNMS base URL (internal Docker hostname) |
| `OPENNMS_USER` | `admin` | API username |
| `OPENNMS_PASSWORD` | `admin` | API password |
| `OPENNMS_FOREIGN_SOURCE` | `MQTT-Sites` | Requisition name |
| `MQTT_BROKER` | `mosquitto` | Broker hostname |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_TOPIC` | `lab/#` | Subscription filter |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| OpenNMS UI not reachable after 5 min | Check `docker compose logs opennms` — may be OOM; ensure 2 GB RAM available |
| Sidecar `OpenNMS API not reachable after 5 minutes` | OpenNMS took too long — restart sidecar: `docker compose restart opennms-mqtt-sidecar` |
| No pins on Geo Map | Sidecar sets lat/lon asset fields — check sidecar logs; nodes must be fully imported |
| Events page empty | Sidecar sends events only after provisioning completes; wait ~60s after node appears |
| `404` on REST API calls | OpenNMS still initialising — wait and retry |
| Nodes missing from Geo Map after provisioning | Requisition import may not have fired — check sidecar logs for `Triggered sync` |
| Publisher container exits | Check `docker compose logs iot-publisher` — it installs `mosquitto-clients` at startup |
| Many `nodeUpdated` events flooding Events view | Sidecar restart caused location re-sync — clears after one cycle (~10s). Full reset: `docker compose down -v && docker compose up -d` |
| Sidecar re-provisions all sites on every restart | Known issue: startup sync doesn't yet restore state from OpenNMS. Harmless but creates extra events — see README Known Issues |
