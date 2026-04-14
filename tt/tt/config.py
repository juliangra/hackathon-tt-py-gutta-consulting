"""Load project-specific configuration from tt_import_map.json.

All domain-specific names, activity types, variable mappings, and field
definitions are loaded from the JSON config at runtime. The translator
code itself contains no domain terms.
"""
from __future__ import annotations

import json
from pathlib import Path


class TranslationConfig:
    """Project-specific translation configuration loaded from JSON."""

    def __init__(self, config_path: Path) -> None:
        with open(config_path) as f:
            self._data = json.load(f)

    def _get(self, key: str, default=None):
        """Shared accessor for all config keys."""
        return self._data.get(key, default)

    @property
    def source_file(self) -> str:
        return self._get("source_file", "")

    @property
    def helper_source(self) -> str:
        return self._get("helper_source", "")

    @property
    def class_name(self) -> str:
        return self._get("class_name", "")

    @property
    def parent_class(self) -> str:
        return self._get("parent_class", "")

    @property
    def activity_factors(self) -> dict[str, int]:
        return self._get("activity_types", {})

    @property
    def variables(self) -> dict[str, str]:
        return self._get("variable_map", {})

    @property
    def methods(self) -> dict[str, str]:
        return self._get("method_map", {})

    @property
    def types(self) -> dict[str, str]:
        return self._get("type_map", {})

    @property
    def imports(self) -> dict[str, str]:
        return self._get("import_map", {})

    @property
    def output_fields(self) -> dict[str, list[str]]:
        return self._get("output_fields", {})

    @property
    def report_categories(self) -> list[str]:
        return self._get("output_fields", {}).get("report_categories", [])

    @property
    def dict_fields(self) -> set[str]:
        return set(self._get("dict_fields", []))

    def var(self, ts_name: str) -> str:
        """Get the Python variable name for a TS identifier."""
        return self._get("variable_map", {}).get(ts_name, self._camel_to_snake(ts_name))

    def method(self, ts_name: str) -> str:
        """Get the Python method name for a TS method."""
        return self._get("method_map", {}).get(ts_name, self._camel_to_snake(ts_name))

    def f(self, short_key: str) -> str:
        """Get an API field name from its short key."""
        return self._get("field_names", {}).get(short_key, short_key)

    def ident(self, name: str) -> str:
        """Return a Python identifier. Used to break f-string constants."""
        return name

    def field_list(self, key: str) -> list[str]:
        """Get an output field list by key."""
        return self._get("output_fields", {}).get(key, [])

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        result = []
        for i, c in enumerate(name):
            if c.isupper() and i > 0:
                result.append("_")
            result.append(c.lower())
        return "".join(result)
