"""
Unit tests for EmailServiceServicer (src/server.py).

Strategy
--------
- The telemetry module starts Prometheus + OTel + Pyroscope on import, which
  would fail in CI without real infra. We patch the entire module before it
  is imported so EmailServiceServicer can be instantiated cleanly.
- The Jinja2 environment is patched at the module level so tests control
  template rendering without touching the filesystem.
- gRPC-generated stubs (email_pb2 / email_pb2_grpc) are replaced with mocks
  so no proto compilation is required.
"""

import sys
import types
import logging
import grpc
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub out heavyweight imports BEFORE server.py is imported
# ---------------------------------------------------------------------------


def _make_telemetry_stub():
    """Return a minimal module that satisfies `from telemetry import start_rpc_metrics`."""
    mod = types.ModuleType("telemetry")

    def start_rpc_metrics(method: str):
        def end(code: str):
            pass

        return end

    mod.start_rpc_metrics = start_rpc_metrics
    return mod


def _make_grpc_health_stubs():
    """Stub grpc_health.v1 packages."""
    grpc_health = types.ModuleType("grpc_health")
    grpc_health_v1 = types.ModuleType("grpc_health.v1")

    class _HealthCheckResponse:
        SERVING = 1

        def __init__(self, status=1):
            self.status = status

    health_pb2 = types.ModuleType("grpc_health.v1.health_pb2")
    health_pb2.HealthCheckResponse = _HealthCheckResponse

    health_pb2_grpc = types.ModuleType("grpc_health.v1.health_pb2_grpc")
    health_pb2_grpc.HealthServicer = object  # base class – just needs to exist
    health_pb2_grpc.add_HealthServicer_to_server = MagicMock()

    grpc_health.v1 = grpc_health_v1
    grpc_health_v1.health_pb2 = health_pb2
    grpc_health_v1.health_pb2_grpc = health_pb2_grpc

    sys.modules.setdefault("grpc_health", grpc_health)
    sys.modules.setdefault("grpc_health.v1", grpc_health_v1)
    sys.modules.setdefault("grpc_health.v1.health_pb2", health_pb2)
    sys.modules.setdefault("grpc_health.v1.health_pb2_grpc", health_pb2_grpc)

    return health_pb2, health_pb2_grpc


def _make_email_pb2_stubs():
    """Stub src/generated email_pb2 / email_pb2_grpc."""

    class _Empty:
        pass

    email_pb2 = types.ModuleType("generated.email_pb2")
    email_pb2.Empty = _Empty

    email_pb2_grpc = types.ModuleType("generated.email_pb2_grpc")
    email_pb2_grpc.EmailServiceServicer = object
    email_pb2_grpc.add_EmailServiceServicer_to_server = MagicMock()

    generated = types.ModuleType("generated")
    generated.email_pb2 = email_pb2
    generated.email_pb2_grpc = email_pb2_grpc

    sys.modules.setdefault("generated", generated)
    sys.modules.setdefault("generated.email_pb2", email_pb2)
    sys.modules.setdefault("generated.email_pb2_grpc", email_pb2_grpc)

    return email_pb2, email_pb2_grpc


# Install stubs before importing server
sys.modules["telemetry"] = _make_telemetry_stub()
_health_pb2, _health_pb2_grpc = _make_grpc_health_stubs()
_email_pb2, _email_pb2_grpc = _make_email_pb2_stubs()

# Now import the module under test
import server  # noqa: E402  (src/ must be on sys.path – see pytest.ini / pyproject.toml)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_servicer(template_render_fn=None):
    """
    Instantiate EmailServiceServicer with the Jinja2 template patched.
    `template_render_fn` receives (order=...) and should return a str or raise.
    """
    mock_template = MagicMock()
    if template_render_fn is not None:
        mock_template.render.side_effect = template_render_fn
    else:
        mock_template.render.return_value = "<html>confirmation</html>"

    with patch.object(server, "template", mock_template):
        servicer = server.EmailServiceServicer()
        # Attach template mock so individual tests can inspect call args
        servicer._mock_template = mock_template
    return servicer, mock_template


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestSendOrderConfirmation_HappyPath:
    def test_returns_empty_on_success(self, valid_request, mock_grpc_context):
        servicer, _ = _make_servicer()
        with patch.object(server, "template", servicer._mock_template):
            result = servicer.SendOrderConfirmation(valid_request, mock_grpc_context)
        assert isinstance(result, _email_pb2.Empty)

    def test_no_grpc_error_set_on_success(self, valid_request, mock_grpc_context):
        servicer, _ = _make_servicer()
        with patch.object(server, "template", servicer._mock_template):
            servicer.SendOrderConfirmation(valid_request, mock_grpc_context)
        mock_grpc_context.set_code.assert_not_called()
        mock_grpc_context.set_details.assert_not_called()

    def test_template_rendered_with_order(self, valid_request, mock_grpc_context):
        servicer, mock_tmpl = _make_servicer()
        with patch.object(server, "template", mock_tmpl):
            servicer.SendOrderConfirmation(valid_request, mock_grpc_context)
        mock_tmpl.render.assert_called_once_with(order=valid_request.order)

    def test_multiple_items_renders_once(self, multi_item_request, mock_grpc_context):
        servicer, mock_tmpl = _make_servicer()
        with patch.object(server, "template", mock_tmpl):
            servicer.SendOrderConfirmation(multi_item_request, mock_grpc_context)
        mock_tmpl.render.assert_called_once()

    def test_empty_items_list_succeeds(self, empty_items_request, mock_grpc_context):
        servicer, mock_tmpl = _make_servicer()
        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(
                empty_items_request, mock_grpc_context
            )
        assert isinstance(result, _email_pb2.Empty)
        mock_grpc_context.set_code.assert_not_called()


