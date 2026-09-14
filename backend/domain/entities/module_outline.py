from dataclasses import dataclass, field


@dataclass
class LearningModule:
    module_title: str
    objective: str
    target_competencies: list[str] = field(default_factory=list)
    key_topics: list[str] = field(default_factory=list)

@dataclass
class ModuleOutlineReport:
    target_role: str
    modules: list[LearningModule] = field(default_factory=list)