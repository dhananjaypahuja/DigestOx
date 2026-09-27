"""The one exception type the CLI turns into a clean message or a JSON error."""


class PulseError(Exception):
    """An expected failure with a stable code, a plain message, and an optional hint."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, str]:
        data = {"code": self.code, "message": self.message}
        if self.hint:
            data["hint"] = self.hint
        return data
