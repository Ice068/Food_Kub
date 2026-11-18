"""Deployment lifecycle regressions; no Firebase or real child servers are used."""
import io
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import start_render


class RenderStartupTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(start_render.os.environ, {"PORT": "10000"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for stream in ("stdout", "stderr"):
            change = patch.object(sys, stream, io.StringIO())
            change.start()
            self.addCleanup(change.stop)

    @staticmethod
    def process(exit_code=None):
        process = Mock()
        process.poll.return_value = exit_code
        process.returncode = exit_code
        return process

    def test_failed_backend_never_starts_frontend(self):
        backend = self.process(1)
        with patch.object(start_render.subprocess, "Popen", return_value=backend) as spawn:
            result = start_render.run(threading.Event())
        self.assertEqual(result, 1)
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(spawn.call_args.kwargs["cwd"].name, "blackend_py")
        self.assertIn("Backend exited with code 1", sys.stderr.getvalue())
        backend.wait.assert_called_once()

    def test_backend_exit_zero_is_still_service_failure(self):
        with self.assertRaises(start_render.StartupError):
            start_render.wait_for_backend("http://127.0.0.1:8000", self.process(0), threading.Event())

    def test_waits_for_catalog_before_starting_web_and_cleans_up_on_web_exit(self):
        backend, frontend = self.process(), self.process(2)
        with patch.object(start_render.subprocess, "Popen", side_effect=[backend, frontend]) as spawn:
            def ready(*args):
                self.assertEqual(spawn.call_count, 1)
                self.assertIs(args[1], backend)
                return True
            with patch.object(start_render, "wait_for_backend", side_effect=ready):
                self.assertEqual(start_render.run(threading.Event()), 1)
        self.assertEqual(spawn.call_count, 2)
        backend.terminate.assert_called_once()
        frontend.terminate.assert_not_called()
        self.assertEqual(spawn.call_args.kwargs["env"]["FOOD_KUB_BACKEND_URL"], start_render.LOCAL_BACKEND)

    def test_backend_crash_after_ready_stops_frontend(self):
        backend, frontend = self.process(9), self.process()
        with patch.object(start_render.subprocess, "Popen", side_effect=[backend, frontend]), \
             patch.object(start_render, "wait_for_backend", return_value=True):
            self.assertEqual(start_render.run(threading.Event()), 1)
        frontend.terminate.assert_called_once()

    def test_explicit_demo_starts_only_frontend_without_backend_probe(self):
        with patch.dict(start_render.os.environ, {"FOOD_KUB_DEMO": "1"}), \
             patch.object(start_render.subprocess, "Popen", return_value=self.process(1)) as spawn, \
             patch.object(start_render, "wait_for_backend") as probe:
            self.assertEqual(start_render.run(threading.Event()), 1)
        probe.assert_not_called()
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(spawn.call_args.kwargs["cwd"].name, "front_py")

    def test_external_backend_is_probed_without_starting_local_api(self):
        with patch.dict(start_render.os.environ, {"FOOD_KUB_BACKEND_URL": "https://api.example.test/"}), \
             patch.object(start_render.subprocess, "Popen", return_value=self.process(1)) as spawn, \
             patch.object(start_render, "wait_for_backend", return_value=True) as probe:
            start_render.run(threading.Event())
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(probe.call_args.args[:2], ("https://api.example.test", None))

    def test_stop_during_readiness_cleans_up_without_launching_frontend(self):
        backend = self.process()
        with patch.object(start_render.subprocess, "Popen", return_value=backend) as spawn, \
             patch.object(start_render, "wait_for_backend", return_value=False):
            self.assertEqual(start_render.run(threading.Event()), 0)
        self.assertEqual(spawn.call_count, 1)
        backend.terminate.assert_called_once()

    def test_frontend_spawn_failure_cleans_up_backend(self):
        backend = self.process()
        with patch.object(start_render.subprocess, "Popen", side_effect=[backend, OSError("failed")]), \
             patch.object(start_render, "wait_for_backend", return_value=True):
            self.assertEqual(start_render.run(threading.Event()), 1)
        backend.terminate.assert_called_once()

    def test_probe_accepts_empty_catalog_and_retries_connection_failure(self):
        response = io.BytesIO(json.dumps([]).encode())
        response.status = 200
        with patch.object(start_render, "urlopen", side_effect=[URLError("not yet"), response]) as fetch:
            self.assertTrue(start_render.wait_for_backend("http://127.0.0.1:8000", self.process(), Mock(is_set=Mock(return_value=False))))
        self.assertEqual(fetch.call_count, 2)

    def test_unavailable_catalog_has_bounded_deadline_and_safe_diagnostics(self):
        with patch.object(start_render.time, "monotonic", side_effect=[0, 0, 2, 2]), \
             patch.object(start_render, "urlopen", side_effect=URLError("private-credential-value")):
            with self.assertRaises(start_render.StartupError) as failure:
                start_render.wait_for_backend("http://127.0.0.1:8000", self.process(), threading.Event(), timeout=1)
        self.assertIn("URLError", str(failure.exception))
        self.assertNotIn("private-credential-value", str(failure.exception))

    def test_stubborn_child_is_killed_after_grace_period(self):
        process = self.process()
        process.wait.side_effect = [subprocess.TimeoutExpired("child", 8), 0]
        start_render.stop_processes([("Backend", process)])
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_reserved_backend_port_does_not_launch_any_process(self):
        with patch.dict(start_render.os.environ, {"PORT": "8000"}), \
             patch.object(start_render.subprocess, "Popen") as spawn:
            self.assertEqual(start_render.run(threading.Event()), 1)
        spawn.assert_not_called()

    def test_cleanup_failure_cannot_skip_remaining_child(self):
        backend, frontend = self.process(), self.process()
        frontend.wait.side_effect = subprocess.TimeoutExpired("frontend", 8)
        frontend.kill.side_effect = ProcessLookupError()
        start_render.stop_processes([("Backend", backend), ("Frontend", frontend)])
        backend.terminate.assert_called_once()
        backend.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
