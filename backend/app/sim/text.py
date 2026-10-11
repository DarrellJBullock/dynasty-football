"""Play-by-play text, generated only from a play's events."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.sim.engine import PlayRecord
    from app.sim.teams import SimTeam

PENALTY_NAMES = {"false_start": "False start", "holding": "Offensive holding",
                 "pass_interference": "Defensive pass interference"}


def spot_label(ball_on: int, offense: str, defense: str) -> str:
    """Offense-perspective yard line as broadcast text: 'HFD 25', 'ABQ 40', '50'."""
    if ball_on == 50:
        return "50"
    return f"{offense} {ball_on}" if ball_on < 50 else f"{defense} {100 - ball_on}"


def describe(play: "PlayRecord", names: dict[int, str], teams: dict[str, "SimTeam"]) -> str:
    def name(pid: int | None) -> str:
        if pid is None:
            return "nobody"
        return names.get(pid, "a reserve")

    def yards(n: int) -> str:
        if n == 0:
            return "no gain"
        return f"{n} yard{'s' if abs(n) != 1 else ''}" if n > 0 else f"a loss of {-n}"

    parts: list[str] = []
    tackled_by: list[int] = []
    injuries: list[str] = []
    for e in play.events:
        t = e["t"]
        if t == "kickoff":
            parts.append(f"{name(e['kicker'])} kicks off"
                         + (" for a touchback." if e["touchback"]
                            else f", returned to the {e['return']}."))
        elif t == "rush":
            parts.append(f"{name(e['player'])} runs for {yards(e['yards'])}")
        elif t == "scramble":
            parts.append(f"{name(e['qb'])} scrambles for {yards(e['yards'])}")
        elif t == "kneel":
            parts.append(f"{name(e['qb'])} kneels")
        elif t == "sack":
            parts.append(f"{name(e['qb'])} sacked by {name(e['by'])} for {yards(e['yards'])}")
        elif t == "pass":
            qb = name(e["qb"])
            if e["result"] == "complete":
                parts.append(f"{qb} pass complete to {name(e['target'])} for {yards(e['yards'])}")
            elif e["result"] == "incomplete":
                parts.append(f"{qb} pass incomplete intended for {name(e['target'])}")
            elif e["result"] == "throwaway":
                parts.append(f"{qb} throws it away under pressure")
            else:
                parts.append(f"{qb} pass intended for {name(e['target'])}")
        elif t == "interception":
            parts.append(f"INTERCEPTED by {name(e['by'])}, returned {e['return']} yards")
        elif t == "pass_defended":
            parts.append(f"broken up by {name(e['by'])}")
        elif t == "tackle":
            tackled_by = e["by"]
        elif t == "fumble":
            parts.append(f"FUMBLE by {name(e['player'])}, forced by {name(e['forced_by'])}"
                         + (", recovered by the defense" if e["lost"] else ", offense recovers"))
        elif t == "punt":
            if e["touchback"]:
                parts.append(f"{name(e['punter'])} punts into the end zone for a touchback")
            else:
                ending = "fair catch" if e.get("fair_catch") else f"returned {e['return']} yards"
                parts.append(f"{name(e['punter'])} punts {e['yards']} yards, {ending}")
        elif t == "field_goal":
            parts.append(f"{name(e['kicker'])} {e['distance']}-yard field goal is "
                         + ("GOOD" if e["good"] else "NO GOOD"))
        elif t == "extra_point":
            parts.append(f"{name(e['kicker'])} extra point is "
                         + ("good" if e["good"] else "no good"))
        elif t == "two_point":
            parts.append("Two-point conversion " + ("succeeds" if e["good"] else "fails"))
        elif t == "injury":
            injuries.append(f"{name(e['player'])} ({e['team']}) is injured: {e['injury']}")
        elif t == "penalty":
            label = PENALTY_NAMES.get(e["kind"], e["kind"])
            parts.append(f"PENALTY on {e['team']}: {label}, {e['yards']} yards"
                         + (" (play nullified)" if play.result.get("nullified") else ""))

    text = ", ".join(parts) if parts else play.result.get("type", "play")
    if tackled_by and not play.result.get("touchdown"):
        text += f" ({', '.join(name(pid) for pid in tackled_by)})"
    if play.result.get("touchdown") or play.result.get("defensive_td"):
        text += ". TOUCHDOWN"
    elif play.result.get("safety"):
        text += ". SAFETY"
    elif play.result.get("turnover_on_downs"):
        text += ". Turnover on downs"
    elif play.result.get("first_down") and play.result.get("type") != "penalty":
        text += ". First down"
    text += "" if text.endswith(".") else "."
    return " ".join([text, *(f"{injury}." for injury in injuries)])
