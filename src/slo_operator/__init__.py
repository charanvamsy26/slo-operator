"""slo-operator: compile ServiceLevelObjective CRDs into Prometheus rules.

A Kubernetes operator built with kopf. It watches ServiceLevelObjective custom
resources and reconciles each one into a PrometheusRule containing SLI recording
rules and multi-window multi-burn-rate alerts (per the Google SRE workbook),
optionally reporting live error-budget consumption back into the CR's status.
"""

__version__ = "0.1.0"

# API identifiers for the ServiceLevelObjective custom resource.
GROUP = "sre.charanvamsy.dev"
VERSION = "v1alpha1"
PLURAL = "servicelevelobjectives"
KIND = "ServiceLevelObjective"
