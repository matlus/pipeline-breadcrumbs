from collections.abc import Mapping
from typing import final

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.model_service_settings import ModelServiceSettings
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.simulated_work_settings import SimulatedWorkSettings
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_model_service import (
    SettingsProviderModelService,
)
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_simulated_work import (
    SettingsProviderSimulatedWork,
)


@final
class ConfigurationProvider:
    """Typed access to configuration, obtained from the service locator and used only by the manager.

    Composes one settings provider per cohesive group. Each provider reads and validates eagerly, so
    every configuration problem surfaces when the system is built. This class is real in every run,
    the tests included; it is never replaced by a test double.

    Overrides take precedence over environment variables, per variable. They let a host or a test
    arrange configuration explicitly; production passes none.
    """

    def __init__(self, override_by_environment_variable_name: Mapping[str, str] | None = None) -> None:
        self._settings_provider_model_service: SettingsProviderModelService = SettingsProviderModelService(override_by_environment_variable_name)
        self._settings_provider_simulated_work: SettingsProviderSimulatedWork = SettingsProviderSimulatedWork(override_by_environment_variable_name)

    def get_model_service_settings(self) -> ModelServiceSettings:
        return self._settings_provider_model_service.get_model_service_settings()

    def get_simulated_work_settings(self) -> SimulatedWorkSettings:
        return self._settings_provider_simulated_work.get_simulated_work_settings()
