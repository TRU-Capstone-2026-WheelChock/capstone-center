import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType


def _load_visual_harness_module() -> ModuleType:
    module_path = Path(__file__).resolve().parent / "visual_harness" / "visual_harness.py"
    spec = importlib.util.spec_from_file_location("visual_harness_module_for_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_handler_instance(handler_cls, *, path: str, body: bytes = b"{}"):
    handler = object.__new__(handler_cls)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler._status = None
    handler._headers = {}
    handler.send_response = lambda code: setattr(handler, "_status", code)
    handler.send_header = lambda key, value: handler._headers.__setitem__(key, value)
    handler.end_headers = lambda: None
    handler.address_string = lambda: "test-client"
    return handler


def test_visual_harness_api_post_and_get_state_smoke() -> None:
    module = _load_visual_harness_module()
    shared_state = module.SharedState()
    handler_cls = module.build_handler(shared_state, b"<html></html>")

    post_payload = {
        "sensor_1": True,
        "sensor_2": False,
        "sensor_3": True,
        "sensor_1_connected": False,
        "sensor_2_connected": True,
        "sensor_3_connected": True,
        "override": True,
    }
    post_handler = _make_handler_instance(
        handler_cls,
        path="/api/sensors",
        body=json.dumps(post_payload).encode("utf-8"),
    )
    handler_cls.do_POST(post_handler)

    assert post_handler._status == 200
    post_data = json.loads(post_handler.wfile.getvalue().decode("utf-8"))
    assert post_data["sensor_inputs"]["sensor_1"] is True
    assert post_data["sensor_connected"]["sensor_1"] is False
    assert post_data["override_input"] is True

    get_handler = _make_handler_instance(handler_cls, path="/api/state", body=b"")
    handler_cls.do_GET(get_handler)

    assert get_handler._status == 200
    get_data = json.loads(get_handler.wfile.getvalue().decode("utf-8"))
    assert get_data["sensor_inputs"]["sensor_3"] is True
    assert get_data["sensor_connected"]["sensor_2"] is True
    assert get_data["override_input"] is True
