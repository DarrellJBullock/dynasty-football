"""Playoffs: seeding when the regular season ends, round-by-round brackets, champion."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.playoffs import (
    Ranker,
    Result,
    TeamInfo,
    pair_round,
    round_names,
    seed_conference,
    seeds_per_conference,
)
from app.models import Conference, Game, PlayoffSeed, Season, Team
from app.services.errors import RosterError

if TYPE_CHECKING:
    from app.schemas import PlayoffsOut


def regular_week_count(db: Session, season_id: int) -> int:
    return db.scalar(select(func.max(Game.week)).where(
        Game.season_id == season_id, Game.stage == "regular")) or 0


def _teams(db: Session, league_id: int) -> list[TeamInfo]:
    rows = db.execute(select(Team.id, Team.division_id, Conference.id)
                      .join(Team.division).join(Conference)
                      .where(Team.league_id == league_id)).all()
    return [TeamInfo(id=tid, division=div, conference=conf) for tid, div, conf in rows]


def ranker(db: Session, season: Season) -> Ranker:
    games = db.scalars(select(Game).where(Game.season_id == season.id, Game.stage == "regular",
                                          Game.status == "final"))
    results = [Result(g.home_team_id, g.away_team_id, g.home_score, g.away_score) for g in games]
    return Ranker(_teams(db, season.league_id), results, salt=f"season:{season.id}")


def conference_ids(db: Session, league_id: int) -> list[int]:
    return list(db.scalars(select(Conference.id).where(Conference.league_id == league_id)
                           .order_by(Conference.id)))


def _round_names(db: Session, season: Season) -> list[str]:
    conferences = conference_ids(db, season.league_id)
    teams = db.scalar(select(func.count(Team.id)).join(Team.division)
                      .where(Team.league_id == season.league_id)) or 0
    return round_names(seeds_per_conference(teams // max(1, len(conferences))),
                       len(conferences))


def round_name(db: Session, season: Season, playoff_round: int) -> str:
    names = _round_names(db, season)
    return names[playoff_round - 1] if playoff_round <= len(names) else f"Round {playoff_round}"


def rounds_left(db: Session, season: Season) -> int:
    """Playoff rounds still to play (all of them before the playoffs start)."""
    played = {g.playoff_round for g in _playoff_games(db, season) if g.status == "final"}
    return max(0, len(_round_names(db, season)) - len(played))


def start(db: Session, season: Season) -> None:
    """Fix the seeds and schedule the first round. Called once the regular season ends."""
    rank = ranker(db, season)
    for conference_id in conference_ids(db, season.league_id):
        for seed in seed_conference(rank, conference_id):
            db.add(PlayoffSeed(season_id=season.id, conference_id=conference_id,
                               team_id=seed.team_id, seed=seed.seed,
                               division_winner=seed.division_winner))
    season.phase = "playoffs"
    db.flush()
    _schedule_next_round(db, season)


def _seeds(db: Session, season: Season) -> dict[int, dict[int, int]]:
    """conference_id -> {seed: team_id}"""
    result: dict[int, dict[int, int]] = {}
    for row in db.scalars(select(PlayoffSeed).where(PlayoffSeed.season_id == season.id)):
        result.setdefault(row.conference_id, {})[row.seed] = row.team_id
    return result


def _playoff_games(db: Session, season: Season) -> list[Game]:
    return list(db.scalars(select(Game).where(Game.season_id == season.id,
                                              Game.stage == "playoff").order_by(Game.id)))


def _winner(game: Game) -> int:
    return game.home_team_id if game.home_score > game.away_score else game.away_team_id


def _loser(game: Game) -> int:
    return game.away_team_id if game.home_score > game.away_score else game.home_team_id


def _schedule_next_round(db: Session, season: Season) -> None:
    games = _playoff_games(db, season)
    if any(g.status == "scheduled" for g in games):
        return
    eliminated = {_loser(g) for g in games}
    next_round = max((g.playoff_round for g in games), default=0) + 1
    week = regular_week_count(db, season.id) + next_round
    seeds = _seeds(db, season)
    champions = []
    new_games = []
    for by_seed in seeds.values():
        alive = [s for s, team in by_seed.items() if team not in eliminated]
        if len(alive) == 1:
            champions.append((by_seed[alive[0]], alive[0]))
            continue
        _, pairs = pair_round(alive)
        new_games += [Game(season_id=season.id, week=week, stage="playoff",
                           playoff_round=next_round, home_team_id=by_seed[high],
                           away_team_id=by_seed[low]) for high, low in pairs]
    if new_games:
        db.add_all(new_games)
    elif len(champions) == 1:
        season.champion_team_id = champions[0][0]
        season.phase = "offseason"
    else:
        # Conference champions meet at a neutral site; the better seed (then record) is
        # the designated home side.
        rank = ranker(db, season)
        order = sorted(champions, key=lambda c: (c[1], -rank.win_pct(c[0])))
        db.add(Game(season_id=season.id, week=week, stage="playoff", playoff_round=next_round,
                    home_team_id=order[0][0], away_team_id=order[1][0], neutral_site=True))
    db.flush()


def finish_round(db: Session, season: Season) -> None:
    """After a round's games are final, schedule the next one or crown the champion."""
    games = _playoff_games(db, season)
    final_round = [g for g in games if g.playoff_round == max(x.playoff_round for x in games)]
    if len(final_round) == 1 and final_round[0].neutral_site and final_round[0].status == "final":
        season.champion_team_id = _winner(final_round[0])
        season.phase = "offseason"
        db.flush()
        return
    _schedule_next_round(db, season)


