#!/usr/bin/env python3
"""
OpenNMS MQTT Sidecar
Watches MQTT lab/# topics and automatically creates/manages:
  - Per-site OpenNMS nodes with lat/lon inventory (for Geo Map)
  - OpenNMS events carrying sensor metrics
"""

import os
import time
import logging
import requests
import paho.mqtt.client as mqtt
from requests.auth import HTTPBasicAuth

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
OPENNMS_URL            = os.environ.get('OPENNMS_URL',            'http://opennms:8980')
OPENNMS_USER           = os.environ.get('OPENNMS_USER',           'admin')
OPENNMS_PASSWORD       = os.environ.get('OPENNMS_PASSWORD',       'admin')
OPENNMS_FOREIGN_SOURCE = os.environ.get('OPENNMS_FOREIGN_SOURCE', 'MQTT-Sites')
MQTT_BROKER            = os.environ.get('MQTT_BROKER',            'mosquitto')
MQTT_PORT              = int(os.environ.get('MQTT_PORT',          '1883'))
MQTT_TOPIC             = os.environ.get('MQTT_TOPIC',             'lab/#')

AUTH = HTTPBasicAuth(OPENNMS_USER, OPENNMS_PASSWORD)
BASE = f'{OPENNMS_URL}/opennms/rest'

location_cache     = {}
provisioned        = set()
location_confirmed = set()  # sites whose lat/lon has been updated after initial provisioning
node_id_cache      = {}


# ── OpenNMS REST helpers ──────────────────────────────────────────────────────
def onms_get(path, **kwargs):
    r = requests.get(f'{BASE}{path}', auth=AUTH, timeout=10, **kwargs)
    r.raise_for_status()
    return r


def onms_post(path, **kwargs):
    r = requests.post(f'{BASE}{path}', auth=AUTH, timeout=10, **kwargs)
    r.raise_for_status()
    return r


def onms_put(path, **kwargs):
    r = requests.put(f'{BASE}{path}', auth=AUTH, timeout=10, **kwargs)
    r.raise_for_status()
    return r


# ── OpenNMS provisioning ──────────────────────────────────────────────────────
def ensure_foreign_source():
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<model-import xmlns="http://xmlns.opennms.org/xsd/config/model-import"
  foreign-source="{OPENNMS_FOREIGN_SOURCE}"
  date-stamp="2024-01-01T00:00:00.000+00:00"/>'''
    try:
        onms_get(f'/requisitions/{OPENNMS_FOREIGN_SOURCE}')
        log.info(f'Requisition {OPENNMS_FOREIGN_SOURCE} already exists')
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            onms_post('/requisitions', data=xml.encode(),
                      headers={'Content-Type': 'application/xml'})
            log.info(f'Created requisition {OPENNMS_FOREIGN_SOURCE}')
        else:
            raise


def create_node(site, lat='0', lon='0'):
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<node xmlns="http://xmlns.opennms.org/xsd/config/model-import"
  node-label="{site}"
  foreign-id="{site}">
  <interface ip-addr="127.0.0.1" snmp-primary="N" status="1">
    <monitored-service service-name="ICMP"/>
  </interface>
  <asset name="latitude" value="{lat}"/>
  <asset name="longitude" value="{lon}"/>
  <asset name="description" value="MQTT Sensor Site"/>
  <asset name="building" value="IoT Lab"/>
</node>'''
    onms_post(
        f'/requisitions/{OPENNMS_FOREIGN_SOURCE}/nodes',
        data=xml.encode(),
        headers={'Content-Type': 'application/xml'}
    )
    log.info(f'  Added node {site} to requisition ({lat}, {lon})')


def sync_requisition():
    onms_put(f'/requisitions/{OPENNMS_FOREIGN_SOURCE}/import?rescanExisting=false')
    log.info(f'  Triggered sync of {OPENNMS_FOREIGN_SOURCE}')


def get_node_id(site):
    if site in node_id_cache:
        return node_id_cache[site]
    try:
        r = onms_get('/nodes', params={
            'foreignSource': OPENNMS_FOREIGN_SOURCE,
            'foreignId': site
        })
        nodes = r.json().get('node', [])
        if isinstance(nodes, dict):
            nodes = [nodes]
        for n in nodes:
            if n.get('foreignId') == site:
                nid = n['id']
                node_id_cache[site] = nid
                return nid
    except Exception as e:
        log.debug(f'get_node_id({site}) failed: {e}')
    return None


