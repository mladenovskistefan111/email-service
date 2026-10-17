# email-service

A gRPC service that handles order-confirmation emails for the platform-demo e-commerce platform. **It is a stub:** it renders the HTML confirmation template to prove the order data is valid, then logs that a confirmation was requested. It does **not** send any email (no SMTP, no provider). It is stateless, has no downstream dependencies, and is called only by `checkout-service`.

Part of the [platform-demo](https://github.com/mladenovskistefan111) platform — microservices, observability (LGTM stack), GitOps (Argo CD), policy enforcement (Kyverno), infrastructure provisioning (Crossplane) and an internal developer portal (Backstage). See the master `README.md` in the platform-demo root for the whole-system view.

## At a glance

| | |
|---|---|
| **Language / runtime** | Python 3.12 in the image (3.13 pinned for local dev), `grpcio`, Jinja2 |
| **Image** | `mladenovskistefan/email-service` |
| **Protocol / port** | gRPC (HTTP/2, plaintext) on `8080` |
| **Metrics** | Pushed over OTLP/gRPC to Alloy → Mimir every 15 s (no scrape endpoint). Dashboard names: `rpc_server_duration_seconds_{bucket,count,sum}`, `rpc_server_requests_total`, `rpc_server_active_requests` |
| **Health** | `grpc.health.v1.Health/Check` on `8080` — static `SERVING` |
| **State** | None |
| **Depends on** | Nothing (optional: OTLP collector, Pyroscope) |
| **Called by** | `checkout-service` (`SendOrderConfirmation`) |
| **gRPC reflection** | Not enabled — pass `-proto` to `grpcurl` |

## API

Package `hipstershop`, service `EmailService` ([`proto/email.proto`](proto/email.proto)); health in [`proto/health.proto`](proto/health.proto).

| Method | Request | Response | Behaviour |
|---|---|---|---|
| `SendOrderConfirmation` | `{ string email, OrderResult order }` | `Empty` | Renders `templates/confirmation.html` with the order (autoescaped); on success logs "A request to send order confirmation email to <email> has been received."; on template or unexpected error sets gRPC `INTERNAL` |

The rendered HTML is discarded. The template references `street_address_1` / `street_address_2`, which do not exist in the `Address` message, so those render as empty strings.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8080` | gRPC listen port |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP/**gRPC** endpoint for **traces, metrics and logs** (scheme required), e.g. `http://alloy.monitoring.svc.cluster.local:4317`. Legacy fallback: `COLLECTOR_SERVICE_ADDR` (`host:port`) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | Milliseconds between metric pushes |
| `OTEL_SERVICE_NAME` | `email-service` | `service.name` — becomes the Prometheus `job` and the Loki `service_name`; keep the default, dashboards depend on it |
| `SERVICE_VERSION` | `1.0.0` | `service.version` resource attribute |
| `PYROSCOPE_ADDR` | `http://localhost:4040` | Profiles use the Pyroscope SDK push protocol (**not** OTLP). Point it at Alloy (`http://alloy.monitoring.svc.cluster.local:4040`), which forwards to Pyroscope, or directly at Pyroscope |

Notes:

- No secrets and no mail-server settings exist.
- Telemetry is **pushed**, not scraped: traces, metrics and logs share one OTLP/gRPC endpoint (Alloy); profiles go to Pyroscope (via Alloy). `service.instance.id` is the pod hostname, so replicas stay distinct in Mimir.
- The former Prometheus endpoint (`METRICS_PORT`) no longer exists. Logs keep going to stdout and are additionally exported over OTLP with trace ids.
- Telemetry and profiling cannot be switched off with a flag; with no reachable collector the exporters just log errors and the service keeps serving.

## Container image

Multi-stage [`Dockerfile`](Dockerfile):

| Stage | Base | What happens |
|---|---|---|
| builder | `python:3.12-alpine` | installs `g++`/`linux-headers`, `pip install -r requirements.in`, **compiles the protos** with `grpc_tools.protoc` into `generated/` and patches the relative import in `email_pb2_grpc.py` |
| runtime | `python:3.12-alpine` | copies site-packages, generated stubs (`/app/src/generated`), `src/`, `templates/`; runs as non-root |

- **Entrypoint:** `python src/server.py` (working dir `/app`; `src/` is on `sys.path`, so `from generated import …` resolves).
- **User:** `appuser` — UID `100`, GID `101` (verified). Set `runAsUser: 100` for `runAsNonRoot`.
- **EXPOSE:** `8080` only.
- **Docker `HEALTHCHECK`:** Python `grpc.channel_ready_future` against `localhost:${PORT:-8080}` (honours the default).
- **Image size:** ~41 MB.
- **Reproducibility:** the image installs from `requirements.in` (direct dependencies pinned, transitive ones floating), **not** from the fully pinned `requirements.txt`. Builds on different days can pull different transitive versions. Switch to `requirements.txt` if you need byte-for-byte repeatability.
- The generated stubs are **not** in git; they only exist after the Docker build (see local dev below).

## Kubernetes deployment notes

**Workload:** stateless `Deployment`; scale freely.

**Ports to declare**

| Name | Port | Protocol | Expose via Service? |
|---|---|---|---|
| `grpc` | `8080` | TCP (HTTP/2) | Yes — `checkout-service` dials `email-service:8080` |

**Service DNS name expected by callers:** `email-service` (`checkout-service`: `EMAIL_SERVICE_ADDR=email-service:8080`). `recommendation-service` also listens on `8080` — different Service, no clash.

**Probes**

```yaml
readinessProbe:
  grpc: { port: 8080 }
  initialDelaySeconds: 3
  periodSeconds: 5
livenessProbe:
  grpc: { port: 8080 }
  periodSeconds: 10
  failureThreshold: 3
```

**Graceful shutdown:** the process runs as PID 1 and installs no `SIGTERM` handler. The kernel ignores unhandled signals for PID 1, so `SIGTERM` is dropped and every pod termination waits the full grace period before `SIGKILL`. Set `terminationGracePeriodSeconds: 5` (the service has no in-flight work worth waiting for). A proper fix is a `signal.signal(SIGTERM, …)` handler or a tiny init (`tini`) in the image.

**Security context**

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 100
  runAsGroup: 101
  allowPrivilegeEscalation: false
  capabilities: { drop: ["ALL"] }
  readOnlyRootFilesystem: true   # verified in-cluster; no writable /tmp was needed
```

**Resources** — requests sized from measured idle usage in the test stack (see the chart's `values.yaml` for limits):

```yaml
resources:
  requests: { cpu: 100m, memory: 64Mi }
  limits:   { cpu: "500m", memory: 192Mi }
```

**Config / secrets:** none today. If this ever becomes a real mailer, SMTP credentials belong in a `Secret`.

**Telemetry:** pushed, not scraped — OTLP/gRPC to Alloy (`global.monitoring.otlpEndpoint`), profiles to Alloy `:4040`. Metrics carry `job="email-service"` and `instance=<pod>`; no scrape annotations or `ServiceMonitor` are needed.

**Helm chart:** [`platform-demo-helm/email-service`](https://github.com/mladenovskistefan111/platform-demo-helm/tree/main/email-service) (built on the shared `platform-common` library chart). It ships with HA defaults — 2 replicas,
HPA, PodDisruptionBudget, topology spread, NetworkPolicy, restricted pod security context, probes and the full env contract (see Configuration) —
and was verified on a 3-node kind cluster under the `restricted` Pod Security Standard.

**Deployment and admission policies:** Argo CD deploys the chart from `platform-demo-helm` (`envs/<env>/values/email-service.yaml` pins the image digest; promotion is a pull request). In the cluster Kyverno enforces, for this service: pods named `app.kubernetes.io/name: email-service` that run under the ServiceAccount of the same name (Cilium derives the network identity from that label), an image from this repository pinned by digest and signed by our release pipeline, a read-only root filesystem, resource requests and a memory limit, readiness and liveness probes and no API token. The Helm CI evaluates the rendered chart against these policies before merge; see [`platform-demo-helm/policies`](https://github.com/mladenovskistefan111/platform-demo-helm/tree/main/policies).

## Observability

| Signal | Implementation | Destination |
|---|---|---|
| **Traces** | OpenTelemetry SDK, `GrpcInstrumentorServer`, OTLP/gRPC exporter (`BatchSpanProcessor`) | Alloy `:4317` → Tempo |
| **Metrics** | Hand-rolled RPC instruments, `PeriodicExportingMetricReader` over OTLP/gRPC every 15 s (replaces the Prometheus reader) | Alloy → Mimir |
| **Logs** | Python `logging` with a hand-built JSON format to stdout **and** an OTel `LoggingHandler` (OTLP/gRPC, with trace ids) | Alloy → Loki |
| **Profiles** | `pyroscope-io`, tagged with `version` | Alloy `:4040` → Pyroscope |

Metric names: `rpc_server_duration_seconds_{bucket,count,sum}` (buckets 1 ms … 10 s; the unit `s` yields `_seconds`), `rpc_server_requests_total`, `rpc_server_active_requests` (labels `rpc_system`, `rpc_service`, `rpc_method`, `rpc_grpc_status_code`). The JSON stdout line is built with a plain format string, so messages containing `"` can yield invalid JSON (the OTLP copy is unaffected).

Every series carries `job="email-service"` (from `service.name`) and `instance=<pod name>` (`service.instance.id`), which is what the Grafana dashboards select on. Logs land in Loki with `service_name="email-service"` and trace/span ids, so a log line links to its trace.

## Running locally

Requirements: Python 3.13 (see `.python-version`; 3.12 also works), Docker, [`grpcurl`](https://github.com/fullstorydev/grpcurl).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# generate the gRPC stubs (what the Dockerfile does) — required before running from source
mkdir -p src/generated && python -m grpc_tools.protoc -I proto \
  --python_out=src/generated --grpc_python_out=src/generated proto/email.proto
touch src/generated/__init__.py
sed -i 's/^import email_pb2 as email__pb2/from . import email_pb2 as email__pb2/' src/generated/email_pb2_grpc.py

python src/server.py          # run
pytest                        # tests (pytest.ini sets pythonpath=src)

docker build -t email-service .
docker run --rm -p 8080:8080 email-service
```

To regenerate pinned deps: `uv pip compile requirements.in -o requirements.txt` (the lockfile header shows `uv` was used).

### Manual gRPC testing (no reflection — pass the proto)

```bash
grpcurl -plaintext -proto proto/email.proto -d '{
  "email": "test@example.com",
  "order": {
    "order_id": "ord-123",
    "shipping_tracking_id": "track-456",
    "shipping_cost": {"currency_code": "USD", "units": 8, "nanos": 990000000},
    "shipping_address": {"street_address": "1 Main St", "city": "Brooklyn", "state": "NY", "country": "US", "zip_code": 11201},
    "items": [{"item": {"product_id": "OLJCESPC7Z", "quantity": 1}, "cost": {"currency_code": "USD", "units": 19, "nanos": 990000000}}]
  }
}' localhost:8080 hipstershop.EmailService/SendOrderConfirmation

grpcurl -plaintext -proto proto/health.proto localhost:8080 grpc.health.v1.Health/Check
```

## Project structure

```
├── src/
│   ├── server.py        # gRPC server (10-thread pool), EmailService + Health servicers, Jinja2 rendering
│   ├── telemetry.py     # OTel traces/metrics, Prometheus server, Pyroscope; must be imported first
│   ├── generated/       # protoc output (git: only __init__.py; real stubs are built in Docker)
│   └── __init__.py
├── templates/confirmation.html     # Jinja2 order-confirmation template
├── proto/               # email.proto, health.proto
├── requirements.in / requirements.txt / requirements-dev.txt
├── pyproject.toml / pytest.ini / .python-version / .trivyignore
├── Dockerfile
└── docs/                # empty placeholder
```

## Known limitations

- Does not send email.
- `SIGTERM` is ignored when running as PID 1 (see Graceful shutdown).
- Image build uses the un-pinned `requirements.in`.
- Template placeholders `street_address_1/2` don't exist in the proto.
- Recipient addresses are logged.
