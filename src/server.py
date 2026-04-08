# telemetry must be imported first to patch grpc before anything else
from telemetry import start_rpc_metrics  # noqa: F401, E402

import os
import time
import logging
from concurrent import futures

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError

from generated import email_pb2, email_pb2_grpc

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("email-service")
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        '{"timestamp": %(created)f, "severity": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
    )
)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------

env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)
template = env.get_template("confirmation.html")

# ---------------------------------------------------------------------------
# gRPC service implementation
# ---------------------------------------------------------------------------


class EmailServiceServicer(email_pb2_grpc.EmailServiceServicer):
    """Dummy email service — logs the confirmation instead of sending real email."""

    def SendOrderConfirmation(self, request, context):
        end_metrics = start_rpc_metrics("SendOrderConfirmation")
        try:
            email = request.email
            order = request.order

            # Render the confirmation template
            try:
                template.render(order=order)
            except TemplateError as err:
                logger.error(f"Template rendering failed: {err}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(
                    "An error occurred when preparing the confirmation mail."
                )
                end_metrics("13")  # INTERNAL
                return email_pb2.Empty()

            logger.info(
                f"A request to send order confirmation email to {email} has been received."
            )
            end_metrics("0")  # OK
            return email_pb2.Empty()

        except Exception as err:
            logger.error(f"SendOrderConfirmation failed: {err}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to send order confirmation.")
            end_metrics("13")  # INTERNAL
            return email_pb2.Empty()


class HealthServicer(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING,
        )


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def main():
    port = os.environ.get("PORT", "8080")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    email_pb2_grpc.add_EmailServiceServicer_to_server(EmailServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)

    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"EmailService gRPC server started on port {port}")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    main()
