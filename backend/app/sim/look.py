"""What each side sees at the line, before the snap (Coach Mode's audibles). Pure.

The offense sees the defense's personnel, its safeties (two deep, one deep, or none) and
whether a blitz is showing. Most of the time that's what the defense is in; sometimes it's
disguised: the safeties rotate after the snap, or a blitz is faked or hidden. Smarter
defenses (their safeties' and middle linebacker's awareness) disguise more. The defense
sees the offense's formation, which can't be disguised. Design: docs/design/dynasty-mode.md
§5.
"""

import random
from statistics import mean

from app.domain.positions import Position
from app.sim.playbook import OFFENSE_BY_KEY
from app.sim.teams import SimTeam

# Safeties deep for each coverage before the snap.
SAFETIES: dict[str, str] = {
    "cover0": "none", "cover1": "single_high", "cover3": "single_high",
    "fire_zone": "single_high", "cover2": "two_high", "tampa2": "two_high",
    "cover4": "two_high", "two_man": "two_high", "prevent": "two_high",
}
SAFETY_NAMES = {"two_high": "two deep safeties", "single_high": "one deep safety",
                "none": "no deep safety"}
# A disguise shows the other picture: two deep rotate down to one, one rotates to two.
ROTATED = {"two_high": "single_high", "single_high": "two_high", "none": "single_high"}
DISGUISE_BASE, DISGUISE_PER_POINT = 0.12, 0.01  # at 70 awareness; per point above or below
DISGUISE_MIN, DISGUISE_MAX = 0.05, 0.35


def disguise_rate(defense: SimTeam) -> float:
    """How often the defense's look isn't what it's in: its safeties' and middle
    linebacker's awareness."""
    awareness = mean(p.ratings.get("awareness", 60) for p in [
        defense.one(Position.FS), defense.one(Position.SS), defense.one(Position.MLB)])
    rate = DISGUISE_BASE + DISGUISE_PER_POINT * (awareness - 70)
    return min(DISGUISE_MAX, max(DISGUISE_MIN, rate))


def defensive_look(package: str, shell: str | None, blitz: bool, defense: SimTeam,
                   rng: random.Random) -> dict:
    """What the offense sees: personnel (never hidden), safeties and a blitz showing."""
    safeties = SAFETIES.get(shell or "", "single_high")
    showing = blitz
    if rng.random() < disguise_rate(defense):
        safeties = ROTATED[safeties]
        if rng.random() < 0.5:
            showing = not blitz
    return {"package": package, "safeties": safeties, "blitz": showing}


def offensive_look(play: str | None) -> dict:
    """What the defense sees: the offense's formation."""
    formation = OFFENSE_BY_KEY[play].formation if play in OFFENSE_BY_KEY else None
    return {"formation": formation}