def next_round_games(db: Session, season: Season) -> list[Game]:
    if season.phase != "playoffs":
        raise RosterError("There are no playoff games to play.")
    return [g for g in _playoff_games(db, season) if g.status == "scheduled"]


def playoffs_view(db: Session, season: Season) -> "PlayoffsOut":
    """The bracket: projected seeds during the regular season, then the real thing."""
    from app.schemas import PlayoffConference, PlayoffRound, PlayoffSeedOut, PlayoffsOut
    from app.services.season import season_view
    from app.services.serializers import game_out, team_summary
    from app.services.standings import compute_records

    conferences = db.scalars(select(Conference).where(Conference.league_id == season.league_id)
                             .order_by(Conference.id)).all()
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.league_id == season.league_id))}
    records = compute_records(db, season, list(teams))
    games = _playoff_games(db, season)
    eliminated = {_loser(g) for g in games if g.status == "final"}

    stored = _seeds(db, season)
    winners = {row.team_id for row in db.scalars(
        select(PlayoffSeed).where(PlayoffSeed.season_id == season.id,
                                  PlayoffSeed.division_winner))}
    if not stored:  # projected from current standings
        rank = ranker(db, season)
        for conference in conferences:
            projected = seed_conference(rank, conference.id)
            stored[conference.id] = {s.seed: s.team_id for s in projected}
            winners |= {s.team_id for s in projected if s.division_winner}

    view_conferences = []
    for conference in conferences:
        by_seed = stored.get(conference.id, {})
        view_conferences.append(PlayoffConference(conference=conference.name, seeds=[
            PlayoffSeedOut(seed=seed, team=team_summary(teams[team_id]),
                           wins=records[team_id].wins, losses=records[team_id].losses,
                           ties=records[team_id].ties, division_winner=team_id in winners,
                           eliminated=team_id in eliminated)
            for seed, team_id in sorted(by_seed.items())
        ]))

    seed_count = max((len(s) for s in stored.values()), default=0)
    names = round_names(seed_count, len(conferences)) if seed_count else []
    rounds = [PlayoffRound(round=i + 1, name=name,
                           games=[game_out(g) for g in games if g.playoff_round == i + 1])
              for i, name in enumerate(names)]
    status = ("complete" if season.champion_team_id else
              "in_progress" if season.phase == "playoffs" else "projected")
    champion = teams.get(season.champion_team_id) if season.champion_team_id else None
    return PlayoffsOut(season=season_view(db, season), status=status,
                       conferences=view_conferences, rounds=rounds,
                       champion=team_summary(champion) if champion else None)
