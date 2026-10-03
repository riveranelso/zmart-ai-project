"""BIBLIA retrieval: load canonical knowledge for one isolated business context."""
from dataclasses import dataclass
from pathlib import Path

from .registry import sanpedro_resolve


@dataclass(frozen=True)
class BibliaContext:
    business_id: str
    refs: tuple[str, ...]
    documents: tuple[tuple[str, str], ...]

    @property
    def text(self) -> str:
        return "\n\n".join(text for _, text in self.documents)


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
            documents.append((ref,path.read_text(encoding="utf-8")))
    return BibliaContext(
        business_id=business_id,
        refs=context.context_refs,
        documents=tuple(documents),
    )
