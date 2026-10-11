"""The playbooks: named offensive plays and defensive calls (docs/design/coach-mode.md §4).

Each offensive play is one of the engine's coarse calls (run inside/outside; pass by depth,
with or without play action) plus a concept: who the quarterback looks for, and how the
concept fares against each coverage shell. Each defensive call is a package-independent
coverage shell, man or zone, with or without a blitz. Pure data; no engine imports.

Concept-versus-shell nudges (`Tuning.concept_edges`) are centered against the AI's own
defensive mix (`AI_SHELL_MIX`), so calling plays at random gains nothing on average:
what pays off is calling the right play against the defense you expect.
"""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["run", "pass", "punt", "field_goal", "kneel"]
Category = Literal["run", "quick", "intermediate", "deep", "play_action", "screen", "special"]
Shell = Literal["cover0", "cover1", "two_man", "cover2", "tampa2", "cover3", "cover4",
                "fire_zone", "prevent"]

# Target weights in the read order the engine uses: (WR1, WR2, WR3, TE, RB).
Targets = tuple[float, float, float, float, float]


@dataclass(frozen=True)
class OffensivePlay:
    key: str
    name: str
    category: Category
    formation: str
    kind: Kind
    description: str
    direction: Literal["inside", "outside"] | None = None
    depth: Literal["screen", "short", "medium", "deep"] | None = None
    play_action: bool = False
    targets: Targets | None = None  # None: the engine's defaults for the depth


@dataclass(frozen=True)
class DefensivePlay:
    key: str
    name: str
    category: Literal["zone", "man", "pressure", "situational"]
    shell: Shell
    coverage: Literal["man", "zone"]
    blitz: bool
    description: str
    package: Literal["base", "nickel", "dime"] | None = None  # None: fit the situation


def _run(key: str, name: str, formation: str, direction: Literal["inside", "outside"],
         description: str) -> OffensivePlay:
    return OffensivePlay(key, name, "run", formation, "run", description, direction=direction)


def _pass(key: str, name: str, category: Category, formation: str,
          depth: Literal["screen", "short", "medium", "deep"], targets: Targets,
          description: str, play_action: bool = False) -> OffensivePlay:
    return OffensivePlay(key, name, category, formation, "pass", description, depth=depth,
                         play_action=play_action, targets=targets)


