from dataclasses import dataclass

from  core.agent_logger import AgentLogger

@dataclass
class UserConfig:
	"""Configuración del sistema RAG."""
	archivo: str = r"Documentacion/GoodExample.cs"
	tarea: str = "find_code_smellls"
	formato: str = "markdown"
    
	def create_instruction(self,logger: AgentLogger | None = None):
		logger._logger.debug(f"Leyendo archivo: {self.archivo}")
		archivo_contenido = open(rf"{self.archivo}").read()
		logger._logger.debug(f"Archivo con contenido: {archivo_contenido}")
		return f"Segun el archivo {self.archivo} con contenido {archivo_contenido}, aplica la tarea de {self.tarea}. Dame la salida en formato {self.formato}"
        
        