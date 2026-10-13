"""Trades between managers (docs/design/leagues-with-friends.md §5): one member offers
another a trade, who accepts, rejects or counters it. Offers expire after a few days, and
one whose players or picks have moved since is no longer valid. If the league has a veto
window, an accepted trade waits it out for the commissioner before it goes through.

Offers settle lazily: whenever a league's offers are read or answered (and on the worker's
minute), expired ones expire, invalid ones are marked, and finished reviews go through.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DraftPick, League, Player, TradeOffer
from app.schemas import TradeOfferItem, TradeOfferOut, TradeProposal
from app.services import trades
from app.services.errors import RosterError
from app.services.members import display_name, human_team_ids, manager_of
from app.services.serializers import team_summary
from app.services.teams import current_season

OFFER_DAYS = 3
REVIEW_HOURS = (0, 24, 48)  # the commissioner's veto window, to choose from
OPEN = ("pending", "review")


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def manager_name(db: Session, team_id: int) -> str | None:
    """The display name of whoever runs the team (None: the AI)."""
    from app.models import User

    user_id = manager_of(db, team_id)
    return display_name(db.get(User, user_id)) if user_id else None


def _proposal(offer: TradeOffer) -> TradeProposal:
    """The offer as its sender's proposal."""
    def ids(items: list, kind: str) -> list[int]:
        return [i["id"] for i in items if i["kind"] == kind]
    return TradeProposal(partner_id=offer.to_team_id,
                         send_players=ids(offer.send, "player"), send_picks=ids(offer.send, "pick"),
                         receive_players=ids(offer.receive, "player"),
                         receive_picks=ids(offer.receive, "pick"))


def _deal(db: Session, league: League, team_id: int, proposal: TradeProposal) -> "trades._Deal":
    deal = trades._Deal(trades._Desk(db, league, team_id), proposal)
    if not deal.managed:
        raise RosterError("The AI runs that team: propose the trade, and they answer at once.")
    return deal


def _check(deal: "trades._Deal") -> None:
    """Refuse a deal the window, a roster or a payroll won't allow."""
    reason = trades.window(deal.desk.season)
    problems = ([reason] if reason else []) + deal.problems()
    if problems:
        raise RosterError(problems[0])


def make(db: Session, league: League, team_id: int | None, proposal: TradeProposal,
         note: str | None = None, parent: TradeOffer | None = None) -> TradeOffer:
    """`team_id`'s manager offers a trade to another member's team."""
    deal = _deal(db, league, team_id, proposal)
    _check(deal)
    offer = TradeOffer(
        league_id=league.id, season_id=deal.desk.season.id, from_team_id=team_id,
        to_team_id=deal.partner.id, parent_id=parent.id if parent else None,
        send=[{"kind": "player" if isinstance(a, Player) else "pick", "id": a.id}
              for a in deal.send],
        receive=[{"kind": "player" if isinstance(a, Player) else "pick", "id": a.id}
                 for a in deal.receive],
        note=(note or "").strip() or None, status="pending",
        expires_at=_now() + timedelta(days=OFFER_DAYS))
    db.add(offer)
    db.flush()
    return offer


def _get(db: Session, league: League, offer_id: int) -> TradeOffer:
    offer = db.get(TradeOffer, offer_id)
    if offer is None or offer.league_id != league.id:
        raise RosterError("Offer not found.", 404)
    return offer


def _open(db: Session, offer: TradeOffer, *statuses: str) -> None:
    settle(db, db.get(League, offer.league_id))
    if offer.status not in statuses:
        raise RosterError(f"This offer is {offer.status} now.")


def accept(db: Session, offer: TradeOffer, team_id: int | None) -> TradeOffer:
    """The receiving manager says yes: the trade goes through now, or after the
    commissioner's veto window."""
    if team_id != offer.to_team_id:
        raise RosterError("Only the team the offer was made to can accept it.", 403)
    _open(db, offer, "pending")
    league = db.get(League, offer.league_id)
    deal = _deal(db, league, offer.from_team_id, _proposal(offer))
    _check(deal)
    offer.decided_at = _now()
    if league.trade_review_hours:
        offer.status = "review"
        offer.review_ends_at = offer.decided_at + timedelta(hours=league.trade_review_hours)
        db.flush()
        return offer
    _complete(db, offer, deal)
    return offer


def _complete(db: Session, offer: TradeOffer, deal: "trades._Deal") -> None:
    trade = trades._execute(db, deal)
    offer.status = "accepted"
    offer.trade_id = trade.id
    db.flush()
    _invalidate_moved(db, offer.league_id)  # (other offers with these players are stale)


def reject(db: Session, offer: TradeOffer, team_id: int | None) -> TradeOffer:
    if team_id != offer.to_team_id:
        raise RosterError("Only the team the offer was made to can reject it.", 403)
    _open(db, offer, "pending")
    offer.status, offer.decided_at = "rejected", _now()
    db.flush()
    return offer


def withdraw(db: Session, offer: TradeOffer, team_id: int | None) -> TradeOffer:
    if team_id != offer.from_team_id:
        raise RosterError("Only the team that made the offer can withdraw it.", 403)
    _open(db, offer, "pending")
    offer.status, offer.decided_at = "withdrawn", _now()
    db.flush()
    return offer


