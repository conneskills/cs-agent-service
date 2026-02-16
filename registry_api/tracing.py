"""
OpenTelemetry tracing for Agent Registry API.

Sends spans to Phoenix (or any OTLP-compatible collector) via gRPC.
If OTEL_EXPORTER_OTLP_ENDPOINT is not set, returns a no-op tracer.
"""

import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_tracer = None


def init_tracing(service_name: str = "agent-registry-api"):
    """Initialize OTEL tracing. Returns the tracer instance."""
    global _tracer
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled (no-op)")
        from opentelemetry.trace import NoOpTracer
        _tracer = NoOpTracer()
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
        logger.warning("opentelemetry packages not installed — tracing disabled")
        from opentelemetry.trace import NoOpTracer
        _tracer = NoOpTracer()
        return _tracer
    except Exception as e:
        logger.warning(f"Failed to init tracing: {e} — tracing disabled")
        from opentelemetry.trace import NoOpTracer
        _tracer = NoOpTracer()
        return _tracer


def get_tracer():
    """Get the initialized tracer (or no-op if not initialized)."""
    global _tracer
    if _tracer is None:
        init_tracing()
    return _tracer