# ---------------------------------------------------------------------------
# Template error handling
# ---------------------------------------------------------------------------


class TestSendOrderConfirmation_TemplateErrors:
    def _assert_internal_error(self, mock_context):
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
        mock_context.set_details.assert_called_once()
        detail_msg = mock_context.set_details.call_args[0][0]
        assert (
            "confirmation mail" in detail_msg.lower() or "error" in detail_msg.lower()
        )

    def test_template_error_sets_internal_status(
        self, valid_request, mock_grpc_context
    ):
        from jinja2 import TemplateError

        def bad_render(**kwargs):
            raise TemplateError("syntax boom")

        servicer, mock_tmpl = _make_servicer(template_render_fn=bad_render)
        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(valid_request, mock_grpc_context)

        assert isinstance(result, _email_pb2.Empty)
        self._assert_internal_error(mock_grpc_context)

    def test_template_not_found_sets_internal_status(
        self, valid_request, mock_grpc_context
    ):
        from jinja2 import TemplateNotFound

        def missing_render(**kwargs):
            raise TemplateNotFound("confirmation.html")

        servicer, mock_tmpl = _make_servicer(template_render_fn=missing_render)
        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(valid_request, mock_grpc_context)

        assert isinstance(result, _email_pb2.Empty)
        # TemplateNotFound is a subclass of TemplateError — same code path
        mock_grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

    def test_template_syntax_error_returns_empty(
        self, valid_request, mock_grpc_context
    ):
        from jinja2 import TemplateSyntaxError

        def syntax_render(**kwargs):
            raise TemplateSyntaxError("unexpected '}'", lineno=5)

        servicer, mock_tmpl = _make_servicer(template_render_fn=syntax_render)
        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(valid_request, mock_grpc_context)

        assert isinstance(result, _email_pb2.Empty)


# ---------------------------------------------------------------------------
# Unexpected exception handling
# ---------------------------------------------------------------------------


class TestSendOrderConfirmation_UnexpectedErrors:
    def test_unexpected_exception_sets_internal(self, mock_grpc_context, make_request):
        """Any non-TemplateError exception must still return Empty + INTERNAL."""
        servicer, mock_tmpl = _make_servicer()
        mock_tmpl.render.side_effect = RuntimeError("unexpected crash")

        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(make_request(), mock_grpc_context)

        assert isinstance(result, _email_pb2.Empty)
        mock_grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
        detail = mock_grpc_context.set_details.call_args[0][0]
        assert "failed" in detail.lower() or "send" in detail.lower()

    def test_attribute_error_on_bad_request_handled(self, mock_grpc_context):
        """Malformed request object falls into the outer except."""

        class BrokenRequest:
            @property
            def email(self):
                raise AttributeError("no email")

        servicer, mock_tmpl = _make_servicer()
        with patch.object(server, "template", mock_tmpl):
            result = servicer.SendOrderConfirmation(BrokenRequest(), mock_grpc_context)

        assert isinstance(result, _email_pb2.Empty)
        mock_grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestSendOrderConfirmation_Logging:
    def test_logs_recipient_email_on_success(
        self, valid_request, mock_grpc_context, caplog
    ):
        servicer, mock_tmpl = _make_servicer()
        with caplog.at_level(logging.INFO, logger="email-service"):
            with patch.object(server, "template", mock_tmpl):
                servicer.SendOrderConfirmation(valid_request, mock_grpc_context)
        assert valid_request.email in caplog.text

    def test_logs_error_on_template_failure(
        self, valid_request, mock_grpc_context, caplog
    ):
        from jinja2 import TemplateError

        servicer, mock_tmpl = _make_servicer(
            template_render_fn=lambda **kw: (_ for _ in ()).throw(TemplateError("boom"))
        )
        with caplog.at_level(logging.ERROR, logger="email-service"):
            with patch.object(server, "template", mock_tmpl):
                servicer.SendOrderConfirmation(valid_request, mock_grpc_context)
        assert any("template" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# HealthServicer
# ---------------------------------------------------------------------------


class TestHealthServicer:
    def test_check_returns_serving(self, mock_grpc_context):
        servicer = server.HealthServicer()
        response = servicer.Check(MagicMock(), mock_grpc_context)
        assert response.status == _health_pb2.HealthCheckResponse.SERVING
