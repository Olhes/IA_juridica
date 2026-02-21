"""
Anti-Hallucination Layer para IA Jurídica.

Detecta patrones de alucinación específicos del dominio legal peruano:
  - Referencias a artículos/leyes inexistentes o mal formateadas
  - Números de casación sin información completa
  - Frases de incertidumbre en contexto de cita legal
  - Respuestas sin soporte suficiente del RAG (penalización por rag_score bajo)
  - Estadísticas numéricas inventadas (porcentajes, montos sin fuente)

Uso:
    layer = AntiHallucinationLayer()
    report = layer.analyze(response_text, rag_score=0.85)
    if report.requires_correction:
        # pasar al SelfCorrectionEngine
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from loguru import logger

# ── Patrones de alucinación legal (Perú) ──────────────────────────────────────
#
# Cada entrada: (pattern_regex, nombre, descripción, severidad 0–1)
#
LEGAL_HALLUCINATION_PATTERNS: List[Tuple[str, str, str, float]] = [
    # Artículos con números inusualmente altos para el Código Civil (≥ 700 ya es sospechoso)
    (
        r"\bartículo\s+[789]\d{2,}\b",
        "articulo_alto",
        "Artículo con número inusualmente alto para el Código Civil peruano",
        0.45,
    ),
    # Ley N° con número demasiado corto (leyes peruanas tienen 4-5 dígitos desde los 2000s)
    (
        r"\bley\s+n[°º]?\s*\d{1,3}(?!\d)",
        "ley_corta",
        "Número de ley demasiado corto para leyes peruanas contemporáneas",
        0.40,
    ),
    # Casación sin año o sin sala/región
    (
        r"\bcasación\s+\d+[-–]\d{2,3}(?!\d)",
        "casacion_incompleta",
        "Casación con año de 2-3 dígitos; formato correcto es XXXX-AAAA, Sala/Región",
        0.35,
    ),
    # Incertidumbre explícita en cita legal concreta
    (
        r"(podría ser|posiblemente|quizás|tal vez|creo que)\s+(el artículo|la ley|el decreto|la casación)",
        "incertidumbre_legal",
        "Expresión de incertidumbre al citar una norma legal específica",
        0.55,
    ),
    # Monto fijo de pensión sin fuente (el juez fija según caso)
    (
        r"la pensión\s+(mínima|máxima|es de|será de)\s+s[/.]?\s*\d+",
        "monto_fijo_pension",
        "La ley peruana no fija montos fijos de pensión; el juez determina según cada caso",
        0.50,
    ),
    # Plazo inventado para proceso judicial
    (
        r"el proceso\s+dura\s+exactamente\s+\d+",
        "plazo_exacto_inventado",
        "Afirmar un plazo exacto de proceso judicial sin citar norma",
        0.40,
    ),
    # Entidades que no existen en Perú
    (
        r"\b(tribunal constitucional federal|juzgado civil federal|ministerio de justicia federal)\b",
        "entidad_inexistente",
        "Entidad judicial que no existe en el sistema legal peruano",
        0.70,
    ),
    # Referencia a derogación sin año verificable
    (
        r"(fue derogad[ao]|quedó sin efecto)\s+en\s+(?:199\d|20[0-2]\d)",
        "derogacion_no_verificada",
        "Afirmación de derogación de norma sin citar decreto o ley de derogación",
        0.35,
    ),
]

# ── Penalizaciones estructurales ───────────────────────────────────────────────

# Si el RAG score es menor a este umbral, penalizar por falta de respaldo
RAG_SCORE_THRESHOLD = 0.45

# Si la respuesta supera este largo (chars) con RAG score bajo, penalizar más
LONG_RESPONSE_CHARS = 1200

# Umbral de riesgo a partir del cual se requiere corrección
DEFAULT_RISK_THRESHOLD = 0.40


@dataclass
class HallucinationReport:
    """Resultado del análisis de alucinación."""
    risk_score          : float          # 0.0 = sin riesgo, 1.0 = máximo riesgo
    flags               : List[str] = field(default_factory=list)
    pattern_details     : List[dict] = field(default_factory=list)
    requires_correction : bool = False
    rag_penalty         : float = 0.0
    pattern_penalty     : float = 0.0
    structural_penalty  : float = 0.0


class AntiHallucinationLayer:
    """
    Primera línea de defensa contra alucinaciones en el dominio legal peruano.

    Combina:
      1. Regex patterns específicos del dominio legal peruano
      2. Penalización por baja cobertura del RAG (rag_score)
      3. Penalización estructural (respuestas largas sin respaldo)

    El risk_score resultante (0.0–1.0) determina si se requiere corrección.
    """

    def __init__(self, risk_threshold: float = DEFAULT_RISK_THRESHOLD):
        self.threshold = risk_threshold
        self.patterns  = LEGAL_HALLUCINATION_PATTERNS
        logger.info(
            f"AntiHallucinationLayer inicializado (threshold={risk_threshold}, "
            f"patterns={len(self.patterns)})"
        )

    def analyze(self, response: str, rag_score: float = 1.0) -> HallucinationReport:
        """
        Analiza una respuesta del LLM en busca de señales de alucinación.

        Args:
            response:  Texto generado por el LLM (puede ser JSON serializado o texto plano)
            rag_score: Score de relevancia promedio de los chunks RAG usados (0–1)

        Returns:
            HallucinationReport con risk_score y lista de flags
        """
        if not response or not response.strip():
            # Respuesta vacía es problemática por sí misma
            return HallucinationReport(
                risk_score=0.3,
                flags=["Respuesta vacía o demasiado corta"],
                requires_correction=True,
                structural_penalty=0.3,
            )

        flags        : List[str] = []
        pattern_details : List[dict] = []

        # 1. Chequeo de patrones regex de dominio
        pattern_penalty = 0.0
        for regex, name, description, severity in self.patterns:
            if re.search(regex, response, re.IGNORECASE):
                flags.append(description)
                pattern_details.append({"name": name, "description": description, "severity": severity})
                pattern_penalty += severity
                logger.debug(f"Hallucination pattern hit: {name}")

        pattern_penalty = min(pattern_penalty, 0.70)

        # 2. Penalización por rag_score bajo (poca evidencia recuperada)
        rag_penalty = 0.0
        if rag_score < RAG_SCORE_THRESHOLD:
            # Escala lineal: 0.0 cuando score=threshold, ~0.40 cuando score=0.0
            rag_penalty = round((RAG_SCORE_THRESHOLD - rag_score) * (0.40 / RAG_SCORE_THRESHOLD), 3)

        # 3. Penalización estructural: respuesta larga + RAG débil
        structural_penalty = 0.0
        if len(response) > LONG_RESPONSE_CHARS and rag_score < 0.60:
            structural_penalty = 0.10
            flags.append(
                "Respuesta extensa con cobertura RAG insuficiente "
                f"(len={len(response)}, rag_score={rag_score:.2f})"
            )

        risk_score = min(pattern_penalty + rag_penalty + structural_penalty, 1.0)

        report = HallucinationReport(
            risk_score          = round(risk_score, 4),
            flags               = flags,
            pattern_details     = pattern_details,
            requires_correction = risk_score >= self.threshold,
            rag_penalty         = rag_penalty,
            pattern_penalty     = pattern_penalty,
            structural_penalty  = structural_penalty,
        )

        if report.requires_correction:
            logger.warning(
                f"Posible alucinación detectada (risk={risk_score:.3f}, flags={len(flags)}): "
                + " | ".join(flags[:3])
            )
        else:
            logger.debug(f"Respuesta OK (risk={risk_score:.3f})")

        return report