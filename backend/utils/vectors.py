"""Operaciones numéricas compartidas por recuperación y evaluación."""

import numpy as np


def cosine_scores(vectors, query) -> list[float]:
    """Similitud de cada fila con la consulta; un vector nulo puntúa cero."""
    rows = np.asarray(vectors, dtype=np.float64)
    target = np.asarray(query, dtype=np.float64)
    if target.ndim != 1 or not target.size:
        raise ValueError("Dimensiones incompatibles")
    if rows.shape == (0,):
        rows = rows.reshape(0, target.size)
    if rows.ndim != 2 or rows.shape[1] != target.size:
        raise ValueError("Dimensiones incompatibles")
    if not np.isfinite(rows).all() or not np.isfinite(target).all():
        raise ValueError("Vector no finito")
    denominator = np.linalg.vector_norm(rows, axis=1) * np.linalg.vector_norm(target)
    similarity = np.divide(
        np.einsum("ij,j->i", rows, target), denominator,
        out=np.zeros(len(rows)), where=denominator != 0,
    )
    return similarity.tolist()


def cosine(left, right) -> float:
    return cosine_scores([left], right)[0]
