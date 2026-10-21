"""RabbitMQ events: one topic exchange (``drukrescue.events``) + one work queue (``dispatch.requests``).

Publishing::

    bus.publish("incident.created", {...})            # to the topic exchange
    bus.enqueue(DISPATCH_QUEUE, "dispatch.requested", {...})  # straight onto a work queue

Consuming::

    @bus.consumer("notification.events", ["incident.*", "dispatch.assigned"])
    def on_event(event: Event) -> None: ...

Delivery guarantees (say these in the viva):

- Exchange, queues and messages are durable/persistent; publishes use confirms.
- A message is acked only after the handler returns. If the pod dies mid-way the
  message goes back on the queue and another replica picks it up.
- A handler that raises gets one redelivery; if it fails again the message is
  dead-lettered to ``drukrescue.dead-letter`` instead of looping forever.
- The trace context travels in message headers, so a trace continues across RabbitMQ.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial

from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from drukcommon.config import get_settings

log = logging.getLogger(__name__)

EXCHANGE = "drukrescue.events"
DEAD_LETTER_EXCHANGE = "drukrescue.dlx"
DEAD_LETTER_QUEUE = "drukrescue.dead-letter"
DISPATCH_QUEUE = "dispatch.requests"


def queue_arguments() -> dict:
    # Must be identical everywhere a queue is declared, or RabbitMQ rejects the declare.
    return {"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE}


@dataclass
class Event:
    type: str
    data: dict
    source: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_body(self) -> bytes:
        return json.dumps(
            {"id": self.id, "type": self.type, "source": self.source, "occurred_at": self.occurred_at, "data": self.data},
            default=str,
        ).encode()

    @classmethod
    def from_body(cls, body: bytes) -> Event:
        raw = json.loads(body)
        return cls(type=raw["type"], data=raw.get("data", {}), source=raw.get("source", "?"),
                   id=raw.get("id", str(uuid.uuid4())), occurred_at=raw.get("occurred_at", ""))


Handler = Callable[[Event], None]


@dataclass
class Consumer:
    queue: str
    routing_keys: tuple[str, ...]
    handler: Handler


def topic_matches(pattern: str, routing_key: str) -> bool:
    """AMQP topic matching: ``*`` = exactly one word, ``#`` = zero or more words."""
    p, k = pattern.split("."), routing_key.split(".")

    def match(i: int, j: int) -> bool:
        if i == len(p):
            return j == len(k)
        if p[i] == "#":
            return any(match(i + 1, jj) for jj in range(j, len(k) + 1))
        return j < len(k) and (p[i] == "*" or p[i] == k[j]) and match(i + 1, j + 1)

    return match(0, 0)


class EventBus:
    """Base class; also the ``none`` backend (publishing is a no-op)."""

    def __init__(self, service: str):
        self.service = service
        self.consumers: list[Consumer] = []

    def consumer(self, queue: str, routing_keys: Iterable[str] = ()):
        def register(handler: Handler) -> Handler:
            self.consumers.append(Consumer(queue, tuple(routing_keys), handler))
            return handler

        return register

    def publish(self, routing_key: str, data: dict) -> Event:
        event = Event(type=routing_key, data=data, source=self.service)
        self._send(EXCHANGE, routing_key, event, declare_queue=None)
        return event

    def enqueue(self, queue: str, event_type: str, data: dict) -> Event:
        event = Event(type=event_type, data=data, source=self.service)
        self._send("", queue, event, declare_queue=queue)
        return event

    def _send(self, exchange: str, routing_key: str, event: Event, declare_queue: str | None) -> None:
        log.debug("events backend 'none': dropping %s", event.type)

    def start(self) -> None:
        if self.consumers:
            log.warning("events backend 'none': %d consumer(s) will not run", len(self.consumers))

    def stop(self) -> None:
        pass

    def healthy(self) -> bool:
        return True


class InMemoryEventBus(EventBus):
    """For tests: records what was published and lets a test deliver events to handlers."""

    def __init__(self, service: str):
        super().__init__(service)
        self.published: list[tuple[str, Event]] = []  # (routing key or queue name, event)

    def _send(self, exchange, routing_key, event, declare_queue):
        self.published.append((routing_key, event))

    def sent(self, routing_key: str) -> list[dict]:
        return [e.data for rk, e in self.published if rk == routing_key]

    def clear(self) -> None:
        self.published.clear()

    def deliver(self, event_type: str, data: dict, queue: str | None = None) -> int:
        """Run every consumer whose bindings match (or that listens on ``queue``). Returns how many ran."""
        event = Event(type=event_type, data=data, source="test")
        ran = 0
        for c in self.consumers:
            if (queue and c.queue == queue) or (not queue and any(topic_matches(p, event_type) for p in c.routing_keys)):
                c.handler(event)
                ran += 1
        return ran


