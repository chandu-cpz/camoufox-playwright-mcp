from camoufox_playwright_mcp.backend.codegen import python_invocation
from camoufox_playwright_mcp.backend.locator_generator import (
    as_python_locator,
    as_python_locator_description,
    as_python_locators,
)


def test_generates_python_role_locator() -> None:
    locator = as_python_locator('internal:role=button[name="Submit"i]')

    assert locator == 'get_by_role("button", name="Submit")'


def test_generates_python_test_id_locator() -> None:
    locator = as_python_locator('internal:testid=[data-tid="submit"s]')

    assert locator == 'get_by_test_id("submit")'


def test_formats_python_locator_invocation() -> None:
    code = python_invocation(
        'get_by_role("button", name="Submit")',
        "click",
        [("modifiers", ["Shift", "Alt"])],
    )

    assert code == 'await page.get_by_role("button", name="Submit").click(modifiers=["Shift", "Alt"])'


def test_generates_python_attribute_locators() -> None:
    assert as_python_locator('internal:attr=[placeholder="Email"s]') == 'get_by_placeholder("Email", exact=True)'
    assert as_python_locator('internal:attr=[title=/hello/i]') == 'get_by_title(re.compile(r"hello", re.IGNORECASE))'


def test_generates_python_nested_has_locator() -> None:
    locator = as_python_locator('css=article >> internal:has="internal:text=Submit"')

    assert locator == 'locator("article").filter(has=get_by_text("Submit"))'


def test_generates_python_or_locator() -> None:
    locator = as_python_locator('internal:role=button[name="Save"s] >> internal:or="internal:role=link[name=\\"Cancel\\"i]"')

    assert locator == 'get_by_role("button", name="Save", exact=True).or_(get_by_role("link", name="Cancel"))'


def test_generates_python_frame_locator_options() -> None:
    locators = as_python_locators('iframe >> internal:control=enter-frame >> internal:role=button[name="Submit"i]', max_output_size=4)

    assert locators == [
        'locator("iframe").content_frame.get_by_role("button", name="Submit")',
        'locator("css=iframe").content_frame.get_by_role("button", name="Submit")',
        'frame_locator("iframe").get_by_role("button", name="Submit")',
        'frame_locator("css=iframe").get_by_role("button", name="Submit")',
    ]


def test_generates_python_visible_and_regex_locators() -> None:
    assert as_python_locator("css=div >> visible=true") == 'locator("div").filter(visible=True)'
    assert as_python_locator("internal:text=/foo/i") == 'get_by_text(re.compile(r"foo", re.IGNORECASE))'
    assert as_python_locator("internal:role=button[name=/save/i]") == 'get_by_role("button", name=re.compile(r"save", re.IGNORECASE))'


def test_python_locator_description_defaults_to_locator() -> None:
    assert as_python_locator_description('internal:role=button[name="Submit"i]') == 'get_by_role("button", name="Submit")'


def test_python_locator_description_uses_internal_describe() -> None:
    selector = 'internal:role=button[name="Submit"i] >> internal:describe="Primary submit button"'

    assert as_python_locator_description(selector) == "Primary submit button"
    assert as_python_locator(selector) == 'get_by_role("button", name="Submit")'


def test_python_locator_description_tolerates_invalid_selector() -> None:
    selector = 'internal:describe="unterminated'

    assert as_python_locator_description(selector) == selector
