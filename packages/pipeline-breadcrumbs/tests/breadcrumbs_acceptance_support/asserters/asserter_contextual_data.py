from collections.abc import Mapping

from pipeline_breadcrumbs import ContextualExceptionProtocol


class AsserterContextualData:
    """Checks the named diagnostic data an exception carries."""

    @staticmethod
    def assert_exactly_these_entries(
        expected_contextual_data_by_name: Mapping[str, object],
        actual_exception: ContextualExceptionProtocol,
    ) -> None:
        actual_contextual_data_by_name: Mapping[str, object] = actual_exception.contextual_data_by_name
        assertion_failures: list[str] = []
        for expected_name, expected_value in expected_contextual_data_by_name.items():
            if expected_name not in actual_contextual_data_by_name:
                assertion_failures.append(f"'{expected_name}' is missing; expected {expected_value!r}")
            elif actual_contextual_data_by_name[expected_name] != expected_value:
                assertion_failures.append(
                    f"'{expected_name}': expected {expected_value!r} but found {actual_contextual_data_by_name[expected_name]!r}"
                )
        assertion_failures.extend(
            f"'{actual_name}' was not expected"
            for actual_name in actual_contextual_data_by_name
            if actual_name not in expected_contextual_data_by_name
        )
        assert not assertion_failures, "CONTEXTUAL DATA ASSERTION FAILED\n" + "\n".join(assertion_failures)
