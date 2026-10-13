"""Trades: players and picks in the next draft. With an AI team, at once; with another
member's team, as an offer they answer (services/trade_offers.py).

The AI values each side with domain/trades.py and accepts when it comes out ahead by a
small margin (more for positions it needs). Both rosters must stay within 53 (or not
grow if already over) and both payrolls under the cap. Trades are open in the offseason,
free agency, the preseason, and the regular season through the deadline; closed during
the draft and the playoffs.
"""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.draft import draft_order
from app.domain.positions import ROSTER_MAX, ROSTER_TEMPLATE, available_jersey
from app.domain.trades import (
    TRADE_DEADLINE_WEEK,
    Asset,
    acceptable,
    ai_side,
    pick_value,
    player_value,
)
from app.models import Contract, DraftPick, League, Player, Season, Team, Trade
from app.schemas import (
    TradeAssetOut,
    TradeAssets,
    TradeCenter,
    TradeEvaluation,
    TradeOut,
    TradeProposal,
    TradeResult,
)
from app.services import cap, draft
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.members import human_team_ids
from app.services.season import season_view
from app.services.serializers import player_summary, team_summary
from app.services.teams import current_season, load_roster, payroll


def window(season: Season) -> str | None:
    """Why trades are closed right now, or None if they're open."""
    if season.phase == "draft":
        return "Trades are closed during the draft."
    if season.phase == "playoffs":
        return "Trades are closed during the playoffs."
    if season.phase == "regular_season" and season.current_week > TRADE_DEADLINE_WEEK:
        return f"The trade deadline (week {TRADE_DEADLINE_WEEK}) has passed."
    return None


def _value(player: Player, season: Season) -> float:
    contract = player.active_contract
    salary = contract.salary if contract else 0
    years_left = contract.end_year - season.year + 1 if contract else 0
    return player_value(player.position, player.overall, player.age, player.potential, salary,
                        years_left)


def _pick_label(pick: DraftPick) -> str:
    via = f" (from {pick.original_team.abbreviation})" if pick.original_team_id != pick.team_id \
        else ""
    number = f", #{pick.number}" if pick.number else ""
    return f"{pick.year} round {pick.round}{number}{via}"


