#!/bin/sh
set -x
apk add --no-cache mosquitto-clients curl &&
SELF=$(cat /etc/hostname | tr -d '[:space:]') &&
CONTAINER_NAME=$(curl -s --unix-socket /var/run/docker.sock \
  "http://localhost/containers/${SELF}/json" | \
  grep -o '"Name":"[^"]*"' | head -1 | cut -d'"' -f4)
INDEX=$(echo "$CONTAINER_NAME" | awk -F'-' '{print $NF}')
INDEX=${INDEX:-1}
START=$(( (INDEX - 1) * 15 + 1 ))

while true; do
  NOW=$(date +%s)
  SECS_IN_DAY=$(( NOW % 86400 ))

  for i in $(seq 0 14); do
    site="site$(( START + i ))"

    temp=$(awk -v secs="$SECS_IN_DAY" -v site="${site#site}" '
      BEGIN {
        pi = 3.14159265
        phase = (secs - 10800) / 86400 * 2 * pi
        base = 17; amplitude = 5
        srand(secs + site * 9973)
        noise = (rand() - 0.5) * 0.4
        printf "%.1f", base + amplitude * sin(phase) + noise
      }')

    power=$(awk -v secs="$SECS_IN_DAY" -v site="${site#site}" '
      BEGIN {
        pi = 3.14159265
        phase = (secs - 14400) / 86400 * 2 * pi
        base = 350; amplitude = 70
        srand(secs + site * 9973 + 1)
        noise = (rand() - 0.5) * 5
        printf "%.1f", base + amplitude * sin(phase) + noise
      }')

    hum="65.0"

    # Dynamic M6 corridor positioning
    # Site 1 = southern end (London area), higher sites = further north
    # M6 runs roughly from 51.5 lat (London) to 54.9 lat (Newcastle)
    # and 0.1W lon (London) to 2.7W lon (northwest)
    geo=$(awk -v site="${site#site}" -v total=150 '
      BEGIN {
        # M6 waypoints: lat, lon pairs from south to north
        n = 8
        lat[1]=51.5074; lon[1]=-0.1278   # London
        lat[2]=52.2820; lon[2]=-1.5849   # Coventry (M6 starts)
        lat[3]=52.4862; lon[3]=-1.8904   # Birmingham
        lat[4]=52.7500; lon[4]=-2.1000   # Wolverhampton area
        lat[5]=53.0000; lon[5]=-2.2000   # Stoke-on-Trent
        lat[6]=53.4808; lon[6]=-2.2426   # Manchester
        lat[7]=53.7632; lon[7]=-2.7044   # Preston
        lat[8]=54.9783; lon[8]=-1.6178   # Newcastle

        # interpolate position along route
        t = (site - 1) / (total - 1) * (n - 1) + 1
        seg = int(t)
        if (seg >= n) seg = n - 1
        frac = t - seg

        ilat = lat[seg] + frac * (lat[seg+1] - lat[seg])
        ilon = lon[seg] + frac * (lon[seg+1] - lon[seg])

        # add small random offset so sites dont overlap exactly
        srand(site * 9973)
        ilat += (rand() - 0.5) * 0.05
        ilon += (rand() - 0.5) * 0.05

        printf "%.4f,%.4f", ilat, ilon
      }')

    mosquitto_pub -h mosquitto -t lab/temp/$site -m "$temp"
    mosquitto_pub -h mosquitto -t lab/humidity/$site -m "$hum"
    mosquitto_pub -h mosquitto -t lab/power/$site -m "$power"
    mosquitto_pub -h mosquitto -t lab/location/$site -m "$geo"
  done

  # Publish retained discovery JSON
  discovery=$(awk -v start="$START" '
    BEGIN {
      printf "["
      for (i = 0; i < 15; i++) {
        if (i > 0) printf ","
        printf "{\"{#SITE}\":\"site%d\"}", start + i
      }
      printf "]"
    }')
  mosquitto_pub -r -h mosquitto -t lab/discovery -m "$discovery"

  sleep 10
done
