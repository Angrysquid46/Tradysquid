"""Start the resource worker with every supported free-data extension."""

from __future__ import annotations

import free_provider_policy
import resource_mesh_worker
import resource_mesh_worker_extensions

# Load .env.worker before installing quota policy so optional registered-key
# allowances, worker identity, mesh path, and HTTP settings are active.
resource_mesh_worker.load_worker_env()
free_provider_policy.install(resource_mesh_worker)
resource_mesh_worker_extensions.install(resource_mesh_worker)


if __name__ == "__main__":
    raise SystemExit(resource_mesh_worker.main())
