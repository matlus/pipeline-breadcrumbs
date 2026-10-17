from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulatedWorkSettings:
    # How long each simulated non-model processing step takes. Zero unless an environment asks for a
    # pace, which only the demo does, so a person watching can follow the log as it appears.
    delay_seconds: float
