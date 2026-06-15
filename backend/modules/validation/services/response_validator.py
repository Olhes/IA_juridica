"""
ResponseValidator — Orquestador del pipeline de validación de IA Jurídica.

Este es el punto de entrada único para todo el proceso de validación.
Integra en secuencia:
  1. AntiHallucinationLayer  → detecta patrones de alucinación
  2. RAGCrossChecker         → verifica soporte en corpus RAG
  3. SelfCorrectionEngine    → corrige si es necesario (usa Cohere)
  4. Validación cultural     → delega a ContextEngineer si disponible
  5. Construcción del ValidationReport final

Uso desde main.py:
    validator = ResponseValidator(
        rag_engine=app.state.rag_engine,
        cohere_client=app.state.legal_agent.cohere_client,
        context_engineer=app.state.context_engineer,
    )

    validated = await validator.validate(
        response_data=response_payload,
        rag_result=rag_result,
        query=query,
        language=language,
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from .anti_hallucination import AntiHallucinationLayer, HallucinationReport
from .cross_checker import RAGCrossChecker, CrossCheckResult
from .self_correction import SelfCorrectionEngine
from .schemas import (
    ConfidenceLevel,
    CrossCheckSummary,
    HallucinationFlag,
    ValidatedResponse,
    ValidationReport,
    ValidationStatus,
)


@dataclass
class ValidationConfig:
    """Configuración tuneable del pipeline de validación."""
    hallucination_threshold    : float = 0.40   # risk_score mínimo para requerir corrección
    cross_check_threshold      : float = 0.55   # overlap mínimo para is_grounded=True
    min_confidence_score       : float = 0.30   # Debajo de esto → ValidationStatus.FAILED
    max_self_correction_retries: int   = 2
    enable_cross_check         : bool  = True
    enable_self_correction     : bool  = True
    enable_cultural_validation : bool  = True


class ResponseValidator:
    """
    Orquestador del pipeline completo de validación.

    Inicialización recomendada: una sola instancia por request o en el lifespan de la app
    (el CrossChecker tiene estado interno cacheado del corpus RAG).

    Args:
        rag_engine:        LegalRAGEngine – se accede a .documents y .cohere_client
        cohere_client:     AsyncClient de Cohere del LegalAgent (reutilización, sin doble instancia)
        context_engineer:  ContextEngineer para validación cultural (opcional)
        config:            ValidationConfig con umbrales personalizables
    """

    def __init__(
        self,
        rag_engine,
        cohere_client,
        context_engineer=None,
        config: Optional[ValidationConfig] = None,
    ):
        self.config = config or ValidationConfig()
        cfg = self.config

        self.anti_hallucination = AntiHallucinationLayer(
            risk_threshold=cfg.hallucination_threshold
        )
        self.cross_checker = RAGCrossChecker(
            documents         =rag_engine.documents,
            grounded_threshold=cfg.cross_check_threshold,
        )
        self.self_correction = SelfCorrectionEngine(
            cohere_client=cohere_client,
            max_retries  =cfg.max_self_correction_retries,
        )
        self.context_engineer = context_engineer
        self._rag_engine      = rag_engine

        logger.info("ResponseValidator inicializado (pipeline completo)")

    # ── API pública ────────────────────────────────────────────────────────────

    async def validate(
        self,
        response_data : Dict[str, Any],
        rag_result    : Dict[str, Any],
        query         : str,
        language      : str = "spanish",
        enriched_context: Optional[Dict[str, Any]] = None,
    ) -> ValidatedResponse:
        """
        Pipeline principal de validación.

        Args:
            response_data:    Dict serializado de GeneralLegalResponse (o similar)
            rag_result:       Resultado de rag_engine.query_with_rerank()
            query:            Consulta original del usuario
            language:         Idioma de la respuesta
            enriched_context: Contexto cultural del ContextEngineer (opcional)

        Returns:
            ValidatedResponse con answer_data validado e informe completo
        """
        t0 = time.monotonic()

        # ── Extraer texto plano de la respuesta para análisis ──────────────────
        answer_text  = self._extract_answer_text(response_data)
        rag_score    = self._compute_avg_rag_score(rag_result)
        rag_context  = self._build_rag_context_str(rag_result)
        sources      = rag_result.get("sources", [])

        # Asegurar que el CrossChecker use el corpus actualizado
        self.cross_checker.update_documents(self._rag_engine.documents)

        warnings : List[str] = []
        status   = ValidationStatus.PASSED

        # ── PASO 1: Anti-hallucination ─────────────────────────────────────────
        hallucination_report: HallucinationReport = self.anti_hallucination.analyze(
            response=answer_text,
            rag_score=rag_score,
        )

        # ── PASO 2: Cross-check RAG ────────────────────────────────────────────
        cross_result: Optional[CrossCheckResult] = None
        if self.config.enable_cross_check:
            cross_result = self.cross_checker.check(answer_text, query)
            if not cross_result.is_grounded:
                warnings.append(
                    f"Respuesta con soporte RAG bajo (overlap={cross_result.overlap_score:.2f})"
                )

        # ── PASO 3: Self-correction ────────────────────────────────────────────
        corrections_applied = 0
        if self.config.enable_self_correction and hallucination_report.requires_correction:
            corrected_text, corrections_applied = await self.self_correction.correct(
                original_text        =answer_text,
                hallucination_report =hallucination_report,
                rag_context          =rag_context,
                query                =query,
                language             =language,
            )
            if corrections_applied > 0:
                status = ValidationStatus.CORRECTED
                # Actualizar el campo de respuesta en español con el texto corregido
                response_data = self._inject_corrected_text(response_data, corrected_text)
                # Re-analizar el texto corregido
                hallucination_report = self.anti_hallucination.analyze(
                    response=corrected_text,
                    rag_score=rag_score,
                )

        # ── PASO 4: Validación cultural ────────────────────────────────────────
        cultural_issues: List[str] = []
        if (
            self.config.enable_cultural_validation
            and self.context_engineer
            and enriched_context
        ):
            cultural_result = self.context_engineer.validate_response_cultural_appropriateness(
                response=answer_text,
                context=enriched_context,
            )
            cultural_issues = cultural_result.get("issues", [])
            if cultural_issues and status == ValidationStatus.PASSED:
                status = ValidationStatus.WARNED

        # ── PASO 5: Score de confianza final ───────────────────────────────────
        confidence_score = self._compute_confidence_score(
            hallucination_report=hallucination_report,
            cross_result        =cross_result,
            rag_score           =rag_score,
        )

        if confidence_score < self.config.min_confidence_score:
            status = ValidationStatus.FAILED
            warnings.append(
                f"Confianza insuficiente: {confidence_score:.2f} < {self.config.min_confidence_score}"
            )
        elif status == ValidationStatus.PASSED and hallucination_report.flags:
            status = ValidationStatus.WARNED

        # ── Construir ValidationReport ─────────────────────────────────────────
        processing_ms = round((time.monotonic() - t0) * 1000, 2)

        report = ValidationReport(
            status             =status,
            confidence         =ConfidenceLevel.from_score(confidence_score),
            confidence_score   =round(confidence_score, 4),
            hallucination_risk =hallucination_report.risk_score,
            is_grounded        =cross_result.is_grounded if cross_result else True,
            corrections_applied=corrections_applied,
            flags              =[
                HallucinationFlag(
                    pattern_name=d["name"],
                    description =d["description"],
                    severity    =d["severity"],
                )
                for d in hallucination_report.pattern_details
            ],
            cross_check=CrossCheckSummary(
                is_grounded      =cross_result.is_grounded,
                overlap_score    =cross_result.overlap_score,
                ungrounded_claims=cross_result.ungrounded_claims,
                supporting_chunks=cross_result.supporting_chunks,
            ) if cross_result else None,
            cultural_issues   =cultural_issues,
            warnings          =warnings,
            processing_time_ms=processing_ms,
        )

        logger.info(
            f"Validación completada: status={status}, confidence={confidence_score:.2f}, "
            f"hallucination_risk={hallucination_report.risk_score:.2f}, "
            f"corrections={corrections_applied}, time={processing_ms}ms"
        )

        return ValidatedResponse(
            answer_data      =response_data,
            validation_report=report,
            query            =query,
            language         =language,
            sources          =sources,
        )

    # ── Helpers privados ───────────────────────────────────────────────────────

    def _extract_answer_text(self, response_data: Dict[str, Any]) -> str:
        """
        Extrae texto plano de un response_data (GeneralLegalResponse serializado).
        Prioriza respuesta_espanol, luego medidas_inmediatas, luego str completo.
        """
        if isinstance(response_data, str):
            return response_data

        # GeneralLegalResponse
        if "respuesta_espanol" in response_data:
            return str(response_data["respuesta_espanol"])

        # ViolenceResponse
        if "medidas_inmediatas" in response_data:
            medidas = response_data.get("medidas_inmediatas", [])
            return " ".join(str(m) for m in medidas) if medidas else ""

        # PensionResponse
        if "tipo_pension" in response_data:
            pasos = response_data.get("pasos_proceso", [])
            return " ".join(
                str(p.get("descripcion", "")) if isinstance(p, dict) else str(p)
                for p in pasos
            )

        # Fallback: serializar todo a string
        return str(response_data)

    def _compute_avg_rag_score(self, rag_result: Dict[str, Any]) -> float:
        """Calcula el score RAG promedio de los documentos recuperados."""
        scores = rag_result.get("rerank_scores", [])
        if not scores:
            # Si no hay rerank scores, usar confidence del rag_result
            return float(rag_result.get("confidence", 0.70))
        return round(sum(scores) / len(scores), 4)

    def _build_rag_context_str(self, rag_result: Dict[str, Any]) -> str:
        """Construye un string de contexto RAG para el prompt de corrección."""
        documents = rag_result.get("documents", [])
        if documents:
            parts = []
            for doc in documents[:5]:   # Limitar a 5 docs
                content = doc.get("content", "")[:600]
                source  = doc.get("metadata", {}).get("filename", "Fuente desconocida")
                parts.append(f"[{source}]\n{content}")
            return "\n\n---\n\n".join(parts)

        # Fallback: usar answer del RAG
        answer = rag_result.get("answer", "")
        return str(answer)[:2000] if answer else ""

    def _inject_corrected_text(
        self, response_data: Dict[str, Any], corrected_text: str
    ) -> Dict[str, Any]:
        """
        Inyecta el texto corregido en el campo apropiado del response_data.
        Retorna un nuevo dict (no muta el original).
        """
        updated = dict(response_data)
        if "respuesta_espanol" in updated:
            updated["respuesta_espanol"] = corrected_text
        elif "medidas_inmediatas" in updated:
            updated["medidas_inmediatas"] = [corrected_text]
        return updated

    def _compute_confidence_score(
        self,
        hallucination_report: HallucinationReport,
        cross_result        : Optional[CrossCheckResult],
        rag_score           : float,
    ) -> float:
        """
        Combina múltiples señales en un score de confianza 0–1.

        Pesos:
          - rag_score base                           40%
          - penalización por hallucination_risk      30%
          - soporte del cross-check (overlap_score)  30%
        """
        base      = rag_score * 0.40
        hall_comp = (1.0 - hallucination_report.risk_score) * 0.30
        cross_comp = (
            cross_result.overlap_score * 0.30
            if cross_result
            else 0.20   # Sin cross-check → valor neutro
        )
        return min(base + hall_comp + cross_comp, 1.0)