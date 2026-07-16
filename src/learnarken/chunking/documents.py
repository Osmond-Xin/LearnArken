"""Chunk ⇄ LangChain Document bridge (Day 4a, D13).

LangChain components (retrievers, splitters, future chains) speak `Document`;
the project's canonical retrieval unit stays the Day 3 `Chunk` (it carries
applicability, hazard flags and graph hooks with types). This bridge is the
single conversion point: metadata round-trips the full Chunk losslessly.
"""

from __future__ import annotations

from langchain_core.documents import Document

from learnarken.chunking.base import Chunk


def to_document(chunk: Chunk) -> Document:
    metadata = chunk.model_dump(mode="json", exclude={"text"})
    return Document(page_content=chunk.text, metadata=metadata)


def from_document(document: Document) -> Chunk:
    return Chunk.model_validate({**document.metadata, "text": document.page_content})


def to_documents(chunks: list[Chunk]) -> list[Document]:
    return [to_document(c) for c in chunks]


def from_documents(documents: list[Document]) -> list[Chunk]:
    return [from_document(d) for d in documents]
