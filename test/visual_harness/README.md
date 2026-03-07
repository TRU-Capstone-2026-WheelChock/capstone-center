# Visual Harness

Manual visual test setup for `capstone_center`.

## What it shows

- Input:
  - 3 sensor toggles (`ON/OFF`)
  - sensor disconnected checkboxes (per sensor)
  - override toggle (`ON/OFF`)
- Internal state: values inferred from latest `DisplayMessage`
- Output:
  - latest display command (raw JSON)
  - latest motor command (raw JSON)

## Run

```bash
docker compose -f docker-compose.visual-harness.yml up --build
```

Open:

```text
http://localhost:8080
```

## Timeout Check

To verify heartbeat timeout behavior:

1. Keep the harness running.
2. Turn on `disconnected` for one sensor.
3. Confirm the center logs timeout warnings for that sensor after threshold time.

## Notes

- This harness intentionally lives under `test/` because it is for manual test/verification, not production runtime.
- `run_center.py` includes a compatibility shim for `msg_handler` variants that do not provide `MotorState` or `GenericMessageDatatype`.
