import os
from collections.abc import Mapping
from typing import TypeGuard, final


@final
class SettingsSource:
    """The one seam through which settings providers read configuration values.

    Reads the process environment, with per-variable overrides taking precedence so a host or a test
    can arrange configuration explicitly without changing the process environment.
    """

    def __init__(self, override_by_environment_variable_name: Mapping[str, str] | None = None) -> None:
        self._override_by_environment_variable_name: dict[str, str] = dict(override_by_environment_variable_name or {})

    def read_setting_value(self, environment_variable_name: str) -> str | None:
        if environment_variable_name in self._override_by_environment_variable_name:
            return self._override_by_environment_variable_name[environment_variable_name]
        return os.environ.get(environment_variable_name)

    @staticmethod
    def is_setting_present(setting_raw_value: str | None) -> TypeGuard[str]:
        return setting_raw_value is not None and setting_raw_value.strip() != ""
