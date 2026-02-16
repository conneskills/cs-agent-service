"""
OpenTelemetry tracing for Agent Registry API.

Sends spans to Phoenix (or any OTLP-compatible collector) via gRPC.
Gracefully degrades:
- If OTEL_EXPORTER_OTLP_ENDPOINT is not set → no-op tracer
- If opentelemetry packages are not installed → no-op tracer
- If Phoenix is unreachable → no-op tracer (no crash)
"""

import os
import logging

logger = logging.getLogger(__name__)

_tracer = None


class _NoOpSpan:
    """Minimal no-op span for when tracing is unavailable."""
    def set_attribute(self, key, value): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    """Minimal no-op tracer that doesn't require opentelemetry."""
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()


def init_tracing(service_name: str = "agent-registry-api"):
    """Initialize OTEL tracing. Returns the tracer instance."""
    global _tracer
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled")
        _tracer = _NoOpTracer()
        return _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)

        logger.info(f"OTEL tracing enabled → {endpoint}")
        return _tracer

    except ImportError:
        logger.warning("opentelemetry packages not installed — tracing disabled (install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc)")
        _tracer = _NoOpTracer()
        return _tracer
    except Exception as e:
        logger.warning(f"Failed to init tracing: {e} — tracing disabled")
        _tracer = _NoOpTracer()
        return _tracer


def get_tracer():
    """Get the initialized tracer (or no-op if not initialized)."""
    global _tracer
    if _tracer is None:
        init_tracing()
    return _tracer
