from __future__ import annotations

import logging
import uuid
from datetime import datetime

import openai
import google.generativeai as genai
from django.conf import settings

try:
    from langfuse import Langfuse, TraceContext
except Exception:  # pragma: no cover - Langfuse optional
    Langfuse = None  # type: ignore[assignment]
    TraceContext = None  # type: ignore[assignment]

try:
    from google.api_core import exceptions as g_exceptions
except ModuleNotFoundError:
    g_exceptions = None

logger = logging.getLogger("llm_debugger")

lf: Langfuse | None = None
if Langfuse is not None:
    try:
        lf = Langfuse(
            public_key=getattr(settings, "LANGFUSE_PUBLIC_KEY", ""),
            secret_key=getattr(settings, "LANGFUSE_SECRET_KEY", ""),
            host=getattr(settings, "LANGFUSE_HOST", ""),
        )
    except Exception:  # pragma: no cover - Fehler bei Initialisierung
        lf = None


def _timestamp() -> str:
    """Aktuelle Zeit im ISO-Format."""
    return datetime.utcnow().isoformat()


def query_llm(
    prompt_object: "Prompt",
    context_data: dict,
    model_type: str = "default",
    temperature: float = 0.5,
    project_prompt: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    """Sende eine Anfrage an ein LLM und gib die Antwort zurück.

    :param max_output_tokens: Optionale Begrenzung der Antwortlänge.
    """
    from .models import LLMConfig, LLMRole

    correlation_id = str(uuid.uuid4())
    model_name = LLMConfig.get_default(model_type)
    trace_id = lf.create_trace_id() if lf else None
    span = None
    if lf and trace_id:
        try:
            span = lf.start_span(
                name="query_llm",
                trace_context=TraceContext(id=trace_id),
                metadata={
                    "correlation_id": correlation_id,
                    "model_type": model_type,
                },
            )
        except Exception as lf_exc:  # pragma: no cover - Logging
            logger.warning(
                "[%s] [%s] Langfuse-Fehler: %s",
                _timestamp(),
                correlation_id,
                str(lf_exc),
            )

    def _end_span() -> None:
        """Beende den Langfuse-Span und flush ihn."""
        if span:
            try:
                span.end()
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )

    limit = max_output_tokens or getattr(settings, "LLM_MAX_OUTPUT_TOKENS", 2048)
    logger.debug(
        "[%s] [%s] Verwende max_output_tokens=%s",
        _timestamp(),
        correlation_id,
        limit,
    )

    final_role_prompt = ""

    if prompt_object.use_system_role:
        if prompt_object.role:
            final_role_prompt = prompt_object.role.role_prompt
        else:
            default_role = LLMRole.objects.filter(is_default=True).first()
            if default_role:
                final_role_prompt = default_role.role_prompt

    # Formatierung nur, wenn Kontext vorhanden ist.
    # Ohne Kontext bleibt der Prompt unverändert.
    if context_data:
        try:
            task_prompt = prompt_object.text.format(**context_data)
        except KeyError as exc:  # Platzhalter nicht vorhanden
            logger.error(
                "[%s] [%s] Fehlender Platzhalter %s in Prompt %s",
                _timestamp(),
                correlation_id,
                exc.args[0],
                prompt_object.name,
            )
            _end_span()
            raise KeyError(
                f"Missing placeholder '{exc.args[0]}' in prompt '{prompt_object.name}'"
            ) from exc
    else:
        task_prompt = prompt_object.text

    if project_prompt and getattr(prompt_object, "use_project_context", True):
        task_prompt = project_prompt.strip() + "\n\n" + task_prompt

    prompt = (
        f"{final_role_prompt}\n\n---\n\n{task_prompt}" if final_role_prompt else task_prompt
    )

    final_prompt_to_llm = prompt
    logger.debug(
        f"--- PROMPT SENT TO MODEL {model_name} ---\n{final_prompt_to_llm}\n--------------------"
    )

    if not settings.GOOGLE_API_KEY and not settings.OPENAI_API_KEY:
        logger.error(
            "[%s] [%s] Missing LLM API key in environment.",
            _timestamp(),
            correlation_id,
        )
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise RuntimeError("Missing LLM credentials from environment.")

    if settings.GOOGLE_API_KEY:
        try:
            # Hier konfigurierst und nutzt du das SDK.
            # Du brauchst keinen manuellen Endpoint.
            genai.configure(api_key=settings.GOOGLE_API_KEY)

            name = model_name
            model = genai.GenerativeModel(name)

            logger.debug(
                "[%s] [%s] Request to Google Gemini model=%s",
                _timestamp(),
                correlation_id,
                name,
            )

            retries = 1
            llm_response = ""
            for attempt in range(retries + 1):
                resp = model.generate_content(
                    prompt,
                    generation_config={
                        "max_output_tokens": limit,
                        "response_mime_type": "text/plain",
                    },
                )

                finish_reason = None
                block_reason = None
                parts_summary: list[str] = []

                if getattr(resp, "candidates", []):
                    finish_reason = getattr(
                        resp.candidates[0], "finish_reason", None
                    )
                    content = getattr(resp.candidates[0], "content", None)
                    parts = getattr(content, "parts", []) if content else []
                    for part in parts:
                        text_part = getattr(part, "text", "")
                        parts_summary.append(
                            text_part[:30] if text_part else type(part).__name__
                        )

                if getattr(resp, "prompt_feedback", None):
                    block_reason = getattr(
                        resp.prompt_feedback, "block_reason", None
                    )

                usage_meta = getattr(resp, "usage_metadata", None) or {}
                usage = {
                    "prompt_tokens": getattr(
                        usage_meta, "prompt_token_count", None
                    ),
                    "completion_tokens": getattr(
                        usage_meta, "candidates_token_count", None
                    ),
                    "total_tokens": getattr(
                        usage_meta, "total_token_count", None
                    ),
                }

                logger.debug(
                    "[%s] [%s] LLM-Metadaten: finish_reason=%s block_reason=%s parts=%s",
                    _timestamp(),
                    correlation_id,
                    finish_reason,
                    block_reason,
                    parts_summary,
                )

                try:
                    llm_response = resp.text
                    if not llm_response:
                        raise ValueError("empty text")
                except Exception:
                    texts: list[str] = []
                    for cand in getattr(resp, "candidates", []) or []:
                        content = getattr(cand, "content", None)
                        parts = getattr(content, "parts", []) if content else []
                        for part in parts:
                            text_part = getattr(part, "text", "")
                            if text_part:
                                texts.append(text_part)
                    llm_response = "\n".join(texts).strip()

                if llm_response:
                    break

                if attempt < retries:
                    logger.warning(
                        "[%s] [%s] Leere Gemini-Antwort, wiederhole (%s/%s)",
                        _timestamp(),
                        correlation_id,
                        attempt + 1,
                        retries,
                    )

            if not llm_response:
                logger.error(
                    "[%s] [%s] Keine Text-Antwort erhalten: finish_reason=%s, block_reason=%s, parts=%s",
                    _timestamp(),
                    correlation_id,
                    finish_reason,
                    block_reason,
                    parts_summary,
                )
                if lf:
                    try:
                        lf.start_generation(
                            trace_context=TraceContext(id=trace_id) if trace_id else None,
                            name="query_llm",
                            input=final_prompt_to_llm,
                            output="",
                            model=model_name,
                            usage_details=usage,
                            metadata={
                                "context": context_data,
                                "correlation_id": correlation_id,
                                "finish_reason": finish_reason,
                                "block_reason": block_reason,
                                "content_parts": parts_summary,
                                "error": "no_text_returned",
                            },
                        )
                        lf.flush()
                    except Exception as lf_exc:  # pragma: no cover - Logging
                        logger.warning(
                            "[%s] [%s] Langfuse-Fehler: %s",
                            _timestamp(),
                            correlation_id,
                            str(lf_exc),
                        )
                _end_span()
                raise RuntimeError(
                    "LLM returned no text: finish_reason=%s, block_reason=%s"
                    % (finish_reason, block_reason)
                )

            logger.debug(
                "[%s] [%s] Response 200 %s",
                _timestamp(),
                correlation_id,
                repr(llm_response)[:200],
            )

            logger.debug(
                f"--- RESPONSE RECEIVED ---\n{llm_response}\n-----------------------"
            )

            if lf:
                try:
                    lf.start_generation(
                        trace_context=TraceContext(id=trace_id) if trace_id else None,
                        name="query_llm",
                        input=final_prompt_to_llm,
                        output=llm_response,
                        model=model_name,
                        usage_details=usage,
                        metadata={
                            "context": context_data,
                            "correlation_id": correlation_id,
                            "finish_reason": finish_reason,
                            "block_reason": block_reason,
                            "content_parts": parts_summary,
                        },
                    )
                    lf.flush()
                except Exception as lf_exc:  # pragma: no cover - Logging
                    logger.warning(
                        "[%s] [%s] Langfuse-Fehler: %s",
                        _timestamp(),
                        correlation_id,
                        str(lf_exc),
                    )

            _end_span()
            return llm_response

        except Exception as exc:
            if g_exceptions and isinstance(exc, g_exceptions.NotFound):
                logger.error(
                    "[%s] [%s] Unbekanntes Gemini-Modell %s",
                    _timestamp(),
                    correlation_id,
                    name,
                )
                if lf:
                    try:
                        lf.flush()
                    except Exception:
                        logger.warning("Langfuse flush failed", exc_info=True)
                _end_span()
                raise RuntimeError(f"Unsupported Gemini model: {name}.") from exc

            logger.error(
                "[%s] [%s] LLM service error: %s",
                _timestamp(),
                correlation_id,
                str(exc),
                exc_info=True,
            )
            if lf:
                try:
                    lf.flush()
                except Exception:
                    logger.warning("Langfuse flush failed", exc_info=True)
            _end_span()
            raise

    endpoint = "https://api.openai.com/v1/chat/completions"
    openai_model = model_name
    payload = {"model": openai_model, "messages": [{"role": "user", "content": prompt}]}
    if limit:
        payload["max_tokens"] = limit
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
        llm_response = completion.choices[0].message.content
        usage_info = completion.get("usage", {})
        usage = {
            "prompt_tokens": usage_info.get("prompt_tokens"),
            "completion_tokens": usage_info.get("completion_tokens"),
            "total_tokens": usage_info.get("total_tokens"),
        }
        logger.debug(
            "[%s] [%s] Response %s %s",
            _timestamp(),
            correlation_id,
            completion.response_ms,
            repr(completion)[:200],
        )

        logger.debug(
            f"--- RESPONSE RECEIVED ---\n{llm_response}\n-----------------------"
        )

        if lf:
            try:
                lf.start_generation(
                    trace_context=TraceContext(id=trace_id) if trace_id else None,
                    name="query_llm",
                    input=final_prompt_to_llm,
                    output=llm_response,
                    model=model_name,
                    usage_details=usage,
                    metadata={
                        "context": context_data,
                        "correlation_id": correlation_id,
                    },
                )
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )

        _end_span()
        return llm_response
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
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise


