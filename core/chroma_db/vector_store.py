"""Almacén vectorial usando Chroma."""

from __future__ import annotations

try:
	import chromadb
except ImportError:
	chromadb = None

from core.chroma_db.rag_config import RAGConfig


class VectorStore:
	"""Almacén vectorial usando Chroma."""
	
	def __init__(self, config: RAGConfig):
		if chromadb is None:
			raise ImportError("chromadb no está instalado. Instala con: pip install chromadb")
		
		self.config = config
		self.client = chromadb.PersistentClient(path=config.chroma_db_path)
		self.collection = self.client.get_or_create_collection(
			name=config.collection_name,
			metadata={"hnsw:space": "cosine"}
		)
	
	def add_documents(self, documents: list[dict[str, str]]) -> int:
		"""Agrega documentos al almacén vectorial."""
		if not documents:
			return 0
		
		# Chroma genera embeddings automáticamente
		ids = [doc["id"] for doc in documents]
		documents_text = [doc["text"] for doc in documents]
		metadatas = [{"source": doc.get("source", "unknown")} for doc in documents]
		
		self.collection.upsert(
			ids=ids,
			documents=documents_text,
			metadatas=metadatas
		)
		
		return len(documents)
	
	def search(self, query: str) -> list[dict[str, str]]:
		"""Busca documentos similares."""
		results = self.collection.query(
			query_texts=[query],
			n_results=self.config.top_k  # Usar top_k de configuración
		)
		
		documents = []
		if results["documents"] and len(results["documents"]) > 0:
			for i, doc in enumerate(results["documents"][0]):
				metadata = results["metadatas"][0][i] if results["metadatas"] else {}
				documents.append({
					"text": doc,
					"source": metadata.get("source", "unknown"),
					"distance": float(results["distances"][0][i]) if results["distances"] else 0
				})
		
		return documents
	
	def clear(self):
		"""Limpia la colección."""
		self.client.delete_collection(name=self.config.collection_name)
		self.collection = self.client.get_or_create_collection(
			name=self.config.collection_name,
			metadata={"hnsw:space": "cosine"}
		)

# Made with Bob
