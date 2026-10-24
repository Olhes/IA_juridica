"""Faithfulness: **diagnóstico**, no decide el lanzamiento.

Mide si la respuesta se apoya en la evidencia recuperada, no si es jurídicamente
correcta. Dos lecturas independientes: el solapamiento léxico que ya calcula el
validador (``cross_check.overlap_score``) y, si hay juez, su veredicto.
"""

from evaluation.harness.metrics.common import Score


def faithfulness_overlap(answer) -> Score:
    if answer.cross_check_overlap is None:
        return Score.na("el validador no reportó solapamiento")
    return Score(float(answer.cross_check_overlap), float(answer.cross_check_overlap), 1.0)


def faithfulness_judge(value) -> Score:
    if value is None:
        return Score.na("juez no disponible")
    return Score(float(value), float(value), 1.0)