OFFENSE: list[OffensivePlay] = [
    _run("inside_zone", "Inside Zone", "Singleback", "inside",
         "The line steps in unison; the back reads the first down lineman and cuts."),
    _run("power", "Power", "I-Form", "inside",
         "Down blocks at the point of attack, the backside guard pulls to lead through."),
    _run("counter", "Counter", "Singleback", "inside",
         "A step one way, then back the other behind two pulling linemen."),
    _run("draw", "Draw", "Shotgun", "inside",
         "Show pass, let the rush come upfield, then hand it off underneath it."),
    _run("outside_zone", "Outside Zone", "Pistol", "outside",
         "The line reaches to the sideline; the back presses the edge and cuts back."),
    _run("toss", "Toss", "I-Form", "outside",
         "A quick pitch to the back, racing the defense to the corner."),
    _pass("slants", "Slants", "quick", "Shotgun", "short", (3.4, 3.2, 2.4, 1.2, 0.6),
          "Three-step drop, receivers break inside on quick slants."),
    _pass("stick", "Stick", "quick", "Shotgun", "short", (2.2, 2.0, 2.8, 3.2, 1.6),
          "The tight end sits at six yards with a flat route outside him."),
    _pass("hitches", "Hitches", "quick", "Shotgun", "short", (3.0, 3.0, 2.4, 1.4, 0.8),
          "Receivers push five yards and turn back to the quarterback."),
    _pass("curl_flat", "Curl-Flat", "quick", "Singleback", "short", (2.8, 2.2, 1.8, 2.0, 2.6),
          "A curl over a flat route: a high-low read on the flat defender."),
    _pass("mesh", "Mesh", "quick", "Shotgun", "short", (2.0, 2.0, 3.2, 3.0, 1.6),
          "Two shallow crossers rub past each other underneath."),
    _pass("smash", "Smash", "intermediate", "Shotgun", "medium", (3.6, 2.4, 2.6, 1.4, 0.4),
          "A hitch underneath a corner route: a high-low read on the cornerback."),
    _pass("flood", "Flood", "intermediate", "Singleback", "medium", (3.0, 2.2, 2.6, 2.6, 0.6),
          "Three receivers at three depths to one side of the field."),
    _pass("dig", "Dig", "intermediate", "Shotgun", "medium", (3.6, 3.0, 2.0, 1.8, 0.5),
          "Receivers push fifteen yards and break across the middle."),
    _pass("y_cross", "Y-Cross", "intermediate", "Shotgun", "medium", (2.6, 2.2, 2.0, 3.6, 0.5),
          "The tight end runs a deep crosser behind the linebackers."),
    _pass("four_verts", "Four Verticals", "deep", "Shotgun", "deep", (3.6, 3.4, 2.4, 1.6, 0.1),
          "Four receivers straight down the field, stretching the safeties."),
    _pass("post_wheel", "Post-Wheel", "deep", "Shotgun", "deep", (4.2, 2.6, 1.6, 0.8, 0.8),
          "A post from the outside with a wheel route up the sideline under it."),
    _pass("pa_boot", "PA Boot", "play_action", "Singleback", "short", (2.4, 1.8, 1.6, 3.4, 1.6),
          "Fake the run, roll out against the flow, find the tight end in the flat.",
          play_action=True),
    _pass("pa_crossers", "PA Crossers", "play_action", "I-Form", "medium",
          (3.2, 2.8, 2.0, 2.4, 0.4),
          "Fake the run, then two crossers behind the linebackers who bit on it.",
          play_action=True),
    _pass("pa_post", "PA Post", "play_action", "I-Form", "deep", (4.4, 2.6, 1.6, 1.0, 0.2),
          "Fake the run to pull the safety up, then the post behind him.", play_action=True),
    _pass("rb_screen", "RB Screen", "screen", "Shotgun", "screen", (1.0, 0.8, 0.6, 0.6, 7.0),
          "Let the rush through, then dump it to the back behind a wall of linemen."),
    _pass("bubble", "WR Bubble", "screen", "Shotgun", "screen", (4.0, 3.0, 3.4, 0.8, 1.0),
          "A quick throw to a receiver drifting outside, his teammates blocking."),
    OffensivePlay("kneel", "Kneel", "special", "Victory", "kneel",
                  "Take the snap and kneel to run the clock."),
    OffensivePlay("punt", "Punt", "special", "Punt", "punt", "Punt it away."),
    OffensivePlay("field_goal", "Field Goal", "special", "Field Goal", "field_goal",
                  "Kick for three points."),
]

DEFENSE: list[DefensivePlay] = [
    DefensivePlay("cover2", "Cover 2", "zone", "cover2", "zone", False,
                  "Two deep safeties, five underneath; the corners squeeze the flats."),
    DefensivePlay("tampa2", "Tampa 2", "zone", "tampa2", "zone", False,
                  "Cover 2 with the middle linebacker running deep down the middle."),
    DefensivePlay("cover3", "Cover 3", "zone", "cover3", "zone", False,
                  "Three deep thirds, four underneath; a safety in the box against the run."),
    DefensivePlay("cover4", "Cover 4", "zone", "cover4", "zone", False,
                  "Quarters: four deep defenders, nothing over the top."),
    DefensivePlay("cover1", "Cover 1", "man", "cover1", "man", False,
                  "Man to man with a single deep safety."),
    DefensivePlay("two_man", "2-Man Under", "man", "two_man", "man", False,
                  "Tight man coverage underneath with two safeties deep."),
    DefensivePlay("cover0", "Cover 0 Blitz", "pressure", "cover0", "man", True,
                  "Everyone in man, no deep help, and an extra rusher: all or nothing."),
    DefensivePlay("mike_blitz", "Mike Blitz", "pressure", "cover1", "man", True,
                  "The middle linebacker rushes up the middle; man coverage behind."),
    DefensivePlay("fire_zone", "Fire Zone", "pressure", "fire_zone", "zone", True,
                  "A linebacker blitzes while a lineman drops: three deep, three under."),
    DefensivePlay("edge_blitz", "Edge Blitz", "pressure", "cover2", "zone", True,
                  "An outside linebacker comes off the edge; Cover 2 behind him."),
    DefensivePlay("prevent", "Prevent", "situational", "prevent", "zone", False,
                  "Dime personnel playing deep: give up the short ones, never the long one.",
                  package="dime"),
]

