"""Skill adapter base: progressive disclosure + dynamic tool registration.

Follows LangChain official Skills architecture pattern:
- Agents start with lightweight skill manifests (name + description)
- load_skill @tool loads full prompt + tools on demand
- Loaded tools dynamically register to the current agent
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """Lightweight descriptor for progressive disclosure."""
    name: str
    description: str
    sub_capabilities: list[str] = Field(default_factory=list)
    version: str = "0.0.0"


class SkillAdapter(ABC):
    """Abstract base for all Skill adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description for the manifest."""

    @abstractmethod
    def get_manifest(self) -> SkillManifest:
        """Return a lightweight manifest (no heavy loading)."""

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Load the full skill: return {prompt: str, tools: list[BaseTool]}."""

    def as_tools(self) -> list[BaseTool]:
        """Shortcut: load and return just the tools."""
        return self.load().get("tools", [])


def create_load_skill_tool(registry: Any) -> BaseTool:
    """Create the load_skill @tool that agents use for progressive disclosure.

    Args:
        registry: SkillRegistry instance

    Returns:
        A LangChain tool that loads a skill by name and returns its prompt + tool list.
    """

    @tool
    def load_skill(skill_name: str) -> str:
        """Load a skill by name. Returns the skill's detailed prompt and available tools.

        Use this when you need specialized capabilities (e.g., stock analysis, news fetching).
        Available skills can be seen in the system prompt.
        """
        sk = registry.get(skill_name)
        if not sk:
            available = [m.name for m in registry.list_manifests()]
            return f"Skill '{skill_name}' not found. Available: {available}"

        loaded = sk.load()
        prompt = loaded.get("prompt", "")
        tool_names = [t.name for t in loaded.get("tools", [])]
        return f"Skill '{skill_name}' loaded.\n\nPrompt:\n{prompt}\n\nTools: {tool_names}"

    return load_skill
