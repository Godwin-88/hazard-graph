"""HazardGraph — DataHub metadata integration package.

Registers HazardGraph datasets, ML models, lineage edges, and data
quality assertions with DataHub. Provides the MCP bridge used by the
HazardGraph LangGraph agent.
"""

from hazarddatahub.client import HazardGraphDataHubClient

__all__ = ["HazardGraphDataHubClient"]