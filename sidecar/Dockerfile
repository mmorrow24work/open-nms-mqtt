FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir paho-mqtt requests
COPY sidecar.py .
CMD ["python", "-u", "sidecar.py"]
