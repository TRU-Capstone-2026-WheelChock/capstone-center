# Visual Harness

Manual visual test setup for `capstone_center`.

## What it shows

- Input: 3 sensor toggles (`ON/OFF`)
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

## Notes

- This harness intentionally lives under `test/` because it is for manual test/verification, not production runtime.
- `run_center.py` includes a compatibility shim for `msg_handler` variants that do not provide `MotorState` or `GenericMessageDatatype`.
