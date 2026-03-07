import argparse
import json
import logging
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import msg_handler
import zmq


LOGGER = logging.getLogger("visual_harness")
SENSOR_IDS = ("sensor_1", "sensor_2", "sensor_3")
OVERRIDE_INPUT_KEY = "override"
OVERRIDE_SENDER_ID = "override_1"
OVERRIDE_DATA_TYPE = "override_button"


def _unwrap_topic_prefixed_payload(raw_msg: str) -> str:
    if raw_msg.lstrip().startswith("{"):
        return raw_msg

    parts = raw_msg.split(" ", 1)
    if len(parts) == 2 and parts[1].lstrip().startswith("{"):
        return parts[1]
    return raw_msg


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sensor_inputs: dict[str, bool] = {sensor_id: False for sensor_id in SENSOR_IDS}
        self.sensor_connected: dict[str, bool] = {sensor_id: True for sensor_id in SENSOR_IDS}
        self.override_input: bool = False
        self.sequences: dict[str, int] = {sensor_id: 0 for sensor_id in SENSOR_IDS}
        self.sequences[OVERRIDE_SENDER_ID] = 0

        self.last_display_raw: str | None = None
        self.last_display_obj: dict[str, Any] | None = None
        self.last_display_received_at: str | None = None

        self.last_motor_raw: str | None = None
        self.last_motor_obj: dict[str, Any] | None = None
        self.last_motor_received_at: str | None = None

    def set_sensor(self, sensor_id: str, value: bool) -> None:
        with self._lock:
            self.sensor_inputs[sensor_id] = value

    def get_sensor_inputs(self) -> dict[str, bool]:
        with self._lock:
            return dict(self.sensor_inputs)

    def set_sensor_connected(self, sensor_id: str, connected: bool) -> None:
        with self._lock:
            self.sensor_connected[sensor_id] = connected

    def get_sensor_connected(self) -> dict[str, bool]:
        with self._lock:
            return dict(self.sensor_connected)

    def set_override(self, value: bool) -> None:
        with self._lock:
            self.override_input = value

    def get_override(self) -> bool:
        with self._lock:
            return self.override_input

    def bump_sequence(self, sensor_id: str) -> int:
        with self._lock:
            self.sequences[sensor_id] += 1
            return self.sequences[sensor_id]

    def update_display(self, raw_json: str, parsed_obj: dict[str, Any]) -> None:
        with self._lock:
            self.last_display_raw = raw_json
            self.last_display_obj = parsed_obj
            self.last_display_received_at = datetime.now().isoformat(timespec="seconds")

    def update_motor(self, raw_json: str, parsed_obj: dict[str, Any]) -> None:
        with self._lock:
            self.last_motor_raw = raw_json
            self.last_motor_obj = parsed_obj
            self.last_motor_received_at = datetime.now().isoformat(timespec="seconds")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            sensor_inputs = dict(self.sensor_inputs)
            sensor_connected = dict(self.sensor_connected)
            override_input = self.override_input
            display_obj = self.last_display_obj
            motor_obj = self.last_motor_obj

            majority_human: bool | None = None
            if display_obj and isinstance(display_obj.get("sensor_display_dict"), dict):
                values = display_obj["sensor_display_dict"].values()
                flags = [
                    bool(item.get("is_there_human"))
                    for item in values
                    if isinstance(item, dict) and "is_there_human" in item
                ]
                if flags:
                    majority_human = flags.count(True) > flags.count(False)

            internal_state = {
                "is_override_mode": display_obj.get("is_override_mode") if display_obj else None,
                "motor_mode": display_obj.get("moter_mode") if display_obj else None,
                "majority_human_from_display": majority_human,
            }

            return {
                "sensor_inputs": sensor_inputs,
                "sensor_connected": sensor_connected,
                "override_input": override_input,
                "internal_state": internal_state,
                "display_last_command_raw_json": self.last_display_raw,
                "display_last_command_received_at": self.last_display_received_at,
                "motor_last_command_raw_json": self.last_motor_raw,
                "motor_last_command_received_at": self.last_motor_received_at,
                "display_last_command_parsed": display_obj,
                "motor_last_command_parsed": motor_obj,
            }


class SensorPublisherThread(threading.Thread):
    def __init__(
        self,
        *,
        shared_state: SharedState,
        context: zmq.Context,
        endpoint: str,
        publish_interval_sec: float = 0.5,
    ) -> None:
        super().__init__(name="sensor-publisher", daemon=True)
        self.shared_state = shared_state
        self.context = context
        self.endpoint = endpoint
        self.publish_interval_sec = publish_interval_sec
        self.stop_event = threading.Event()

    def run(self) -> None:
        socket = self.context.socket(zmq.PUB)
        socket.connect(self.endpoint)
        socket.setsockopt(zmq.LINGER, 0)

        # Let subscription settle before first send.
        time.sleep(0.4)

        LOGGER.info("sensor publisher connected to %s", self.endpoint)
        try:
            while not self.stop_event.is_set():
                snapshot = self.shared_state.get_sensor_inputs()
                connected_snapshot = self.shared_state.get_sensor_connected()
                for sensor_id, is_on in snapshot.items():
                    if not connected_snapshot.get(sensor_id, True):
                        continue
                    sequence_no = self.shared_state.bump_sequence(sensor_id)
                    msg = msg_handler.SensorMessage(
                        sender_id=sensor_id,
                        sender_name=None,
                        data_type="sensor",
                        sequence_no=sequence_no,
                        payload=msg_handler.SensorPayload(
                            isThereHuman=is_on,
                            human_exist_possibility=100.0 if is_on else 0.0,
                            sensor_status="OK",
                            sensor_status_code=200,
                        ),
                    )
                    socket.send_string(msg.model_dump_json())

                override_is_on = self.shared_state.get_override()
                override_seq = self.shared_state.bump_sequence(OVERRIDE_SENDER_ID)
                override_status = "override" if override_is_on else "active"
                override_msg = msg_handler.SensorMessage(
                    sender_id=OVERRIDE_SENDER_ID,
                    sender_name=None,
                    data_type=OVERRIDE_DATA_TYPE,
                    sequence_no=override_seq,
                    payload=msg_handler.HeartBeatPayload(
                        status=override_status,
                        status_code=200,
                    ),
                )
                socket.send_string(override_msg.model_dump_json())
                time.sleep(self.publish_interval_sec)
        finally:
            socket.close()
            LOGGER.info("sensor publisher stopped")

    def stop(self) -> None:
        self.stop_event.set()


