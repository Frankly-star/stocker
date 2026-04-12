"""Skill-to-Tool bridge: wraps each Skill's capabilities as independent LangChain tools.

Architecture:
  - Each skill exposes 1-N tools via its SkillAdapter.load()["tools"]
  - This module provides get_all_skill_tools() to collect ALL skill tools in one call
  - Supervisor / Intelligence Team can bind any subset of these tools
  - Skills are hot-pluggable: add/remove a skill adapter = add/remove its tools

Usage:
    from stocker.skills.skill_tools import get_all_skill_tools, get_skill_tools_by_name

    # Get all tools from all registered skills
    all_tools = get_all_skill_tools()

    # Get tools from a specific skill
    news_tools = get_skill_tools_by_name("finance-news")

    # Bind to LLM
    llm_with_tools = llm.bind_tools(all_tools)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def get_all_skill_tools() -> list[BaseTool]:
    """Collect all tools from all registered skills.

    Returns a flat list of LangChain tools ready to bind to any LLM or agent.
    Each tool is self-contained — it knows which skill it belongs to.
    """
    from stocker.skills.registry import SkillRegistry

    registry = SkillRegistry.get_instance()
    registry.discover_and_register()

    all_tools: list[BaseTool] = []
    for name in registry.list_names():
        try:
            adapter = registry.get(name)
            if adapter:
                tools = adapter.as_tools()
                logger.info("Loaded %d tools from skill '%s': %s",
                           len(tools), name, [t.name for t in tools])
                all_tools.extend(tools)
        except Exception as e:
            logger.warning("Failed to load tools from skill '%s': %s", name, e)

    return all_tools


def get_skill_tools_by_name(skill_name: str) -> list[BaseTool]:
    """Get tools from a specific skill by name.

    Returns empty list if skill not found or load fails.
    """
    from stocker.skills.registry import SkillRegistry

    registry = SkillRegistry.get_instance()
    registry.discover_and_register()

    adapter = registry.get(skill_name)
    if not adapter:
        logger.warning("Skill '%s' not found in registry", skill_name)
        return []

    try:
        return adapter.as_tools()
    except Exception as e:
        logger.warning("Failed to load tools from skill '%s': %s", skill_name, e)
        return []


def get_skill_tools_map() -> dict[str, list[BaseTool]]:
    """Get all skills' tools as a {skill_name: [tools]} mapping.

    Useful for selective binding — you pick which skills to wire into each agent.
    """
    from stocker.skills.registry import SkillRegistry

    registry = SkillRegistry.get_instance()
    registry.discover_and_register()

    result: dict[str, list[BaseTool]] = {}
    for name in registry.list_names():
        try:
            adapter = registry.get(name)
            if adapter:
                result[name] = adapter.as_tools()
        except Exception as e:
            logger.warning("Failed to load tools from skill '%s': %s", name, e)
            result[name] = []

    return result
