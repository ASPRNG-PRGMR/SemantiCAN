import queue
import threading
import time


class MessageBus:
    def __init__(self):
        self.topics: dict = {}
        self.lock = threading.Lock()

    def _ensure_topic(self, name: str):
        with self.lock:
            if name not in self.topics:
                self.topics[name] = queue.Queue()

    def publish(self, topic: str, message: dict):
        self._ensure_topic(topic)
        self.topics[topic].put((time.time(), message))

    def subscribe(self, topic: str) -> queue.Queue:
        self._ensure_topic(topic)
        return self.topics[topic]
