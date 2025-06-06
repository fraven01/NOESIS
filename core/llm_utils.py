import logging
import uuid
from datetime import datetime

import openai
import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger("llm_debug")
logger.setLevel(logging.DEBUG)


def _timestamp() -> str:
    """Aktuelle Zeit im ISO-Format."""
    return datetime.utcnow().isoformat()


def query_llm(prompt: str, model_name: str | None = None) -> str:
    """Sende eine Anfrage an ein LLM und gib die Antwort zurück."""
    correlation_id = str(uuid.uuid4())

    if not settings.GOOGLE_API_KEY and not settings.OPENAI_API_KEY:
        logger.error(
            "[%s] [%s] Missing LLM API key in environment.",
            _timestamp(),
            correlation_id,
        )
        raise RuntimeError("Missing LLM credentials from environment.")

    if settings.GOOGLE_API_KEY:
        try:
        # Hier konfigurierst und nutzt du das SDK. 
        # Du brauchst keinen manuellen Endpoint.
            genai.configure(api_key=settings.GOOGLE_API_KEY)

            name = model_name or settings.GOOGLE_LLM_MODEL
            model = genai.GenerativeModel(name)
        
            logger.debug(
                "[%s] [%s] Request to Google Gemini model=%s",
                _timestamp(),
                correlation_id,
                name,  # Logge den Modellnamen, nicht einen alten Endpoint.
            )
        
            resp = model.generate_content(prompt)
        
            logger.debug(
                "[%s] [%s] Response 200 %s",
                _timestamp(),
                correlation_id,
                repr(resp.text)[:200],
            )
            return resp.text
        
        except Exception as exc:
            logger.error(
                "[%s] [%s] LLM service error: %s",
                _timestamp(),
                correlation_id,
                str(exc),
                exc_info=True,
            )
            raise

    endpoint = "https://api.openai.com/v1/chat/completions"
    openai_model = model_name or settings.OPENAI_LLM_MODEL
    payload = {"model": openai_model, "messages": [{"role": "user", "content": prompt}]}
    logger.debug(
        "[%s] [%s] Request to %s payload=%s",
        _timestamp(),
        correlation_id,
        endpoint,
        payload,
    )
    try:
        openai.api_key = settings.OPENAI_API_KEY
        completion = openai.ChatCompletion.create(**payload)
        logger.debug(
            "[%s] [%s] Response %s %s",
            _timestamp(),
            correlation_id,
            completion.response_ms,
            repr(completion)[:200],
        )
        return completion.choices[0].message.content
    except Exception as exc:
        status = getattr(exc, "http_status", "N/A")
        body = getattr(exc, "http_body", "")
        logger.error(
            "[%s] [%s] LLM service error: %s %s",
            _timestamp(),
            correlation_id,
            status,
            body,
            exc_info=True,
        )
        raise

