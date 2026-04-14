from pydantic import BaseModel, Field
from typing import Literal, Any
import uuid


class CommandSignature(BaseModel):
    component: str
    command: str = ""
    method: Literal["GET", "PUT"] = "PUT"
    description: str = ""
    wait_time: float = 0.0
    feedback_status_command: str = ""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:6])
    feedback_answer: str = "true"

    @property
    def resume_id(self) -> str:
        return f"{self.component}-{self.command}-{self.id}"

    @property
    def has_feedback(self) -> bool:
        return bool(self.feedback_status_command)

    @property
    def parameters(self) -> dict[str, Any]:
        base_fields = set(CommandSignature.model_fields)
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name not in base_fields
        }

    def validate_feedback_answer(self, answer: Any) -> bool:
        return answer == self.feedback_answer

