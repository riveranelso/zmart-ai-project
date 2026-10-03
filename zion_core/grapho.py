"""GRAPHO: deterministic writer for approved BIBLIA promotion decisions."""
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class GraphoResult:
    action: str
    destination_ref: str | None
    changed: bool
    content: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _section_header(business_id: str) -> str:
    return f"## {business_id}"

def _rule_line(rule: str) -> str:
    return f"- {rule.strip()}"

def grapho_render(existing_text: str, decision: Any) -> GraphoResult:
    """Render a deterministic BIBLIA mutation. Does not perform external I/O."""
    if decision.action not in {"ADD", "UPDATE"}:
        return GraphoResult(decision.action, decision.destination_ref, False, existing_text,
                            "PROMOTION_ACTION_NOT_WRITABLE")
    rules=tuple(x.strip() for x in decision.proposed_rules if isinstance(x,str) and x.strip())
    if not rules:
        return GraphoResult(decision.action, decision.destination_ref, False, existing_text,
                            "NO_RULES_TO_WRITE")
    text=existing_text.rstrip()
    header=_section_header(decision.business_id)
    if decision.action=="ADD":
        block="\n".join(_rule_line(x) for x in rules)
        if header in text:
            content=text+"\n"+block+"\n"
        else:
            content=text+"\n\n"+header+"\n"+block+"\n"
        return GraphoResult("ADD",decision.destination_ref,content!=existing_text,content,"RULES_APPENDED")
    candidates=tuple(x.strip() for x in decision.matched_rules if isinstance(x,str) and x.strip())
    if not candidates:
        return GraphoResult("UPDATE",decision.destination_ref,False,existing_text,
                            "UPDATE_CANDIDATE_REQUIRED")
    content=text
    replaced=0
    for old,new in zip(candidates,rules):
        old_line=_rule_line(old)
        new_line=_rule_line(new)
        if old_line in content:
            content=content.replace(old_line,new_line,1)
            replaced+=1
    if replaced==0:
        return GraphoResult("UPDATE",decision.destination_ref,False,existing_text,
                            "UPDATE_CANDIDATE_NOT_FOUND")
    return GraphoResult("UPDATE",decision.destination_ref,True,content+"\n","RULES_UPDATED")

def grapho_write(path: Path, decision: Any) -> GraphoResult:
    """Persist a rendered BIBLIA mutation to an explicitly supplied local path."""
    existing=path.read_text(encoding="utf-8")
    result=grapho_render(existing,decision)
    if result.changed:
        path.write_text(result.content,encoding="utf-8")
    return result