def call_gemini_api(
    prompt: str, model_name: str, temperature: float = 0.5, max_output_tokens: int | None = None
) -> str:
    """Sendet einen Prompt direkt an das Gemini-Modell.

    :param max_output_tokens: Optionale Begrenzung der Antwortlänge.
    """
    correlation_id = str(uuid.uuid4())
    trace_id = lf.create_trace_id() if lf else None
    span = None
    if lf and trace_id:
        try:
            span = lf.start_span(
                name="call_gemini_api",
                trace_context=TraceContext(id=trace_id),
                metadata={
                    "correlation_id": correlation_id,
                    "model_name": model_name,
                },
            )
        except Exception as lf_exc:  # pragma: no cover - Logging
            logger.warning(
                "[%s] [%s] Langfuse-Fehler: %s",
                _timestamp(),
                correlation_id,
                str(lf_exc),
            )

    def _end_span() -> None:
        """Beende den Langfuse-Span und flush ihn."""
        if span:
            try:
                span.end()
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )

    limit = max_output_tokens or getattr(settings, "LLM_MAX_OUTPUT_TOKENS", 2048)
    logger.debug(
        "[%s] [%s] Verwende max_output_tokens=%s",
        _timestamp(),
        correlation_id,
        limit,
    )

    if not settings.GOOGLE_API_KEY:
        logger.error(
            "[%s] [%s] Missing LLM API key in environment.",
            _timestamp(),
            correlation_id,
        )
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise RuntimeError("Missing LLM credentials from environment.")

    try:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(model_name)
        logger.debug(
            "[%s] [%s] Request to Google Gemini model=%s",
            _timestamp(),
            correlation_id,
            model_name,
        )

        retries = 1
        llm_response = ""
        for attempt in range(retries + 1):
            resp = model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": limit,
                    "response_mime_type": "text/plain",
                },
            )

            usage_meta = getattr(resp, "usage_metadata", None) or {}
            usage = {
                "prompt_tokens": getattr(
                    usage_meta, "prompt_token_count", None
                ),
                "completion_tokens": getattr(
                    usage_meta, "candidates_token_count", None
                ),
                "total_tokens": getattr(
                    usage_meta, "total_token_count", None
                ),
            }

            try:
                llm_response = resp.text
                if not llm_response:
                    raise ValueError("empty text")
            except Exception:
                texts: list[str] = []
                for cand in getattr(resp, "candidates", []) or []:
                    content = getattr(cand, "content", None)
                    parts = getattr(content, "parts", []) if content else []
                    for part in parts:
                        text_part = getattr(part, "text", "")
                        if text_part:
                            texts.append(text_part)
                llm_response = "\n".join(texts).strip()

            if llm_response:
                break

            if attempt < retries:
                logger.warning(
                    "[%s] [%s] Leere Gemini-Antwort, wiederhole (%s/%s)",
                    _timestamp(),
                    correlation_id,
                    attempt + 1,
                    retries,
                )

            if not llm_response:
                logger.error(
                    "[%s] [%s] Keine Text-Antwort erhalten", _timestamp(), correlation_id
                )
                if lf:
                    try:
                        lf.start_generation(
                            trace_context=TraceContext(id=trace_id) if trace_id else None,
                            name="call_gemini_api",
                            input=prompt,
                            output="",
                            model=model_name,
                            usage_details=usage,
                            metadata={
                                "temperature": temperature,
                                "correlation_id": correlation_id,
                                "error": "no_text_returned",
                            },
                        )
                        lf.flush()
                    except Exception as lf_exc:  # pragma: no cover - Logging
                        logger.warning(
                            "[%s] [%s] Langfuse-Fehler: %s",
                            _timestamp(),
                            correlation_id,
                            str(lf_exc),
                        )
            _end_span()
            raise RuntimeError("LLM returned no text")

        logger.debug(
            "[%s] [%s] Response 200 %s",
            _timestamp(),
            correlation_id,
            repr(llm_response)[:200],
        )
        if lf:
            try:
                lf.start_generation(
                    trace_context=TraceContext(id=trace_id) if trace_id else None,
                    name="call_gemini_api",
                    input=prompt,
                    output=llm_response,
                    model=model_name,
                    usage_details=usage,
                    metadata={
                        "temperature": temperature,
                        "correlation_id": correlation_id,
                    },
                )
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )
        _end_span()
        return llm_response
    except Exception as exc:  # noqa: BLE001 - Weitergabe an Aufrufer
        if g_exceptions and isinstance(exc, g_exceptions.NotFound):
            logger.error(
                "[%s] [%s] Unbekanntes Gemini-Modell %s",
                _timestamp(),
                correlation_id,
                model_name,
            )
            if lf:
                try:
                    lf.flush()
                except Exception:
                    logger.warning("Langfuse flush failed", exc_info=True)
            _end_span()
            raise RuntimeError(f"Unsupported Gemini model: {model_name}.") from exc

        logger.error(
            "[%s] [%s] LLM service error: %s",
            _timestamp(),
            correlation_id,
            str(exc),
            exc_info=True,
        )
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise


