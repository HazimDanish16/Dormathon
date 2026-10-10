"""Actionable errors safe to return through MCP."""


class AppError(Exception):
    def __init__(self, error: str, hint: str):
        super().__init__(error)
        self.error = error
        self.hint = hint

    def payload(self) -> dict:
        return {"error": self.error, "hint": self.hint}
