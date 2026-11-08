"""An integration that changes nothing outside the test: its state is a field, and it can be made
to refuse changes or to fail when checked."""

from reflektortts.integrations import IntegrationError, IntegrationState, IntegrationStatus


class FakeIntegration:
    name = "Fake integration"
    description = "Turns on the fake app's remote control. Disable puts it back."

    def __init__(self, status: IntegrationStatus = IntegrationStatus.DISABLED, reason: str | None = None) -> None:
        self.current = IntegrationState(status, reason)
        self.refusal: str | None = None
        """The message enable and disable raise IntegrationError with, or None to do as asked."""
        self.failure: Exception | None = None
        """What state raises, or None to answer."""
        self.calls: list[str] = []

    def state(self) -> IntegrationState:
        if self.failure is not None:
            raise self.failure
        return self.current

    def enable(self) -> None:
        self._change("enable", IntegrationStatus.ENABLED)

    def disable(self) -> None:
        self._change("disable", IntegrationStatus.DISABLED)

    def _change(self, call: str, status: IntegrationStatus) -> None:
        self.calls.append(call)
        if self.refusal is not None:
            raise IntegrationError(self.refusal)
        self.current = IntegrationState(status)
