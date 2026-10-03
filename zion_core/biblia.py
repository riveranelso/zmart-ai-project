"""BIBLIA retrieval: load canonical knowledge for one isolated business context."""
from dataclasses import dataclass
from pathlib import Path

from .registry import sanpedro_resolve


SCOPE_PRECEDENCE={
    "GLOBAL":10,
    "WORKFLOW":20,
    "BRAND":30,
    "PROJECT":40,
    "CAMPAIGN":50,
}
_REF_SCOPE={
    "GLOBAL.md":"GLOBAL",
    "WORKFLOWS.md":"WORKFLOW",
    "BRANDS.md":"BRAND",
    "PROJECTS.md":"PROJECT",
    "ACTIVE_CONTEXT.md":"CAMPAIGN",
}


@dataclass(frozen=True)
class BibliaDocument:
    ref: str
    text: str
    scope: str
    precedence: int


@dataclass(frozen=True)
class BibliaContext:
    business_id: str
    refs: tuple[str, ...]
    documents: tuple[BibliaDocument, ...]

    @property
    def text(self) -> str:
        """Canonical knowledge from broadest to most specific; later rules prevail."""
        ordered=sorted(self.documents,key=lambda doc:doc.precedence)
        return "\n\n".join(doc.text for doc in ordered)

    @property
    def precedence(self) -> tuple[str, ...]:
        return tuple(doc.scope for doc in sorted(self.documents,key=lambda doc:doc.precedence))


def _scope_for_ref(ref: str)->str:
    return _REF_SCOPE.get(Path(ref).name,"GLOBAL")


def _business_section(text: str, business_id: str) -> str:
    """Return one exact business section; fail closed when a segmented document lacks it."""
    header=f"## {business_id}"
    lines=text.splitlines(keepends=True)
    heading_indexes=tuple(
        idx for idx,line in enumerate(lines)
        if line.rstrip("\r\n").startswith("## ")
    )
    if not heading_indexes:
        return text
    target_index=next(
        (idx for idx in heading_indexes if lines[idx].rstrip("\r\n")==header),
        None,
    )
    if target_index is None:
        return ""
    end_index=next((idx for idx in heading_indexes if idx>target_index),len(lines))
    return "".join(lines[target_index:end_index]).rstrip()+"\n"


def retrieve_biblia(
    business_id: str,
    *,
    root: Path,
    registry_path: Path | None = None,
) -> BibliaContext:
    context=sanpedro_resolve(business_id,registry_path)
    documents=[]
    for ref in context.context_refs:
        path=(root/ref).resolve()
        root_resolved=root.resolve()
        if root_resolved not in path.parents and path != root_resolved:
            raise ValueError("BIBLIA_REF_OUTSIDE_ROOT")
        if path.is_file():
            scope=_scope_for_ref(ref)
            documents.append(BibliaDocument(
                ref=ref,
                text=_business_section(path.read_text(encoding="utf-8"),business_id),
                scope=scope,
                precedence=SCOPE_PRECEDENCE[scope],
            ))
    return BibliaContext(
        business_id=business_id,
        refs=context.context_refs,
        documents=tuple(documents),
    )
