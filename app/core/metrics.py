"""
Prometheus metrics for PIX payment platform observability.
Exposes counters, histograms and gauges for financial operations,
gateway health, and webhook processing.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response

router = APIRouter(tags=["Metrics"])

# -- PIX transaction counters --
pix_transactions_total = Counter(
    "pix_transactions_total",
    "Total PIX transactions created",
    ["type", "status"],
)

pix_balance_mutations_total = Counter(
    "pix_balance_mutations_total",
    "Total balance mutations (debit/credit)",
    ["direction"],
)

# -- Webhook counters --
pix_webhook_events_total = Counter(
    "pix_webhook_events_total",
    "Total Asaas webhook events processed",
    ["event"],
)

# -- Asaas gateway --
asaas_requests_total = Counter(
    "asaas_requests_total",
    "Total Asaas API requests",
    ["method", "status"],
)

asaas_circuit_breaker_state = Gauge(
    "asaas_circuit_breaker_state",
    "Asaas circuit breaker state (0=closed, 1=half_open, 2=open)",
)

# -- Ledger --
ledger_entries_total = Counter(
    "ledger_entries_total",
    "Total ledger entries created",
    ["entry_type", "status"],
)

# -- Latency --
pix_operation_duration_seconds = Histogram(
    "pix_operation_duration_seconds",
    "Duration of PIX operations",
    ["operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)


@router.get("/metrics")
def prometheus_metrics():
    """Prometheus scrape endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