def _slots(db: Session, league: League, season: Season, year: int) -> dict[int, int]:
    """Each team's projected spot (1 = first) in the `year` draft: last season's finish if
    this year's draft is next, the standings so far for next year's, else mid-round."""
    teams = list(db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)))
    source = None
    if year == season.year:
        source = db.scalar(select(Season).where(Season.league_id == league.id,
                                                Season.year == season.year - 1))
    elif season.phase in ("regular_season", "playoffs", "offseason"):
        source = season
    if source is None:
        return {t.id: (len(teams) + 1) // 2 for t in teams}
    finishes = draft._finishes(db, source, teams)
    order = draft_order(finishes, salt=f"draft:{league.id}:{year}")
    return {team_id: index + 1 for index, team_id in enumerate(order)}


class _Desk:
    """Everything a trade needs, loaded once."""

    def __init__(self, db: Session, league: League, team_id: int | None):
        self.db = db
        self.league = league
        self.season = current_season(db, league.id)
        # The next draft not yet held: this year's during free agency, next year's after.
        self.year = self.season.year + (0 if self.season.phase == "free_agency" else 1)
        self.team_count = len(league.teams)
        self.user_team = team_id  # the trading member's team
        self.humans = human_team_ids(db, league.id)  # (their managers answer offers)
        self.slots = _slots(db, league, self.season, self.year)

    def picks(self, team_id: int) -> list[DraftPick]:
        picks = draft.ensure_picks(self.db, self.league, self.year)
        return sorted((p for p in picks if p.team_id == team_id and p.player_id is None),
                      key=lambda p: (p.round, self.expected(p)))

    def expected(self, pick: DraftPick) -> int:
        return pick.number or (pick.round - 1) * self.team_count + self.slots[pick.original_team_id]

    def pick_value(self, pick: DraftPick) -> float:
        return pick_value(self.expected(pick))

    def roster(self, team_id: int) -> list[Player]:
        return [p for p in load_roster(self.db, team_id) if not p.is_prospect]


def _asset_out(desk: _Desk, item: Player | DraftPick) -> TradeAssetOut:
    if isinstance(item, Player):
        return TradeAssetOut(kind="player", id=item.id, label=item.full_name,
                             value=round(_value(item, desk.season), 1),
                             player=player_summary(item))
    return TradeAssetOut(kind="pick", id=item.id, label=_pick_label(item),
                         value=round(desk.pick_value(item), 1),
                         round=item.round, year=item.year,
                         projected_number=desk.expected(item))


def _assets(desk: _Desk, team_id: int) -> TradeAssets:
    roster = sorted(desk.roster(team_id), key=lambda p: (-_value(p, desk.season), p.id))
    return TradeAssets(players=[_asset_out(desk, p) for p in roster],
                       picks=[_asset_out(desk, p) for p in desk.picks(team_id)])


def trade_center(db: Session, league: League, partner_id: int | None,
                 team_id: int | None = None, commissioner: bool = False) -> TradeCenter:
    """The trade desk for `team_id`'s manager: every other team to deal with (the AI's at
    once, members' by offer), their offers, and their trades."""
    from app.services import trade_offers

    trade_offers.settle(db, league)
    desk = _Desk(db, league, team_id)
    teams = [t for t in league.teams if t.id != team_id]
    partner = next((t for t in teams if t.id == partner_id), None) or next(
        (t for t in teams if t.id not in desk.humans), teams[0] if teams else None)
    mine = Trade.team_id == (team_id or 0)
    history = db.scalars(select(Trade).where(Trade.league_id == league.id,
                                             mine | (Trade.partner_id == (team_id or 0)))
                         .order_by(Trade.id.desc()).limit(20)).all()
    return TradeCenter(
        season=season_view(db, desk.season), closed_reason=window(desk.season),
        deadline_week=TRADE_DEADLINE_WEEK, draft_year=desk.year,
        partners=[team_summary(t) for t in teams],
        partner=team_summary(partner) if partner else None,
        partner_manager=trade_offers.manager_name(db, partner.id) if partner else None,
        managed=sorted(desk.humans - {team_id}),
        mine=_assets(desk, desk.user_team) if desk.user_team else TradeAssets(players=[],
                                                                                 picks=[]),
        theirs=_assets(desk, partner.id) if partner else TradeAssets(players=[], picks=[]),
        history=[_trade_out(t, team_id) for t in history],
        offers=trade_offers.offers_for(db, league, team_id, commissioner),
        review_hours=league.trade_review_hours)


def _trade_out(trade: Trade, viewer: int | None = None) -> TradeOut:
    """The trade from `viewer`'s side (the proposer's, unless the viewer took the other)."""
    if viewer is not None and viewer == trade.partner_id:
        return TradeOut(id=trade.id, partner=team_summary(trade.team),
                        season_phase=trade.phase, week=trade.week, sent=trade.received,
                        received=trade.sent)
    return TradeOut(id=trade.id, partner=team_summary(trade.partner),
                    season_phase=trade.phase, week=trade.week, sent=trade.sent,
                    received=trade.received)


class _Deal:
    """A proposal resolved into players and picks, with each side's constraints."""

    def __init__(self, desk: _Desk, proposal: TradeProposal):
        self.desk = desk
        db = desk.db
        if desk.user_team is None:
            raise RosterError("You don't run a team in this league.", 400)
        partner = db.get(Team, proposal.partner_id)
        if partner is None or partner.league_id != desk.league.id or partner.id == desk.user_team:
            raise RosterError("Choose another team in this league.", 404)
        self.partner = partner
        self.managed = partner.id in desk.humans  # (its manager answers: an offer)
        self.send = self._players(proposal.send_players, desk.user_team) + \
            self._picks(proposal.send_picks, desk.user_team)
        self.receive = self._players(proposal.receive_players, partner.id) + \
            self._picks(proposal.receive_picks, partner.id)
        if not self.send and not self.receive:
            raise RosterError("Add players or picks to the trade.")

    def _players(self, ids: Sequence[int], team_id: int) -> list[Player]:
        players = [self.desk.db.get(Player, pid) for pid in dict.fromkeys(ids)]
        if any(p is None or p.team_id != team_id or p.is_prospect for p in players):
            raise RosterError("A player in the trade isn't on that team.")
        return players

    def _picks(self, ids: Sequence[int], team_id: int) -> list[DraftPick]:
        picks = [self.desk.db.get(DraftPick, pid) for pid in dict.fromkeys(ids)]
        if any(p is None or p.team_id != team_id or p.player_id is not None
               or p.league_id != self.desk.league.id or p.year != self.desk.year
               for p in picks):
            raise RosterError(f"Only unused picks in the {self.desk.year} draft can be traded.")
        return picks

    def problems(self) -> list[str]:
        desk, problems = self.desk, []
        salary_cap = desk.league.salary_cap
        year = cap.cap_year(desk.season)
        sides = ((desk.user_team, self.send, self.receive, "Your"),
                 (self.partner.id, self.receive, self.send, f"The {self.partner.nickname}'"))
        for team_id, out, into, whose in sides:
            roster = desk.roster(team_id)
            out_players = [a for a in out if isinstance(a, Player)]
            in_players = [a for a in into if isinstance(a, Player)]
            size = len(roster) - len(out_players) + len(in_players)
            if size > max(ROSTER_MAX, len(roster)):
                problems.append(f"{whose} roster would have {size} players (max {ROSTER_MAX}).")
            # Trading a player away leaves the rest of his bonus behind as dead money.
            current = payroll(roster) + cap.dead_money_for(desk.db, team_id, year)
            new_payroll = (current - payroll(out_players) + payroll(in_players)
                           + sum(cap.release_cost(p.active_contract, year) for p in out_players))
            if new_payroll > salary_cap and new_payroll > current:
                problems.append(f"{whose} payroll would be over the cap.")
        return problems

    def evaluate(self) -> TradeEvaluation:
        desk = self.desk
        problems = [reason] if (reason := window(desk.season)) else []
        problems += self.problems()
        needs = _needs(desk.roster(self.partner.id))
        best = defaultdict(int)
        for player in desk.roster(self.partner.id):
            best[player.position] = max(best[player.position], player.overall)
        received = [Asset(_value(p, desk.season), needed=p.position in needs
                          or p.overall >= best[p.position])
                    if isinstance(p, Player) else Asset(desk.pick_value(p))
                    for p in self.send]
        given = [Asset(_value(p, desk.season)) if isinstance(p, Player)
                 else Asset(desk.pick_value(p)) for p in self.receive]
        gets, wants = ai_side(received, given)
        balance = round(gets / wants, 2) if wants else (2.0 if gets else 0.0)
        ok = acceptable(gets, wants)
        if self.managed:  # (the meter still shows how the AI would see it, as a guide)
            ok = True
        if problems:
            message = problems[0]
        elif self.managed:
            message = f"The {self.partner.nickname}' manager decides: send them an offer."
        elif ok:
            message = f"The {self.partner.nickname} would accept this trade."
        else:
            message = (f"The {self.partner.nickname} want more: about {wants - gets:.0f} more "
                       "trade value.")
        return TradeEvaluation(acceptable=ok and not problems, balance=min(balance, 2.0),
                               message=message, problems=problems,
                               value_in=round(gets, 1), value_needed=round(wants, 1))


def _needs(roster: list[Player]) -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    for player in roster:
        counts[player.position] += 1
    return {p.value for p, n in ROSTER_TEMPLATE.items() if counts[p.value] < n}


def evaluate(db: Session, league: League, proposal: TradeProposal,
             team_id: int | None) -> TradeEvaluation:
    return _Deal(_Desk(db, league, team_id), proposal).evaluate()


def propose(db: Session, league: League, proposal: TradeProposal,
            team_id: int | None) -> TradeResult:
    deal = _Deal(_Desk(db, league, team_id), proposal)
    if deal.managed:
        raise RosterError("Another member runs that team: send them an offer.")
    evaluation = deal.evaluate()
    if not evaluation.acceptable:
        return TradeResult(accepted=False, evaluation=evaluation, trade=None)
    trade = _execute(db, deal)
    return TradeResult(accepted=True, evaluation=evaluation, trade=_trade_out(trade))


def _move_contract(db: Session, player: Player, to_team: int, year: int) -> None:
    """His old team keeps the rest of his signing bonus as dead money; the new team takes
    his salary for the seasons left, with no bonus."""
    old = player.active_contract
    if old is None:
        return
    cap.charge(db, player, old, year, "traded")
    old.is_active = False
    remaining = old.end_year - year + 1
    if remaining > 0:
        player.contracts.append(Contract(team_id=to_team, start_year=year, years=remaining,
                                         salary=old.salary, signing_bonus=0))


def _execute(db: Session, deal: _Deal) -> Trade:
    desk = deal.desk
    user, partner = desk.user_team, deal.partner.id

    def label(item: Player | DraftPick) -> dict:
        if isinstance(item, Player):
            return {"kind": "player", "id": item.id,
                    "label": f"{item.position} {item.full_name} ({item.overall})"}
        return {"kind": "pick", "id": item.id, "label": _pick_label(item)}

    sent, received = [label(a) for a in deal.send], [label(a) for a in deal.receive]
    for items, to_team in ((deal.send, partner), (deal.receive, user)):
        taken = {p.jersey_number for p in desk.roster(to_team)}
        for item in items:
            if isinstance(item, DraftPick):
                item.team_id = to_team
                continue
            remove_player(db, item)
            if item.jersey_number in taken:
                item.jersey_number = available_jersey(item.position, taken)
            taken.add(item.jersey_number)
            item.team_id = to_team
            _move_contract(db, item, to_team, cap.cap_year(desk.season))
    trade = Trade(league_id=desk.league.id, season_id=desk.season.id, team_id=user,
                  partner_id=partner, phase=desk.season.phase, week=desk.season.current_week,
                  sent=sent, received=received)
    db.add(trade)
    db.flush()
    return trade

