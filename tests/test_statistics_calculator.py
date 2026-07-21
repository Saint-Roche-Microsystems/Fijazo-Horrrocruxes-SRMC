"""Tests unitarios PUROS de los cálculos de estadísticas y ranking (sin BD)."""

from datetime import datetime, timedelta, timezone

from fijazo_api.domain.entities.bet import Bet, BetStatus, BetType
from fijazo_api.domain.entities.statistics import UserStatistics
from fijazo_api.domain.services.ranking_scorer import (
    MIN_BETS_THRESHOLD,
    compute_ranking_score,
)
from fijazo_api.domain.services.statistics_calculator import compute_statistics

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_bet(status: BetStatus, odds: float, stake: float, minutes: int = 0) -> Bet:
    """Crea una apuesta mínima para los tests, con orden temporal controlado."""

    bet = Bet(
        user_id="u1",
        sport="Fútbol",
        league="LaLiga",
        event="A vs B",
        bet_type=BetType.SIMPLE,
        market="1X2",
        selection="A",
        odds=odds,
        stake=stake,
        bookmaker="Bet365",
        event_datetime=BASE + timedelta(minutes=minutes),
        status=status,
    )
    bet.recalculate()  # fija combined_odds (= odds en apuestas simples)
    return bet


def test_empty_history():
    stats = compute_statistics("u1", [])
    assert stats.total_bets == 0
    assert stats.win_rate == 0.0
    assert stats.ranking_score == 0.0  # entidad por defecto
    assert stats.last_bet_at is None


def test_counts_and_financials():
    bets = [
        make_bet(BetStatus.WON, 2.0, 10, minutes=0),
        make_bet(BetStatus.LOST, 3.0, 20, minutes=10),
        make_bet(BetStatus.VOID, 1.5, 5, minutes=20),
        make_bet(BetStatus.PENDING, 2.0, 10, minutes=30),
    ]
    s = compute_statistics("u1", bets, username="carlos")

    assert (s.total_bets, s.won, s.lost, s.void, s.pending) == (4, 1, 1, 1, 1)
    assert s.win_rate == 50.0  # 1 de 2 decididas
    assert s.total_stake == 35.0  # 10 + 20 + 5 (finalizadas)
    assert s.total_return == 25.0  # 20 (won) + 0 (lost) + 5 (void)
    assert s.net_profit == -10.0
    assert round(s.roi, 2) == -28.57
    assert s.biggest_win == 10.0
    assert s.biggest_loss == -20.0
    assert s.username == "carlos"


def test_streaks_skip_void_and_order_by_datetime():
    # Desordenadas en la lista; deben ordenarse por event_datetime.
    bets = [
        make_bet(BetStatus.WON, 2.0, 10, minutes=0),
        make_bet(BetStatus.WON, 2.0, 10, minutes=10),
        make_bet(BetStatus.VOID, 2.0, 10, minutes=15),  # se ignora en rachas
        make_bet(BetStatus.LOST, 2.0, 10, minutes=20),
        make_bet(BetStatus.LOST, 2.0, 10, minutes=30),
    ]
    s = compute_statistics("u1", bets)
    assert s.current_streak == -2  # dos derrotas al final
    assert s.best_streak == 2  # dos victorias consecutivas al inicio


def test_consistency_variation():
    # WON roi=+1, LOST roi=-1 -> pstdev=1 -> 100/(1+1)=50
    bets = [
        make_bet(BetStatus.WON, 2.0, 10, minutes=0),
        make_bet(BetStatus.LOST, 2.0, 10, minutes=10),
    ]
    s = compute_statistics("u1", bets)
    assert s.consistency == 50.0


def _winning_stats(finalized: int) -> UserStatistics:
    return UserStatistics(
        user_id="u",
        won=finalized,
        win_rate=100.0,
        roi=50.0,
        net_profit=200.0,
        consistency=90.0,
        current_streak=finalized,
    )


def test_ranking_penalizes_low_sample():
    few = _winning_stats(5)  # < umbral
    many = _winning_stats(MIN_BETS_THRESHOLD)  # cumple umbral

    score_few = compute_ranking_score(few)
    score_many = compute_ranking_score(many)

    assert score_few < score_many  # penalización por pocas apuestas
    # Con 5/30 la confianza es 1/6, muy por debajo de la puntuación plena.
    assert score_few < score_many / 2


def test_ranking_monotonic_in_win_rate():
    a = _winning_stats(MIN_BETS_THRESHOLD)
    b = _winning_stats(MIN_BETS_THRESHOLD)
    b.win_rate = 40.0
    assert compute_ranking_score(a) > compute_ranking_score(b)
