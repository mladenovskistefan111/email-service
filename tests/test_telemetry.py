"""
Unit tests for telemetry.py — specifically the start_rpc_metrics helper.

All OTel SDK objects (MeterProvider, counters, histograms, etc.) and the
Pyroscope / Prometheus side-effects are mocked so these tests run in CI
with zero external infra.
"""

import sys
import types
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub every telemetry side-effect before importing the module
# ---------------------------------------------------------------------------


def _install_otel_stubs():
    """Replace opentelemetry packages with no-op mocks."""

    def _mod(name):
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    # opentelemetry.trace
    trace_mod = _mod("opentelemetry.trace")
    trace_mod.set_tracer_provider = MagicMock()

    # opentelemetry.metrics
    metrics_mod = _mod("opentelemetry.metrics")
    fake_meter = MagicMock()
    metrics_mod.set_meter_provider = MagicMock()
    metrics_mod.get_meter = MagicMock(return_value=fake_meter)

    # SDK / exporters
    for name in [
        "opentelemetry",
        "opentelemetry.sdk",
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.trace.export",
        "opentelemetry.exporter.otlp.proto.http",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.sdk.metrics",
        "opentelemetry.sdk.metrics.view",
        "opentelemetry.sdk.metrics._internal",
        "opentelemetry.sdk.metrics._internal.aggregation",
        "opentelemetry.exporter.prometheus",
        "opentelemetry.sdk.resources",
        "opentelemetry.instrumentation.grpc",
    ]:
        sys.modules.setdefault(name, types.ModuleType(name))

    # Concrete classes used by telemetry.py
    sys.modules["opentelemetry.sdk.trace"].TracerProvider = MagicMock()
    sys.modules["opentelemetry.sdk.trace.export"].BatchSpanProcessor = MagicMock()
    sys.modules[
        "opentelemetry.exporter.otlp.proto.http.trace_exporter"
    ].OTLPSpanExporter = MagicMock()
    sys.modules["opentelemetry.sdk.metrics"].MeterProvider = MagicMock()
    sys.modules["opentelemetry.sdk.metrics.view"].View = MagicMock()
    sys.modules[
        "opentelemetry.sdk.metrics._internal.aggregation"
    ].ExplicitBucketHistogramAggregation = MagicMock()
    sys.modules[
        "opentelemetry.exporter.prometheus"
    ].PrometheusMetricReader = MagicMock()

    resource_mod = sys.modules["opentelemetry.sdk.resources"]
    resource_mod.Resource = MagicMock()
    resource_mod.SERVICE_NAME = "service.name"
    resource_mod.SERVICE_VERSION = "service.version"

    grpc_instr = sys.modules["opentelemetry.instrumentation.grpc"]
    grpc_instr.GrpcInstrumentorServer = MagicMock()

    return fake_meter


def _install_misc_stubs():
    prometheus_client = types.ModuleType("prometheus_client")
    prometheus_client.start_http_server = MagicMock()
    sys.modules["prometheus_client"] = prometheus_client

    pyroscope_mod = types.ModuleType("pyroscope")
    pyroscope_mod.configure = MagicMock()
    sys.modules["pyroscope"] = pyroscope_mod


_fake_meter = _install_otel_stubs()
_install_misc_stubs()

# Now import the real telemetry module
import telemetry  # noqa: E402  (src/ must be on sys.path)


# ---------------------------------------------------------------------------
# Tests for start_rpc_metrics
# ---------------------------------------------------------------------------


class TestStartRpcMetrics:
    def test_returns_callable(self):
        end = telemetry.start_rpc_metrics("TestMethod")
        assert callable(end)

    def test_end_callable_accepts_status_code(self):
        end = telemetry.start_rpc_metrics("TestMethod")
        # Should not raise
        end("0")

    def test_end_callable_accepts_error_status(self):
        end = telemetry.start_rpc_metrics("TestMethod")
        end("13")  # INTERNAL

    def test_active_requests_incremented_on_start(self):
        counter = telemetry.rpc_server_active_requests
        counter.add.reset_mock()

        telemetry.start_rpc_metrics("MyMethod")

        first_call = counter.add.call_args_list[0]
        assert first_call[0][0] == 1  # value=1 (increment)

    def test_active_requests_decremented_on_end(self):
        counter = telemetry.rpc_server_active_requests
        counter.add.reset_mock()

        end = telemetry.start_rpc_metrics("MyMethod")
        end("0")

        calls = counter.add.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == 1  # increment on start
        assert calls[1][0][0] == -1  # decrement on end

    def test_duration_recorded_on_end(self):
        hist = telemetry.rpc_server_duration
        hist.record.reset_mock()

        end = telemetry.start_rpc_metrics("MyMethod")
        end("0")

        hist.record.assert_called_once()
        elapsed = hist.record.call_args[0][0]
        assert elapsed >= 0

    def test_request_counter_incremented_on_end(self):
        ctr = telemetry.rpc_server_requests_total
        ctr.add.reset_mock()

        end = telemetry.start_rpc_metrics("MyMethod")
        end("0")

        ctr.add.assert_called_once()
        assert ctr.add.call_args[0][0] == 1

    def test_attributes_contain_method_name(self):
        counter = telemetry.rpc_server_active_requests
        counter.add.reset_mock()

        telemetry.start_rpc_metrics("SpecificMethodName")

        attrs = counter.add.call_args[0][1]
        assert attrs["rpc_method"] == "SpecificMethodName"

    def test_attributes_contain_service_name(self):
        counter = telemetry.rpc_server_active_requests
        counter.add.reset_mock()

        telemetry.start_rpc_metrics("AnyMethod")

        attrs = counter.add.call_args[0][1]
        assert "hipstershop.EmailService" in attrs["rpc_service"]

    def test_end_attributes_contain_grpc_status_code(self):
        hist = telemetry.rpc_server_duration
        hist.record.reset_mock()

        end = telemetry.start_rpc_metrics("AnyMethod")
        end("13")

        final_attrs = hist.record.call_args[0][1]
        assert final_attrs["rpc_grpc_status_code"] == "13"

    def test_independent_calls_do_not_share_state(self):
        """Two concurrent metric spans should track independently."""
        hist = telemetry.rpc_server_duration
        hist.record.reset_mock()

        end1 = telemetry.start_rpc_metrics("Method1")
        end2 = telemetry.start_rpc_metrics("Method2")
        end1("0")
        end2("0")

        assert hist.record.call_count == 2
        attrs1 = hist.record.call_args_list[0][0][1]
        attrs2 = hist.record.call_args_list[1][0][1]
        assert attrs1["rpc_method"] == "Method1"
        assert attrs2["rpc_method"] == "Method2"
