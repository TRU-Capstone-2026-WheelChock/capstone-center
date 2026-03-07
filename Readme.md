# Capstone Center

`capstone-center` is the center-side process that receives sensor messages over ZeroMQ, derives a single human-presence decision, and publishes display and motor commands.

## Repository Notes

- Main entry point: `src/capstone_center/main.py`
- Default runtime config: `config.yml`
- Visual harness config: `test/visual_harness/config.center.visual.yml`
- Visual harness Docker setup: `docker-compose.visual-harness.yml`
- Config reference: `CONFIG_REFERENCE.md`

## Run the Visual Harness

The visual harness is the current manual test path for this repository. It starts:

- the center process with `test/visual_harness/config.center.visual.yml`
- the browser UI for driving sensor inputs and observing display/motor output

Start it with Docker Compose:

```bash
docker compose -f docker-compose.visual-harness.yml up --build
```

Then open:

```text
http://localhost:8080
```

More details are in `test/visual_harness/README.md`.

## Configuration

`config.yml` is the default application config.

`test/visual_harness/config.center.visual.yml` uses the same schema, but changes endpoints for the local visual harness topology.

Detailed config notes, including which keys are currently used by the implementation and which are currently unused, are documented in `CONFIG_REFERENCE.md`.
