from collections.abc import Mapping
from typing import Final, final
from urllib.parse import ParseResult, urlparse

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.model_service_settings import ModelServiceSettings
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_source import SettingsSource
from pipeline_breadcrumbs_app.document_analysis.exceptions import ConfigurationSettingError

MODEL_SERVICE_BASE_URL_VARIABLE_NAME: Final[str] = "DOCUMENT_ANALYSIS_MODEL_SERVICE_BASE_URL"


def _describe_absence(setting_raw_value: str | None) -> str:
    return "missing" if setting_raw_value is None else "empty or whitespace"


@final
class SettingsProviderModelService:
    """Reads and validates the model service settings eagerly, when the system is built.

    A mangled URL fails at startup naming the setting, not at the first model call as a confusing
    transport error.
    """

    def __init__(self, override_by_environment_variable_name: Mapping[str, str] | None = None) -> None:
        self._settings_source: SettingsSource = SettingsSource(override_by_environment_variable_name)
        self._model_service_settings: ModelServiceSettings = ModelServiceSettings(base_url=self._read_base_url())

    def get_model_service_settings(self) -> ModelServiceSettings:
        return self._model_service_settings

    def _read_base_url(self) -> str:
        base_url_raw_value: str | None = self._settings_source.read_setting_value(MODEL_SERVICE_BASE_URL_VARIABLE_NAME)
        if not SettingsSource.is_setting_present(base_url_raw_value):
            raise ConfigurationSettingError(
                f"Setting '{MODEL_SERVICE_BASE_URL_VARIABLE_NAME}' needs the model service base URL but was {_describe_absence(base_url_raw_value)}",
                MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
            )
        base_url: str = base_url_raw_value.strip()
        parsed_base_url: ParseResult = urlparse(base_url)
        if parsed_base_url.scheme not in ("http", "https") or not parsed_base_url.netloc:
            raise ConfigurationSettingError(
                f"Setting '{MODEL_SERVICE_BASE_URL_VARIABLE_NAME}' is '{base_url}', which is not an absolute http or https URL",
                MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
            )
        return base_url
