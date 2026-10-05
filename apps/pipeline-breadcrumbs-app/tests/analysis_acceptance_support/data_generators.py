import secrets

_RANDOM_SUFFIX_BYTES: int = 3


def create_random_section_titles(section_title_count: int) -> list[str]:
    """Distinct section titles no other scenario shares, so a reply keyed by title can never meet the wrong page."""
    return [f"Section {index} {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}" for index in range(section_title_count)]


def create_page_texts(section_titles: list[str]) -> list[str]:
    """One page of text per title, in the shape the system's pages arrive in."""
    return [f"SECTION: {section_title}\nText of the page that starts '{section_title}'." for section_title in section_titles]
