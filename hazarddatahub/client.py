"""HazardGraph — DataHub client.

Emits metadata to DataHub using the REST emitter.
Reads metadata via the DataHub Python SDK.
"""

import logging

from config.settings import settings

logger = logging.getLogger(__name__)


class HazardGraphDataHubClient:
    """Thin wrapper around DataHub REST emitter.

    Provides emit() and query() for HazardGraph entities.
    All DataHub SDK imports are deferred so the application can
    start even when acryl-datahub is not installed (e.g. tests).
    """

    def __init__(self, gms_server: str | None = None, token: str | None = None):
        self._gms_server = gms_server or settings.datahub_gms_url
        self._token = token if token is not None else settings.datahub_token
        self._emitter = None

    @property
    def emitter(self):
        """Lazily construct the DataHub REST emitter."""
        if self._emitter is None:
            from datahub.emitter.rest_emitter import DatahubRestEmitter

            kwargs = {"gms_server": self._gms_server}
            if self._token:
                kwargs["token"] = self._token
            self._emitter = DatahubRestEmitter(**kwargs)
        return self._emitter

    def emit(self, mcp) -> None:
        """Emit a single MetadataChangeProposal to DataHub."""
        self.emitter.emit(mcp)

    def emit_batch(self, mcps: list) -> None:
        """Emit a batch of MetadataChangeProposals to DataHub."""
        for mcp in mcps:
            self.emitter.emit(mcp)

    def dataset_urn(self, name: str, platform: str = "neo4j") -> str:
        """Build a DataHub dataset URN."""
        import datahub.emitter.mce_builder as builder

        return builder.make_dataset_urn(platform=platform, name=name)

    def model_urn(self, name: str) -> str:
        """Build a DataHub MLModel URN."""
        import datahub.emitter.mce_builder as builder

        return builder.make_ml_model_urn(
            platform="hazardgraph",
            name=name,
            env="PROD",
        )

    def health_check(self) -> bool:
        """Check connectivity to the DataHub GMS server."""
        try:
            self.emitter.test_connection()
            return True
        except Exception as exc:
            logger.warning("DataHub health check failed: %s", exc)
            return False


def get_datahub_client() -> HazardGraphDataHubClient:
    """FastAPI dependency returning a DataHub client singleton."""
    return HazardGraphDataHubClient()