def counter(db: Session, offer: TradeOffer, team_id: int | None, proposal: TradeProposal,
            note: str | None = None) -> TradeOffer:
    """Answer an offer with another: from the receiving team, back to the sender."""
    if team_id != offer.to_team_id:
        raise RosterError("Only the team the offer was made to can counter it.", 403)
    if proposal.partner_id != offer.from_team_id:
        raise RosterError("A counter-offer goes back to the team that made the offer.")
    _open(db, offer, "pending")
    countered = make(db, db.get(League, offer.league_id), team_id, proposal, note, parent=offer)
    offer.status, offer.decided_at = "countered", _now()
    db.flush()
    return countered


def veto(db: Session, offer: TradeOffer, reason: str | None = None) -> TradeOffer:
    """The commissioner stops an accepted trade during the veto window."""
    _open(db, offer, "review")
    offer.status = "vetoed"
    offer.reason = (reason or "").strip() or "Vetoed by the commissioner."
    db.flush()
    return offer


def approve(db: Session, offer: TradeOffer) -> TradeOffer:
    """The commissioner lets an accepted trade through before the window ends."""
    _open(db, offer, "review")
    league = db.get(League, offer.league_id)
    deal = _deal(db, league, offer.from_team_id, _proposal(offer))
    _check(deal)
    _complete(db, offer, deal)
    return offer


# ---------- settling ----------

def _moved(db: Session, offer: TradeOffer) -> bool:
    """Something in the offer isn't where it was (traded, released, or a pick used)."""
    for items, team_id in ((offer.send, offer.from_team_id), (offer.receive, offer.to_team_id)):
        for item in items:
            if item["kind"] == "player":
                player = db.get(Player, item["id"])
                if player is None or player.team_id != team_id:
                    return True
            else:
                pick = db.get(DraftPick, item["id"])
                if pick is None or pick.team_id != team_id or pick.player_id is not None:
                    return True
    return False


def _invalidate_moved(db: Session, league_id: int) -> None:
    humans = human_team_ids(db, league_id)
    for offer in db.scalars(select(TradeOffer).where(TradeOffer.league_id == league_id,
                                                     TradeOffer.status.in_(OPEN))):
        if _moved(db, offer) or not {offer.from_team_id, offer.to_team_id} <= humans:
            offer.status = "invalid"
            offer.reason = "A player or pick in it moved, or a manager left."
    db.flush()


def settle(db: Session, league: League, now: datetime | None = None) -> None:
    """Expire old offers, mark ones whose players or picks moved, and put through
    trades whose veto window has ended (or void them if they can't go through now)."""
    now = now or _now()
    _invalidate_moved(db, league.id)
    for offer in db.scalars(select(TradeOffer).where(TradeOffer.league_id == league.id,
                                                     TradeOffer.status.in_(OPEN))).all():
        if offer.status == "pending" and _as_utc(offer.expires_at) <= now:
            offer.status, offer.reason = "expired", "Nobody answered in time."
        elif offer.status == "review" and _as_utc(offer.review_ends_at) <= now:
            try:
                deal = _deal(db, league, offer.from_team_id, _proposal(offer))
                _check(deal)
            except RosterError as exc:
                offer.status, offer.reason = "invalid", exc.message
            else:
                _complete(db, offer, deal)
    db.flush()


def leagues_to_settle(db: Session) -> list[League]:
    ids = set(db.scalars(select(TradeOffer.league_id).where(TradeOffer.status.in_(OPEN))))
    return [db.get(League, i) for i in sorted(ids)]


# ---------- views ----------

def _label(db: Session, item: dict) -> str:
    if item["kind"] == "player":
        player = db.get(Player, item["id"])
        return f"{player.position} {player.full_name} ({player.overall})" if player else "A player"
    pick = db.get(DraftPick, item["id"])
    return trades._pick_label(pick) if pick else "A pick"


def offer_out(db: Session, offer: TradeOffer, viewer: int | None) -> TradeOfferOut:
    direction = ("outgoing" if viewer == offer.from_team_id else
                 "incoming" if viewer == offer.to_team_id else "other")
    return TradeOfferOut(
        id=offer.id, from_team=team_summary(offer.from_team), to_team=team_summary(offer.to_team),
        from_manager=manager_name(db, offer.from_team_id) or "The AI",
        to_manager=manager_name(db, offer.to_team_id) or "The AI",
        gives=[TradeOfferItem(kind=i["kind"], id=i["id"], label=_label(db, i))
               for i in offer.send],
        gets=[TradeOfferItem(kind=i["kind"], id=i["id"], label=_label(db, i))
              for i in offer.receive],
        note=offer.note, status=offer.status, reason=offer.reason, direction=direction,
        parent_id=offer.parent_id, created_at=offer.created_at, expires_at=offer.expires_at,
        review_ends_at=offer.review_ends_at)


def offers_for(db: Session, league: League, team_id: int | None,
               commissioner: bool) -> list[TradeOfferOut]:
    """The viewer's offers (open ones first, then the latest), and, for a commissioner,
    every trade waiting out the veto window."""
    season = current_season(db, league.id)
    if season is None:
        return []
    involved = (TradeOffer.from_team_id == (team_id or 0)) | \
        (TradeOffer.to_team_id == (team_id or 0))
    if commissioner:
        involved = involved | (TradeOffer.status == "review")
    rows = db.scalars(select(TradeOffer).where(TradeOffer.league_id == league.id, involved)
                      .order_by(TradeOffer.id.desc()).limit(30)).all()
    rows = sorted(rows, key=lambda o: (o.status not in OPEN, -o.id))
    return [offer_out(db, o, team_id) for o in rows]
