"""
RAGService — PDF ingestion + retrieval using LangChain.

Pipeline:
  1. Load PDF          → LangChain PyMuPDFLoader
  2. Chunk text        → LangChain RecursiveCharacterTextSplitter
  3. Embed chunks      → LangChain HuggingFaceEmbeddings (all-MiniLM-L6-v2, free + local)
  4. Store in FAISS    → LangChain FAISS vector store (persisted to disk)
  5. Retrieve          → similarity search top-K chunks for a user query
"""
import logging
import os
import shutil

from django.conf import settings

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

# Embedding model — runs locally, no API key needed
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Lazy-loaded singleton so the model is only loaded once
_embeddings = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Return a cached HuggingFaceEmbeddings instance."""
    global _embeddings
    if _embeddings is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings


def _collection_dir(conversation_id: str) -> str:
    """Each conversation gets its own sub-folder inside the vector store base."""
    base = settings.CHROMA_PERSIST_DIR
    path = os.path.join(base, f"conv_{str(conversation_id).replace('-', '_')}")
    os.makedirs(path, exist_ok=True)
    return path


class RAGService:
    def __init__(self):
        self.chunk_size    = settings.RAG_CHUNK_SIZE
        self.chunk_overlap = settings.RAG_CHUNK_OVERLAP
        self.top_k         = settings.RAG_TOP_K

    # ── Ingestion ──────────────────────────────────────────────────────────

    def ingest_document(self, document) -> int:
        """
        Load a PDF, chunk it with LangChain, embed + store in FAISS.

        Returns the number of chunks created.
        """
        file_path = document.file_path.path
        logger.info("Ingesting document: %s", document.filename)

        # 1. Load PDF with LangChain PyMuPDFLoader
        loader = PyMuPDFLoader(file_path)
        pages  = loader.load()
        logger.info("Loaded %d pages from %s", len(pages), document.filename)

        if not pages:
            raise ValueError(
                f"Could not load '{document.filename}'. "
                "Make sure it is a valid PDF file."
            )

        # Check if any page has actual text (image-only PDFs have no text layer)
        total_text = " ".join(p.page_content.strip() for p in pages)
        if not total_text.strip():
            raise ValueError(
                f"'{document.filename}' appears to be an image-based or scanned PDF "
                "with no extractable text. Please use a text-based PDF."
            )

        # 2. Chunk with LangChain RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size      = self.chunk_size,
            chunk_overlap   = self.chunk_overlap,
            length_function = len,
        )
        chunks = splitter.split_documents(pages)
        logger.info("Created %d chunks from %s", len(chunks), document.filename)

        if not chunks:
            raise ValueError(
                f"No text chunks could be created from '{document.filename}'."
            )

        # 3 + 4. Embed chunks + store in FAISS
        persist_dir      = _collection_dir(str(document.conversation_id))
        faiss_index_path = os.path.join(persist_dir, "index.faiss")

        if os.path.exists(faiss_index_path):
            # Append new chunks to the existing index
            vectorstore = FAISS.load_local(
                persist_dir,
                get_embeddings(),
                allow_dangerous_deserialization=True,
            )
            vectorstore.add_documents(chunks)
        else:
            # Create a fresh index
            vectorstore = FAISS.from_documents(chunks, get_embeddings())

        vectorstore.save_local(persist_dir)
        logger.info("Stored %d chunks in FAISS at %s", len(chunks), persist_dir)

        # Save chunk records in Django DB for reference
        from conversations.models import DocumentChunk
        chunk_objs = [
            DocumentChunk(
                document    = document,
                chunk_text  = c.page_content,
                chunk_index = i,
                embedding_id= f"doc_{document.id}_chunk_{i}",
            )
            for i, c in enumerate(chunks)
        ]
        DocumentChunk.objects.bulk_create(chunk_objs)

        return len(chunks)

    # ── Retrieval ──────────────────────────────────────────────────────────

    def retrieve(self, query: str, conversation_id: str) -> str:
        """
        Retrieve top-K relevant chunks for a user query using FAISS.

        Returns concatenated chunk text ready to inject into the LLM prompt.
        """
        persist_dir      = _collection_dir(conversation_id)
        faiss_index_path = os.path.join(persist_dir, "index.faiss")

        if not os.path.exists(faiss_index_path):
            logger.debug("No FAISS index found for conversation %s", conversation_id)
            return ""

        try:
            vectorstore = FAISS.load_local(
                persist_dir,
                get_embeddings(),
                allow_dangerous_deserialization=True,
            )
            results = vectorstore.similarity_search(query, k=self.top_k)

            if not results:
                return ""

            context = "\n\n---\n\n".join(doc.page_content for doc in results)
            logger.debug(
                "RAG retrieved %d chunks for query: %s...",
                len(results), query[:50]
            )
            return context

        except Exception as exc:
            logger.error("RAG retrieval failed for conversation %s: %s", conversation_id, exc)
            return ""

    # ── Cleanup ────────────────────────────────────────────────────────────

    def delete_collection(self, conversation_id: str) -> None:
        """Delete the FAISS index folder for a conversation when it is deleted."""
        persist_dir = _collection_dir(conversation_id)
        if os.path.exists(persist_dir):
            shutil.rmtree(persist_dir)
            logger.info("Deleted FAISS index for conversation %s", conversation_id)
