# Acceptance tests for declaring steps: what a pipeline writes once, as constants.
# A step's number, name and key are the only identity the trail carries, so the boundary
# refuses a declaration that could not be told apart or sorted later.

import pytest

from pipeline_breadcrumbs import Step, StepPath


@pytest.mark.acceptance
class TestStepDeclaration:
    def test_Step_WhenNoKeyIsGiven_ThenTheKeyIsDerivedFromTheName(self) -> None:
        # Arrange / Act
        actual_step: Step = Step(2, "Metadata Audit")

        # Assert
        expected_key: str = "metadata_audit"
        assert actual_step.key == expected_key

    def test_Step_WhenTheNameHasPunctuation_ThenTheKeyCollapsesItToSingleUnderscores(self) -> None:
        # Arrange / Act
        actual_step: Step = Step(5, "Header/Footer Analysis")

        # Assert
        expected_key: str = "header_footer_analysis"
        assert actual_step.key == expected_key

    def test_Step_WhenAKeyIsRequested_ThenThatKeyIsKept(self) -> None:
        # Arrange / Act
        actual_step: Step = Step(1, "Page Image Extraction", requested_key="page_images")

        # Assert
        expected_key: str = "page_images"
        assert actual_step.key == expected_key

    def test_Step_WhenTheNameHasSurroundingSpaces_ThenTheNameIsTrimmed(self) -> None:
        # Arrange / Act
        actual_step: Step = Step(1, "  Load  ")

        # Assert
        expected_name: str = "Load"
        assert actual_step.name == expected_name

    @pytest.mark.parametrize("step_number", [0, -1, 100])
    def test_Step_WhenTheNumberIsOutsideOneToNinetyNine_ThenItIsRefused(self, step_number: int) -> None:
        # Arrange / Act / Assert - the padded filename range is 1 to 99
        with pytest.raises(ValueError, match="between 1 and 99"):
            Step(step_number, "Load")

    def test_Step_WhenTheNameIsBlank_ThenItIsRefused(self) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="name must not be blank"):
            Step(1, "   ")

    @pytest.mark.parametrize("requested_key", ["Has Space", "UPPER", "double__underscore", "_leading"])
    def test_Step_WhenTheRequestedKeyIsMalformed_ThenItIsRefused(self, requested_key: str) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="lowercase letters and digits"):
            Step(1, "Load", requested_key=requested_key)


@pytest.mark.acceptance
class TestStepPathComposition:
    def test_StepPath_WhenAChildIsDeclaredInsideAChild_ThenTheNumbersComposeWithDots(self) -> None:
        # Arrange / Act
        actual_step_path: StepPath = StepPath().child(3).child(2)

        # Assert
        expected_text: str = "3.2"
        assert str(actual_step_path) == expected_text

    def test_StepPath_WhenTheTenthSubStepIsReported_ThenItIsNotMistakenForTheFirst(self) -> None:
        # Arrange / Act - float("2.10") is 2.1, so a float-based number would log the tenth sub-step as the first
        actual_step_path: StepPath = StepPath().child(2).child(10)

        # Assert
        expected_text: str = "2.10"
        assert str(actual_step_path) == expected_text

    def test_StepPath_WhenPathsAreListedAsFilenameSegments_ThenTheyStayInPipelineOrderPastNine(self) -> None:
        # Arrange
        step_paths: list[StepPath] = [StepPath().child(2).child(step_number) for step_number in (10, 2, 9, 1)]

        # Act
        actual_segments_sorted_as_text: list[str] = sorted(step_path.padded() for step_path in step_paths)
        actual_segments_in_path_order: list[str] = [step_path.padded() for step_path in sorted(step_paths)]

        # Assert
        expected_segments: list[str] = ["02.01", "02.02", "02.09", "02.10"]
        assert actual_segments_sorted_as_text == actual_segments_in_path_order == expected_segments

    def test_StepPath_WhenTwoPathsDifferInTheirLastNumber_ThenTheyOrderNumericallyNotAlphabetically(self) -> None:
        # Arrange / Act / Assert
        assert StepPath((2, 9)) < StepPath((2, 10))

    def test_StepPath_WhenCountingSegments_ThenDepthIsTheNumberOfSteps(self) -> None:
        # Arrange / Act / Assert
        assert StepPath().depth == 0
        assert StepPath().child(1).child(2).depth == 2
