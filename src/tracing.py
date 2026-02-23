"""
OpenTelemetry tracing setup for Phoenix integration and agent lifecycle.

This module provides a lightweight TracerManager that configures an OTLP exporter
when OTEL_ENDPOINT (or PHOENIX_OTLP_ENDPOINT) is available in the environment.
If no endpoint is provided, tracing remains disabled gracefully.
"""

import os
import time
from typing import Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    # Try grpc exporter first, fall back to http if not available
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPSpanExporterGrpc,
        )
        OTLPSpanExporter = OTLPSpanExporterGrpc
    except Exception:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPSpanExporterHttp,
        )
        OTLPSpanExporter = OTLPSpanExporterHttp

    OTEL_AVAILABLE = True
except Exception:
    OTEL_AVAILABLE = False
    trace = None


class TracerManager:
    """Centralized OTEL tracer management."""

    enabled: bool = False
    tracer = None
    provider = None

    @staticmethod
    def init_tracing() -> bool:
        """Initialize OpenTelemetry tracing if a valid endpoint is configured."""
        global OTEL_AVAILABLE
        if not OTEL_AVAILABLE:
            TracerManager.enabled = False
            return False

        # Endpoint can come from env var or application config; try common names
        endpoint = os.getenv("OTEL_ENDPOINT") or os.getenv("PHOENIX_OTLP_ENDPOINT") or os.getenv("PHOENIX_ENDPOINT")
        if not endpoint:
            # No endpoint configured; tracing remains disabled
            TracerManager.enabled = False
            return False

        try:
            provider = TracerProvider()
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            TracerManager.tracer = trace.get_tracer(__name__)
            TracerManager.provider = provider
            TracerManager.enabled = True
            return True
        except Exception:
            TracerManager.enabled = False
            return False

    @staticmethod
    def get_tracer():
        if not TracerManager.enabled:
            return None
        return TracerManager.tracer

    @staticmethod
    def get_status() -> dict:
        """Return the current tracing status for health checks."""
        return {
            "enabled": TracerManager.enabled,
            "otel_available": OTEL_AVAILABLE,
            "endpoint": os.getenv("OTEL_ENDPOINT") or os.getenv("PHOENIX_OTLP_ENDPOINT") or os.getenv("PHOENIX_ENDPOINT"),
            "has_tracer": TracerManager.tracer is not None,
        }


def init_tracing_from_config() -> bool:
    """Backward-compatible helper alias."""
    return TracerManager.init_tracing()
