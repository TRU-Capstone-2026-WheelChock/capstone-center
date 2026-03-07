from types import SimpleNamespace

import msg_handler


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
