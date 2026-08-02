"""Start the resource worker with every supported free-data extension."""

from __future__ import annotations

import resource_mesh_worker
import resource_mesh_worker_extensions

resource_mesh_worker_extensions.install(resource_mesh_worker)


if __name__ == "__main__":
    raise SystemExit(resource_mesh_worker.main())
