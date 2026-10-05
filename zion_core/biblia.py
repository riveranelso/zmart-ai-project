"""BIBLIA retrieval: load canonical knowledge for one isolated business context."""
from dataclasses import dataclass
from pathlib import Path

from .registry import sanpedro_business_ids, sanpedro_resolve


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
    "LOS_DUROS.md":"BRAND",
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


def _business_section(
    text: str,business_id: str,known_business_ids: tuple[str,...]
) -> str:
    """Return one exact registered-business section.

    The section runs from its exact registered header until the next H2
    header of any kind (or end of document): an unregistered ## header never
    leaks foreign text into the business's canonical context. The target
    header itself must be an exact registered header, so thematic H2s are
    never mistaken for tenants. Documents with no registered headers are
    returned whole (global content).
    """
    lines=text.splitlines(keepends=True)
    business_headers={f"## {item}" for item in known_business_ids}
    business_indexes=tuple(
        idx for idx,line in enumerate(lines)
        if line.rstrip("\r\n") in business_headers
    )
    if not business_indexes:
        return text
    header=f"## {business_id}"
    target_index=next(
        (idx for idx in business_indexes if lines[idx].rstrip("\r\n")==header),
        None,
    )
    if target_index is None:
        return ""
    end_index=next(
        (idx for idx in range(target_index+1,len(lines)) if lines[idx].startswith("## ")),
        len(lines),
    )
    return "".join(lines[target_index:end_index]).rstrip()+"\n"


def retrieve_biblia(
    business_id: str,
    *,
    root: Path,
    registry_path: Path | None = None,
) -> BibliaContext:
    context=sanpedro_resolve(business_id,registry_path)
    known_business_ids=sanpedro_business_ids(registry_path)
    root_resolved=root.resolve()
    if not root_resolved.is_dir():
        raise ValueError("BIBLIA_ROOT_REQUIRED")
    documents=[]
    for ref in context.context_refs:
        path=(root/ref).resolve()
        if root_resolved not in path.parents and path != root_resolved:
            raise ValueError("BIBLIA_REF_OUTSIDE_ROOT")
        if path.is_file():
            scope=_scope_for_ref(ref)
            documents.append(BibliaDocument(
                ref=ref,
                # Use the canonical identity for section extraction so a
                # legacy alias (e.g. "zerolag" -> "zero-lag-wifi") retrieves
                # the same knowledge as the canonical id.
                text=_business_section(
                    path.read_text(encoding="utf-8"),context.business_id,known_business_ids
                ),
                scope=scope,
                precedence=SCOPE_PRECEDENCE[scope],
            ))
    return BibliaContext(
        # The envelope always carries the canonical identity: a legacy alias
        # (e.g. "zerolag") must not propagate as a second working identity.
        business_id=context.business_id,
        refs=context.context_refs,
        documents=tuple(documents),
    )
