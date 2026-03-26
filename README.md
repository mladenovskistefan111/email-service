# email-service

A gRPC service that sends order confirmation emails on the platform-demo e-commerce platform. It receives order data from `checkout-service`, renders an HTML confirmation template, and logs the result. Part of a broader microservices platform built with full observability, GitOps, and internal developer platform tooling.

## Overview

The service exposes one gRPC method:

| Method | Description |
|---|---|
| `SendOrderConfirmation` | Accepts an order and recipient email, renders an HTML confirmation, and logs it |

**Port:** `8080` (gRPC)  
**Metrics Port:** `9464` (Prometheus)  
**Protocol:** gRPC  
**Language:** Python  
**Called by:** `checkout-service`

## Requirements

- Python 3.12+
- Docker
- `grpcurl` for manual testing

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PORT` | No | gRPC server port (default: `8080`) |
| `METRICS_PORT` | No | Prometheus metrics port (default: `9464`) |
| `OTEL_SERVICE_NAME` | No | Service name reported to OTel (default: `email-service`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP HTTP endpoint (default: `http://localhost:4318`) |
| `PYROSCOPE_ADDR` | No | Pyroscope profiling endpoint (default: `http://localhost:4040`) |
| `SERVICE_VERSION` | No | Service version tag (default: `1.0.0`) |

## Running Locally

### 1. Install dependencies

```bash
pip install pip-tools
pip-compile requirements.in
pip install -r requirements.txt
```

### 2. Run the service

```bash
python src/server.py
```

### 3. Run with Docker

```bash
docker build -t email-service .

docker run -p 8080:8080 -p 9095:9464 \
  email-service
```

## Testing

### Manual gRPC testing

Install `grpcurl` then, from the service root:

```bash
# send an order confirmation
grpcurl -plaintext \
  -proto proto/email.proto \
  -d '{
    "email": "test@example.com",
    "order": {
      "order_id": "ord-123",
      "shipping_tracking_id": "track-456",
      "shipping_cost": {"currency_code": "USD", "units": 5, "nanos": 0},
      "shipping_address": {"street_address": "1 Main St", "city": "Brooklyn", "state": "NY", "country": "US", "zip_code": 11201},
      "items": []
    }
  }' \
  localhost:8080 \
  hipstershop.EmailService/SendOrderConfirmation

# health check
grpcurl -plaintext \
  -proto proto/health.proto \
  localhost:8080 \
  grpc.health.v1.Health/Check
```

### Generate traffic

```bash
while true; do
  grpcurl -plaintext \
    -proto proto/email.proto \
    -d '{"email": "test@example.com", "order": {"order_id": "ord-123"}}' \
    localhost:8080 \
    hipstershop.EmailService/SendOrderConfirmation
  sleep 1
done
```

## Project Structure

```
├── proto/
│   ├── email.proto            # Service definition and message types
│   └── health.proto           # gRPC health check
├── src/
│   ├── server.py              # gRPC server, service implementation
│   ├── telemetry.py           # OpenTelemetry traces, Prometheus metrics, Pyroscope profiling
│   ├── generated/             # Proto-generated stubs (built in Dockerfile)
│   └── __init__.py
├── templates/
│   └── confirmation.html      # Jinja2 order confirmation email template
├── requirements.in            # Direct dependencies
├── requirements.txt           # Pinned lockfile
└── Dockerfile                 # Two-stage build with proto compilation
```

## Observability

- **Traces** — OTLP HTTP → Alloy → Tempo. Inbound server spans instrumented automatically via `GrpcInstrumentorServer`.
- **Metrics** — Prometheus endpoint on `:9464/metrics`, scraped by Alloy → Mimir. Exposes `rpc_server_duration`, `rpc_server_requests_total`, `rpc_server_active_requests`.
- **Logs** — JSON structured logs to stdout, collected by Alloy via Docker socket → Loki.
- **Profiles** — Continuous CPU and heap profiling via Pyroscope SDK → Pyroscope.

## Part Of

This service is part of [platform-demo](https://github.com/mladenovskistefan111) — a full platform engineering project featuring microservices, observability (LGTM stack), GitOps (Argo CD), policy enforcement (Kyverno), infrastructure provisioning (Crossplane), and an internal developer portal (Backstage).