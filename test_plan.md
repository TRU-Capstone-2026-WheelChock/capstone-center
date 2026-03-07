# Test Plan

This document describes the current automated test coverage in `test/`, including the intent of each test area and the mock strategy used.

## Scope

The current suite focuses on:

- heartbeat timeout and cleanup behavior
- config loading and startup wiring
- message receive dispatch
- signal fan-out between processors
- motor command publishing
- visual harness HTTP handler behavior

The suite is mostly unit testing plus a small amount of narrow integration testing. Most tests avoid real ZeroMQ sockets and replace `msg_handler` transport helpers with in-memory stand-ins.

## Test Files

### `test/test_heartBeat.py`

Purpose:

- Verifies heartbeat timeout, removal, and cancellation behavior in `HeartbeatProcessor`.

Coverage:

- dead marking after timeout
- heartbeat entry removal after remove threshold
- validation of positive loop parameters
- cancellation propagation from the watchdog loop
- recovery when a fresh heartbeat arrives before the next watchdog pass

Mocking details:

- No external mocks are used.
- The tests operate on real `RuntimeState` and `HeartbeatProcessor` instances with synthetic timestamps.

### `test/test_main.py`

Purpose:

- Verifies config parsing and startup helper wiring in `src/capstone_center/main.py`.

Coverage:

- YAML loading from disk
- subscriber option construction
- explicit override argument handling
- invalid config rejection
- display publisher option construction
- motor publisher option construction
- heartbeat config extraction
- `CenterApp.run()` task orchestration

Mocking details:

- `test_center_app_run_starts_recv_and_heartbeat` uses `AsyncMock` for every processor `run()` method.
- Other tests use real in-memory config dicts and a real `zmq.asyncio.Context`.
- `test_load_config_reads_yaml` uses a real temporary file instead of mocking file I/O.

### `test/test_msg_recv_processor.py`

Purpose:

- Verifies dispatch and error handling in `MessageRecvProcessor`.

Coverage:

- heartbeat dispatch to `_other_msg_handler`
- sensor dispatch to `_sensor_msg_handler`
- override dispatch to `_override_button`
- ignoring unknown message types
- continuing after validation errors
- continuing after assertion errors
- override mode state updates
- subscriber options passed through to the subscriber factory
- receiver-side timestamp selection for heartbeats

Mocking details:

- `msg_handler.get_async_subscriber` is replaced with an async context manager backed by an in-memory async iterator.
- `msg_handler.SensorMessage.model_validate` is replaced with lightweight fake validators.
- Some tests patch `msg_handler.GenericMessageDatatype`.
- Several tests replace internal handlers with `AsyncMock` to isolate dispatch behavior.
- `test_handle_heart_beat_uses_receiver_time_not_message_timestamp` patches the module-local `datetime` provider.

### `test/test_signal_pipeline_integration.py`

Purpose:

- Verifies narrow integration between receive, sensor, display, and motor processing stages.

Coverage:

- sensor message propagation into derived-state updates
- fan-out from sensor processing to display and motor signals
- override propagation into outbound display and motor messages

Mocking details:

- subscriber input is simulated with an in-memory async iterator
- publisher output is simulated with in-memory async publishers
- `msg_handler.SensorPayload`, `DisplayMessage`, `MotorState`, and `MotorMessage` are replaced with lightweight stand-ins where needed
- real `CoalescedUpdateSignal`, `RuntimeState`, and `DerivedState` instances are used

### `test/test_motor_sender_processor.py`

Purpose:

- Verifies event-driven motor command generation.

Coverage:

- motor state decision logic
- message publishing when the motor signal is triggered

Mocking details:

- `msg_handler.get_async_publisher` is replaced with an in-memory async context manager
- `msg_handler.MotorState` is replaced with a simple namespace
- `msg_handler.MotorMessage` is replaced with a `SimpleNamespace` factory

### `test/test_motor_sender_periodic_retry.py`

Purpose:

- Verifies periodic resend behavior in `MotorSenderProcessor` when no signal event arrives.

Coverage:

- periodic publishing on timeout
- repeated outbound messages with the expected sender and folding command

Mocking details:

- `msg_handler.get_async_publisher` is replaced with an in-memory async context manager
- `msg_handler.MotorState` is replaced with a simple namespace
- `msg_handler.MotorMessage` is replaced with a `SimpleNamespace` factory

### `test/test_visual_harness_api_smoke.py`

Purpose:

- Verifies the visual harness HTTP handler without starting an actual server.

Coverage:

- POST `/api/sensors`
- GET `/api/state`
- state persistence between handler calls through shared state

Mocking details:

- no real HTTP server is started
- request and response streams are provided with `io.BytesIO`
- the handler object is manually constructed with the minimum methods and fields required by `BaseHTTPRequestHandler`
- the visual harness module is imported directly from file using `importlib`

## What Is Not Covered Well Yet

- real ZeroMQ socket interoperability
- end-to-end execution through `main()`
- config-driven behavior for keys that currently exist but are not wired into the implementation
- display publisher timing behavior, because current tests focus on event-driven sends and override propagation
- Docker-based visual harness startup

## Notes for Future Test Additions

- If config keys such as `presence.*`, `status.*`, or `display.refresh_interval_sec` become active, tests should be added at the processor level first.
- If ZeroMQ interoperability becomes important, add a dedicated integration layer rather than expanding unit tests with more socket setup.
- Keep the current strategy of mocking transport boundaries while exercising real state and processor logic inside the application.
