from agent_orchestrator.repositories.base import RepositoryBase
from agent_orchestrator.repositories.jobs import JobRepositoryMixin
from agent_orchestrator.repositories.sessions import SessionRepositoryMixin


class Repository(SessionRepositoryMixin, JobRepositoryMixin, RepositoryBase):
    pass
