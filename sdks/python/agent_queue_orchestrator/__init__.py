"""Backward compatibility — 'agent_queue_orchestrator' is now 'flint_ai'."""
import warnings
warnings.warn(
    "The 'agent_queue_orchestrator' package has been renamed to 'flint-ai'. "
    "Please update your imports: from flint_ai import OrchestratorClient",
    DeprecationWarning,
    stacklevel=2,
)
from flint_ai import *  # noqa: F401, F403
from flint_ai import OrchestratorClient, AsyncOrchestratorClient  # explicit re-exports
