# Acceptance tests for declaring steps: what a pipeline writes once, as constants.
# A step's number, name and key are the only identity the trail carries, so the boundary
# refuses a declaration that could not be told apart or sorted later.

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import ExceptionAsserter, ExpectedException

from pipeline_breadcrumbs import InvalidDeclarationException, Step, StepPath


@pytest.mark.acceptance
class TestStepDeclaration:
    def test_Step_WhenNoKeyIsGiven_ThenTheKeyIsDerivedFromTheName(self) -> None:
        # Arrange
        expected_key: str = "metadata_audit"

        # Act
        actual_step: Step = Step(2, "Metadata Audit")

        # Assert
        assert actual_step.key == expected_key

    def test_Step_WhenTheNameHasPunctuation_ThenTheKeyCollapsesItToSingleUnderscores(self) -> None:
        # Arrange
        expected_key: str = "header_footer_analysis"

        # Act
        actual_step: Step = Step(5, "Header/Footer Analysis")

        # Assert
        assert actual_step.key == expected_key

    def test_Step_WhenAKeyIsRequested_ThenThatKeyIsKept(self) -> None:
        # Arrange
        expected_key: str = "page_images"

        # Act
        actual_step: Step = Step(1, "Page Image Extraction", requested_key=expected_key)

        # Assert
        assert actual_step.key == expected_key

    def test_Step_WhenTheNameHasSurroundingSpaces_ThenTheNameIsTrimmed(self) -> None:
        # Arrange
        expected_name: str = "Load"

        # Act
        actual_step: Step = Step(1, f"  {expected_name}  ")

        # Assert
        assert actual_step.name == expected_name

    @pytest.mark.parametrize("step_number", [0, -1, 100])
    def test_Step_WhenTheNumberIsOutsideOneToNinetyNine_ThenItIsRefused(self, step_number: int) -> None:
        # Arrange - the padded filename range is 1 to 99
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationException, message_phrases=["between 1 and 99", f"got {step_number}"]
        )

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            Step(step_number, "Load")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    def test_Step_WhenTheNameIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["name must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            Step(1, "   ")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    @pytest.mark.parametrize("requested_key", ["Has Space", "UPPER", "double__underscore", "_leading"])
    def test_Step_WhenTheRequestedKeyIsMalformed_ThenItIsRefused(self, requested_key: str) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationException, message_phrases=[requested_key, "lowercase letters and digits"]
        )

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            Step(1, "Load", requested_key=requested_key)

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestStepPathComposition:
    def test_StepPath_WhenAChildIsDeclaredInsideAChild_ThenTheNumbersComposeWithDots(self) -> None:
        # Arrange
        expected_text: str = "3.2"

        # Act
        actual_step_path: StepPath = StepPath().child(3).child(2)

        # Assert
        assert str(actual_step_path) == expected_text

    def test_StepPath_WhenTheTenthSubStepIsReported_ThenItIsNotMistakenForTheFirst(self) -> None:
        # Arrange - float("2.10") is 2.1, so a float-based number would log the tenth sub-step as the first
        expected_text: str = "2.10"

        # Act
        actual_step_path: StepPath = StepPath().child(2).child(10)

        # Assert
        assert str(actual_step_path) == expected_text

    def test_StepPath_WhenPathsAreListedAsFilenameSegments_ThenTheyStayInPipelineOrderPastNine(self) -> None:
        # Arrange
        step_paths: list[StepPath] = [StepPath().child(2).child(step_number) for step_number in (10, 2, 9, 1)]
        expected_segments: list[str] = ["02.01", "02.02", "02.09", "02.10"]

        # Act
        actual_segments_sorted_as_text: list[str] = sorted(step_path.padded() for step_path in step_paths)
        actual_segments_in_path_order: list[str] = [step_path.padded() for step_path in sorted(step_paths)]

        # Assert
        assert (actual_segments_sorted_as_text, actual_segments_in_path_order) == (expected_segments, expected_segments)

    def test_StepPath_WhenTwoPathsDifferInTheirLastNumber_ThenTheyOrderNumericallyNotAlphabetically(self) -> None:
        # Arrange
        ninth_sub_step_path: StepPath = StepPath((2, 9))
        tenth_sub_step_path: StepPath = StepPath((2, 10))
        expected_paths_in_order: list[StepPath] = [ninth_sub_step_path, tenth_sub_step_path]

        # Act
        actual_paths_in_order: list[StepPath] = sorted([tenth_sub_step_path, ninth_sub_step_path])

        # Assert
        assert actual_paths_in_order == expected_paths_in_order

    def test_StepPath_WhenCountingSegments_ThenDepthIsTheNumberOfSteps(self) -> None:
        # Arrange
        expected_depths: tuple[int, int] = (0, 2)

        # Act
        actual_depths: tuple[int, int] = (StepPath().depth, StepPath().child(1).child(2).depth)

        # Assert
        assert actual_depths == expected_depths
