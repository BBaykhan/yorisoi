"""Deterministic safety limits that run around the agent loop (Strands hooks)."""
from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry


class SafetyLimits(HookProvider):
    """Per request: at most MAX_TOTAL tool calls, and notify_family at most once
    (so a confused model can never spam the family)."""

    MAX_TOTAL = 12
    PER_TOOL = {"notify_family": 1}

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.total = 0

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.check)

    def reset(self, event: BeforeInvocationEvent) -> None:
        self.counts = {}
        self.total = 0

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        self.total += 1
        self.counts[name] = self.counts.get(name, 0) + 1

        if self.total > self.MAX_TOTAL:
            event.cancel_tool = "Tool-call limit reached. Do NOT call more tools; answer with what you have."
        elif self.counts[name] > self.PER_TOOL.get(name, self.MAX_TOTAL):
            event.cancel_tool = f"'{name}' was already used in this request. Do NOT call it again."
