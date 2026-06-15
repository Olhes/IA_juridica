"""
Self-Correction Engine para IA Jurídica.

Cuando el AntiHallucinationLayer o el ResponseValidator detectan
problemas en la respuesta generada, este módulo reintenta la generación
con un prompt enriquecido que incluye:
  - La respuesta original con sus problemas identificados
  - El contexto RAG completo como "fuente de verdad"
  - Instrucciones explícitas de corrección

Integración:
  - Usa el mismo cliente Cohere del LegalAgent (reutilización, sin doble instancia)
  - Máximo `max_retries` reintentos para evitar loops infinitos
  - Devuelve (texto_corregido, num_correcciones_aplicadas)

Uso:
    engine = SelfCorrectionEngine(cohere_client=agent.cohere_client)
    corrected_text, n = await engine.correct(
        original_text=response_text,
        hallucination_report=report,
        rag_context=rag_context_str,
        query=query,
    )
"""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from config.settings import settings
from .anti_hallucination import HallucinationReport


# ── Prompt de corrección ───────────────────────────────────────────────────────

_CORRECTION_SYSTEM_PROMPT = (
    "Eres un asistente legal peruano altamente especializado. "
    "Tu tarea es CORREGIR una respuesta que contiene posibles errores o información "
    "no fundamentada en los documentos legales disponibles. "
    "REGLAS ESTRICTAS: "
    "1) Basa tu respuesta EXCLUSIVAMENTE en el contexto proporcionado. "
    "2) Si el contexto no cubre algo, indícalo con 'Según la información disponible...'. "
    "3) No inventes leyes, artículos, montos ni plazos. "
    "4) Mantén el mismo idioma (español o quechua) de la respuesta original. "
    "5) Devuelve solo el texto corregido, sin explicaciones adicionales ni JSON."
)

_CORRECTION_PROMPT_TEMPLATE = """\
RESPUESTA ORIGINAL CON POSIBLES ERRORES:
{original_answer}

PROBLEMAS DETECTADOS:
{issues}

CONTEXTO LEGAL (fuente de verdad — úsalo como referencia exclusiva):
{rag_context}

CONSULTA DEL USUARIO (contexto de la pregunta):
{query}

Reescribe la respuesta corrigiendo los problemas. Sé preciso, claro y cita el contexto cuando sea posible."""


class SelfCorrectionEngine:
    """
    Reintenta la generación LLM con instrucciones de corrección explícitas
    cuando se detectan alucinaciones o baja calidad en la respuesta original.

    Args:
        cohere_client:  AsyncClient de Cohere (reutilizado del LegalAgent)
        max_retries:    Máximo de reintentos de corrección (default=2)
        min_length:     Longitud mínima para considerar una corrección válida
    """

    def __init__(
        self,
        cohere_client,                  # cohere.AsyncClient – sin importar clase para evitar circular import
        max_retries: int   = 2,
        min_length  : int  = 50,
    ):
        self.cohere   = cohere_client
        self.max_retries = max_retries
        self.min_length  = min_length
        logger.info(f"SelfCorrectionEngine inicializado (max_retries={max_retries})")

    async def correct(
        self,
        original_text       : str,
        hallucination_report: HallucinationReport,
        rag_context         : str,
        query               : str,
        language            : str = "spanish",
    ) -> tuple[str, int]:
        """
        Corrige una respuesta problemática.

        Args:
            original_text:        Texto original generado por el LLM
            hallucination_report: Informe del AntiHallucinationLayer
            rag_context:          Chunks RAG concatenados como contexto de verdad
            query:                Consulta original del usuario
            language:             Idioma de la respuesta ("spanish" | "quechua")

        Returns:
            (texto_corregido, num_correcciones_aplicadas)
            Si no se requiere corrección → (original_text, 0)
        """
        if not hallucination_report.requires_correction:
            logger.debug("Self-correction: no se requiere corrección")
            return original_text, 0

        if not self.cohere:
            logger.warning("Self-correction: Cohere no disponible, retornando original")
            return original_text, 0

        current_text = original_text
        corrections  = 0

        issues_text = self._format_issues(hallucination_report)

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"Self-correction intento {attempt}/{self.max_retries}")

            correction_prompt = _CORRECTION_PROMPT_TEMPLATE.format(
                original_answer=current_text,
                issues         =issues_text,
                rag_context    =rag_context[:3500],   # Cap tokens
                query          =query,
            )

            try:
                response = await self.cohere.chat(
                    message  =correction_prompt,
                    model    =settings.COHERE_LLM_MODEL,
                    preamble =_CORRECTION_SYSTEM_PROMPT,
                    temperature=max(0.1, settings.COHERE_TEMPERATURE - 0.1),  # Más determinista
                    max_tokens=settings.COHERE_MAX_TOKENS,
                )

                corrected = getattr(response, "text", "").strip()

                if len(corrected) >= self.min_length:
                    current_text = corrected
                    corrections += 1
                    logger.info(
                        f"Corrección aplicada (intento {attempt}, "
                        f"len_original={len(original_text)}, len_corrected={len(corrected)})"
                    )
                    # Si la corrección es substancialmente diferente a la original, detener
                    if self._is_meaningful_correction(original_text, corrected):
                        break
                else:
                    logger.warning(
                        f"Corrección intento {attempt} produjo texto demasiado corto "
                        f"({len(corrected)} chars), reintentando..."
                    )

            except Exception as exc:
                logger.error(f"Error en self-correction intento {attempt}: {exc}")
                # No propagar el error – retornar lo mejor que tenemos
                break

        if corrections == 0:
            logger.warning("Self-correction: no se pudo mejorar la respuesta")

        return current_text, corrections

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _format_issues(self, report: HallucinationReport) -> str:
        """Formatea los problemas detectados en texto legible para el prompt."""
        if not report.flags:
            parts = [f"- Cobertura RAG insuficiente (score bajo: {report.rag_penalty:.2f})"]
        else:
            parts = [f"- {flag}" for flag in report.flags[:5]]   # Limitar a 5

        if report.rag_penalty > 0.15:
            parts.append(
                f"- La respuesta tiene poca evidencia de soporte en los documentos legales "
                f"(penalización RAG: {report.rag_penalty:.2f})"
            )
        return "\n".join(parts)

    def _is_meaningful_correction(self, original: str, corrected: str) -> bool:
        """
        Heurística para saber si la corrección cambió suficiente el texto.
        Compara tokens únicos de ambas versiones.
        """
        orig_tokens = set(original.lower().split())
        corr_tokens = set(corrected.lower().split())

        if not orig_tokens:
            return True

        # Si más del 30% de los tokens son diferentes, la corrección fue sustantiva
        symmetric_diff = len(orig_tokens.symmetric_difference(corr_tokens))
        change_ratio   = symmetric_diff / max(len(orig_tokens), 1)
        return change_ratio > 0.30