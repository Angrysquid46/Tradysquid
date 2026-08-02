"""Start the resource worker with every supported free-data extension."""

from __future__ import annotations

import free_provider_policy
import resource_mesh_worker
import resource_mesh_worker_extensions

free_provider_policy.install(resource_mesh_worker)
resource_mesh_worker_extensions.install(resource_mesh_worker)


if __name__ == "__main__":
    raise SystemExit(resource_mesh_worker.main())
