"""Punto de entrada principal para el módulo RAG."""

from __future__ import annotations

import argparse
import sys

from core.chroma_db.rag_agent import RAGAgent


def parse_args() -> argparse.Namespace:
	"""Parsea argumentos de línea de comandos."""
	parser = argparse.ArgumentParser(description="Agente RAG para consultar documentos de la empresa")
	parser.add_argument("question", nargs="*", help="Pregunta a responder")
	parser.add_argument("--chat", action="store_true", help="Modo interactivo")
	parser.add_argument("--reset", action="store_true", help="Limpia la BD vectorial")
	return parser.parse_args()


def main() -> int:
	"""Función principal."""
	args = parse_args()
	
	try:
		agent = RAGAgent()
		
		# Resetear si se solicita
		if args.reset:
			print("🗑️  Limpiando base de datos vectorial...")
			agent.vector_store.clear()
		
		# Inicializar
		if agent.initialize() != 0:
			return 1
		
		# Procesar pregunta o entrar en modo interactivo
		question = " ".join(args.question).strip()
		
		if args.chat or not question:
			agent.run_interactive()
		else:
			reply = agent.answer_question(question)
			print(f"\nAgente> {reply.text}\n")
		
		return 0
		
	except Exception as e:
		print(f"\n✗ Error: {e}")
		return 1


if __name__ == "__main__":
	sys.exit(main())

# Made with Bob
