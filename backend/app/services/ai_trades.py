"""AI front offices trade (docs/design/owners-and-front-offices.md §5): they offer managers
trades, and trade with each other near the deadline, by their direction
(services/direction.py).

- **Offers to managers** (`offer_managers`): after each week through the deadline, and when
  the preseason opens, a member may get one, never more than one open at a time. A
  contending AI team offers picks for a member's player at a position it needs; a rebuilder
  offers a veteran for picks. Each says why. They're ordinary trade offers (accept, reject,
  counter: the AI answers a counter at once).
- **Deadline deals** (`deadline_deals`): in the last weeks before the deadline, sometimes a
  contender buys a veteran from a rebuilder.

Every draw comes from `random.Random(f"ai-trades:{league}:{year}:{week}")`, never the game's
or the generator's streams. An AI team wants a little more than it gives, as it does
answering a member's offer (domain/trades.ai_side).
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.trades import AI_MARGIN, TRADE_DEADLINE_WEEK
from app.models import DraftPick, League, Player, Season, TradeOffer
from app.schemas import TradeProposal
from app.services import direction, trades
from app.services.members import human_team_ids
from app.services.notifications import notify_team

OFFER_CHANCE = 0.35  # each member, each week, of an AI offer (with none open already)
DEADLINE_WEEKS = 3  # deadline deals happen in the deadline's week and the ones before it
DEADLINE_DEAL_CHANCE = 0.5  # each of those weeks
UPGRADE = 5  # a buyer wants a player at least this much better than its starter there
VETERAN_AGE = 29  # a rebuilder sells players this old...
VETERAN_OVERALL = 74  # ...and at least this good
YOUNG_BACKUP = 26  # teams pay with picks and backups this young or younger
OFFER_DAYS = 3


def _rng(league: League, season: Season, week: int) -> random.Random:
    return random.Random(f"ai-trades:{league.id}:{season.year}:{week}")


def _starters(roster: list[Player]) -> dict[str, int]:
    best: dict[str, int] = {}
    for player in roster:
        best[player.position] = max(best.get(player.position, 0), player.overall)
    return best


def _value(desk: trades._Desk, item: Player | DraftPick) -> float:
    return trades._value(item, desk.season) if isinstance(item, Player) else desk.pick_value(item)


def _room(desk: trades._Desk, team_id: int) -> int:
    """Players a team could take in for one going out (its open roster spots, and the one)."""
    return desk.league.roster_max - len(desk.roster(team_id)) + 1


def _payment(desk: trades._Desk, assets: list[Player | DraftPick], target: float,
             at_least: bool, players: int) -> list[Player | DraftPick] | None:
    """Assets adding up to about `target` value: just over it (`at_least`), or as close
    under it as can be (most valuable first), with at most `players` players (the other
    side's roster room)."""
    chosen: list[Player | DraftPick] = []
    total = 0.0
    for asset in sorted(assets, key=lambda a: (-_value(desk, a), a.id)):
        if isinstance(asset, Player) and sum(isinstance(c, Player) for c in chosen) >= players:
            continue
        value = _value(desk, asset)
        if at_least:
            if total >= target:
                break
            chosen.append(asset)
            total += value
        elif total + value <= target:
            chosen.append(asset)
            total += value
    if at_least:
        return chosen if total >= target else None
    return chosen if chosen and total >= target * 0.8 else None


def _currency(desk: trades._Desk, team_id: int) -> list[Player | DraftPick]:
    """What a team trades with: its picks, and its young backups (26 or younger, and not
    the best at their position)."""
    roster = desk.roster(team_id)
    best = _starters(roster)
    backups = [p for p in roster if p.age <= YOUNG_BACKUP and p.overall < best[p.position]]
    return [*desk.picks(team_id), *backups]


def _buy(desk: trades._Desk, buyer: int, seller: int) -> tuple[Player, list] | None:
    """A buyer's target on the seller's roster (at a position it needs an upgrade, the
    biggest it can afford), and what it would pay: a little less than he's worth to it."""
    mine = _starters(desk.roster(buyer))
    targets = sorted((p for p in desk.roster(seller)
                      if p.overall >= mine.get(p.position, 0) + UPGRADE and p.age <= 31),
                     key=lambda p: (-(p.overall - mine.get(p.position, 0)), -p.overall, p.id))
    currency = _currency(desk, buyer)
    for target in targets:
        paid = _payment(desk, currency, _value(desk, target) / (1 + AI_MARGIN), False,
                        _room(desk, seller))
        if paid:
            return target, paid
    return None


def _sell(desk: trades._Desk, seller: int, buyer: int) -> tuple[Player, list] | None:
    """A rebuilder's veteran the buyer could use, and what it would ask (picks and young
    backups): a little more than he's worth."""
    theirs = _starters(desk.roster(buyer))
    veterans = sorted((p for p in desk.roster(seller)
                       if p.age >= VETERAN_AGE and p.overall >= VETERAN_OVERALL
                       and p.overall >= theirs.get(p.position, 0) + UPGRADE),
                      key=lambda p: (-p.overall, p.id))
    currency = _currency(desk, buyer)
    for veteran in veterans:
        asked = _payment(desk, currency, _value(desk, veteran) * (1 + AI_MARGIN), True,
                         _room(desk, seller))
        if asked:
            return veteran, asked
    return None


def _ids(items: list[Player | DraftPick], kind: type) -> list[int]:
    return [i.id for i in items if isinstance(i, kind)]


# ---------- offers to managers ----------

def offer_managers(db: Session, league: League, season: Season, week: int) -> list[TradeOffer]:
    """This week's AI offers to managers (with the trade window open)."""
    if trades.window(season) is not None:
        return []
    direction.ensure(db, league)
    humans = sorted(human_team_ids(db, league.id))
    if not humans:
        return []
    rng = _rng(league, season, week)
    teams = {t.id: t for t in league.teams}
    shoppers = sorted((t for t in league.teams if t.id not in humans
                       and t.direction in ("contend", "rebuild")), key=lambda t: t.id)
    made = []
    for member in humans:
        if rng.random() >= OFFER_CHANCE or not shoppers:
            continue
        if db.scalar(select(TradeOffer.id).where(
                TradeOffer.league_id == league.id, TradeOffer.to_team_id == member,
                TradeOffer.status == "pending",
                TradeOffer.from_team_id.not_in(humans)).limit(1)):
            continue  # (one open AI offer at a time)
        ai = rng.choice(shoppers)
        desk = trades._Desk(db, league, ai.id)
        if ai.direction == "contend":
            found = _buy(desk, ai.id, member)
            if found is None:
                continue
            player, paid = found
            send, receive = paid, [player]
            note = (f"The {ai.nickname} are contending and want {player.position} "
                    f"{player.full_name}.")
        else:
            found = _sell(desk, ai.id, member)
            if found is None:
                continue
            player, asked = found
            send, receive = [player], asked
            note = (f"The {ai.nickname} are rebuilding: {player.position} {player.full_name} "
                    "could help you now.")
        proposal = TradeProposal(partner_id=member, send_players=_ids(send, Player),
                                 send_picks=_ids(send, DraftPick),
                                 receive_players=_ids(receive, Player),
                                 receive_picks=_ids(receive, DraftPick))
        deal = trades._Deal(desk, proposal)
        if deal.problems():
            continue
        offer = TradeOffer(
            league_id=league.id, season_id=season.id, from_team_id=ai.id, to_team_id=member,
            send=[{"kind": "player" if isinstance(a, Player) else "pick", "id": a.id}
                  for a in deal.send],
            receive=[{"kind": "player" if isinstance(a, Player) else "pick", "id": a.id}
                     for a in deal.receive],
            note=note, status="pending", from_ai=True,
            expires_at=datetime.now(UTC) + timedelta(days=OFFER_DAYS))
        db.add(offer)
        db.flush()
        from app.services.trade_offers import _summary  # (offers build on trades)

        notify_team(db, member, "trade_offer", f"The {teams[ai.id].full_name} offer a trade",
                    f"{_summary(db, offer, member)} “{note}”", f"/trades?partner={ai.id}")
        made.append(offer)
    return made


# ---------- AI-to-AI deadline deals ----------

def deadline_deals(db: Session, league: League, season: Season, week: int) -> list:
    """Sometimes, in the weeks before the deadline, a contender buys a veteran from a
    rebuilder (the rebuilder takes picks, a little more than he's worth)."""
    if (season.phase != "regular_season" or week > TRADE_DEADLINE_WEEK
            or week <= TRADE_DEADLINE_WEEK - DEADLINE_WEEKS):
        return []
    rng = _rng(league, season, -week)
    if rng.random() >= DEADLINE_DEAL_CHANCE:
        return []
    direction.ensure(db, league)
    humans = human_team_ids(db, league.id)
    ai = sorted((t for t in league.teams if t.id not in humans), key=lambda t: t.id)
    buyers = [t for t in ai if t.direction == "contend"]
    sellers = [t for t in ai if t.direction == "rebuild"]
    rng.shuffle(buyers)
    rng.shuffle(sellers)
    for buyer in buyers:
        for seller in sellers:
            desk = trades._Desk(db, league, buyer.id)
            found = _sell(desk, seller.id, buyer.id)
            if found is None:
                continue
            veteran, picks = found
            deal = trades._Deal(desk, TradeProposal(partner_id=seller.id,
                                                    send_players=_ids(picks, Player),
                                                    send_picks=_ids(picks, DraftPick),
                                                    receive_players=[veteran.id]))
            if deal.problems() or not deal.evaluate().acceptable:
                continue
            return [trades._execute(db, deal)]
    return []


def after_week(db: Session, season: Season, week: int) -> None:
    """The front offices' week: a deadline deal, maybe, then offers to managers."""
    league = db.get(League, season.league_id)
    deadline_deals(db, league, season, week)
    offer_managers(db, league, season, week)

