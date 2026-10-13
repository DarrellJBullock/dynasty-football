"""A team's money (docs/design/owners-and-front-offices.md §3; the rules: domain/money.py).

Nothing is stored week by week: a season's finances are worked out from its games (each
home game's gate from the fans' mood going into it, which comes from the record so far),
the media share, merchandise, and what the team pays its players and staff. When the
season ends, the owner's review keeps them (`OwnerSeason.finances`).
"""

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import money as rules
from app.domain import owners as owner_rules
from app.models import Game, OwnerSeason, Season, Team
from app.schemas import FinanceLine, FinancesOut, FinanceYear, GateOut, TicketPriceOut
from app.services import cap
from app.services.errors import RosterError
from app.services.serializers import team_summary
from app.services.teams import current_season, load_roster, payroll

LOCKED = ("regular_season", "playoffs")


@dataclass
class Finances:
    """A team's season so far (or, once it's over, all of it)."""
    gates: list[rules.Gate] = field(default_factory=list)
    media: int = 0
    merchandise: int = 0
    players: int = 0
    dead_money: int = 0
    staff: int = 0
    share: float = 0.0  # of the regular season played
    projected_profit: int = 0  # the season's, at this pace

    @property
    def tickets(self) -> int:
        return sum(g.revenue for g in self.gates if not g.playoff)

    @property
    def playoff_gates(self) -> int:
        return sum(g.revenue for g in self.gates if g.playoff)

    @property
    def revenue(self) -> int:
        return self.tickets + self.playoff_gates + self.media + self.merchandise

    @property
    def expenses(self) -> int:
        return self.players + self.dead_money + self.staff

    @property
    def profit(self) -> int:
        return self.revenue - self.expenses

    def summary(self, price: str) -> dict:
        """What the owner's review keeps."""
        return {"ticket_price": price, "home_games": len(self.gates),
                "attendance": round(sum(g.attendance for g in self.gates)
                                    / max(1, len(self.gates))),
                "tickets": self.tickets, "playoff_gates": self.playoff_gates,
                "media": self.media, "merchandise": self.merchandise,
                "revenue": self.revenue, "players": self.players,
                "dead_money": self.dead_money, "staff": self.staff,
                "expenses": self.expenses, "profit": self.profit}


def _weeks(db: Session, season: Season) -> int:
    from app.services.season import season_weeks  # (the season services build on money)

    return season_weeks(db, season.id)


def base_mood(db: Session, season: Season, team: Team) -> int:
    """The fans' mood when the season started."""
    row = db.scalar(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                              OwnerSeason.team_id == team.id))
    if row is not None and row.fan_mood_before is not None:
        return row.fan_mood_before
    return team.fan_mood if team.fan_mood is not None else 50


def season_finances(db: Session, season: Season, team: Team) -> Finances:
    from app.services.carousel import payroll as staff_payroll  # (it builds on seasons)

    league = team.league
    market = team.market or "medium"
    price = team.ticket_price
    weeks = _weeks(db, season)
    base = base_mood(db, season, team)
    roster = load_roster(db, team.id)
    stars = sum(1 for p in roster if p.overall >= owner_rules.STAR_OVERALL)
    seat = rules.ticket_price(market, price, league.salary_cap)

    games = db.scalars(select(Game).where(
        Game.season_id == season.id, Game.status == "final",
        or_(Game.home_team_id == team.id, Game.away_team_id == team.id))
        .order_by(Game.stage.desc(), Game.week, Game.id)).all()  # (regular, then playoffs)
    wins = losses = ties = 0
    result = Finances()
    for game in games:
        playoff = game.stage == "playoff"
        if game.home_team_id == team.id and not game.neutral_site:
            mood = owner_rules.fan_mood(base, owner_rules.Season(
                wins=wins, losses=losses, ties=ties, weeks=weeks, stars=stars,
                ticket_price=price))
            sold = rules.attendance(market, mood, price)
            each = round(seat * rules.PLAYOFF_GATE) if playoff else seat
            result.gates.append(rules.Gate(game.id, game.week, playoff, mood, sold, each,
                                           sold * each))
        if not playoff:
            ours, theirs = ((game.home_score, game.away_score) if game.home_team_id == team.id
                            else (game.away_score, game.home_score))
            wins += ours > theirs
            losses += ours < theirs
            ties += ours == theirs

    played = wins + losses + ties
    result.share = min(1.0, played / weeks) if weeks else 0.0
    win_pct = (wins + 0.5 * ties) / played if played else 0.5
    year = season.year
    full = {"media": rules.media(league.salary_cap),
            "merchandise": rules.merchandise(league.salary_cap, market, stars, win_pct),
            "players": payroll(roster), "dead_money": cap.dead_money_for(db, team.id, year),
            "staff": staff_payroll(db, team.id, year)}
    for name, amount in full.items():
        setattr(result, name, round(amount * result.share))

    # At this pace: the rest of the home games at today's gate, a full season's media and
    # merchandise, and a full season's costs.
    home_left = sum(1 for g in db.scalars(select(Game).where(
        Game.season_id == season.id, Game.stage == "regular", Game.status == "scheduled",
        Game.home_team_id == team.id, Game.neutral_site.is_(False))))
    mood_now = owner_rules.fan_mood(base, owner_rules.Season(
        wins=wins, losses=losses, ties=ties, weeks=weeks, stars=stars, ticket_price=price))
    gate_now = rules.attendance(market, mood_now, price) * seat
    result.projected_profit = (result.tickets + result.playoff_gates + home_left * gate_now
                               + full["media"] + full["merchandise"]
                               - full["players"] - full["dead_money"] - full["staff"])
    return result