def query_llm_with_images(
    prompt: str, images: list[bytes], model_name: str, project_prompt: str | None = None
) -> str:
    """Sendet einen Prompt mit Bildern an ein LLM."""

    import base64

    correlation_id = str(uuid.uuid4())
    trace_id = lf.create_trace_id() if lf else None
    span = None
    if lf and trace_id:
        try:
            span = lf.start_span(
                name="query_llm_with_images",
                trace_context=TraceContext(id=trace_id),
                metadata={
                    "correlation_id": correlation_id,
                    "model_name": model_name,
                },
            )
        except Exception as lf_exc:  # pragma: no cover - Logging
            logger.warning(
                "[%s] [%s] Langfuse-Fehler: %s",
                _timestamp(),
                correlation_id,
                str(lf_exc),
            )

    def _end_span() -> None:
        """Beende den Langfuse-Span und flush ihn."""
        if span:
            try:
                span.end()
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )

    if project_prompt:
        prompt = project_prompt.strip() + "\n\n" + prompt

    if not settings.GOOGLE_API_KEY and not settings.OPENAI_API_KEY:
        logger.error(
            "[%s] [%s] Missing LLM API key in environment.",
            _timestamp(),
            correlation_id,
        )
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise RuntimeError("Missing LLM credentials from environment.")

    if settings.GOOGLE_API_KEY:
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel(model_name)
            content = [prompt] + [
                {"mime_type": "image/png", "data": img} for img in images
            ]
            logger.debug(
                "[%s] [%s] Request to Google Gemini model=%s with %s images",
                _timestamp(),
                correlation_id,
                model_name,
                len(images),
            )
            retries = 1
            llm_response = ""
            for attempt in range(retries + 1):
                resp = model.generate_content(
                    content,
                    generation_config={"response_mime_type": "text/plain"},
                )
                usage_meta = getattr(resp, "usage_metadata", None) or {}
                usage = {
                    "prompt_tokens": getattr(
                        usage_meta, "prompt_token_count", None
                    ),
                    "completion_tokens": getattr(
                        usage_meta, "candidates_token_count", None
                    ),
                    "total_tokens": getattr(
                        usage_meta, "total_token_count", None
                    ),
                }
                try:
                    llm_response = resp.text
                    if not llm_response:
                        raise ValueError("empty text")
                except Exception:
                    texts: list[str] = []
                    for cand in getattr(resp, "candidates", []) or []:
                        content_c = getattr(cand, "content", None)
                        parts = (
                            getattr(content_c, "parts", []) if content_c else []
                        )
                        for part in parts:
                            text_part = getattr(part, "text", "")
                            if text_part:
                                texts.append(text_part)
                    llm_response = "\n".join(texts).strip()
                if llm_response:
                    break
                if attempt < retries:
                    logger.warning(
                        "[%s] [%s] Leere Gemini-Antwort, wiederhole (%s/%s)",
                        _timestamp(),
                        correlation_id,
                        attempt + 1,
                        retries,
                    )
            if not llm_response:
                logger.error(
                    "[%s] [%s] Keine Text-Antwort erhalten",
                    _timestamp(),
                    correlation_id,
                )
                if lf:
                    try:
                        lf.start_generation(
                            trace_context=TraceContext(id=trace_id) if trace_id else None,
                            name="query_llm_with_images",
                            input=prompt,
                            output="",
                            model=model_name,
                            usage_details=usage,
                            metadata={
                                "images": len(images),
                                "correlation_id": correlation_id,
                                "error": "no_text_returned",
                            },
                        )
                        lf.flush()
                    except Exception as lf_exc:  # pragma: no cover - Logging
                        logger.warning(
                            "[%s] [%s] Langfuse-Fehler: %s",
                            _timestamp(),
                            correlation_id,
                            str(lf_exc),
                        )
                _end_span()
                raise RuntimeError("LLM returned no text")
            logger.debug(
                "[%s] [%s] Response 200 %s",
                _timestamp(),
                correlation_id,
                repr(llm_response)[:200],
            )
            if lf:
                try:
                    lf.start_generation(
                        trace_context=TraceContext(id=trace_id) if trace_id else None,
                        name="query_llm_with_images",
                        input=prompt,
                        output=llm_response,
                        model=model_name,
                        usage_details=usage,
                        metadata={
                            "images": len(images),
                            "correlation_id": correlation_id,
                        },
                    )
                    lf.flush()
                except Exception as lf_exc:  # pragma: no cover - Logging
                    logger.warning(
                        "[%s] [%s] Langfuse-Fehler: %s",
                        _timestamp(),
                        correlation_id,
                        str(lf_exc),
                    )
            _end_span()
            return llm_response
        except Exception as exc:  # noqa: BLE001
            if g_exceptions and isinstance(exc, g_exceptions.NotFound):
                logger.error(
                    "[%s] [%s] Unbekanntes Gemini-Modell %s",
                    _timestamp(),
                    correlation_id,
                    model_name,
                )
                if lf:
                    try:
                        lf.flush()
                    except Exception:
                        logger.warning("Langfuse flush failed", exc_info=True)
                _end_span()
                raise RuntimeError(
                    f"Unsupported Gemini model: {model_name}."
                ) from exc
            logger.error(
                "[%s] [%s] LLM service error: %s",
                _timestamp(),
                correlation_id,
                str(exc),
                exc_info=True,
            )
            if lf:
                try:
                    lf.flush()
                except Exception:
                    logger.warning("Langfuse flush failed", exc_info=True)
            _end_span()
            raise

    endpoint = "https://api.openai.com/v1/chat/completions"
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    for img in images:
        b64 = base64.b64encode(img).decode("ascii")
        messages[0]["content"].append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )
    payload = {"model": model_name, "messages": messages}
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
        llm_response = completion.choices[0].message.content
        usage_info = completion.get("usage", {})
        usage = {
            "prompt_tokens": usage_info.get("prompt_tokens"),
            "completion_tokens": usage_info.get("completion_tokens"),
            "total_tokens": usage_info.get("total_tokens"),
        }
        logger.debug(
            "[%s] [%s] Response %s %s",
            _timestamp(),
            correlation_id,
            completion.response_ms,
            repr(completion)[:200],
        )
        if lf:
            try:
                lf.start_generation(
                    trace_context=TraceContext(id=trace_id) if trace_id else None,
                    name="query_llm_with_images",
                    input=prompt,
                    output=llm_response,
                    model=model_name,
                    usage_details=usage,
                    metadata={
                        "images": len(images),
                        "correlation_id": correlation_id,
                    },
                )
                lf.flush()
            except Exception as lf_exc:  # pragma: no cover - Logging
                logger.warning(
                    "[%s] [%s] Langfuse-Fehler: %s",
                    _timestamp(),
                    correlation_id,
                    str(lf_exc),
                )
        _end_span()
        return llm_response
    except Exception as exc:  # noqa: BLE001
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
        if lf:
            try:
                lf.flush()
            except Exception:
                logger.warning("Langfuse flush failed", exc_info=True)
        _end_span()
        raise
