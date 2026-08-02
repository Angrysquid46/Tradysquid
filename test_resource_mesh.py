from __future__ import annotations

import os
import tempfile
import unittest

import resource_mesh


class ResourceMeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.environ["RESOURCE_MESH_ROOT"] = self.temp.name

    def tearDown(self) -> None:
        os.environ.pop("RESOURCE_MESH_ROOT", None)
        self.temp.cleanup()

    def test_atomic_task_lifecycle_and_deduplication(self) -> None:
        first = resource_mesh.submit_task(
            "ticker-enrichment",
            {"symbol": "F"},
            dedupe_key="F-hour",
            dedupe_seconds=300,
        )
        second = resource_mesh.submit_task(
            "ticker-enrichment",
            {"symbol": "F"},
            dedupe_key="F-hour",
            dedupe_seconds=300,
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])

        claimed = resource_mesh.claim_task("test-worker")
        self.assertIsNotNone(claimed)
        path, task = claimed
        resource_mesh.finish_task(
            path,
            task,
            worker_id="test-worker",
            status="OK",
            result={"symbol": "F", "value": 1},
        )
        results = resource_mesh.collect_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["result"]["symbol"], "F")
        self.assertEqual(resource_mesh.task_counts()["inbox"], 0)

    def test_worker_heartbeat(self) -> None:
        resource_mesh.write_heartbeat(
            "worker-a", role="remote-worker", detail="healthy"
        )
        self.assertTrue(resource_mesh.worker_available(max_age_seconds=30))
        heartbeat = resource_mesh.read_heartbeat()
        self.assertEqual(heartbeat["worker_id"], "worker-a")


if __name__ == "__main__":
    unittest.main()
