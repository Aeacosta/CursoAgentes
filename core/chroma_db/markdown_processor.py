"""Procesa archivos Markdown y extrae texto por sección."""

from __future__ import annotations

import re
from pathlib import Path

from core.chroma_db.rag_config import RAGConfig
from core.agent_logger import AgentLogger


class MarkdownProcessor:
	"""Procesa archivos .md y retorna chunks de texto conscientes de secciones.

	La estrategia de chunking es:
	1. Dividir el documento por encabezados (## / ###) para mantener contexto semántico.
	2. Si un bloque de sección supera ``chunk_size`` caracteres, subdivide con
	   solapamiento igual al del PDFProcessor.
	3. Los bloques vacíos (solo espacios/saltos) se descartan.
	"""

	_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)

	def __init__(self, config: RAGConfig, logger: AgentLogger | None = None):
		self.config = config
		self.md_folder = Path(config.pdf_folder)
		self._log = logger or AgentLogger(name="markdown_processor")

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def process_all_markdown(self) -> list[dict[str, str]]:
		"""Procesa todos los .md en la carpeta configurada y retorna chunks."""
		documents: list[dict[str, str]] = []

		if not self.md_folder.exists():
			self._log._logger.warning("Carpeta %s no existe", self.config.pdf_folder)
			return documents

		md_files = list(self.md_folder.glob("*.md"))
		if not md_files:
			self._log._logger.debug("No se encontraron .md en %s", self.md_folder)
			return documents

		self._log._logger.debug("Procesando %d archivo(s) Markdown...", len(md_files))

		for md_path in md_files:
			try:
				chunks = self._extract_chunks(md_path)
				documents.extend(chunks)
				self._log._logger.debug("  %s -> %d chunks", md_path.name, len(chunks))
			except Exception as e:
				self._log._logger.error("Error procesando %s: %s", md_path.name, e)

		return documents

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _extract_chunks(self, md_path: Path) -> list[dict[str, str]]:
		"""Divide un archivo Markdown en chunks semánticamente coherentes."""
		text = md_path.read_text(encoding="utf-8")

		# Split on section headings, keeping the heading with its body.
		sections = self._HEADING_RE.split(text)
		headings = [""] + self._HEADING_RE.findall(text)  # leading non-heading block gets ""

		chunks: list[dict[str, str]] = []
		chunk_size = self.config.chunk_size
		overlap = self.config.chunk_overlap

		for heading, body in zip(headings, sections):
			block = (heading + body).strip()
			if not block:
				continue

			if len(block) <= chunk_size:
				chunk_id = f"{md_path.name}_sec_{len(chunks)}"
				chunks.append({"id": chunk_id, "text": block, "source": md_path.name})
			else:
				# Sub-chunk oversized section with sliding window
				for i in range(0, len(block), chunk_size - overlap):
					sub = block[i : i + chunk_size].strip()
					if sub:
						chunk_id = f"{md_path.name}_sec_{len(chunks)}"
						chunks.append({"id": chunk_id, "text": sub, "source": md_path.name})

		return chunks
