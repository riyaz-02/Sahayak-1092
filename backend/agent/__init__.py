"""Bounded agent runtime for Sahayak 1092.

The public APIs, Twilio voice stream, and dashboard actions enter through this
package. The existing decision engine remains the operational brain; the agent
layer makes the observe -> decide -> act -> remember loop explicit.
"""

from backend.agent.sahayak_agent import SahayakAgent, get_sahayak_agent

__all__ = ["SahayakAgent", "get_sahayak_agent"]
