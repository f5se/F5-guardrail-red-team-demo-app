"""Skill registry with auto-discovery.

On import, all ``*.py`` modules under the ``skills/`` package (except private
modules and ``base``/``utils``) are scanned.  Any concrete
:class:`~skills.base.AbstractSkill` subclass found is instantiated and
registered by its ``name`` attribute.
"""

import importlib
import pkgutil
from typing import Any, Dict, List

from .base import AbstractSkill

_SKIP_MODULES = {"base", "utils"}

_registry: Dict[str, AbstractSkill] = {}


def _auto_discover() -> None:
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name in _SKIP_MODULES:
            continue
        mod = importlib.import_module(f".{info.name}", __package__)
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if (
                isinstance(cls, type)
                and issubclass(cls, AbstractSkill)
                and cls is not AbstractSkill
            ):
                instance = cls()
                _registry[instance.name] = instance


_auto_discover()


def get_all_tool_definitions() -> List[dict]:
    """Return Claude-compatible tool definitions for every registered skill."""
    return [skill.to_tool_definition() for skill in _registry.values()]


def dispatch_tool(
    name: str, arguments: Dict[str, Any], settings: Dict[str, Any]
) -> dict:
    """Execute a registered skill by name; return error dict for unknowns."""
    skill = _registry.get(name)
    if not skill:
        return {"ok": False, "error": f"unknown tool: {name}"}
    return skill.execute(arguments, settings)
