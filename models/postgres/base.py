"""HazardGraph — PostgreSQL Base re-export and model registration.

Importing this module ensures all SQLAlchemy models are registered
on the shared Base metadata for create_all_tables().
"""

from db.postgres_client import Base  # noqa: F401 — re-export

# Import all models so they register with Base.metadata
import models.postgres.alerts  # noqa: F401, E402
import models.postgres.users  # noqa: F401, E402
import models.postgres.audit  # noqa: F401, E402
import models.postgres.jobs  # noqa: F401, E402
import models.postgres.causal  # noqa: F401, E402

__all__ = ["Base"]