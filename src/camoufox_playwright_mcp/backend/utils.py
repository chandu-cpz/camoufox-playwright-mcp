from __future__ import annotations

import re

_UNSAFE_FILE_PATH_CHARS = re.compile(r"[\x00-\x2C\x2E-\x2F\x3A-\x40\x5B-\x60\x7B-\x7F]+")


def sanitize_for_file_path(value: str) -> str:
    separator = value.rfind(".")
    if separator == -1:
        return _sanitize_file_path_part(value)
    return _sanitize_file_path_part(value[:separator]) + "." + _sanitize_file_path_part(value[separator + 1 :])


def _sanitize_file_path_part(value: str) -> str:
    return _UNSAFE_FILE_PATH_CHARS.sub("-", value)
