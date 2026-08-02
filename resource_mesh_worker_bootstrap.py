"""Start the resource worker with every supported free-data extension."""

from __future__ import annotations

import resource_mesh_worker

# Load .env.worker before importing policies whose defaults are derived from the
# environment, including registered BLS quota and bootstrap sample count.
resource_mesh_worker.load_worker_env()

import free_provider_policy  # noqa: E402
import resource_compute_runtime  # noqa: E402
import resource_mesh  # noqa: E402
import resource_mesh_worker_extensions  # noqa: E402

free_provider_policy.install(resource_mesh_worker)
resource_mesh_worker_extensions.install(resource_mesh_worker)
resource_mesh.ALLOWED_KINDS.add("outcome-analysis")
resource_mesh_worker.HANDLERS["outcome-analysis"] = (
    resource_compute_runtime.analyze
)


if __name__ == "__main__":
    raise SystemExit(resource_mesh_worker.main())
