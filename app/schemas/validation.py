from pydantic import BaseModel


class ValidationIssue(BaseModel):
    issue_type: str
    severity: str
    message: str
    location: str | None = None


class RepairSuggestion(BaseModel):
    target_agent: str = "code_agent"
    message: str


class ValidationResponse(BaseModel):
    passed: bool
    issues: list[ValidationIssue]
    severity: str
    repair_suggestions: list[RepairSuggestion]
    should_retry: bool
