"""ORM -> API schema conversion, kept in one place so routes stay thin."""

from sqlalchemy.orm import object_session

from app.domain.positions import group_of
from app.domain.ratings import key_attributes
from app.models import Contract, Game, Job, League, Player, Season, Team
from app.schemas import (
    ContractOut,
    GameOut,
    JobOut,
    LeagueOut,
    PlayerDetail,
    PlayerSummary,
    SeasonOut,
    TeamSummary,
)

# Jobs that stop between steps when asked (the others run as one step).
CANCELLABLE_JOBS = {"sim_regular_season", "sim_playoffs", "finish_free_agency", "sim_seasons"}


def job_out(job: Job) -> JobOut:
    return JobOut(id=job.id, league_id=job.league_id, kind=job.kind, params=job.params,
                  status=job.status,
                  progress=job.progress, total=job.total, label=job.label,
                  cancellable=job.kind in CANCELLABLE_JOBS,
                  cancel_requested=job.cancel_requested, result=job.result, error=job.error)


def league_out(league: League) -> LeagueOut:
    return LeagueOut(id=league.id, name=league.name, abbreviation=league.abbreviation,
                     salary_cap=league.salary_cap, players=league.players)


def season_out(season: Season, weeks: int) -> SeasonOut:
    return SeasonOut(id=season.id, league_id=season.league_id, year=season.year,
                     phase=season.phase,
                     current_week=season.current_week, weeks=weeks,
                     regular_season_complete=season.current_week > weeks,
                     free_agency_day=season.free_agency_day
                     if season.phase == "free_agency" else None)


def team_summary(team: Team) -> TeamSummary:
    return TeamSummary(
        id=team.id,
        city=team.city,
        nickname=team.nickname,
        full_name=team.full_name,
        abbreviation=team.abbreviation,
        primary_color=team.primary_color,
        secondary_color=team.secondary_color,
        division=team.division.name,
        conference=team.division.conference.name,
    )


def contract_out(contract: Contract | None) -> ContractOut | None:
    if contract is None:
        return None
    return ContractOut(start_year=contract.start_year, years=contract.years,
                       end_year=contract.end_year, salary=contract.salary,
                       signing_bonus=contract.signing_bonus)


def _player_fields(player: Player) -> dict:
    ratings = player.ratings.as_dict()
    return dict(
        id=player.id,
        team_id=player.team_id,
        first_name=player.first_name,
        last_name=player.last_name,
        full_name=player.full_name,
        position=player.position,
        position_group=group_of(player.position),
        jersey_number=player.jersey_number,
        age=player.age,
        height_in=player.height_in,
        weight_lb=player.weight_lb,
        college=player.college,
        years_pro=player.years_pro,
        overall=player.overall,
        potential=player.potential,
        development_trait=player.development_trait,
        injury_status=player.injury_status,
        injury=player.injury,
        injury_weeks=player.injury_weeks,
        retired_year=player.retired_year,
        draft_year=player.draft_year,
        draft_round=player.draft_round,
        draft_pick=player.draft_pick,
        contract=contract_out(player.active_contract),
        key_ratings={name: ratings[name] for name in key_attributes(player.position)},
    )


def player_summary(player: Player) -> PlayerSummary:
    return PlayerSummary(**_player_fields(player))


def player_detail(player: Player) -> PlayerDetail:
    return PlayerDetail(**_player_fields(player), ratings=player.ratings.as_dict())


def game_out(game: Game) -> GameOut:
    round_name = None
    if game.stage == "playoff":
        from app.services.playoffs import round_name as playoff_round_name

        round_name = playoff_round_name(object_session(game), game.season, game.playoff_round)
    return GameOut(id=game.id, week=game.week, home=team_summary(game.home_team),
                   away=team_summary(game.away_team), home_score=game.home_score,
                   away_score=game.away_score, status=game.status,
                   overtime=bool(game.overtime), stage=game.stage, round_name=round_name,
                   neutral_site=bool(game.neutral_site))