class SubscriberThread(threading.Thread):
    def __init__(
        self,
        *,
        name: str,
        context: zmq.Context,
        endpoint: str,
        on_message: Callable[[str], None],
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.context = context
        self.endpoint = endpoint
        self.on_message = on_message
        self.stop_event = threading.Event()

    def run(self) -> None:
        socket = self.context.socket(zmq.SUB)
        socket.connect(self.endpoint)
        socket.subscribe("")
        socket.setsockopt(zmq.LINGER, 0)
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)

        LOGGER.info("%s connected to %s", self.name, self.endpoint)
        try:
            while not self.stop_event.is_set():
                events = dict(poller.poll(200))
                if socket not in events:
                    continue
                raw = socket.recv_string()
                payload = _unwrap_topic_prefixed_payload(raw)
                self.on_message(payload)
        finally:
            socket.close()
            LOGGER.info("%s stopped", self.name)

    def stop(self) -> None:
        self.stop_event.set()


def build_handler(shared_state: SharedState, html_body: bytes) -> type[BaseHTTPRequestHandler]:
    def parse_bool(raw_value: object) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "on"}
        return False

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send_response(HTTPStatus.OK, html_body, "text/html; charset=utf-8")
                return

            if self.path == "/api/state":
                payload = json.dumps(shared_state.snapshot(), ensure_ascii=False).encode("utf-8")
                self._send_response(HTTPStatus.OK, payload, "application/json; charset=utf-8")
                return

            self._send_response(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/sensors":
                self._send_response(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("request body must be a JSON object")
            except Exception as exc:
                payload = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send_response(
                    HTTPStatus.BAD_REQUEST,
                    payload,
                    "application/json; charset=utf-8",
                )
                return

            for sensor_id in SENSOR_IDS:
                if sensor_id not in data:
                    pass
                else:
                    shared_state.set_sensor(sensor_id, parse_bool(data[sensor_id]))

                connected_key = f"{sensor_id}_connected"
                if connected_key in data:
                    shared_state.set_sensor_connected(sensor_id, parse_bool(data[connected_key]))

            if OVERRIDE_INPUT_KEY in data:
                shared_state.set_override(parse_bool(data[OVERRIDE_INPUT_KEY]))

            payload = json.dumps(shared_state.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send_response(HTTPStatus.OK, payload, "application/json; charset=utf-8")

        def _send_response(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info("http %s - %s", self.address_string(), fmt % args)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visual test harness for capstone-center")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--sensor-endpoint", default="tcp://localhost:5555")
    parser.add_argument("--display-endpoint", default="tcp://localhost:5556")
    parser.add_argument("--motor-endpoint", default="tcp://localhost:5557")
    parser.add_argument("--publish-interval-sec", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()

    html_path = Path(__file__).with_name("index.html")
    html_body = html_path.read_bytes()

    shared_state = SharedState()
    context = zmq.Context()

    def on_display(raw_json: str) -> None:
        try:
            parsed = msg_handler.DisplayMessage.model_validate_json(raw_json)
            shared_state.update_display(raw_json, parsed.model_dump(mode="json"))
        except Exception:
            LOGGER.exception("failed to parse display message")

    def on_motor(raw_json: str) -> None:
        try:
            parsed = msg_handler.MotorMessage.model_validate_json(raw_json)
            shared_state.update_motor(raw_json, parsed.model_dump(mode="json"))
        except Exception:
            LOGGER.exception("failed to parse motor message")

    sensor_pub = SensorPublisherThread(
        shared_state=shared_state,
        context=context,
        endpoint=args.sensor_endpoint,
        publish_interval_sec=args.publish_interval_sec,
    )
    display_sub = SubscriberThread(
        name="display-subscriber",
        context=context,
        endpoint=args.display_endpoint,
        on_message=on_display,
    )
    motor_sub = SubscriberThread(
        name="motor-subscriber",
        context=context,
        endpoint=args.motor_endpoint,
        on_message=on_motor,
    )

    sensor_pub.start()
    display_sub.start()
    motor_sub.start()

    handler = build_handler(shared_state, html_body)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    LOGGER.info("visual harness started at http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("stopping visual harness")
    finally:
        server.shutdown()
        sensor_pub.stop()
        display_sub.stop()
        motor_sub.stop()
        sensor_pub.join(timeout=1.0)
        display_sub.join(timeout=1.0)
        motor_sub.join(timeout=1.0)
        context.term()


if __name__ == "__main__":
    main()
