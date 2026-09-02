import queue
import threading
import time


class MessageBus:
    """
    In-process pub/sub bus.

    NOTE: prior to the Attack Replay work (Phase3_Plan.md §1.5), this class
    handed every subscriber of a topic the *same* underlying queue.Queue.
    Since queue.get() removes the item, that meant multiple subscribers to
    one topic were competing consumers, not fan-out subscribers — each
    message went to whichever caller happened to call get() first. That was
    invisible with a single subscriber (the detection loop in main.py), but
    it would have silently broken detection the moment a second subscriber
    (e.g. TelemetryRecorder) was attached to the same topic, since roughly
    half of all messages would have been stolen from the detection loop.

    This version keeps a list of queues per topic and publishes to every
    one of them, so each subscriber gets every message independently. The
    public interface (publish/subscribe) is unchanged.
    """

    def __init__(self):
        self.topics: dict = {}
        self.lock = threading.Lock()

    def _ensure_topic(self, name: str):
        with self.lock:
            if name not in self.topics:
                self.topics[name] = []

    def publish(self, topic: str, message: dict):
        self._ensure_topic(topic)
        with self.lock:
            subscribers = list(self.topics[topic])
        payload = (time.time(), message)
        for q in subscribers:
            q.put(payload)

    def subscribe(self, topic: str) -> queue.Queue:
        self._ensure_topic(topic)
        q = queue.Queue()
        with self.lock:
            self.topics[topic].append(q)
        return q
