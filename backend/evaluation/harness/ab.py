"""Comparación A/B ciega con orden invertido de las respuestas de dos commits.

Para cada caso cuyas respuestas difieren se crean **dos** ensayos con las posiciones
cruzadas (A=base,B=head y A=head,B=base) bajo identificadores opacos. Un juez (humano o
modelo) elige ``A``, ``B`` o ``empate`` sin saber qué commit es cuál. Un caso solo cuenta si
ambos ensayos coinciden tras deshacer el cruce; si no, es ``inconsistente`` (sesgo de posición).
"""

import hashlib
import math
import random
from dataclasses import asdict, dataclass
from typing import Optional

WINNERS = ("base", "head", "tie")


@dataclass(frozen=True)
class Trial:
    trial_id: str  # opaco: no revela caso ni orden
    case_id: str
    query: str
    answer_a: str
    answer_b: str
    a_is: str  # "base" | "head": la clave, que no se entrega al juez

    def blinded(self) -> dict:
        return {"trial_id": self.trial_id, "query": self.query, "answer_a": self.answer_a, "answer_b": self.answer_b}

    def to_json(self) -> dict:
        return asdict(self)


def build_trials(base_answers: dict, head_answers: dict, queries: dict, *, seed: int = 0) -> list:
    """``*_answers``: ``{case_id: texto}``. Solo los casos con respuestas distintas generan ensayos."""
    rnd = random.Random(seed)
    trials = []
    for case_id in sorted(set(base_answers) & set(head_answers)):
        base, head = base_answers[case_id], head_answers[case_id]
        if base.strip() == head.strip():
            continue
        for a_is in ("base", "head"):
            a, b = (base, head) if a_is == "base" else (head, base)
            token = hashlib.sha256(f"{seed}:{case_id}:{a_is}:{rnd.random()}".encode()).hexdigest()[:16]
            trials.append(Trial(token, case_id, queries.get(case_id, ""), a, b, a_is))
    rnd.shuffle(trials)  # el orden de presentación tampoco delata el cruce
    return trials


def resolve(trials, verdicts: dict) -> dict:
    """``verdicts``: ``{trial_id: 'A'|'B'|'tie'|None}``. Devuelve el ganador por caso y el resumen."""
    by_case: dict = {}
    for trial in trials:
        verdict = verdicts.get(trial.trial_id)
        if verdict is None:
            winner = None
        elif verdict == "tie":
            winner = "tie"
        elif verdict in ("A", "B"):
            picked_a = verdict == "A"
            winner = trial.a_is if picked_a else ("head" if trial.a_is == "base" else "base")
        else:
            winner = None
        by_case.setdefault(trial.case_id, []).append(winner)
    cases, counts = {}, {"base": 0, "head": 0, "tie": 0, "inconsistent": 0, "unjudged": 0}
    for case_id, winners in by_case.items():
        if any(w is None for w in winners):
            outcome = "unjudged"
        elif len(set(winners)) == 1:
            outcome = winners[0]
        else:
            outcome = "inconsistent"
        cases[case_id] = outcome
        counts[outcome] += 1
    decisive = counts["base"] + counts["head"]
    return {
        "cases": cases,
        "counts": counts,
        "head_win_rate": counts["head"] / decisive if decisive else None,
        "sign_test_p": sign_test_p(counts["head"], counts["base"]),
        "position_bias_rate": counts["inconsistent"] / len(cases) if cases else None,
    }


def sign_test_p(wins: int, losses: int) -> Optional[float]:
    """p-valor exacto bilateral de la prueba del signo (empates excluidos); ``None`` sin decisiones."""
    n = wins + losses
    if n == 0:
        return None
    extreme = min(wins, losses)
    tail = sum(math.comb(n, k) for k in range(extreme + 1)) / 2**n
    return min(1.0, 2 * tail)


async def judge_trials(judge, trials) -> dict:
    """Pide al juez que elija en cada ensayo; ``None`` si el juez no está disponible."""
    verdicts = {}
    for trial in trials:
        verdicts[trial.trial_id] = await judge.prefer(trial.query, trial.answer_a, trial.answer_b) if judge.available else None
    return verdicts
