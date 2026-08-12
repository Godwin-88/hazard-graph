"""HazardGraph — Registers all upstream and output datasets as DataHub Dataset entities."""

import logging

from hazarddatahub.entities import DATASETS, DATASET_SPECS

logger = logging.getLogger(__name__)


def register_all_datasets(client) -> None:
    """Register all 9 HazardGraph datasets as DataHub Dataset entities."""
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import DatasetPropertiesClass

    for spec in DATASET_SPECS:
        dataset_urn = DATASETS[spec["key"]]

        props = DatasetPropertiesClass(
            name=spec["name"],
            description=spec["description"],
            customProperties={
                "update_frequency": spec["update_frequency"],
                "owner": spec["owner"],
                "project": "HazardGraph",
                "platform": spec["platform"],
                "igad_region": "Horn of Africa",
            },
        )

        mcp = MetadataChangeProposalWrapper(
            entityUrn=dataset_urn,
            aspect=props,
        )
        client.emit(mcp)

    logger.info("Registered %d datasets to DataHub", len(DATASET_SPECS))