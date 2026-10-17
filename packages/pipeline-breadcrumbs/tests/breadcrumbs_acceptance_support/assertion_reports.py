from collections.abc import Sequence


def format_assertion_report(header: str, business_claim: str, scenario_context: str, mismatches: Sequence[str]) -> str:
    """One failure report: the claim that did not hold, the scenario it was checked for, and every mismatch, counted."""
    mismatch_lines: str = "\n".join(f"  - {mismatch}" for mismatch in mismatches)
    return f"\n{header}\nClaim: {business_claim}\nScenario: {scenario_context}\n{len(mismatches)} mismatch(es):\n{mismatch_lines}"
