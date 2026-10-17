# API

Package `hipstershop`, service `EmailService` ([`proto/email.proto`](https://github.com/platform-boutique/app-email-service/blob/main/proto/email.proto)); health in [`proto/health.proto`](https://github.com/platform-boutique/app-email-service/blob/main/proto/health.proto).

| Method | Request | Response | Behaviour |
|---|---|---|---|
| `SendOrderConfirmation` | `{ string email, OrderResult order }` | `Empty` | Renders `templates/confirmation.html` with the order (autoescaped); on success logs "A request to send order confirmation email to <email> has been received."; on template or unexpected error sets gRPC `INTERNAL` |

The rendered HTML is discarded. The template references `street_address_1` / `street_address_2`, which do not exist in the `Address` message, so those render as empty strings.
