"""
Backend autostart — launches external services NEXA depends on.

Currently launches Hailo-Ollama (or any HTTP LLM backend) before the LLM
warmup. Without this, NEXA boots and assumes the LLM HTTP server is already
running. With this, NEXA can bring it up itself when the user starts NEXA.
"""
from .service import BackendAutostartService, BackendAutostartResult

__all__ = ["BackendAutostartService", "BackendAutostartResult"]
