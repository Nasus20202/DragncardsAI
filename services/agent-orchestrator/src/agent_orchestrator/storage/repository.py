from agent_orchestrator.repositories.base import RepositoryBase
from agent_orchestrator.repositories.context import ContextRepositoryMixin
from agent_orchestrator.repositories.jobs import JobRepositoryMixin
from agent_orchestrator.repositories.personas import PersonaRepositoryMixin
from agent_orchestrator.repositories.players import PlayerConfigRepositoryMixin
from agent_orchestrator.repositories.questions import QuestionRepositoryMixin
from agent_orchestrator.repositories.sessions import SessionRepositoryMixin


class Repository(
    ContextRepositoryMixin,
    SessionRepositoryMixin,
    PersonaRepositoryMixin,
    PlayerConfigRepositoryMixin,
    QuestionRepositoryMixin,
    JobRepositoryMixin,
    RepositoryBase,
):
    pass
