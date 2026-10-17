from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelServiceSettings:
    # The model service is an HTTP API in front of the model, so the only connection setting is
    # where that API lives. It varies per environment and must be configured in each one.
    base_url: str
