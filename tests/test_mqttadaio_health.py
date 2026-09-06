import os
import threading
import unittest
from datetime import datetime, timedelta

# ada.mqttadaio reads these when the module is imported.
os.environ.setdefault("IO_KEY", "test-key")
os.environ.setdefault("IO_USERNAME", "test-user")

import paho.mqtt.client as mqtt  # noqa: E402

from ada import const  # noqa: E402
from ada import mqttadaio  # noqa: E402


class FakePahoClient(object):
    def __init__(self, connected=True, publish_rc=mqtt.MQTT_ERR_SUCCESS, thread=None):
        self._connected = connected
        self._thread = thread
        self._thread_terminate = False
        self.publish_rc = publish_rc
        self.published = []
        self.suppress_exceptions = False
        self.reconnect_delays = None

    def is_connected(self):
        return self._connected

    def reconnect_delay_set(self, min_delay=1, max_delay=120):
        self.reconnect_delays = (min_delay, max_delay)

    def publish(self, topic, payload=None):
        self.published.append((topic, payload))
        info = mqtt.MQTTMessageInfo(1)
        info.rc = self.publish_rc
        return info


class FakeAioClient(object):
    def __init__(self, **kwargs):
        self._client = FakePahoClient(**kwargs)
        self.disconnect_calls = 0

    def is_connected(self):
        return self._client._connected

    def disconnect(self):
        self.disconnect_calls += 1


class HealthTestBase(unittest.TestCase):
    def setUp(self):
        self._saved_state = mqttadaio._state
        mqttadaio._state = mqttadaio.State(self.record_event, [], {}, [])
        self.events = []

    def tearDown(self):
        mqttadaio._state = self._saved_state

    def record_event(self, event):
        self.events.append(event)

    def connect_events(self):
        return [e.params[1] for e in self.events if e.name == "MqttConnectEvent"]


class ConnectedTest(HealthTestBase):
    def test_a_dead_network_loop_is_not_connected(self):
        dead_thread = threading.Thread(target=lambda: None)
        dead_thread.start()
        dead_thread.join()
        mqttadaio._state.aio_client = FakeAioClient(connected=True, thread=dead_thread)

        # Both the wrapper and paho still claim to be connected; only the gone
        # network loop says otherwise.
        self.assertFalse(mqttadaio._aio_client_is_connected())

    def test_a_live_loop_with_connected_flags_is_connected(self):
        keep_running = threading.Event()
        live_thread = threading.Thread(target=keep_running.wait)
        live_thread.daemon = True
        live_thread.start()
        mqttadaio._state.aio_client = FakeAioClient(connected=True, thread=live_thread)
        try:
            self.assertTrue(mqttadaio._aio_client_is_connected())
        finally:
            keep_running.set()
            live_thread.join()

    def test_no_client_is_not_connected(self):
        self.assertFalse(mqttadaio._aio_client_is_connected())


class IterateTest(HealthTestBase):
    def setUp(self):
        HealthTestBase.setUp(self)
        mqttadaio._state.aio_rest_client = object()
        self.nuked = []
        self._saved_nuke = mqttadaio._nuke_aio_client
        mqttadaio._nuke_aio_client = lambda state: self.nuked.append(state)

    def tearDown(self):
        mqttadaio._nuke_aio_client = self._saved_nuke
        HealthTestBase.tearDown(self)

    def dead_client(self):
        dead_thread = threading.Thread(target=lambda: None)
        dead_thread.start()
        dead_thread.join()
        return FakeAioClient(connected=True, thread=dead_thread)

    def test_losing_the_connection_is_reported(self):
        state = mqttadaio._state
        state.aio_client = self.dead_client()
        state.aio_client_connected = True
        state.aio_client_update_ts = datetime.now() - timedelta(seconds=mqttadaio.CONNECT_TIMEOUT)

        mqttadaio._iterate_aio_client()

        # Telling the parent comes first; it is what arms the watchdog that
        # used to never hear about a client dropping.
        self.assertEqual([const.MQTT_DISCONNECTED], self.connect_events())
        self.assertFalse(state.aio_client_connected)
        # The client just got a fresh chance to come back on its own.
        self.assertEqual([], self.nuked)

    def test_a_connection_that_does_not_come_back_is_recycled(self):
        state = mqttadaio._state
        state.aio_client = self.dead_client()
        state.aio_client_connected = False
        state.aio_client_update_ts = datetime.now() - timedelta(seconds=mqttadaio.CONNECT_TIMEOUT)

        mqttadaio._iterate_aio_client()

        self.assertEqual([], self.connect_events())
        self.assertEqual([state], self.nuked)

    def test_refused_publishes_recycle_the_client(self):
        state = mqttadaio._state
        state.aio_client = FakeAioClient(connected=True)
        state.aio_client_connected = True
        state.aio_client_update_ts = datetime.now()
        state.publish_failures = mqttadaio.PUBLISH_FAILURES_MAX

        mqttadaio._iterate_aio_client()

        self.assertEqual([state], self.nuked)

    def test_a_healthy_client_is_left_alone(self):
        state = mqttadaio._state
        state.aio_client = FakeAioClient(connected=True)
        state.aio_client_connected = True
        state.aio_client_update_ts = datetime.now()
        state.aio_client_healthy_ts = datetime.now() - timedelta(days=1)

        mqttadaio._iterate_aio_client()

        self.assertEqual([], self.nuked)
        self.assertEqual([], self.connect_events())
        # Being connected is what makes the client healthy again.
        self.assertLess(mqttadaio._elapsed_secs(state.aio_client_healthy_ts), 5)

    def test_an_unusable_client_gives_up_so_the_process_restarts(self):
        state = mqttadaio._state
        state.aio_client = self.dead_client()
        state.aio_client_connected = False
        state.aio_client_update_ts = datetime.now()
        state.aio_client_healthy_ts = datetime.now() - timedelta(seconds=mqttadaio.STUCK_TIMEOUT)

        with self.assertRaises(RuntimeError):
            mqttadaio._iterate_aio_client()

    def test_reconnects_wait_for_the_backoff(self):
        state = mqttadaio._state
        state.aio_connect_after_ts = datetime.now() + timedelta(seconds=30)

        mqttadaio._iterate_aio_client()

        self.assertIsNone(state.aio_client)


