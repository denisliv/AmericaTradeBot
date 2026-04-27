"""FAISS-backed knowledge base for the AI manager RAG layer.

Implementation detail: we use the default `IndexFlatL2` (via
`DistanceStrategy.EUCLIDEAN_DISTANCE`) together with `normalize_L2=True`.
With unit-norm vectors, FAISS returns squared L2 distance `d² = 2·(1 − cosθ)`,
so cosine similarity is recovered as `cosθ = 1 − d²/2`. We threshold that
cosine similarity directly instead of relying on
`similarity_search_with_relevance_scores` (whose `_cosine_relevance_score_fn`
is a known footgun in combination with langchain-community's FAISS
internals). This path is canonical for langchain and avoids the
"Normalizing L2 is not applicable for metric type ..." warning.
"""

import hashlib
import logging
from pathlib import Path
from typing import Iterable

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

INDEX_FORMAT_VERSION = "v4-l2-normalized"

# Dialogue scripts and the top-level goal live in runtime prompts, so we keep
# them out of the vector index to avoid polluting retrieval.
DEFAULT_EXCLUDED_SECTIONS: set[str] = {
    "## Назначение документа",
    "## Главная цель менеджера",
    "## Сценарий диалога",
}


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        knowledge_file_path: str,
        index_path: str,
        embeddings_api_key: str,
        embeddings_base_url: str,
        embeddings_model_name: str,
        score_threshold: float,
    ) -> None:
        self.knowledge_file_path = Path(knowledge_file_path)
        self.index_path = Path(index_path)
        # Threshold is applied directly to cosine similarity (IP of unit-norm
        # vectors). Typical relevant matches from OpenAI `text-embedding-3-small`
        # land in the 0.3–0.7 range.
        self.score_threshold = score_threshold
        self.embeddings = OpenAIEmbeddings(
            api_key=embeddings_api_key,
            base_url=embeddings_base_url,
            model=embeddings_model_name,
        )
        self.vector_store: FAISS | None = None

    def ensure_index(self) -> None:
        """Builds/reuses the vector index, re-building on content or format changes."""
        self.index_path.mkdir(parents=True, exist_ok=True)
        marker = self.index_path / "knowledge.sha256"
        format_marker = self.index_path / "index.format"
        current_hash = self._file_sha256(self.knowledge_file_path)

        stored_hash = (
            marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        )
        stored_format = (
            format_marker.read_text(encoding="utf-8").strip()
            if format_marker.exists()
            else ""
        )
        should_rebuild = (
            stored_hash != current_hash
            or stored_format != INDEX_FORMAT_VERSION
            or not (self.index_path / "index.faiss").exists()
        )

        if should_rebuild:
            logger.info(
                "Building AI manager FAISS (L2 + normalize_L2) index from %s",
                self.knowledge_file_path,
            )
            docs = self._prepare_documents()
            self.vector_store = FAISS.from_documents(
                docs,
                self.embeddings,
                distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
                normalize_L2=True,
            )
            self.vector_store.save_local(str(self.index_path))
            marker.write_text(current_hash, encoding="utf-8")
            format_marker.write_text(INDEX_FORMAT_VERSION, encoding="utf-8")
            return

        logger.info("Loading AI manager FAISS index from %s", self.index_path)
        self.vector_store = FAISS.load_local(
            str(self.index_path),
            self.embeddings,
            allow_dangerous_deserialization=True,
            distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
            normalize_L2=True,
        )

    def retrieve(self, query: str, *, k: int) -> list[dict[str, str]]:
        """Return chunks whose cosine similarity to the query is above threshold."""
        if not self.vector_store:
            self.ensure_index()
        assert self.vector_store is not None

        # FAISS IndexFlatL2 returns squared L2 distance. With unit-norm
        # vectors, `d² = 2·(1 − cosθ)`, so cosine similarity is:
        #   cosθ = 1 − d²/2  ∈ [-1, 1]   (higher = more relevant)
        rows = self.vector_store.similarity_search_with_score(query, k=max(k, 4))
        scored: list[tuple[float, Document]] = [
            (1.0 - float(raw_distance) / 2.0, doc) for doc, raw_distance in rows
        ]
        context: list[dict[str, str]] = []
        for similarity, doc in scored:
            if similarity < self.score_threshold:
                continue
            context.append(
                {
                    "content": doc.page_content,
                    "section": str(doc.metadata.get("section", "")),
                    "source": str(doc.metadata.get("source", "")),
                    "score": f"{similarity:.4f}",
                }
            )
            if len(context) >= k:
                break

        if not context:
            logger.debug(
                "RAG miss for query=%r (threshold=%.2f, scanned=%d, top_cos_sim=%s).",
                query,
                self.score_threshold,
                len(rows),
                [round(s, 3) for s, _ in scored[:4]],
            )
        return context

    def _prepare_documents(self) -> list[Document]:
        raw_text = self.knowledge_file_path.read_text(encoding="utf-8")
        sections = list(self._split_markdown_sections(raw_text))

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=900,
            chunk_overlap=120,
            separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
        )

        documents: list[Document] = []
        for heading, body in sections:
            if heading in DEFAULT_EXCLUDED_SECTIONS:
                continue
            text = f"{heading}\n{body}".strip()
            if not text:
                continue
            chunks = splitter.split_text(text)
            for idx, chunk in enumerate(chunks):
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": str(self.knowledge_file_path),
                            "section": heading,
                            "chunk_id": idx,
                        },
                    )
                )
        logger.info(
            "Prepared %d chunks from %d knowledge sections for FAISS index.",
            len(documents),
            len(sections),
        )
        return documents

    @staticmethod
    def _split_markdown_sections(text: str) -> Iterable[tuple[str, str]]:
        lines = text.splitlines()
        current_heading = "ROOT"
        current_body: list[str] = []
        for line in lines:
            if line.startswith("## "):
                if current_body:
                    yield current_heading, "\n".join(current_body).strip()
                current_heading = line.strip()
                current_body = []
                continue
            current_body.append(line)
        if current_body:
            yield current_heading, "\n".join(current_body).strip()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()
