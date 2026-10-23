# email-service

<div class="pd-hero" markdown>
<span class="pd-kicker">service · platform-demo</span>

A gRPC service that handles order-confirmation emails for the platform-demo e-commerce platform. **It is a stub:** it renders the HTML confirmation template to prove the order data is valid, then logs that a confirmation was requested. It does **not** send any email (no SMTP, no provider). It is stateless, has no downstream dependencies, and is called only by `checkout-service`.
</div>

<div class="pd-facts" markdown>
<div><span>Runtime</span><strong>Python 3.12</strong><small>Python</small></div>
<div><span>Listens on</span><strong>8080</strong><small>gRPC</small></div>
<div><span>State</span><strong>Stateless</strong></div>
<div><span>Image</span><strong>email-service</strong><small>mladenovskistefan/</small></div>
</div>

## Where it sits

Called by `checkout-service`. It has no downstream dependencies.

```mermaid
flowchart LR
  email_service["<b>email-service</b><br/>8080 (gRPC)"]:::me
  checkout_service["checkout-service"] --> email_service
  classDef me stroke-width:3px;
```

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

## Find it elsewhere

<div class="pd-cards" markdown>
<div><h4><a href="https://argocd.platform-demo.test/applications/argocd/dev-email-service">Argo CD</a></h4><p>Sync and health of <code>dev-email-service</code>.</p></div>
<div><h4><a href="https://grafana.platform-demo.test/d/email-service-overview">Grafana</a></h4><p>Latency, traffic and errors (<code>email-service-overview</code>).</p></div>
<div><h4><a href="https://github.com/platform-boutique/app-email-service">Repository</a></h4><p>Source, pull requests and releases of <code>app-email-service</code>.</p></div>
</div>

!!! info "Part of the platform-demo platform"
    Cross-cutting facts (service wiring, observability contract, Kubernetes translation, CI/CD) are in the
    [master reference](https://github.com/platform-boutique/platform-demo-docs). This site only describes email-service.
