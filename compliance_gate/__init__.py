"""compliance_gate — a compliance-gate-first pattern demo.

Public API:
    from compliance_gate import Gate, Decision, AuditLogger, load_rules
    from compliance_gate import get_provider  # vendor-agnostic LLM factory
"""
from .gate import Gate, Decision, GateResult
from .audit import AuditLogger
from .rules import load_rules
from .providers import get_provider, GeminiProvider, OpenAIProvider

__all__ = [
    "Gate",
    "Decision",
    "GateResult",
    "AuditLogger",
    "load_rules",
    "get_provider",
    "GeminiProvider",
    "OpenAIProvider",
]
__version__ = "0.2.0"