def set_ticket_price(db: Session, team: Team, price: str) -> None:
    """The team's ticket price, for the coming season: changed between seasons only."""
    if price not in rules.TICKET_PRICES:
        raise RosterError("A ticket price is low, normal or high.", 422)
    season = current_season(db, team.league_id)
    if season is not None and season.phase in LOCKED:
        raise RosterError("Ticket prices are set before the season: change them once it's "
                          "over.")
    team.ticket_price = price
    db.flush()


# ---------- the view ----------

def finances_view(db: Session, team: Team) -> FinancesOut:
    from app.services.owners import ensure_owners  # (owners build on money)

    ensure_owners(db, team.league)
    season = current_season(db, team.league_id)
    market = team.market or "medium"
    cap_ = team.league.salary_cap
    result = season_finances(db, season, team) if season else Finances()
    opponents = {g.id: (g.away_team if g.home_team_id == team.id else g.home_team).abbreviation
                 for g in db.scalars(select(Game).where(
                     Game.id.in_([gate.game_id for gate in result.gates])))}
    history = []
    for row, year in db.execute(select(OwnerSeason, Season.year).join(Season).where(
            OwnerSeason.team_id == team.id, OwnerSeason.finances.is_not(None))
            .order_by(Season.year.desc())):
        f = row.finances
        history.append(FinanceYear(year=year, revenue=f["revenue"], expenses=f["expenses"],
                                   profit=f["profit"]))
    return FinancesOut(
        team=team_summary(team), season_year=season.year if season else None, market=market,
        capacity=rules.CAPACITY[market], ticket_price=team.ticket_price,
        prices=[TicketPriceOut(price=p, label=rules.PRICE_LABELS[p],
                               seat=rules.ticket_price(market, p, cap_))
                for p in rules.TICKET_PRICES],
        price_locked=("Ticket prices are set before the season: change them once it's over."
                      if season and season.phase in LOCKED else None),
        share=round(result.share, 3),
        gates=[GateOut(game_id=g.game_id, week=g.week, playoff=g.playoff,
                       opponent=opponents.get(g.game_id, ""), fan_mood=g.mood,
                       attendance=g.attendance, capacity=rules.CAPACITY[market], price=g.price,
                       revenue=g.revenue) for g in result.gates],
        revenue=[FinanceLine(label=label, amount=amount) for label, amount in (
            ("Tickets", result.tickets), ("Playoff gates", result.playoff_gates),
            ("Media", result.media), ("Merchandise", result.merchandise))],
        expenses=[FinanceLine(label=label, amount=amount) for label, amount in (
            ("Players", result.players), ("Dead money", result.dead_money),
            ("Staff and facilities", result.staff))],
        total_revenue=result.revenue, total_expenses=result.expenses, profit=result.profit,
        projected_profit=result.projected_profit, history=history)
