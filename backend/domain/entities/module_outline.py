from dataclasses import dataclass, field
from typing import List

@dataclass
class LearningModule:
    module_title: str
    objective: str
    target_competencies: List[str] = field(default_factory=list)
    key_topics: List[str] = field(default_factory=list)

@dataclass
class ModuleOutlineReport:
    target_role: str
    modules: List[LearningModule] = field(default_factory=list)