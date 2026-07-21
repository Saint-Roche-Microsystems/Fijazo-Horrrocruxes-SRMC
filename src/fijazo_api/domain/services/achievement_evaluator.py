"""Servicio de dominio PURO: evaluación de logros desbloqueados.

Solo evalúa las definiciones **aún bloqueadas** (los logros son monótonos: una
vez obtenidos no se revocan), lo que evita recálculos innecesarios y duplicados.
"""

from collections.abc import Iterable
from datetime import datetime

from fijazo_api.domain.entities.statistics import UserStatistics
from fijazo_api.domain.services.achievements_catalog import CATALOG


def evaluate(stats: UserStatistics, now: datetime, unlocked_ids: Iterable[str]) -> list[str]:
    """Devuelve los ids de logros recién satisfechos (excluye los ya obtenidos)."""

    already = set(unlocked_ids)
    newly: list[str] = []
    for achievement in CATALOG:
        if achievement.id in already:
            continue
        if achievement.condition(stats, now):
            newly.append(achievement.id)
    return newly
