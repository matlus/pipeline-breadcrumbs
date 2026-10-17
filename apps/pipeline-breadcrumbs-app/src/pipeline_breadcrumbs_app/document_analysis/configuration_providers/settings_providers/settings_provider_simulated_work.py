import math
from collections.abc import Mapping
from typing import Final, final

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.simulated_work_settings import SimulatedWorkSettings
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_source import SettingsSource
from pipeline_breadcrumbs_app.document_analysis.exceptions import ConfigurationSettingError

SIMULATED_WORK_SECONDS_VARIABLE_NAME: Final[str] = "DOCUMENT_ANALYSIS_SIMULATED_WORK_SECONDS"
SIMULATED_WORK_SECONDS_DEFAULT: Final[float] = 0.0


@final
class SettingsProviderSimulatedWork:
    """Reads the simulated-work pace eagerly. Optional: absent means no delay."""

    def __init__(self, override_by_environment_variable_name: Mapping[str, str] | None = None) -> None:
        self._settings_source: SettingsSource = SettingsSource(override_by_environment_variable_name)
        self._simulated_work_settings: SimulatedWorkSettings = SimulatedWorkSettings(delay_seconds=self._read_delay_seconds())

    def get_simulated_work_settings(self) -> SimulatedWorkSettings:
        return self._simulated_work_settings

    def _read_delay_seconds(self) -> float:
        delay_seconds_raw_value: str | None = self._settings_source.read_setting_value(SIMULATED_WORK_SECONDS_VARIABLE_NAME)
        if not SettingsSource.is_setting_present(delay_seconds_raw_value):
            return SIMULATED_WORK_SECONDS_DEFAULT
        try:
            delay_seconds: float = float(delay_seconds_raw_value.strip())
        except ValueError as value_error:
            raise self._create_invalid_delay_error(delay_seconds_raw_value) from value_error
        if not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise self._create_invalid_delay_error(delay_seconds_raw_value)
        return delay_seconds

    @staticmethod
    def _create_invalid_delay_error(delay_seconds_raw_value: str) -> ConfigurationSettingError:
        return ConfigurationSettingError(
            f"Setting '{SIMULATED_WORK_SECONDS_VARIABLE_NAME}' is '{delay_seconds_raw_value}', which is not a number of seconds of 0 or more",
            SIMULATED_WORK_SECONDS_VARIABLE_NAME,
        )