OFFENSE_BY_KEY = {p.key: p for p in OFFENSE}
DEFENSE_BY_KEY = {p.key: p for p in DEFENSE}

# Which named plays the AI picks for each of its coarse calls, and how often.
AI_RUNS: dict[str, list[tuple[str, float]]] = {
    "inside": [("inside_zone", 0.4), ("power", 0.3), ("counter", 0.15), ("draw", 0.15)],
    "outside": [("outside_zone", 0.55), ("toss", 0.45)],
}
AI_PASSES: dict[tuple[str, bool], list[tuple[str, float]]] = {
    ("screen", False): [("rb_screen", 0.5), ("bubble", 0.5)],
    ("screen", True): [("rb_screen", 0.5), ("bubble", 0.5)],
    ("short", False): [("slants", 0.22), ("stick", 0.2), ("hitches", 0.18), ("curl_flat", 0.2),
                       ("mesh", 0.2)],
    ("short", True): [("pa_boot", 1.0)],
    ("medium", False): [("smash", 0.27), ("flood", 0.25), ("dig", 0.26), ("y_cross", 0.22)],
    ("medium", True): [("pa_crossers", 1.0)],
    ("deep", False): [("four_verts", 0.55), ("post_wheel", 0.45)],
    ("deep", True): [("pa_post", 1.0)],
}
# The AI's defensive calls for each (coverage, blitz) choice, and how often.
AI_DEFENSES: dict[tuple[str, bool], list[tuple[str, float]]] = {
    ("zone", False): [("cover2", 0.25), ("cover3", 0.4), ("cover4", 0.2), ("tampa2", 0.15)],
    ("zone", True): [("fire_zone", 0.5), ("edge_blitz", 0.5)],
    ("man", False): [("cover1", 0.6), ("two_man", 0.4)],
    ("man", True): [("cover0", 0.5), ("mike_blitz", 0.5)],
}
# The AI's typical mix of coverage (45% man) and blitzes (about one snap in five).
_AI_MAN = 0.45
_AI_BLITZ = 0.2


def _ai_shell_mix() -> dict[str, float]:
    mix: dict[str, float] = {}
    for (coverage, blitz), calls in AI_DEFENSES.items():
        share = (_AI_MAN if coverage == "man" else 1 - _AI_MAN) * (_AI_BLITZ if blitz else
                                                                     1 - _AI_BLITZ)
        for key, weight in calls:
            shell = DEFENSE_BY_KEY[key].shell
            mix[shell] = mix.get(shell, 0.0) + share * weight
    return mix


AI_SHELL_MIX = _ai_shell_mix()


def concept_edge(edges: dict[str, dict[str, float]], play: str | None,
                 shell: str | None) -> float:
    """How much `play`'s concept gains (or loses) against `shell`, centered so that the
    play breaks even against the AI's usual mix of shells."""
    table = edges.get(play or "")
    if not table or not shell:
        return 0.0
    mean = sum(table.get(s, 0.0) * share for s, share in AI_SHELL_MIX.items())
    return table.get(shell, 0.0) - mean


def offense_name(call: dict | None) -> str | None:
    """The name of the named play in a play log's call, unless it's a kick or a kneel."""
    play = OFFENSE_BY_KEY.get((call or {}).get("play", ""))
    return play.name if play and play.category != "special" else None


def defense_name(call: dict | None) -> str | None:
    """The name of the named defensive call in a play log's defense."""
    play = DEFENSE_BY_KEY.get((call or {}).get("play", ""))
    return play.name if play else None
