"""GRAPHO: deterministic writer for approved BIBLIA promotion decisions."""
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .persistence import LocalOperationLock

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

def _section_bounds(text: str, business_id: str) -> tuple[int, int] | None:
    header=_section_header(business_id)
    offset=0
    start=None
    for line in text.splitlines(keepends=True):
        body=line.rstrip("\r\n")
        if start is None:
            if body==header:
                start=offset+len(line)
        elif body.startswith("## "):
            return start,offset
        offset+=len(line)
    return (start,len(text)) if start is not None else None

def grapho_render(existing_text: str, decision: Any) -> GraphoResult:
    """Render a deterministic BIBLIA mutation. Does not perform external I/O."""
    if decision.action not in {"ADD", "UPDATE", "SUPERSEDE"}:
        return GraphoResult(decision.action, decision.destination_ref, False, existing_text,
                            "PROMOTION_ACTION_NOT_WRITABLE")
    business_id=getattr(decision,"business_id",None)
    if (not isinstance(business_id,str) or not business_id.strip()
            or business_id!=business_id.strip()
            or "\n" in business_id or "\r" in business_id):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "INVALID_BUSINESS_ID")
    proposed=getattr(decision,"proposed_rules",())
    matched=getattr(decision,"matched_rules",())
    if not isinstance(proposed,tuple) or any(
        not isinstance(x,str) or not x.strip() for x in proposed
    ):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "INVALID_PROPOSED_RULES")
    if not isinstance(matched,tuple) or any(
        not isinstance(x,str) or not x.strip() for x in matched
    ):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "INVALID_MATCHED_RULES")
    raw_rules=proposed
    raw_candidates=matched
    if any("\n" in value or "\r" in value for value in raw_rules+raw_candidates):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "MULTILINE_RULE_REJECTED")
    rules=tuple(x.strip() for x in raw_rules)
    if not rules:
        return GraphoResult(decision.action, decision.destination_ref, False, existing_text,
                            "NO_RULES_TO_WRITE")
    if len({_rule_line(rule) for rule in rules}) != len(rules):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "DUPLICATE_PROPOSED_RULE")
    text=existing_text.rstrip() if decision.action=="ADD" else existing_text
    header=_section_header(decision.business_id)
    if decision.action=="ADD":
        bounds=_section_bounds(text,decision.business_id)
        if bounds is not None:
            start,insert_at=bounds
            section=text[start:insert_at]
            section_lines=tuple(
                line.rstrip("\r\n") for line in section.splitlines(keepends=True)
            )
            missing=tuple(rule for rule in rules if _rule_line(rule) not in section_lines)
            if not missing:
                return GraphoResult("ADD",decision.destination_ref,False,existing_text,
                                    "RULES_ALREADY_PRESENT")
            block="\n".join(_rule_line(x) for x in missing)
            prefix=text[:insert_at].rstrip()
            suffix=text[insert_at:]
            content=prefix+"\n"+block+"\n"+suffix.lstrip("\n")
            if suffix and not content.endswith("\n"):
                content+="\n"
        else:
            block="\n".join(_rule_line(x) for x in rules)
            content=text+"\n\n"+header+"\n"+block+"\n"
        return GraphoResult("ADD",decision.destination_ref,content!=existing_text,content,"RULES_APPENDED")
    candidates=tuple(x.strip() for x in raw_candidates)
    if not candidates:
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "SUPERSESSION_CANDIDATE_REQUIRED" if decision.action=="SUPERSEDE" else "UPDATE_CANDIDATE_REQUIRED")
    if len(candidates) != len(rules):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "SUPERSESSION_RULE_COUNT_MISMATCH" if decision.action=="SUPERSEDE" else "UPDATE_RULE_COUNT_MISMATCH")
    bounds=_section_bounds(text,decision.business_id)
    if bounds is None:
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "BUSINESS_SECTION_NOT_FOUND")
    section_start,section_end=bounds
    prefix=text[:section_start]
    section=text[section_start:section_end]
    original_section=section
    suffix=text[section_end:]
    candidate_lines=tuple(_rule_line(old) for old in candidates)
    section_lines=section.splitlines(keepends=True)
    line_bodies=tuple(line.rstrip("\r\n") for line in section_lines)
    if not all(line in line_bodies for line in candidate_lines):
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "SUPERSESSION_CANDIDATE_NOT_FOUND" if decision.action=="SUPERSEDE" else "UPDATE_CANDIDATE_NOT_FOUND")
    rendered_lines=list(section_lines)
    used_indexes=set()
    for old_line,new_rule in zip(candidate_lines,rules):
        match_index=next(
            (idx for idx,line in enumerate(rendered_lines)
             if idx not in used_indexes and line.rstrip("\r\n")==old_line),
            None,
        )
        if match_index is None:
            return GraphoResult(
                decision.action,decision.destination_ref,False,existing_text,
                "SUPERSESSION_CANDIDATE_NOT_FOUND"
                if decision.action=="SUPERSEDE" else "UPDATE_CANDIDATE_NOT_FOUND",
            )
        current=rendered_lines[match_index]
        ending="\r\n" if current.endswith("\r\n") else ("\n" if current.endswith("\n") else "")
        rendered_lines[match_index]=_rule_line(new_rule)+ending
        used_indexes.add(match_index)
    section="".join(rendered_lines)
    if section==original_section:
        return GraphoResult(decision.action,decision.destination_ref,False,existing_text,
                            "RULES_ALREADY_PRESENT")
    content=prefix+section+suffix
    return GraphoResult(decision.action,decision.destination_ref,True,content,
                        "RULES_SUPERSEDED" if decision.action=="SUPERSEDE" else "RULES_UPDATED")

