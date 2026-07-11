"""Clase para respuestas del agente."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentReply:
	text: str
	should_exit: bool = False

# Made with Bob
