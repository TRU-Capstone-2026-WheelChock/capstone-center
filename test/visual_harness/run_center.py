import sys
from pathlib import Path
from types import SimpleNamespace

import msg_handler

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Compatibility shim for environments where msg_handler package
# does not include these symbols.
if not hasattr(msg_handler, "MotorState"):
    msg_handler.MotorState = SimpleNamespace(  # type: ignore[attr-defined]
        STARTING="STARTING",
        DEPLOYING="DEPLOYING",
        FOLDING="FOLDING",
        DEPLOYED="DEPLOYED",
        FOLDED="FOLDED",
        ERROR="ERROR",
    )

if not hasattr(msg_handler, "GenericMessageDatatype"):
    msg_handler.GenericMessageDatatype = SimpleNamespace(  # type: ignore[attr-defined]
        OVERRIDE_BUTTON="override_button"
    )

from capstone_center.main import main


if __name__ == "__main__":
    main()
