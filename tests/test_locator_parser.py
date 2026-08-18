from camoufox_playwright_mcp.backend.locator_generator import as_python_locator
from camoufox_playwright_mcp.backend.locator_parser import (
    locator_or_selector_as_selector,
)


def test_python_role_locator_to_selector() -> None:
    selector = locator_or_selector_as_selector('get_by_role("button", name="Submit", exact=True)')

    assert selector == 'internal:role=button[name="Submit"s]'


def test_python_chained_locator_to_selector() -> None:
    selector = locator_or_selector_as_selector('locator("article").filter(has=get_by_text("Submit"))')

    assert selector == 'article >> internal:has="internal:text=\\"Submit\\"i"'


def test_python_nested_test_id_uses_custom_attribute() -> None:
    selector = locator_or_selector_as_selector(
        'locator("article").filter(has=get_by_test_id("submit"))',
        test_id_attribute="data-pw",
    )

    assert selector == 'article >> internal:has="internal:testid=[data-pw=\\"submit\\"s]"'


def test_python_frame_locator_to_selector() -> None:
    selector = locator_or_selector_as_selector('page.locator("iframe").content_frame.get_by_role("heading", name="Inner")')

    assert selector == 'iframe >> internal:control=enter-frame >> internal:role=heading[name="Inner"i]'


def test_python_regex_locator_to_selector() -> None:
    selector = locator_or_selector_as_selector('get_by_text(re.compile(r"foo", re.IGNORECASE))')

    assert selector == "internal:text=/foo/i"


def test_selector_round_trip_back_to_python_locator() -> None:
    selector = locator_or_selector_as_selector('page.locator("iframe").content_frame.get_by_role("heading", name="Inner")')

    assert as_python_locator(selector) == 'locator("iframe").content_frame.get_by_role("heading", name="Inner")'


def test_non_locator_selector_passes_through() -> None:
    assert locator_or_selector_as_selector("button.submit") == "button.submit"
