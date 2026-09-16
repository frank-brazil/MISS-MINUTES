"""Built-in MISSMINUTES agents.

Each agent specialises in a domain of work and implements the shared
``Agent`` interface defined in ``app.agents.base``.  Agents are
provider-independent: any specialised behaviour (research, prediction,
critique, verification, vision) is supplied through dependency injection.
"""

from app.agents.base import Agent, AgentResult
from app.agents.coding import CodingAgent
from app.agents.critic import CriticAgent
from app.agents.prediction import PredictionAgent
from app.agents.research import ResearchAgent
from app.agents.system import SystemAgent
from app.agents.verification import VerificationAgent
from app.agents.vision import VisionAgent

__all__ = [
    "Agent",
    "AgentResult",
    "CodingAgent",
    "CriticAgent",
    "PredictionAgent",
    "ResearchAgent",
    "SystemAgent",
    "VerificationAgent",
    "VisionAgent",
]
