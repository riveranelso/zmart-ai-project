"""Brain -> Omar bridge: reusable adapter from a Zmart Brain result to Omar Core.

See zmart360/BRAIN_OMAR_BRIDGE.md for the design note. The bridge is
fail-closed: it never invents a route. Any doubt about the Brain payload,
the business identity, or Omar's answer raises a typed error instead.
"""
from .bridge import (
    BRAIN_TO_OMAR_BUSINESS_ID,
    OMAR_BUSINESS_IDS,
    BridgeError,
    BridgeResult,
    BrainContractError,
    MissingBusinessContextError,
    OmarAuthError,
    OmarClient,
    OmarConfigError,
    OmarRejectedError,
    OmarResponseError,
    OmarUnreachableError,
    UnknownBusinessError,
    route_for_brain_output,
)

__all__ = [
    "BRAIN_TO_OMAR_BUSINESS_ID",
    "OMAR_BUSINESS_IDS",
    "BridgeError",
    "BridgeResult",
    "BrainContractError",
    "MissingBusinessContextError",
    "OmarAuthError",
    "OmarClient",
    "OmarConfigError",
    "OmarRejectedError",
    "OmarResponseError",
    "OmarUnreachableError",
    "UnknownBusinessError",
    "route_for_brain_output",
]
