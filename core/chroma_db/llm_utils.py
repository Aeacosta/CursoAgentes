"""Utilidades para interactuar con el LLM."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import urlopen
import urllib.request as urllib_request


def get_llm_config() -> dict[str, str]:
	"""Obtiene configuración del LLM."""
	return {
		"base_url": os.getenv(
			"LLM_BASE_URL",
			"http://localhost:8082/v1/messages"
		),
		"api_key": os.getenv(
			"LLM_API_KEY",
			"freecc"
		),
		"model": os.getenv(
			"LLM_MODEL",
			"nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
		),
		"api_type": os.getenv(
			"LLM_API_TYPE",
			"anthropic"
		),
	}


def llm_is_configured() -> bool:
	"""Verifica si el LLM está configurado."""
	config = get_llm_config()
	return bool(config["base_url"])


def post_json(url: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
	"""POST request con manejo de SSE streaming."""
	data = json.dumps(body).encode("utf-8")
	request_headers = {"Content-Type": "application/json"}
	if headers:
		request_headers.update(headers)
	request = urllib_request.Request(url, data=data, headers=request_headers, method="POST")
	
	with urlopen(request, timeout=60) as response:
		response_text = response.read().decode("utf-8")
		
		if not response_text or not response_text.strip():
			raise ValueError(f"Servidor devolvió respuesta vacía. Status: {response.status}")
		
		# Detectar Server-Sent Events (SSE)
		if response_text.strip().startswith("event:"):
			events = []
			current_event = None
			
			for line in response_text.strip().split("\n"):
				line = line.strip()
				if not line:
					continue
				
				if line.startswith("event:"):
					current_event = line[6:].strip()
				elif line.startswith("data:"):
					data_str = line[5:].strip()
					try:
						data_json = json.loads(data_str)
						events.append({"type": current_event, "data": data_json})
					except json.JSONDecodeError:
						pass
			
			if events:
				return {"__sse_events": events}
			else:
				raise ValueError("No se pudieron parsear eventos SSE")
		
		# JSON normal
		try:
			return json.loads(response_text)
		except json.JSONDecodeError as e:
			preview = response_text[:200] if len(response_text) > 200 else response_text
			raise ValueError(f"Servidor devolvió respuesta no-JSON: {preview}")


def call_llm(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
	"""Llama al LLM y retorna la respuesta."""
	config = get_llm_config()
	api_type = config.get("api_type", "anthropic").lower()
	
	# Extraer mensaje del sistema
	system_message = ""
	user_messages = []
	
	for msg in messages:
		if msg["role"] == "system":
			system_message = msg["content"]
		else:
			user_messages.append({"role": msg["role"], "content": msg["content"]})
	
	# Preparar body
	body = {
		"model": config["model"],
		"max_tokens": 2048,
		"messages": user_messages,
		"temperature": temperature,
	}
	if system_message:
		body["system"] = system_message
	
	headers = {"x-api-key": config["api_key"]}
	
	try:
		response = post_json(config["base_url"], body, headers=headers)
	except Exception as e:
		raise ValueError(f"Error al conectar con LLM: {e}")
	
	# Manejar SSE
	if "__sse_events" in response:
		events = response["__sse_events"]
		text_content = ""
		
		for event in events:
			if event["type"] == "content_block_delta":
				delta = event["data"].get("delta", {})
				if "text" in delta:
					text_content += delta["text"]
		
		if text_content:
			return text_content
		else:
			raise ValueError("No se encontró contenido en los eventos SSE")
	
	# JSON normal (Anthropic)
	content = response.get("content") or []
	if content and isinstance(content, list) and len(content) > 0:
		return str(content[0].get("text", ""))
	
	raise ValueError("No se pudo extraer respuesta del LLM")

# Made with Bob