class RabbitMQEventBus(EventBus):
    def __init__(self, service: str, url: str):
        super().__init__(service)
        import pika  # imported lazily so tests don't need a broker

        self._pika = pika
        self._params = pika.URLParameters(url)
        self._params.client_properties = {"connection_name": f"{service}"}
        self._lock = threading.Lock()  # pika connections are not thread-safe
        self._conn = None
        self._channel = None
        self._declared_queues: set[str] = set()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._connected: dict[str, bool] = {}
        self._tracer = trace.get_tracer("drukcommon.events")

    # --- topology -----------------------------------------------------------------------
    def _declare_base(self, ch) -> None:
        ch.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        ch.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
        ch.queue_declare(DEAD_LETTER_QUEUE, durable=True)
        ch.queue_bind(DEAD_LETTER_QUEUE, DEAD_LETTER_EXCHANGE)

    # --- publishing ---------------------------------------------------------------------
    def _publisher_channel(self):
        if self._conn is None or self._conn.is_closed or self._channel is None or self._channel.is_closed:
            self._close_publisher()
            self._conn = self._pika.BlockingConnection(self._params)
            self._channel = self._conn.channel()
            self._channel.confirm_delivery()
            self._declare_base(self._channel)
            self._declared_queues.clear()
        return self._channel

    def _close_publisher(self) -> None:
        try:
            if self._conn is not None and self._conn.is_open:
                self._conn.close()
        except Exception:
            log.debug("error closing publisher connection", exc_info=True)
        self._conn = self._channel = None

    def _send(self, exchange, routing_key, event, declare_queue):
        with self._tracer.start_as_current_span(
            f"{routing_key} publish",
            kind=SpanKind.PRODUCER,
            attributes={"messaging.system": "rabbitmq", "messaging.destination.name": exchange or routing_key,
                        "messaging.rabbitmq.destination.routing_key": routing_key},
        ), self._lock:
            headers: dict[str, str] = {}
            propagate.inject(headers)  # carries traceparent across the broker
            props = self._pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistent
                message_id=event.id,
                type=event.type,
                headers=headers,
            )
            for attempt in (1, 2):
                try:
                    ch = self._publisher_channel()
                    if declare_queue and declare_queue not in self._declared_queues:
                        ch.queue_declare(declare_queue, durable=True, arguments=queue_arguments())
                        self._declared_queues.add(declare_queue)
                    ch.basic_publish(exchange, routing_key, event.to_body(), props)
                    return
                except self._pika.exceptions.AMQPError:
                    self._close_publisher()  # stale connection (e.g. missed heartbeats); reconnect once
                    if attempt == 2:
                        raise

    # --- consuming ----------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        for c in self.consumers:
            t = threading.Thread(target=self._consume_loop, args=(c,), name=f"consumer:{c.queue}", daemon=True)
            t.start()
            self._threads.append(t)

    def _consume_loop(self, c: Consumer) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            conn = None
            try:
                conn = self._pika.BlockingConnection(self._params)
                ch = conn.channel()
                self._declare_base(ch)
                ch.queue_declare(c.queue, durable=True, arguments=queue_arguments())
                for rk in c.routing_keys:
                    ch.queue_bind(c.queue, EXCHANGE, routing_key=rk)
                ch.basic_qos(prefetch_count=1)  # one message at a time per consumer
                ch.basic_consume(c.queue, on_message_callback=partial(self._on_message, c))
                self._connected[c.queue] = True
                backoff = 1.0
                log.info("consuming", extra={"queue": c.queue, "bindings": list(c.routing_keys)})
                while not self._stop.is_set():
                    conn.process_data_events(time_limit=1)
            except Exception:
                log.warning("consumer connection lost, reconnecting", extra={"queue": c.queue}, exc_info=True)
            finally:
                self._connected[c.queue] = False
                try:
                    if conn is not None and conn.is_open:
                        conn.close()
                except Exception:
                    log.debug("error closing consumer connection", exc_info=True)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30)

    def _on_message(self, c: Consumer, ch, method, props, body: bytes) -> None:
        ctx = propagate.extract((props.headers or {}) if props else {})
        with self._tracer.start_as_current_span(
            f"{c.queue} process",
            context=ctx,
            kind=SpanKind.CONSUMER,
            attributes={"messaging.system": "rabbitmq", "messaging.destination.name": c.queue,
                        "messaging.rabbitmq.destination.routing_key": method.routing_key},
        ):
            try:
                event = Event.from_body(body)
            except (ValueError, KeyError):
                log.error("malformed message, dead-lettering", extra={"queue": c.queue})
                ch.basic_reject(method.delivery_tag, requeue=False)
                return
            try:
                c.handler(event)
            except Exception:
                log.exception("handler failed", extra={"queue": c.queue, "event_type": event.type, "event_id": event.id})
                if method.redelivered:
                    ch.basic_reject(method.delivery_tag, requeue=False)  # -> dead-letter queue
                else:
                    ch.basic_nack(method.delivery_tag, requeue=True)  # one more try
                return
            ch.basic_ack(method.delivery_tag)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()
        with self._lock:
            self._close_publisher()

    def healthy(self) -> bool:
        if any(not self._connected.get(c.queue, False) for c in self.consumers):
            return False
        with self._lock:
            try:
                self._publisher_channel()
                return True
            except Exception:
                self._close_publisher()
                return False


def create_event_bus(service: str) -> EventBus:
    settings = get_settings()
    backend = settings.events_backend
    if backend == "memory":
        return InMemoryEventBus(service)
    if backend == "rabbitmq":
        if not settings.rabbitmq_url:
            raise RuntimeError("EVENTS_BACKEND=rabbitmq but RABBITMQ_URL / RABBITMQ_HOST is not set")
        return RabbitMQEventBus(service, settings.rabbitmq_url)
    return EventBus(service)
