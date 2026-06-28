"""Console entrypoint: `slo-operator` / `python -m slo_operator`.

Thin wrapper around kopf's embedded runner. Flags are mapped onto the environment
variables the handlers read at startup, so the same behavior is available whether
the operator is launched via this entrypoint or via `kopf run -m
slo_operator.operator` (as the container image does).
"""

from __future__ import annotations

import argparse
import os
import sys

import kopf


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slo-operator",
        description="Compile ServiceLevelObjective CRs into Prometheus rules.",
    )
    parser.add_argument(
        "--prometheus-url",
        default=os.getenv("SLO_PROMETHEUS_URL", ""),
        help="Prometheus base URL for live error-budget reporting (optional).",
    )
    parser.add_argument(
        "--prometheusrule-labels",
        default=os.getenv("SLO_PROMETHEUSRULE_LABELS", ""),
        help="Comma-separated key=value labels added to generated PrometheusRules "
        "(so the Prometheus Operator ruleSelector can discover them).",
    )
    parser.add_argument(
        "--namespace",
        action="append",
        default=None,
        help="Namespace to watch; repeatable. Defaults to all namespaces.",
    )
    parser.add_argument(
        "--budget-interval",
        type=float,
        default=float(os.getenv("SLO_BUDGET_INTERVAL_SECONDS", "300")),
        help="Seconds between error-budget evaluations (default: 300).",
    )
    parser.add_argument(
        "--liveness",
        default=os.getenv("SLO_LIVENESS_ENDPOINT", "http://0.0.0.0:8080/healthz"),
        help="Liveness probe endpoint kopf should serve (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    os.environ["SLO_PROMETHEUS_URL"] = args.prometheus_url
    os.environ["SLO_PROMETHEUSRULE_LABELS"] = args.prometheusrule_labels
    os.environ["SLO_BUDGET_INTERVAL_SECONDS"] = str(args.budget_interval)

    # Importing the handlers module registers the kopf handlers.
    from . import operator  # noqa: F401

    run_kwargs = {"standalone": True, "liveness_endpoint": args.liveness or None}
    if args.namespace:
        kopf.run(namespaces=args.namespace, **run_kwargs)
    else:
        kopf.run(clusterwide=True, **run_kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
