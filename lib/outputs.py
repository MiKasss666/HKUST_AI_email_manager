"""Tool output helper.

Dify tools must emit one ``variable message`` per declared output on **every**
path, otherwise downstream workflow nodes cannot resolve the variable. This
helper mirrors the official plugins' ``with_outputs`` decorator without reading
YAML: each tool passes its own declared default mapping.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generator

from . import graph


def _coerce(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, (int, float)) and not isinstance(default, bool):
        try:
            return type(default)(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return "" if value is None else str(value)
    if isinstance(default, list):
        if isinstance(value, (list, tuple)):
            return list(value)
        return default
    if isinstance(default, dict):
        return value if isinstance(value, dict) else default
    return value


def run_tool(tool, declared: Dict[str, Any],
             fn: Callable[[], Dict[str, Any]]) -> Generator:
    """Run ``fn`` and always emit every declared output variable."""
    out: Dict[str, Any] = dict(declared)
    error = ""
    try:
        result = fn() or {}
        if isinstance(result, dict):
            out.update(result)
            if "success" in declared and "success" not in result:
                out["success"] = True
        elif "success" in declared:
            out["success"] = True
    except graph.AuthRequired as ex:
        error = str(ex)
        out["success"] = False
    except graph.MailboxUnavailable as ex:
        error = str(ex)
        out["success"] = False
        if "transient" in declared:
            out["transient"] = True
    except graph.GraphError as ex:
        error = str(ex)
        out["success"] = False
        if "transient" in declared:
            out["transient"] = ex.transient
    except Exception as ex:  # noqa: BLE001 - tools must never crash the workflow
        error = f"{type(ex).__name__}: {ex}"
        out["success"] = False

    text = ("OK" if out.get("success") else "ERROR")
    yield tool.create_text_message(text + (": " + error if error else ""))
    for name, default in declared.items():
        if name == "success":
            value = bool(out.get("success"))
        elif name == "error":
            value = error
        else:
            value = _coerce(out.get(name), default)
        yield tool.create_variable_message(name, value)
