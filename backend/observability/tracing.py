"""OpenTelemetry tracing setup and agent span decorator."""

import time
from functools import wraps
from typing import Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer: trace.Tracer | None = None


def setup_tracing(
    service_name: str = "pokedex-arcana",
    otlp_endpoint: str = "http://localhost:4317",
) -> None:
    """Initialise the OpenTelemetry SDK with a BatchSpanProcessor + OTLP exporter.

    Call once at application startup before any agents are invoked.
    """
    global _tracer

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)


def _get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        # Fallback: use the globally configured provider (may be a no-op in tests)
        _tracer = trace.get_tracer("pokedex-arcana")
    return _tracer


def _estimate_tokens(value: object) -> int:
    """Rough token estimate: len(str(value)) // 4."""
    return max(0, len(str(value)) // 4)


def trace_agent(agent_name: str) -> Callable:
    """Decorator that wraps an async agent function with an OpenTelemetry span.

    The span is named ``agent.<agent_name>`` and carries the attributes:
    - ``agent.name``      – the agent identifier
    - ``input.tokens``    – estimated token count of the function arguments
    - ``output.tokens``   – estimated token count of the return value
    - ``latency_ms``      – wall-clock duration in milliseconds

    Exceptions are recorded as span events and re-raised; the span is always
    ended in the ``finally`` block.

    Usage::

        @trace_agent("stats")
        async def run_stats_agent(sub_task: SubTask) -> StatsResult:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = _get_tracer()
            input_tokens = _estimate_tokens(args) + _estimate_tokens(kwargs)

            with tracer.start_as_current_span(f"agent.{agent_name}") as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("input.tokens", input_tokens)

                start_ms = time.monotonic() * 1000
                try:
                    result = await func(*args, **kwargs)
                    output_tokens = _estimate_tokens(result)
                    span.set_attribute("output.tokens", output_tokens)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    raise
                finally:
                    latency_ms = int(time.monotonic() * 1000 - start_ms)
                    span.set_attribute("latency_ms", latency_ms)

        return wrapper

    return decorator
