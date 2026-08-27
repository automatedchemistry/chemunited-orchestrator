class WorkflowError(Exception):
    """Base exception for workflow model/controller errors."""


class WorkflowRuleViolation(WorkflowError):
    """Raised when a workflow mutation violates editor or domain rules."""
