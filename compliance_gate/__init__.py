"""compliance_gate — a compliance-gate-first pattern demo.

Public API:
    from compliance_gate import Gate, Decision, AuditLogger, load_rules
"""
from .gate import Gate, Decision, GateResult
from .audit import AuditLogger
from .rules import load_rules

__all__ = ["Gate", "Decision", "GateResult", "AuditLogger", "load_rules"]
__version__ = "0.1.0"
