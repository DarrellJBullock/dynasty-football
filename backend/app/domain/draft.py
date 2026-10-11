"""Draft rules: class quality, scouting fog, draft order, AI valuation, rookie contracts.

Pure: random draws come from an explicit `random.Random`.
"""

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

ROUNDS = 7
EXTRA_PROSPECTS = 2.0  # class size = teams × (ROUNDS + this): some go undrafted
SCOUTING_REPORTS = 25  # per class, for the franchise
ROOKIE_YEARS = 4
TOP_PICK_SALARY = 10_000_000
SALARY_SCALE_PICKS = 100  # the rookie scale reaches the minimum around this pick

# Prospect quality by class rank (0 = best): projected OVR falls from TOP to BOTTOM.
TOP_OVR, BOTTOM_OVR, QUALITY_CURVE = 69, 51, 0.8
OVR_NOISE = 3.0
UPSIDE = (14.0, 6.0)  # mean, sd of potential above OVR for the best prospect...
UPSIDE_DROP = 5.0  # ...falling by this much toward the bottom of the class

SCOUT_NOISE_SD = 5.0  # how far an unscouted projection can be from the truth
PROJECTION_RANGE = 4  # shown as projection ± this until scouted

AI_POTENTIAL_WEIGHT = 0.45  # AI value = OVR × (1 - w) + potential × w ...
AI_NOISE_SD = 2.5  # ...plus its own scouting error...
AI_NEED_BONUS = 4.0  # ...plus this for a position it still needs


def class_size(teams: int) -> int:
    return int(teams * (ROUNDS + EXTRA_PROSPECTS))


def prospect_target(rng: random.Random, rank: int, size: int) -> tuple[int, int]:
    """(target OVR, upside) for the prospect at `rank` in a class of `size`."""
    depth = (rank / max(1, size - 1)) ** QUALITY_CURVE
    ovr = round(TOP_OVR - (TOP_OVR - BOTTOM_OVR) * depth + rng.gauss(0, OVR_NOISE))
    upside = max(2, round(rng.gauss(UPSIDE[0] - UPSIDE_DROP * depth, UPSIDE[1])))
    return ovr, upside


def rookie_salary(pick: int, minimum: int) -> int:
    """Slotted rookie salary: about $10M for the first pick, the minimum by ~pick 100."""
    share = max(0.0, 1 - (pick - 1) / SALARY_SCALE_PICKS) ** 3
    return max(minimum, int(round(minimum + (TOP_PICK_SALARY - minimum) * share, -4)))


def potential_grade(potential: int) -> str:
    for floor, grade in ((85, "A+"), (80, "A"), (76, "B+"), (72, "B"), (68, "C+"), (64, "C")):
        if potential >= floor:
            return grade
    return "D"


def scout_noise(league_id: int, prospect_key: str) -> float:
    """The franchise's scouting error for a prospect, stable per prospect. `prospect_key`
    identifies him by content (class, name, position, college), not by database id, so a
    replayed league scouts the same way."""
    digest = hashlib.sha256(f"scout:{league_id}:{prospect_key}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).gauss(0, SCOUT_NOISE_SD)


@dataclass(frozen=True)
class Finish:
    """A team's previous season, for draft order."""
    team_id: int
    playoff_finish: int  # 0 missed the playoffs; else the last round reached (+1 champion)
    win_pct: float
    point_diff: int


def draft_order(finishes: Sequence[Finish], salt: str) -> list[int]:
    """Worst first: non-playoff teams by record, then playoff teams by how far they got
    (the champion picks last). Remaining ties: a stable coin flip."""
    def coin(team_id: int) -> str:
        return hashlib.sha256(f"{salt}:{team_id}".encode()).hexdigest()

    ordered = sorted(finishes, key=lambda f: (f.playoff_finish, f.win_pct, f.point_diff,
                                              coin(f.team_id)))
    return [f.team_id for f in ordered]


def ai_value(rng: random.Random, overall: int, potential: int, needed: bool) -> float:
    return (overall * (1 - AI_POTENTIAL_WEIGHT) + potential * AI_POTENTIAL_WEIGHT
            + rng.gauss(0, AI_NOISE_SD) + (AI_NEED_BONUS if needed else 0.0))
