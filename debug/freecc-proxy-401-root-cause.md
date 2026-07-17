# Root Cause Analysis — HTTP 401 Unauthorized (FreeClaudeCode Proxy)

**Date resolved:** 2025-07  
**Affected scripts:** `test1.py`, `test_tools.py`  
**Symptom:** `LLMProviderError: Error HTTP 401: {"detail":"Missing proxy authentication token"}`

---

## Root Cause

The **FreeClaudeCode (FCC) proxy** at `localhost:8082` authenticates incoming requests via:

```
Authorization: Bearer <token>
```

The code was only sending the token as `x-api-key: freecc`, which the proxy ignores entirely. Fix: add `Authorization: Bearer {api_key}` to all outbound requests in `core/llm_client.py`.

---

## Contributing Bug — urllib silently title-cases headers

`urllib.request.Request` normalises every header name to Title-Case when added via the `headers=` constructor argument:

```
x-api-key  →  X-Api-Key   ← proxy never sees the intended casing
```

Fix: subclass `urllib.request.Request` with `_CaseSensitiveRequest` (see `core/llm_client.py`) that writes directly into `self.headers` dict to bypass normalisation. Use `_make_request()` helper to build all requests.

---

## Why It Was Hard to Find — Three Red Herrings

### 1. The server log pointed to a URL problem
The proxy log showed:
```
POST /v1/messages HTTP/1.1  401 Unauthorized      ← no ?beta=true
POST /v1/messages?beta=true HTTP/1.1  200 OK       ← working calls
```
This looked like a missing `?beta=true` suffix on the URL. Spent two rounds fixing the default URL in `config.py`, `llm_utils.py`, and `.env` — none of which changed the outcome because the bare-URL request was coming from **the IDE extension**, not from the Python script.

### 2. The `.env` file is never loaded
There is no `python-dotenv` (or equivalent) call anywhere in the codebase. Editing `.env` has **zero effect at runtime**. `os.getenv()` only reads variables exported to the process environment. The hardcoded Python defaults in `from_env()` are what actually apply.

### 3. The token `freecc` looked like a placeholder
`ANTHROPIC_AUTH_TOKEN=freecc` in `~/.fcc/.env` looks like a stub value. It is in fact the **correct and intentional** proxy authentication token set by the FCC server.

---

## Diagnosis Technique That Cracked It

Monkey-patching `_opener.open` to print the exact URL and headers at the moment of the HTTP call:

```python
original_open = client._opener.open
def patched_open(req, **kw):
    print('URL:', req.full_url)
    print('Headers:', dict(req.headers))
    return original_open(req, **kw)
client._opener.open = patched_open
```

Output revealed the URL was already correct (`?beta=true` present) and shifted focus to the headers — where the missing `Authorization` was immediately visible.

---

## All Changes Made

| File | Change |
|---|---|
| `core/llm_client.py` | Add `Authorization: Bearer` header to all outbound requests |
| `core/llm_client.py` | Add `_CaseSensitiveRequest` + `_make_request()` to preserve lowercase header names |
| `core/config.py` | Default `LLM_BASE_URL` updated to include `?beta=true` |
| `core/chroma_db/llm_utils.py` | Same `?beta=true` default applied for consistency |
| `.env` | `LLM_BASE_URL` updated (cosmetic — file is not loaded at runtime) |

---

## FCC Proxy Quick Reference

| Setting | Location | Value |
|---|---|---|
| Proxy port | `~/.fcc/.env` → `PORT` | `8082` |
| Auth token | `~/.fcc/.env` → `ANTHROPIC_AUTH_TOKEN` | `freecc` |
| Auth header | HTTP | `Authorization: Bearer freecc` |
| Required URL suffix | Query param | `?beta=true` |
| Default model | `~/.fcc/.env` → `MODEL` | `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` |

---

## Key Takeaway

> **Always verify what is actually on the wire before assuming the cause.**  
> Print the exact request (URL + headers) at the moment it fires. Every layer between your code and the network (urllib, frameworks, middlewares) can silently transform what you wrote.
