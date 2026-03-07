# Configuration Reference

This document describes the current configuration schema used by `capstone-center`.

It is based on:

- `config.yml`
- `test/visual_harness/config.center.visual.yml`
- the implementation under `src/capstone_center/`

The two YAML files share the same overall shape. The visual harness variant mainly changes ZeroMQ endpoints so Docker services and the local harness can connect correctly.

## Current Runtime Reality

Not every key present in `config.yml` is wired into the current code.

- Some keys are actively used at startup or runtime.
- Some keys look planned, but are not currently read anywhere in the implementation.

The sections below call that out explicitly.

## Top-Level Files

### `config.yml`

Default runtime configuration for the application.

### `test/visual_harness/config.center.visual.yml`

Visual harness variant of the same config. It is loaded by `test/visual_harness/run_center.py` and is intended for the manual Docker-based visual test flow.

Main differences from `config.yml`:

- `zmq.sub.endpoint` is `tcp://0.0.0.0:5555`
- `display.endpoint` is `tcp://0.0.0.0:5556`
- `motor.endpoint` is `tcp://0.0.0.0:5557`
- `motor.looptime` is `1.0` instead of `10.0`

## Section Reference

### `app`

Keys:

- `app.name`
- `app.version`
- `app.timezone`

Current status:

- Currently unused by the implementation.

Notes:

- `src/capstone_center/main.py` does not read the `app` section.
- No other file under `src/capstone_center/` currently references these keys.

### `logging`

Keys:

- `logging.level`
- `logging.format`

Current status:

- Used.

Where used:

- `src/capstone_center/main.py`
- `setup_logger()` reads both keys and passes them to `logging.basicConfig()`

Behavior:

- Invalid or missing values cause startup to exit with `SystemExit`.

### `zmq.sub`

Keys:

- `zmq.sub.endpoint`
- `zmq.sub.topics`
- `zmq.sub.is_bind`

Current status:

- Used.

Where used:

- `src/capstone_center/main.py`
- `get_opt()` reads all three values to build `msg_handler.ZmqSubOptions`

Behavior:

- `endpoint` is used for the inbound subscriber socket.
- `topics` must be a list of strings.
- `is_bind` controls whether the subscriber binds or connects.

Important note:

- `display` and `motor` publisher setup also reuse `zmq.sub.is_bind` indirectly.
- In `get_disp_pub_opt()` and `get_motor_pub_opt()`, publisher connect/bind is set as the opposite of `zmq.sub.is_bind`.

### `runtime`

Keys:

- `runtime.loop_interval_sec`
- `runtime.watchdog_interval_sec`
- `runtime.heartbeat_timeout_sec`
- `runtime.heartbeat_remove_sec`
- `runtime.sensor_stale_sec`
- `runtime.history_len`

Current status:

- `watchdog_interval_sec`: used
- `heartbeat_timeout_sec`: used
- `heartbeat_remove_sec`: used
- `loop_interval_sec`: currently unused
- `sensor_stale_sec`: currently unused
- `history_len`: currently unused

Where used:

- `src/capstone_center/main.py`
- `build_heartbeat_config()` reads:
  - `runtime.watchdog_interval_sec`
  - `runtime.heartbeat_timeout_sec`
  - `runtime.heartbeat_remove_sec`

Behavior:

- These values feed `HeartbeatProcessor`.
- Timeout handling marks components dead after `heartbeat_timeout_sec`.
- Components are removed from the heartbeat table after `heartbeat_remove_sec`.

Unused notes:

- `loop_interval_sec` is present in YAML but is not read anywhere in the current implementation.
- `sensor_stale_sec` is present in YAML but there is no stale-sensor filter wired into runtime logic today.
- `history_len` is present in YAML, and `RuntimeState` has a `history_len` field, but startup does not populate it from config and sensor/status stores still use their internal defaults.

### `presence`

Keys:

- `presence.probability_threshold`
- `presence.tie_breaker`
- `presence.use_sensor_local_majority`
- `presence.sensor_local_window`

Current status:

- Currently unused by the implementation.

Notes:

- `src/capstone_center/sensor_information_processor.py` determines presence by simple majority of the latest alive sensor samples.
- The current logic does not read thresholding, tie-break rules, or local history window settings from config.

