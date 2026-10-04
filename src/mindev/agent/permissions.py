"""Permission model: plan/act modes and tool-call approval."""

from enum import Enum


class Mode(str, Enum):
    READONLY = "readonly"  # plan mode: read-only
    READWRITE = "readwrite"  # act mode: full, risky tools need approval


class PermissionPolicy:
    """Decide whether a tool call is allowed.

    - ``read`` tools are always allowed.
    - ``write`` / ``command`` tools are denied in readonly mode.
    - In readwrite mode they go through ``approver`` (allowed when ``approver``
      is None, i.e. non-interactive).
    """

    def __init__(self, mode: Mode = Mode.READWRITE, approver=None) -> None:
        self.mode = mode
        self.approver = approver  # callable(tool_name, arguments) -> bool

    def allow(self, tool_name: str, risk: str, arguments: dict) -> bool:
        if risk == "read":
            return True
        if self.mode == Mode.READONLY:
            return False
        if self.approver is None:
            return True
        return bool(self.approver(tool_name, arguments))
