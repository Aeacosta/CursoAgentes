"""Agente RAG para responder preguntas sobre documentos."""

from __future__ import annotations

from core.chroma_db.rag_config import RAGConfig
from core.chroma_db.vector_store import VectorStore
from core.chroma_db.pdf_processor import PDFProcessor
from core.chroma_db.agent_reply import AgentReply
from core.chroma_db.llm_utils import llm_is_configured, call_llm
from core.agent_logger import AgentLogger


class RAGAgent:
	"""Agente RAG para responder preguntas sobre documentos."""
	
	def __init__(self, logger: AgentLogger | None = None):
		self._log = logger or AgentLogger(name="rag_agent")
		self.config = RAGConfig()
		self.vector_store = VectorStore(self.config, logger=self._log)
		self.pdf_processor = PDFProcessor(self.config, logger=self._log)
	
	def initialize(self) -> int:
		"""Inicializa el agente indexando todos los PDFs."""
		self._log._logger.info("=" * 70)
		self._log._logger.info("AGENTE RAG - INFORMACIÓN DE LA EMPRESA")
		self._log._logger.info("=" * 70)
		
		if not llm_is_configured():
			self._log._logger.warning("LLM no está configurado. Define: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL")
			return 1
		
		self._log._logger.info("LLM configurado correctamente")
		
		# Procesar PDFs
		documents = self.pdf_processor.process_all_pdfs()
		if not documents:
			self._log._logger.warning("No hay documentos para procesar")
			return 1
		
		# Indexar en Chroma
		self._log._logger.info("Indexando %d chunks en Chroma...", len(documents))
		self.vector_store.add_documents(documents)
		self._log._logger.info("Indexación completada")
		
		return 0
	
	def answer_question(self, question: str) -> AgentReply:
		"""Responde una pregunta basada en los documentos."""
		question = question.strip()
		
		if not question:
			return AgentReply("Por favor, escribe una pregunta sobre la empresa.")
		
		if question.lower() in {"salir", "exit", "quit", "q"}:
			return AgentReply("Hasta luego.", should_exit=True)
		
		# Buscar documentos relevantes
		self._log._logger.info("Buscando documentos relevantes para: %r", question[:80])
		relevant_docs = self.vector_store.search(question)
		
		if not relevant_docs:
			return AgentReply("No encontré información relevante en los documentos.")
		
		# Construir contexto
		context = "Documentos relevantes:\n\n"
		for i, doc in enumerate(relevant_docs, 1):
			context += f"[{doc['source']}]:\n{doc['text']}\n\n"
		
		# Llamar al LLM
		self._log._logger.info("Consultando LLM...")
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
			self._log._logger.info("Respuesta LLM recibida (%d caracteres)", len(response))
			return AgentReply(response)
		except Exception as e:
			self._log._logger.error("Error al procesar la pregunta: %s", e)
			return AgentReply(f"Error al procesar la pregunta: {e}")
	
	def run_interactive(self):
		"""Inicia el modo interactivo."""
		self._log._logger.info("Modo interactivo. Escribe 'salir' para terminar.")
		
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

