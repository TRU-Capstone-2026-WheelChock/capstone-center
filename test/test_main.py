from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import zmq.asyncio

from capstone_center.main import (
    CenterApp,
    build_heartbeat_config,
    get_disp_pub_opt,
    get_motor_pub_opt,
    get_opt,
    load_config,
)


def test_load_config_reads_yaml(tmp_path: Path) -> None:
    """Loads YAML config from disk and preserves expected nested values.

    Mocking: none. Uses a temporary real file on disk.
    """
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
logging:
  level: INFO
zmq:
  sub:
    endpoint: tcp://127.0.0.1:5555
    topics:
      - sensor
      - heartbeat
    is_bind: true
runtime:
  watchdog_interval_sec: 1
  heartbeat_timeout_sec: 5
  heartbeat_remove_sec: 60
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(config_file)

    assert cfg["zmq"]["sub"]["endpoint"] == "tcp://127.0.0.1:5555"
    assert cfg["zmq"]["sub"]["topics"] == ["sensor", "heartbeat"]
    assert cfg["zmq"]["sub"]["is_bind"] is True


def test_get_opt_reads_values_from_config() -> None:
    """Builds subscriber options from config values as-is.

    Mocking: none. Uses a real `zmq.asyncio.Context` instance.
    """
    ctx = zmq.asyncio.Context.instance()
    cfg = {
        "zmq": {
            "sub": {
                "endpoint": "tcp://127.0.0.1:6000",
                "topics": ["sensor", "heartbeat"],
                "is_bind": False,
            }
        }
    }

    opt = get_opt(cfg, context=ctx)

    assert opt.endpoint == "tcp://127.0.0.1:6000"
    assert opt.topics == ["sensor", "heartbeat"]
    assert opt.is_bind is False


def test_get_opt_accepts_override_args() -> None:
    """Allows explicit arguments to override subscriber config values.

    Mocking: none. Uses a real `zmq.asyncio.Context` instance.
    """
    ctx = zmq.asyncio.Context.instance()
    cfg = {
        "zmq": {
            "sub": {
                "endpoint": "tcp://127.0.0.1:6000",
                "topics": ["sensor"],
                "is_bind": True,
            }
        }
    }

    opt = get_opt(
        cfg,
        endpoint="tcp://127.0.0.1:7000",
        topics=["all"],
        is_bind=False,
        context=ctx,
    )

    assert opt.endpoint == "tcp://127.0.0.1:7000"
    assert opt.topics == ["all"]
    assert opt.is_bind is False


def test_get_opt_fails_if_topics_is_not_list() -> None:
    """Rejects invalid subscriber topics config when it is not a list.

    Mocking: none. Verifies the real validation path raises `SystemExit`.
    """
    ctx = zmq.asyncio.Context.instance()
    cfg = {
        "zmq": {
            "sub": {
                "endpoint": "tcp://127.0.0.1:6000",
                "topics": "sensor, heartbeat",
                "is_bind": True,
            }
        }
    }

    with pytest.raises(SystemExit, match="topics must be list"):
        get_opt(cfg, context=ctx)


def test_get_disp_pub_opt_reads_display_endpoint() -> None:
    """Builds display publisher options from config and bind/connect inversion.

    Mocking: none. Uses a real `zmq.asyncio.Context` instance.
    """
    ctx = zmq.asyncio.Context.instance()
    cfg = {
        "display": {"endpoint": "tcp://127.0.0.1:7001"},
        "zmq": {"sub": {"is_bind": True}},
    }

    opt = get_disp_pub_opt(cfg, context=ctx)

    assert opt.endpoint == "tcp://127.0.0.1:7001"
    assert opt.is_connect is False


def test_get_motor_pub_opt_reads_motor_endpoint() -> None:
    """Builds motor publisher options from config and bind/connect inversion.

    Mocking: none. Uses a real `zmq.asyncio.Context` instance.
    """
    ctx = zmq.asyncio.Context.instance()
    cfg = {
        "motor": {"endpoint": "tcp://127.0.0.1:7002"},
        "zmq": {"sub": {"is_bind": True}},
    }

    opt = get_motor_pub_opt(cfg, context=ctx)

    assert opt.endpoint == "tcp://127.0.0.1:7002"
    assert opt.is_connect is False


def test_build_heartbeat_config_reads_required_runtime_keys() -> None:
    """Maps runtime heartbeat values into the HeartbeatConfig dataclass.

    Mocking: none. Calls the real builder with an in-memory config dict.
    """
    cfg = {
        "runtime": {
            "watchdog_interval_sec": 1.0,
            "heartbeat_timeout_sec": 5.0,
            "heartbeat_remove_sec": 60.0,
        }
    }

    hb_cfg = build_heartbeat_config(cfg)

    assert hb_cfg.loop_time == 1.0
    assert hb_cfg.timeout_threshold == 5.0
    assert hb_cfg.remove_threshold == 60.0


@pytest.mark.asyncio
async def test_center_app_run_starts_recv_and_heartbeat() -> None:
    """Starts all processor tasks through the CenterApp task group.

    Mocking: uses `AsyncMock` for every processor `run()` method so the test only checks orchestration.
    """
    recv = SimpleNamespace(run=AsyncMock(return_value=None))
    hb = SimpleNamespace(run=AsyncMock(return_value=None))
    sp = SimpleNamespace(run=AsyncMock(return_value=None))
    dis = SimpleNamespace(run=AsyncMock(return_value=None))
    motor = SimpleNamespace(run=AsyncMock(return_value=None))
    app = CenterApp(recv=recv, hb=hb, sp=sp, dis=dis, motor=motor)

    await app.run()

    recv.run.assert_awaited_once_with()
    hb.run.assert_awaited_once_with()
    sp.run.assert_awaited_once_with()
    dis.run.assert_awaited_once_with()
    motor.run.assert_awaited_once_with()
