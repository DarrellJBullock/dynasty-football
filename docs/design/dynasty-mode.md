# Design: Dynasty Mode (Milestone 8)

**Status:** Accepted 2026-10-12 (all §8 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Make the franchise loop deeper over many seasons. **Sim ahead** several seasons at once
and come back to a dynasty that has aged, drafted, signed and won (or not). Give your
team an identity with **your own game plan**: the plays you run, how you call them, and
**audibles** at the line in Coach Mode. And make games feel more like football, with **more
kinds of penalties and injuries** that the players' ratings drive.

### Non-goals for Milestone 8

- Multiplayer (two people in one league), sharing, or trading between users.
- Commentary, crowd sound, or new 3D player models.
- Designing brand-new plays from scratch (routes, formations); see §8, decision 4.
- Changing how ratings work, or calibrating the league to look different. New fouls and
  injuries are calibrated to today's targets.

## 2. What exists

- **One season at a time.** The franchise sims a week, the rest of the season, the
  playoffs, the offseason, free agency and the draft, each as its own step (the long ones
  as background jobs with progress and Stop). A season and its offseason take about
  **19 s** on this machine.
- **The franchise's offseason needs the user.** Expiring contracts leave unless the user
  re-signs them; the free-agency market never bids for the franchise; the draft can
  auto-pick for it; the roster must be cut to 53 before week 1 (the draft can do it).
- **Playbooks are fixed.** 29 named offensive plays and 11 defensive calls. Every team's
  AI picks from the whole book by situation, and so does Coach Mode's "let the AI call".
  The user calls a play, a package and a timeout; there's no changing the call at the line.
- **Three penalties:** false start, holding and pass interference, at flat rates.
- **Injuries** come from contact, more often for low-toughness players, with a table of
  types and games missed; injured players sit out, and statuses count down weekly.
- **Data:** each season's play logs are about **9 MB** per league (about 30 KB a game).
  Ten more seasons would make a league about 100 MB.
- **Coached games replay from their calls**: any change to the engine's random draws
  needs a `SIM_VERSION` bump, and a game in progress on an older engine is abandoned.

## 3. Sim ahead

- **"Sim ahead N seasons"** (from the season controls, when no game is being coached):
  a background job that plays the regular season, the playoffs, the offseason, free
  agency and the draft, and cuts down to 53, season after season, then stops in the
  preseason of the last one. Progress reads "Season 2 of 5 · Week 9", with Stop between
  weeks as today; a stopped run leaves the league at a clean step, and "sim ahead" again
  carries on.
- **The franchise on autopilot** (decision 2): while simming ahead, the franchise is run
  like the AI runs every other team. It re-signs players worth their price, bids in free
  agency for the positions it lost, drafts the best player available, and cuts the
  lowest-rated players to 53. The same code as the AI teams, so the franchise neither
  sinks nor runs away with the league.
- **The report:** when the run ends, a **Dynasty report** sums up each season: the
  franchise's record and playoff result, the champion, awards, the franchise's notable
  signings, draft picks and departures, and retirements of its players. It stays
  reachable from History. (`/dynasty?from=&to=`, up to 10 seasons, from
  `GET /api/leagues/{id}/dynasty`: History's season cards and the dashboard's offseason
  recap, reused.)
- **Built:** a `sim_seasons` job (`params: {seasons: 1–10}`) runs from whatever phase the
  league is in; `autopilot=True` on the offseason, free agency and the draft treats the
  franchise like an AI team. Ten seasons of the full league took **134 s** here (272
  steps, counted exactly). Progress reads "Season 2 of 5 · 2027 · Week 9 of 17" (free
  agency and the draft are labelled with the season they follow).
- **Old play logs** (decision 3): sim ahead fills the database fast. Seasons before the
  last one keep full play-by-play only for the franchise's games and the playoffs; other
  games keep their box scores and lose their play logs (Watch Mode says so). History,
  records, careers and stats all come from box scores and are unaffected.
  - **Built:** compacted games keep the plays the box score page is built from (every
    play that changed the score, every injury, and the last play), so the line score,
    scoring summary and injuries stay exact; `games.log_compacted` marks them. It runs
    as each offseason rolls over. After ten seasons, 2,295 of 3,122 games were
    compacted, cutting the play logs from about 64 MB to 24 MB.
  - **Reads stay fast:** the ten-season report takes about 280 ms and History 160 ms;
    both make about 10 queries a season (CI checks two seasons). The draft board after a
    draft was loading each pick's player one by one (777 ms); now 66 ms.

## 4. Game plans

- **Your game plan** (decision 4), on a new **Game plan** page:
  - **Plays in the plan:** turn plays and calls on or off (at least a working set per
    situation: runs, short and deep passes, a screen, a two-minute play; base, nickel and
    dime looks, man and zone).
  - **Tendencies:** run/pass balance, deep-shot rate, play-action, how often to blitz,
    man vs zone, fourth-down aggressiveness, and when to go for two.
  - **Audibles** (decision 5): up to three per side, picked from the plan.
- **Who uses it:** the AI calling for the franchise (simmed games, "let the AI call" in
  Coach Mode, and sim ahead) picks only from the plan, weighted by the tendencies. The
  other teams get generated plans that suit their rosters (a team with a great passer
  throws more), so the league isn't one playbook.
- **The engine:** a plan is a filter and weights on top of today's situational choice
  (`playcalls.AICoach`); concepts and matchups resolve plays exactly as today. A plan
  that's all deep passes still has to survive third-and-one.

## 5. Audibles

- **At the line in Coach Mode:** after you call a play, you see the defense's **look**:
  its personnel and shell (two-high or single-high), and whether a blitz is showing. The
  look is honest most of the time but disguised sometimes (by the defense's awareness).
- **Audible:** switch to one of your three audibles, or keep the call. On defense,
  check to one of your three defensive audibles after seeing the offense's formation.
- **Replays stay exact:** an audible is recorded as part of the call (`{play, audible}`),
  so a coached game still replays from its calls. Seeing the look draws from its own
  random stream, so it doesn't shift the game's other draws.

## 6. Penalties and injuries

- **Penalties** (decision 6): add the common fouls: offside/encroachment and neutral-zone
  infraction (pre-snap, defense), delay of game, illegal formation, offensive pass
  interference, defensive holding and illegal contact, roughing the passer, unnecessary
  roughness and face mask (with automatic first downs where the rules give them), and
  intentional grounding. Each has a base rate, scaled by the **awareness** of the players
  involved (discipline), so a sloppy team draws more flags. Calibrated to league
  averages: about 6 accepted penalties and 50 yards per team per game (the calibration
  report gains these targets). Play-by-play, the broadcast's FLAG banner and the box
  score's penalty columns all come from the events, as today.
- **Injuries** (decision 7):
  - **Questionable:** some knocks don't sideline a player; they play at reduced ratings
    for a week or two (the depth chart can still bench them).
  - **Season-ending injuries** go to injured reserve for the rest of the season.
  - **Proneness:** low toughness raises the odds, as today; repeated injuries to the
    same player raise them a little more.
  - The injury report and the player page show the status, the injury and the expected
    return.
- **Engine version** (decision 8): the new fouls change the order of random draws, so
  `SIM_VERSION` goes to 1.6. A coached game in progress on 1.5 is offered to be abandoned,
  as today. Completed games keep their records; new games play on 1.6.

## 7. Testing

- **Sim ahead:** the job's steps across seasons (progress labels, Stop and carry on),
  the franchise's autopilot (re-signs, bids, drafts, cuts to 53, stays under the cap), a
  multi-season run that's deterministic for the league's seeds, the report's contents,
  the play-log compaction (which games keep logs; stats and records unchanged), and a
  Playwright run of sim ahead two seasons.
- **Game plans:** plan validation (a working set per situation), the AI calling only
  from the plan and following its tendencies over many snaps, generated plans for AI
  teams, the page's editing and saving, and Coach Mode's "let the AI call" using the plan.
- **Audibles:** the look (honest vs disguised rates by awareness), an audible recorded and
  replayed exactly, audibles limited to the plan, and the call screen's flow.
- **Penalties and injuries:** each foul's yards, spot and automatic first down; rates
  falling with awareness; calibration targets (fouls and yards per game, injury rates by
  severity); questionable players' reduced ratings; season-ending IR; the injury report;
  the 1.5 → 1.6 coached-game handling.

## 8. Decisions

Recommended option first.

1. **How far ahead:** **1 to 10 seasons** a run (recommended: about 3 minutes for 10 on a
   fast machine, with progress); or **up to 25**; or **one season at a time** only (a
   "sim to next season" button).
2. **The franchise while simming ahead:** **the AI runs it like any team**, with a report
   afterwards (recommended); or **stop at each offseason decision** (re-signing, free
   agency, the draft) for the user; or **rules the user sets** ("re-sign anyone over 75
   OVR under 30", "draft for need").
3. **Old play logs:** **keep play-by-play for the current and last seasons, and for the
   franchise's games and the playoffs in older ones** (recommended: about a fifth of the
   space, and Watch Mode keeps what matters); or **keep everything** (simple, but a
   10-season league is ~100 MB); or **box scores only** for older seasons.
4. **Playbooks:** **game plans**: choose plays from the book and set tendencies; the AI
   follows them when it calls for you (recommended); or a **play designer** for new plays
   (formation, routes, the engine call, and the 3D assignments to match: much more work);
   or game plans now and the designer later.
5. **Audibles:** **three per side from the plan, with a pre-snap look** that's sometimes
   disguised (recommended); or **no audibles** (game plans only).
6. **Penalties:** **about ten more common fouls, with rates tied to awareness**,
   calibrated to league averages (recommended); or the same fouls at **flat rates**; or
   **keep the three**.
7. **Injuries:** **questionable players at reduced ratings, season-ending injuries, and
   proneness** (recommended); or **keep them as they are**.
8. **Coached games across the engine change:** **bump `SIM_VERSION` to 1.6 and offer to
   abandon a 1.5 game in progress**, as today (recommended); or **keep the 1.5 engine
   around** to finish old games (more code to keep).

## 9. Delivery plan (separate PRs, each with tests)

1. **Sim ahead:** the multi-season job, the franchise's autopilot through the offseason,
   the Dynasty report, and play-log compaction.
2. **Game plans:** the plan (plays and tendencies), the Game plan page, the AI following
   it (franchise and generated plans for AI teams), and Coach Mode's "let the AI call".
3. **Audibles:** the pre-snap look, audibles in Coach Mode's call screen, recorded and
   replayed.
4. **Penalties and injuries:** the new fouls and injury statuses in the engine
   (`SIM_VERSION` 1.6), calibration, play-by-play, banners, the injury report and player
   pages.
