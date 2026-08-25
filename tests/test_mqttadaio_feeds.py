import os
import unittest

# ada.mqttadaio reads these when the module is imported.
os.environ.setdefault("IO_KEY", "test-key")
os.environ.setdefault("IO_USERNAME", "test-user")

from Adafruit_IO import RequestError as RestRequestError  # noqa: E402

from ada import mqttadaio  # noqa: E402


class FakeResponse(object):
    status_code = 404
    reason = "Not Found"

    def json(self):
        return {"error": "not found"}


def rest_request_error():
    return RestRequestError(FakeResponse())


class FakeFeed(object):
    def __init__(self, key):
        self.key = key


class FakeRestClient(object):
    def __init__(self, keys=(), feeds_error=False, create_error=False, known_groups=()):
        self.keys = list(keys)
        self.feeds_error = feeds_error
        self.create_error = create_error
        self.known_groups = set(known_groups)
        self.feeds_calls = 0
        self.created_feeds = []
        self.created_groups = []

    def feeds(self, feed=None):
        self.feeds_calls += 1
        if self.feeds_error:
            raise rest_request_error()
        return [FakeFeed(key) for key in self.keys]

    def groups(self, group=None):
        if group not in self.known_groups:
            raise rest_request_error()
        return group

    def create_group(self, group):
        self.created_groups.append(group.name)
        self.known_groups.add(group.name)

    def create_feed(self, feed, group_key=None):
        if self.create_error:
            raise rest_request_error()
        self.created_feeds.append((feed.name, group_key))


class MqttAdaIoFeedsTest(unittest.TestCase):
    def setUp(self):
        self._saved_state = mqttadaio._state
        self._saved_publish_now = mqttadaio._publish_now
        mqttadaio._state = mqttadaio.State(None, [], {}, [])
        self.published = []
        mqttadaio._publish_now = lambda *params: self.published.append(params) or True

    def tearDown(self):
        mqttadaio._state = self._saved_state
        mqttadaio._publish_now = self._saved_publish_now

    def set_client(self, client):
        mqttadaio._state.aio_rest_client = client
        return client

    def test_known_key_is_not_created(self):
        client = self.set_client(FakeRestClient(keys=["home-lux.attic"],
                                                known_groups=["home-lux"]))

        mqttadaio._ensure_feed("attic", "home-lux", "home-lux.attic")

        self.assertEqual([], client.created_feeds)
        self.assertEqual([], client.created_groups)

    def test_unknown_key_is_created_once(self):
        client = self.set_client(FakeRestClient(keys=[], known_groups=["home-lux"]))

        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")
        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")

        self.assertEqual([("bedclock", "home-lux")], client.created_feeds)
        # The feed listing is fetched once, not on every publish.
        self.assertEqual(1, client.feeds_calls)

    def test_missing_group_is_created_first(self):
        client = self.set_client(FakeRestClient(keys=[]))

        mqttadaio._ensure_feed("oclock-load-1min", "cpu-load", "cpu-load.oclock-load-1min")

        self.assertEqual(["cpu-load"], client.created_groups)
        self.assertEqual([("oclock-load-1min", "cpu-load")], client.created_feeds)

    def test_group_underscores_match_the_feed_key(self):
        client = self.set_client(FakeRestClient(keys=[], known_groups=["home-lux"]))

        mqttadaio._ensure_feed("bedclock", "home_lux", "home-lux.bedclock")

        self.assertEqual([("bedclock", "home-lux")], client.created_feeds)

    def test_feed_without_group_is_created(self):
        client = self.set_client(FakeRestClient(keys=[]))

        mqttadaio._ensure_feed("local-cmd", None, "local-cmd")

        self.assertEqual([("local-cmd", None)], client.created_feeds)
        self.assertEqual([], client.created_groups)

    def test_create_failure_is_not_retried_per_message(self):
        client = self.set_client(FakeRestClient(keys=[], create_error=True,
                                                known_groups=["home-lux"]))

        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")
        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")

        self.assertIn("home-lux.bedclock", mqttadaio._state.aio_rest_feeds)
        self.assertEqual(1, client.feeds_calls)

    def test_listing_failure_is_retried(self):
        client = self.set_client(FakeRestClient(feeds_error=True))

        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")
        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")

        self.assertFalse(mqttadaio._state.aio_rest_feeds_primed)
        self.assertEqual(2, client.feeds_calls)
        self.assertEqual([], client.created_feeds)

    def test_no_rest_client_yet_is_harmless(self):
        mqttadaio._ensure_feed("bedclock", "home-lux", "home-lux.bedclock")

        self.assertFalse(mqttadaio._state.aio_rest_feeds_primed)

    def test_duplicated_keys_are_reported(self):
        self.set_client(FakeRestClient(keys=["home-lux.bedclock", "home-lux.bedclock",
                                             "home-lux.attic"]))
        logged = []
        saved_error = mqttadaio.logger.error
        mqttadaio.logger.error = lambda msg, *args: logged.append(msg % args)
        try:
            mqttadaio._prime_known_feeds()
        finally:
            mqttadaio.logger.error = saved_error

        self.assertEqual(1, len(logged))
        self.assertIn("home-lux.bedclock", logged[0])

    def test_publish_creates_the_feed_before_publishing(self):
        client = self.set_client(FakeRestClient(keys=[], known_groups=["home-lux"]))

        self.assertTrue(mqttadaio._publish("bedclock", 11, "home-lux"))

        self.assertEqual([("bedclock", "home-lux")], client.created_feeds)
        self.assertEqual([("bedclock", 11, "home-lux")], self.published)

    def test_publish_still_happens_when_rest_is_down(self):
        self.set_client(FakeRestClient(feeds_error=True))

        self.assertTrue(mqttadaio._publish("bedclock", 11, "home-lux"))

        self.assertEqual([("bedclock", 11, "home-lux")], self.published)

    def test_suppressed_publish_does_not_touch_rest(self):
        client = self.set_client(FakeRestClient(keys=["home-lux.bedclock"],
                                                known_groups=["home-lux"]))
        mqttadaio._publish("bedclock", 11, "home-lux")

        self.assertFalse(mqttadaio._publish("bedclock", 11, "home-lux"))

        self.assertEqual(1, client.feeds_calls)
        self.assertEqual(1, len(self.published))


if __name__ == "__main__":
    unittest.main()
