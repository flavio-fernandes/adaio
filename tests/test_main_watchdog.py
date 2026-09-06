import os
import time
import unittest

# ada.main pulls in modules that read these when they are imported.
os.environ.setdefault("IO_KEY", "test-key")
os.environ.setdefault("IO_USERNAME", "test-user")

from ada import log  # noqa: E402
from ada import main  # noqa: E402


class StubProcess(main.ProcessBase):
    """A ProcessBase that is never started, so the test drives its state."""

    max_iteration_secs = 60

    def __init__(self):
        main.ProcessBase.__init__(self, "stub", None)
        self.alive = True

    def is_alive(self):
        return self.alive


class ProcessBaseHeartbeatTest(unittest.TestCase):
    def test_a_fresh_process_is_beating(self):
        p = StubProcess()

        self.assertLess(p.heartbeat_age_secs, 5)

    def test_beating_moves_the_timestamp_forward(self):
        p = StubProcess()
        p.heartbeat.value = time.time() - 600

        p.beat()

        self.assertLess(p.heartbeat_age_secs, 5)

    def test_the_timeout_leaves_room_for_a_slow_iteration(self):
        p = StubProcess()

        self.assertGreater(p.heartbeat_timeout_secs, p.max_iteration_secs)


class CheckChildProcessesTest(unittest.TestCase):
    def setUp(self):
        self._saved_processes = main.myProcesses
        self._saved_logger = main.logger
        main.logger = log.getLogger()
        self.process = StubProcess()
        main.myProcesses = [self.process]

    def tearDown(self):
        main.myProcesses = self._saved_processes
        main.logger = self._saved_logger

    def test_a_beating_child_is_left_running(self):
        main.check_child_processes()

    def test_a_child_that_stopped_beating_takes_the_service_down(self):
        # Alive, queue draining, never reported a disconnect: the shape of the
        # outage this watchdog exists for.
        self.process.heartbeat.value = (time.time() -
                                        self.process.heartbeat_timeout_secs - 1)

        with self.assertRaises(RuntimeError):
            main.check_child_processes()

    def test_a_dead_child_still_takes_the_service_down(self):
        self.process.alive = False

        with self.assertRaises(RuntimeError):
            main.check_child_processes()


if __name__ == "__main__":
    unittest.main()
