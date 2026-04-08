import queue
import threading
import time


class MessageBus:
    def __init__(self):
        self.topics = {}
        self.lock = threading.Lock()

    def create_topic(self, name: str):
        with self.lock:
            if name not in self.topics:
                self.topics[name] = queue.Queue()

    def publish(self, topic: str, message: dict):
        if topic not in self.topics:
            self.create_topic(topic)
        self.topics[topic].put((time.time(), message))

    def subscribe(self, topic: str):
        if topic not in self.topics:
            self.create_topic(topic)
        return self.topics[topic]
