"""HTTP service wrapper around the Brain -> Omar bridge.

A deployable shell around ``brain_omar_bridge.route_for_brain_output``:
it accepts ONE ESCALATION GATE item per POST, returns the verified
Brain/Omar pairing as JSON, and maps every typed bridge failure to a
non-200 response carrying ONLY the error type name. The Omar key comes
from the environment (``OMAR_API_KEY`` / ``OMAR_API_KEY_FILE``, handled
by the bridge itself) and is never logged, returned, or echoed.

See zmart360/BRAIN_OMAR_BRIDGE.md for the design note and
zmart360/BRAIN_OMAR_BRIDGE_WIRING_SPEC.md for how callers should use
this service (shadow / log-only first).
"""