class PublishTest(HealthTestBase):
    def test_a_refused_publish_is_not_reported_as_published(self):
        state = mqttadaio._state
        state.aio_client = FakeAioClient(publish_rc=mqtt.MQTT_ERR_NO_CONN)
        state.aio_client_connected = True

        self.assertFalse(mqttadaio._publish("bedclock", 11, "home-lux"))

        self.assertEqual(1, state.publish_failures)
        # Nothing was recorded, so the next attempt at the same value is not
        # suppressed as a duplicate.
        self.assertTrue(state.publish_filter.should_publish("home-lux.bedclock", 11))

    def test_a_sent_publish_is_recorded(self):
        state = mqttadaio._state
        state.aio_client = FakeAioClient()
        state.aio_client_connected = True

        self.assertTrue(mqttadaio._publish("bedclock", 11, "home-lux"))

        self.assertEqual([("test-user/feeds/home-lux.bedclock", 11)],
                         state.aio_client._client.published)
        self.assertEqual(0, state.publish_failures)
        self.assertFalse(state.publish_filter.should_publish("home-lux.bedclock", 11))

    def test_feed_without_a_group_keeps_its_topic(self):
        self.assertEqual("test-user/feeds/local-cmd",
                         mqttadaio._aio_feed_topic("local-cmd", None))


class StopNetworkLoopTest(unittest.TestCase):
    def test_a_finished_loop_stops(self):
        thread = threading.Thread(target=lambda: None)
        thread.start()
        thread.join()
        client = FakePahoClient(thread=thread)

        self.assertTrue(mqttadaio._stop_network_loop(client))
        self.assertTrue(client._thread_terminate)
        self.assertIsNone(client._thread)

    def test_a_loop_that_will_not_end_is_reported(self):
        keep_running = threading.Event()
        thread = threading.Thread(target=keep_running.wait)
        thread.daemon = True
        thread.start()
        client = FakePahoClient(thread=thread)
        saved_timeout = mqttadaio.LOOP_STOP_TIMEOUT
        mqttadaio.LOOP_STOP_TIMEOUT = 0.1
        try:
            self.assertFalse(mqttadaio._stop_network_loop(client))
        finally:
            mqttadaio.LOOP_STOP_TIMEOUT = saved_timeout
            keep_running.set()
            thread.join()

    def test_no_loop_at_all_stops(self):
        self.assertTrue(mqttadaio._stop_network_loop(FakePahoClient()))


class HardenTest(unittest.TestCase):
    def test_callbacks_can_no_longer_kill_the_network_loop(self):
        aio_client = FakeAioClient()

        mqttadaio._harden_aio_client(aio_client)

        self.assertTrue(aio_client._client.suppress_exceptions)
        self.assertEqual((mqttadaio.CONNECT_BACKOFF_MIN_SECS,
                          mqttadaio.CONNECT_BACKOFF_MAX_SECS),
                         aio_client._client.reconnect_delays)


if __name__ == "__main__":
    unittest.main()
