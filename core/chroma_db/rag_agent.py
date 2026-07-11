"""Agente RAG para responder preguntas sobre documentos."""

from __future__ import annotations

from core.chroma_db.rag_config import RAGConfig
from core.chroma_db.vector_store import VectorStore
from core.chroma_db.pdf_processor import PDFProcessor
from core.chroma_db.agent_reply import AgentReply
from core.chroma_db.llm_utils import llm_is_configured, call_llm


class RAGAgent:
	"""Agente RAG para responder preguntas sobre documentos."""
	
	def __init__(self):
		self.config = RAGConfig()
		self.vector_store = VectorStore(self.config)
		self.pdf_processor = PDFProcessor(self.config)
	
	def initialize(self) -> int:
		"""Inicializa el agente indexando todos los PDFs."""
		print("\n" + "="*70)
		print("AGENTE RAG - INFORMACIÓN DE LA EMPRESA")
		print("="*70)
		
		if not llm_is_configured():
			print("\n⚠ LLM no está configurado")
			print("Define: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL")
			return 1
		
		print("\n✓ LLM configurado correctamente")
		
		# Procesar PDFs
		documents = self.pdf_processor.process_all_pdfs()
		if not documents:
			print("\n⚠ No hay documentos para procesar")
			return 1
		
		# Indexar en Chroma
		print(f"\n🗂️  Indexando {len(documents)} chunks en Chroma...")
		self.vector_store.add_documents(documents)
		print(f"✓ Indexación completada\n")
		
		return 0
	
	def answer_question(self, question: str) -> AgentReply:
		"""Responde una pregunta basada en los documentos."""
		question = question.strip()
		
		if not question:
			return AgentReply("Por favor, escribe una pregunta sobre la empresa.")
		
		if question.lower() in {"salir", "exit", "quit", "q"}:
			return AgentReply("Hasta luego.", should_exit=True)
		
		# Buscar documentos relevantes
		print("\n🔍 Buscando documentos relevantes...", end=" ")
		relevant_docs = self.vector_store.search(question)
		print("✓")
		
		if not relevant_docs:
			return AgentReply("No encontré información relevante en los documentos.")
		
		# Construir contexto
		context = "Documentos relevantes:\n\n"
		for i, doc in enumerate(relevant_docs, 1):
			context += f"[{doc['source']}]:\n{doc['text']}\n\n"
		
		# Llamar al LLM
		print("🤖 Consultando LLM...", end=" ")
		messages = [
			{
				"role": "system",
				"content": """Eres un asistente experto en información empresarial. 
Tu tarea es responder preguntas sobre la empresa basándote en los documentos proporcionados.
Sé conciso, claro y profesional. Si la información no está en los documentos, dilo explícitamente."""
			},
			{
				"role": "user",
				"content": f"{context}\n\nPregunta: {question}"
			}
		]
		
		try:
			response = call_llm(messages)
			print("✓\n")
			return AgentReply(response)
		except Exception as e:
			return AgentReply(f"Error al procesar la pregunta: {e}")
	
	def run_interactive(self):
		"""Inicia el modo interactivo."""
		print("\nModo interactivo. Escribe 'salir' para terminar.\n")
		
		while True:
			try:
				question = input("Tu pregunta> ").strip()
			except KeyboardInterrupt:
				print("\n\nHasta luego.")
				break
			except EOFError:
				print("\n\nHasta luego.")
				break
			
			if not question:
				continue
			
			reply = self.answer_question(question)
			print(f"\nAgente> {reply.text}\n")
			
			if reply.should_exit:
				break

