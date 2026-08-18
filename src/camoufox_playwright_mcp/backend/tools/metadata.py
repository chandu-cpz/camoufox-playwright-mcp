from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    title: str
    description: str


# Mirrors upstream tool metadata from:
# upstream/playwright/packages/playwright-core/src/tools/backend/*.ts
UPSTREAM_TOOL_METADATA: dict[str, ToolMetadata] = {
    "browser_click": ToolMetadata("Click", "Perform click on a web page"),
    "browser_check": ToolMetadata("Check", "Check a checkbox or radio button"),
    "browser_close": ToolMetadata("Close browser", "Close the page"),
    "browser_console_clear": ToolMetadata(
        "Clear console messages", "Clear all console messages"
    ),
    "browser_console_messages": ToolMetadata(
        "Get console messages", "Returns all console messages"
    ),
    "browser_cookie_clear": ToolMetadata("Clear cookies", "Clear all cookies"),
    "browser_cookie_delete": ToolMetadata("Delete cookie", "Delete a specific cookie"),
    "browser_cookie_get": ToolMetadata("Get cookie", "Get a specific cookie by name"),
    "browser_cookie_list": ToolMetadata(
        "List cookies", "List all cookies (optionally filtered by domain/path)"
    ),
    "browser_cookie_set": ToolMetadata(
        "Set cookie",
        "Set a cookie with optional flags (domain, path, expires, httpOnly, secure, sameSite)",
    ),
    "browser_drag": ToolMetadata(
        "Drag mouse", "Perform drag and drop between two elements"
    ),
    "browser_drop": ToolMetadata(
        "Drop files or data onto an element",
        'Drop files or MIME-typed data onto an element, as if dragged from outside the page. At least one of "paths" or "data" must be provided.',
    ),
    "browser_evaluate": ToolMetadata(
        "Evaluate JavaScript", "Evaluate JavaScript expression on page or element"
    ),
    "browser_file_upload": ToolMetadata("Upload files", "Upload one or multiple files"),
    "browser_fill_form": ToolMetadata("Fill form", "Fill multiple form fields"),
    "browser_find": ToolMetadata(
        "Find in page snapshot",
        "Search the accessibility snapshot of the current page for text or a regular expression. Returns matching snapshot nodes with a few lines of surrounding context (like search snippets), which is cheaper than capturing the whole snapshot when you only need to locate an element and its ref.",
    ),
    "browser_generate_locator": ToolMetadata(
        "Create locator for element",
        "Generate locator for the given element to use in tests",
    ),
    "browser_get_config": ToolMetadata(
        "Get config",
        "Get the final resolved config after merging CLI options, environment variables and config file.",
    ),
    "browser_handle_dialog": ToolMetadata("Handle a dialog", "Handle a dialog"),
    "browser_hide_highlight": ToolMetadata(
        "Hide element highlight",
        "Remove a highlight overlay previously added for the element.",
    ),
    "browser_highlight": ToolMetadata(
        "Highlight element",
        "Show a persistent highlight overlay around the element on the page.",
    ),
    "browser_hover": ToolMetadata("Hover mouse", "Hover over element on page"),
    "browser_keydown": ToolMetadata(
        "Press a key down", "Press a key down on the keyboard"
    ),
    "browser_keyup": ToolMetadata("Press a key up", "Press a key up on the keyboard"),
    "browser_localstorage_clear": ToolMetadata(
        "Clear localStorage", "Clear all localStorage"
    ),
    "browser_localstorage_delete": ToolMetadata(
        "Delete localStorage item", "Delete a localStorage item"
    ),
    "browser_localstorage_get": ToolMetadata(
        "Get localStorage item", "Get a localStorage item by key"
    ),
    "browser_localstorage_list": ToolMetadata(
        "List localStorage", "List all localStorage key-value pairs"
    ),
    "browser_localstorage_set": ToolMetadata(
        "Set localStorage item", "Set a localStorage item"
    ),
    "browser_mouse_click_xy": ToolMetadata(
        "Click", "Click mouse button at a given position"
    ),
    "browser_mouse_down": ToolMetadata("Press mouse down", "Press mouse down"),
    "browser_mouse_drag_xy": ToolMetadata(
        "Drag mouse", "Drag left mouse button to a given position"
    ),
    "browser_mouse_move_xy": ToolMetadata(
        "Move mouse", "Move mouse to a given position"
    ),
    "browser_mouse_up": ToolMetadata("Press mouse up", "Press mouse up"),
    "browser_mouse_wheel": ToolMetadata("Scroll mouse wheel", "Scroll mouse wheel"),
    "browser_navigate": ToolMetadata("Navigate to a URL", "Navigate to a URL"),
    "browser_navigate_back": ToolMetadata(
        "Go back", "Go back to the previous page in the history"
    ),
    "browser_navigate_forward": ToolMetadata(
        "Go forward", "Go forward to the next page in the history"
    ),
    "browser_network_request": ToolMetadata(
        "Show network request details",
        "Returns full details (headers and body) of a single network request, or a single part if `part` is set. Use the number from browser_network_requests.",
    ),
    "browser_network_requests": ToolMetadata(
        "List network requests",
        "Returns a numbered list of network requests since loading the page. Use browser_network_request with the number to get full details.",
    ),
    "browser_network_clear": ToolMetadata(
        "Clear network requests", "Clear all network requests"
    ),
    "browser_network_state_set": ToolMetadata(
        "Set network state",
        "Sets the browser network state to online or offline. When offline, all network requests will fail.",
    ),
    "browser_pdf_save": ToolMetadata("Save as PDF", "Save page as PDF"),
    "browser_press_key": ToolMetadata("Press a key", "Press a key on the keyboard"),
    "browser_press_sequentially": ToolMetadata(
        "Type text key by key", "Type text key by key on the keyboard"
    ),
    "browser_reload": ToolMetadata("Reload the page", "Reload the current page"),
    "browser_resize": ToolMetadata(
        "Resize browser window", "Resize the browser window"
    ),
    "browser_resume": ToolMetadata(
        "Resume paused script execution",
        "Resume script execution after it was paused. When called with step set to true, execution will pause again before the next action.",
    ),
    "browser_route": ToolMetadata(
        "Mock network requests",
        "Set up a route to mock network requests matching a URL pattern",
    ),
    "browser_route_list": ToolMetadata(
        "List network routes", "List all active network routes"
    ),
    "browser_run_code_unsafe": ToolMetadata(
        "Run Playwright code (unsafe)",
        "Run a Playwright code snippet. Unsafe: executes arbitrary JavaScript in the Playwright server process and is RCE-equivalent.",
    ),
    "browser_select_option": ToolMetadata(
        "Select option", "Select an option in a dropdown"
    ),
    "browser_sessionstorage_clear": ToolMetadata(
        "Clear sessionStorage", "Clear all sessionStorage"
    ),
    "browser_sessionstorage_delete": ToolMetadata(
        "Delete sessionStorage item", "Delete a sessionStorage item"
    ),
    "browser_sessionstorage_get": ToolMetadata(
        "Get sessionStorage item", "Get a sessionStorage item by key"
    ),
    "browser_sessionstorage_list": ToolMetadata(
        "List sessionStorage", "List all sessionStorage key-value pairs"
    ),
    "browser_sessionstorage_set": ToolMetadata(
        "Set sessionStorage item", "Set a sessionStorage item"
    ),
    "browser_set_storage_state": ToolMetadata(
        "Restore storage state",
        "Restore storage state (cookies, local storage) from a file. This clears existing cookies and local storage before restoring.",
    ),
    "browser_snapshot": ToolMetadata(
        "Page snapshot",
        "Capture accessibility snapshot of the current page, this is better than screenshot",
    ),
    "browser_start_tracing": ToolMetadata("Start tracing", "Start trace recording"),
    "browser_start_video": ToolMetadata("Start video", "Start video recording"),
    "browser_stop_tracing": ToolMetadata("Stop tracing", "Stop trace recording"),
    "browser_stop_video": ToolMetadata("Stop video", "Stop video recording"),
    "browser_storage_state": ToolMetadata(
        "Save storage state",
        "Save storage state (cookies, local storage) to a file for later reuse",
    ),
    "browser_tabs": ToolMetadata(
        "Manage tabs", "List, create, close, or select a browser tab."
    ),
    "browser_take_screenshot": ToolMetadata(
        "Take a screenshot",
        "Take a screenshot of the current page. You can't perform actions based on the screenshot, use browser_snapshot for actions.",
    ),
    "browser_type": ToolMetadata("Type text", "Type text into editable element"),
    "browser_uncheck": ToolMetadata("Uncheck", "Uncheck a checkbox or radio button"),
    "browser_unroute": ToolMetadata(
        "Remove network routes",
        "Remove network routes matching a pattern (or all routes if no pattern specified)",
    ),
    "browser_verify_element_visible": ToolMetadata(
        "Verify element visible", "Verify element is visible on the page"
    ),
    "browser_verify_list_visible": ToolMetadata(
        "Verify list visible", "Verify list is visible on the page"
    ),
    "browser_verify_text_visible": ToolMetadata(
        "Verify text visible",
        "Verify text is visible on the page. Prefer browser_verify_element_visible if possible.",
    ),
    "browser_verify_value": ToolMetadata("Verify value", "Verify element value"),
    "browser_video_chapter": ToolMetadata(
        "Video chapter",
        "Add a chapter marker to the video recording. Shows a full-screen chapter card with blurred backdrop.",
    ),
    "browser_video_hide_actions": ToolMetadata(
        "Hide action overlays",
        "Stop annotating actions performed on the page.",
    ),
    "browser_video_show_actions": ToolMetadata(
        "Show action overlays",
        "Annotate subsequent actions performed on the page with a callout that names the action and highlights the target element. Useful while video recording or screencasting.",
    ),
    "browser_wait_for": ToolMetadata(
        "Wait for", "Wait for text to appear or disappear or a specified time to pass"
    ),
}
