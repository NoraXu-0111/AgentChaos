"""AgentChaos — reliability testing for tool-using AI agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentchaos")
except PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0+unknown"
