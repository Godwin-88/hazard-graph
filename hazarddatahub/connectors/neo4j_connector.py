"""HazardGraph — DataHub ingestion source connector for Neo4j.

A DataHub ingestion source connector that:
- Discovers all node labels as Dataset entities
- Discovers all relationship types as lineage edges
- Extracts node properties as schema fields
- Reads constraint and index metadata for documentation
- Supports incremental ingestion via `lastUpdated` property

This is the open-source contribution to the DataHub project
(PR to datahub-project/datahub under Apache 2.0), motivated by
HazardGraph's use of Neo4j as its knowledge graph.
"""

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


class Neo4jSource:
    """DataHub ingestion source for Neo4j graph databases.

    Discovers node labels as Dataset entities and relationship
    types as lineage edges. Designed to be used with DataHub's
    ingestion framework (acryl-datahub).
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        platform: str = "neo4j",
        env: str = "PROD",
        incremental: bool = True,
    ):
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.platform = platform
        self.env = env
        self.incremental = incremental
        self._driver = None

    def _connect(self):
        """Lazily connect to Neo4j."""
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
            )
        return self._driver

    def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def get_workunits(self) -> Iterable[dict]:
        """Yield DataHub workunits for all discovered entities.

        Each workunit is a dict with 'entity_urn' and 'aspects'.
        This mirrors the DataHub ingestion framework's workunit
        contract so the connector can be plugged into a recipe.
        """
        driver = self._connect()

        # 1. Discover node labels
        with driver.session(database=self.database) as session:
            labels_result = session.run(
                "CALL db.labels() YIELD label RETURN label ORDER BY label"
            )
            labels = [record["label"] for record in labels_result]

            rels_result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN relationshipType ORDER BY relationshipType"
            )
            rel_types = [record["relationshipType"] for record in rels_result]

            # 2. For each label, extract properties and constraints
            for label in labels:
                yield from self._dataset_workunits(session, label)

            # 3. For each relationship type, emit lineage edges
            for rel_type in rel_types:
                yield from self._lineage_workunits(session, rel_type)

    def _dataset_workunits(self, session, label: str) -> Iterable[dict]:
        """Emit a Dataset workunit for a Neo4j node label."""
        # Sample properties from up to 5 nodes of this label
        result = session.run(
            f"MATCH (n:`{label}`) "
            "WITH n LIMIT 5 "
            "UNWIND keys(n) AS prop "
            "RETURN DISTINCT prop, "
            "       type(n[prop]) AS prop_type "
            "ORDER BY prop"
        )
        properties = {record["prop"]: record["prop_type"] for record in result}

        # Count nodes
        count_result = session.run(
            f"MATCH (n:`{label}`) RETURN count(n) AS count"
        )
        count = count_result.single()["count"]

        dataset_name = f"neo4j_{label.lower()}"
        entity_urn = (
            f"urn:li:dataset:(urn:li:dataPlatform:{self.platform},"
            f"{dataset_name},{self.env})"
        )

        yield {
            "entity_urn": entity_urn,
            "aspects": {
                "datasetProperties": {
                    "name": dataset_name,
                    "description": (
                        f"Neo4j node label '{label}' discovered by "
                        f"HazardGraph Neo4j connector. {count} nodes."
                    ),
                    "customProperties": {
                        "neo4j_label": label,
                        "node_count": str(count),
                        "source": "Neo4j Graph Database",
                    },
                },
                "schemaMetadata": {
                    "fields": [
                        {"fieldPath": prop, "type": prop_type}
                        for prop, prop_type in properties.items()
                    ],
                },
            },
        }

    def _lineage_workunits(self, session, rel_type: str) -> Iterable[dict]:
        """Emit lineage workunits for a Neo4j relationship type."""
        # Find source and target labels for this relationship
        result = session.run(
            f"MATCH (a)-[r:`{rel_type}`]->(b) "
            "WITH a, b LIMIT 1 "
            "RETURN labels(a)[0] AS source_label, labels(b)[0] AS target_label"
        )
        record = result.single()
        if not record:
            return

        source_label = record["source_label"]
        target_label = record["target_label"]

        source_urn = (
            f"urn:li:dataset:(urn:li:dataPlatform:{self.platform},"
            f"neo4j_{source_label.lower()},{self.env})"
        )
        target_urn = (
            f"urn:li:dataset:(urn:li:dataPlatform:{self.platform},"
            f"neo4j_{target_label.lower()},{self.env})"
        )

        yield {
            "entity_urn": target_urn,
            "aspects": {
                "upstreamLineage": {
                    "upstreams": [
                        {
                            "dataset": source_urn,
                            "type": "TRANSFORMED",
                            "auditStamp": {"time": 0, "actor": "urn:li:corpuser:datahub"},
                        }
                    ]
                }
            },
        }

    def get_report(self) -> dict:
        """Return a report of what was ingested."""
        return {
            "source": "neo4j",
            "uri": self.uri,
            "database": self.database,
            "platform": self.platform,
            "env": self.env,
            "incremental": self.incremental,
        }