Actual current behavior:

- Presence is `True` only when `count(True) > count(False)`.
- A tie resolves to `False` implicitly.

### `status`

Keys:

- `status.keep_last_n`
- `status.stale_sec`
- `status.timeout_label`

Current status:

- Currently unused by the implementation.

Notes:

- Runtime status messages are stored in memory by `RuntimeState.update_status()`.
- None of the values in the `status` config section are currently read to control retention, staleness, or labeling.

Implementation gap:

- `StatusHistory` still uses its built-in default length rather than `status.keep_last_n`.

### `display`

Keys:

- `display.refresh_interval_sec`
- `display.show_last_status_on_timeout`
- `display.timeout_template`
- `display.endpoint`
- `display.topics`

Current status:

- `display.endpoint`: used
- `display.refresh_interval_sec`: currently unused
- `display.show_last_status_on_timeout`: currently unused
- `display.timeout_template`: currently unused
- `display.topics`: currently unused

Where used:

- `src/capstone_center/main.py`
- `get_disp_pub_opt()` reads `display.endpoint`

Actual current behavior:

- `src/capstone_center/display_sender_processor.py` publishes whenever the sensor-processing signal fires.
- There is no timer-based display refresh loop controlled by config.
- The outgoing display message is built directly from:
  - `state.isin_override_mode`
  - `state.get_alive_latest_display_dict()`
  - `state.motor_mode`

Unused notes:

- `display.topics` exists in YAML, but the publisher setup in current code does not read it.

### `motor`

Keys:

- `motor.name`
- `motor.status`
- `motor.looptime`
- `motor.endpoint`
- `motor.topics`

Current status:

- `motor.looptime`: used
- `motor.endpoint`: used
- `motor.name`: currently unused
- `motor.status`: currently unused
- `motor.topics`: currently unused

Where used:

- `src/capstone_center/main.py`
- `get_motor_pub_opt()` reads `motor.endpoint`
- `main()` passes `motor.looptime` into `MotorSenderProcessor`

Actual current behavior:

- `src/capstone_center/motor_sender_processor.py` publishes immediately on update events and also periodically after `motor.looptime` seconds.
- Motor command selection is hard-coded:
  - override mode => `FOLDING`
  - human present => `DEPLOYING`
  - otherwise => `FOLDING`

Unused notes:

- `motor.status` looks like a future mapping from motor states to booleans, but it is not currently read anywhere.
- `motor.topics` exists in YAML, but the publisher setup does not read it.
- `motor.name` is not used in current runtime behavior.

### `policy`

Keys:

- `policy.status_priority`

Current status:

- Currently unused by the implementation.

Notes:

- No file under `src/capstone_center/` currently reads `policy.status_priority`.

## Summary of Used Keys

The keys that are currently wired into runtime behavior are:

- `logging.level`
- `logging.format`
- `zmq.sub.endpoint`
- `zmq.sub.topics`
- `zmq.sub.is_bind`
- `runtime.watchdog_interval_sec`
- `runtime.heartbeat_timeout_sec`
- `runtime.heartbeat_remove_sec`
- `display.endpoint`
- `motor.looptime`
- `motor.endpoint`

## Summary of Currently Unused Keys

The following keys exist in the config files but are not currently read by the implementation:

- `app.name`
- `app.version`
- `app.timezone`
- `runtime.loop_interval_sec`
- `runtime.sensor_stale_sec`
- `runtime.history_len`
- `presence.probability_threshold`
- `presence.tie_breaker`
- `presence.use_sensor_local_majority`
- `presence.sensor_local_window`
- `status.keep_last_n`
- `status.stale_sec`
- `status.timeout_label`
- `display.refresh_interval_sec`
- `display.show_last_status_on_timeout`
- `display.timeout_template`
- `display.topics`
- `motor.name`
- `motor.status`
- `motor.topics`
- `policy.status_priority`

## Caveats

- This reference describes the code as it exists now, not the intended design.
- Several unused keys appear to be placeholders for planned behavior rather than mistakes in YAML structure.
- If the implementation is updated, this document should be revised together with the code.
