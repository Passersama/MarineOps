"""Explicit plan selection and field override rules, independent of widgets."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TaskSelection:
    state: str
    reason: str = ""

    @classmethod
    def decide(cls, checked, explicitly_excluded, feasible):
        if checked:
            return cls("included")
        if explicitly_excluded:
            return cls("user_excluded", "Excluded by the user from this plan")
        return cls("unavailable", "No feasible route; review From / To and stop order" if not feasible else
                   "Entry has not been assigned to this plan")

    def payload(self):
        return asdict(self)


@dataclass(frozen=True)
class DraftOverride:
    value: str
    base: str

    def applies_to(self, current):
        return current == self.base
