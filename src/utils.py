import dataclasses
from typing import Optional, List

@dataclasses.dataclass
class Segment:
    start: float
    end: float
    speaker: str
    text: Optional[str] = ""
    is_question: bool = False

@dataclasses.dataclass
class AwkwardMoment:
    start: float
    end: float
    severity: float  # 0.0 to 1.0
    label: str       # "Dead Air", "Interruption", "Unanswered Q"
    description: str # "Speaker A asked a question, followed by 4s silence."