def send_event(site, metric, value):
    node_id    = get_node_id(site)
    nodeid_xml = f'<nodeid>{node_id}</nodeid>' if node_id else ''
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<event>
  <uei>uei.opennms.org/generic/traps/SNMP_Trap_Fallback</uei>
  <source>mqtt-sidecar</source>
  {nodeid_xml}
  <host>{site}</host>
  <descr>MQTT metric: {metric} = {value} for {site}</descr>
  <parms>
    <parm>
      <parmName>site</parmName>
      <value type="string" encoding="text">{site}</value>
    </parm>
    <parm>
      <parmName>metric</parmName>
      <value type="string" encoding="text">{metric}</value>
    </parm>
    <parm>
      <parmName>value</parmName>
      <value type="string" encoding="text">{value}</value>
    </parm>
  </parms>
</event>'''
    try:
        onms_post('/events', data=xml.encode(),
                  headers={'Content-Type': 'application/xml'})
    except Exception as e:
        log.debug(f'send_event({site},{metric}) failed: {e}')


def provision_site(site):
    if site in provisioned:
        return

    log.info(f'=== Provisioning {site} ===')
    try:
        lat, lon = location_cache[site].split(',')
        create_node(site, lat.strip(), lon.strip())
        sync_requisition()
        provisioned.add(site)
        log.info(f'=== {site} provisioned OK ===')
    except Exception as e:
        log.error(f'Failed to provision {site}: {e}')


def update_node_location(site):
    try:
        lat, lon = location_cache[site].split(',')
        create_node(site, lat.strip(), lon.strip())
        onms_put(f'/requisitions/{OPENNMS_FOREIGN_SOURCE}/import?rescanExisting=true')
        log.info(f'  Updated location for {site}: ({lat.strip()}, {lon.strip()})')
    except Exception as e:
        log.debug(f'update_node_location({site}) failed: {e}')


# ── MQTT callbacks ────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info(f'Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT}')
        client.subscribe(MQTT_TOPIC)
        log.info(f'Subscribed to {MQTT_TOPIC}')
    else:
        log.error(f'MQTT connect failed rc={rc}')


def on_message(client, userdata, msg):
    parts = msg.topic.split('/')
    if len(parts) != 3:
        return
    _, metric, site = parts

    if metric == 'location':
        location_cache[site] = msg.payload.decode()
        if site not in provisioned:
            provision_site(site)
        elif site not in location_confirmed:
            update_node_location(site)
            location_confirmed.add(site)
    elif site in provisioned and metric in ('temp', 'humidity', 'power'):
        send_event(site, metric, msg.payload.decode())


# ── Startup sync ──────────────────────────────────────────────────────────────
def startup_sync():
    log.info('Waiting for OpenNMS API...')
    for attempt in range(30):
        try:
            r = requests.get(
                f'{OPENNMS_URL}/opennms/rest/info',
                auth=AUTH, timeout=10
            )
            r.raise_for_status()
            version = r.json().get('version', 'unknown')
            log.info(f'OpenNMS ready — version {version}')
            break
        except Exception as e:
            log.info(f'  attempt {attempt+1}/30: {e}')
            time.sleep(10)
    else:
        log.error('OpenNMS API not reachable after 5 minutes — exiting')
        raise SystemExit(1)

    ensure_foreign_source()

    try:
        r = onms_get(f'/requisitions/{OPENNMS_FOREIGN_SOURCE}',
                     headers={'Accept': 'application/json'})
        nodes = r.json().get('node', [])
        if isinstance(nodes, dict):
            nodes = [nodes]
        for n in nodes:
            fid = n.get('foreignId', '')
            if fid.startswith('site'):
                provisioned.add(fid)
                location_confirmed.add(fid)
                log.info(f'  Already provisioned: {fid}')
    except Exception as e:
        log.error(f'Startup sync failed: {e}')


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    startup_sync()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    log.info(f'Connecting to MQTT {MQTT_BROKER}:{MQTT_PORT}...')
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever()