def grapho_write(path: Path, decision: Any, cronicas_sink: Any = None, *, origin_angel_id: str | None = None, correlation_id: str | None = None) -> GraphoResult:
    """Persist one local BIBLIA file mutation without lost concurrent updates."""
    target=Path(path)
    lock=LocalOperationLock(target.parent/".zion-biblia-locks")
    identity=str(target.resolve())
    with lock.hold("BIBLIA","GRAPHO_WRITE",identity):
        existing=target.read_text(encoding="utf-8")
        result=grapho_render(existing,decision)
        if result.changed:
            temp=target.with_suffix(target.suffix+".grapho.tmp")
            with temp.open("w",encoding="utf-8") as handle:
                handle.write(result.content)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(target)
            try:
                dir_fd=os.open(target.parent,os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # The atomic replacement is already logically committed.
                # Do not report false failure and invite duplicate mutation.
                pass
        if cronicas_sink is not None:
            from .cronicas import cronicas_emit_grapho
            cronicas_emit_grapho(decision,result,cronicas_sink,origin_angel_id=origin_angel_id,correlation_id=correlation_id)
        return result


def grapho_reconcile_committed_mutation(path: Path, decision: Any, cronicas_sink: Any) -> GraphoResult:
    """Record missing mutation evidence only after BIBLIA proves the intended rules are present.

    This never mutates BIBLIA and never replays ANGEL work or owner corrections.
    """
    if cronicas_sink is None:
        raise ValueError("CRONICAS_SINK_REQUIRED")
    if getattr(decision,"action",None) not in {"ADD","UPDATE","SUPERSEDE"}:
        return GraphoResult(
            getattr(decision,"action","UNKNOWN"),getattr(decision,"destination_ref",None),
            False,Path(path).read_text(encoding="utf-8"),
            "RECONCILIATION_ACTION_NOT_WRITABLE",
        )
    business_id=getattr(decision,"business_id",None)
    if (not isinstance(business_id,str) or not business_id.strip()
            or business_id!=business_id.strip() or "\n" in business_id or "\r" in business_id):
        return GraphoResult(
            decision.action,getattr(decision,"destination_ref",None),False,
            Path(path).read_text(encoding="utf-8"),"RECONCILIATION_INVALID_BUSINESS_ID",
        )
    proposed=getattr(decision,"proposed_rules",())
    if not isinstance(proposed,tuple) or any(
        not isinstance(rule,str) or not rule.strip() or "\n" in rule or "\r" in rule
        for rule in proposed
    ) or len({_rule_line(rule) for rule in proposed}) != len(proposed):
        return GraphoResult(
            decision.action,getattr(decision,"destination_ref",None),False,
            Path(path).read_text(encoding="utf-8"),"RECONCILIATION_INVALID_RULES",
        )
    target=Path(path)
    destination_ref=getattr(decision,"destination_ref",None)
    if (
        not isinstance(destination_ref,str)
        or not destination_ref.strip()
        or destination_ref != destination_ref.strip()
        or destination_ref != target.name
    ):
        return GraphoResult(
            decision.action,destination_ref,False,target.read_text(encoding="utf-8"),
            "RECONCILIATION_DESTINATION_MISMATCH",
        )
    lock=LocalOperationLock(target.parent/".zion-biblia-locks")
    identity=str(target.resolve())
    with lock.hold("BIBLIA","GRAPHO_WRITE",identity):
        existing=target.read_text(encoding="utf-8")
        bounds=_section_bounds(existing,decision.business_id)
        if bounds is None:
            return GraphoResult(decision.action,decision.destination_ref,False,existing,
                                "RECONCILIATION_BUSINESS_SECTION_NOT_FOUND")
        start,end=bounds
        section=existing[start:end]
        rules=tuple(x.strip() for x in decision.proposed_rules if isinstance(x,str) and x.strip())
        section_lines=tuple(
            line.rstrip("\r\n") for line in section.splitlines(keepends=True)
        )
        if not rules or not all(_rule_line(rule) in section_lines for rule in rules):
            return GraphoResult(decision.action,decision.destination_ref,False,existing,
                                "RECONCILIATION_RULES_NOT_PROVEN")
        result=GraphoResult(decision.action,decision.destination_ref,False,existing,
                            "RECONCILED_ALREADY_COMMITTED")
        from .cronicas import cronicas_emit_grapho
        cronicas_emit_grapho(decision,result,cronicas_sink)
        return result
