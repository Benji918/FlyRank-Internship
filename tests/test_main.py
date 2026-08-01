import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


class TaskDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "tasks.db")
        os.environ["TASKS_DB_PATH"] = self.db_path
        importlib.reload(main)

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("TASKS_DB_PATH", None)

    def test_seed_tasks_are_created_only_once(self):
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        self.assertEqual(count, 3)

        importlib.reload(main)
        with sqlite3.connect(self.db_path) as conn:
            count_after_reload = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        self.assertEqual(count_after_reload, 3)

    def test_crud_operations_persist_in_sqlite(self):
        client = TestClient(main.app)

        create_response = client.post("/tasks", json={"title": "Write tests"})
        self.assertEqual(create_response.status_code, 201)
        created_task = create_response.json()
        self.assertEqual(created_task["title"], "Write tests")

        list_response = client.get("/tasks")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 4)

        update_response = client.put(f"/tasks/{created_task['id']}", json={"done": True})
        self.assertEqual(update_response.status_code, 200)
        self.assertTrue(update_response.json()["done"])

        delete_response = client.delete(f"/tasks/{created_task['id']}")
        self.assertEqual(delete_response.status_code, 204)

        remaining = client.get("/tasks")
        self.assertEqual(len(remaining.json()), 3)


if __name__ == "__main__":
    unittest.main()
