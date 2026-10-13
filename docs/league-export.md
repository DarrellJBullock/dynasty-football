# The league export

Any member of a league can download it whole, as one JSON file, from the Members page
(`GET /api/leagues/{league_id}/export`; `app/services/sharing.py`). It's meant for keeping
a copy, for spreadsheets and scripts, and, later, for importing a league.

## Shape

```json
{
  "format": "dynasty-football/league",
  "version": 1,
  "exported_at": "2026-10-13T02:00:00+00:00",
  "league": { "id": 1, "name": "…", "abbreviation": "…", "salary_cap": 255000000, … },
  "conferences": [ … ],
  "divisions": [ … ],
  "teams": [ … ],
  "players": [ … ],
  "player_ratings": [ … ],
  "contracts": [ … ],
  "dead_money": [ … ],
  "depth_charts": [ … ],
  "seasons": [ … ],
  "games": [ … ],
  "team_game_stats": [ … ],
  "playoff_seeds": [ … ],
  "awards": [ … ],
  "draft_picks": [ … ],
  "trades": [ … ],
  "hall_of_fame": [ … ],
  "retired_numbers": [ … ],
  "staff": [ … ],
  "staff_seasons": [ … ],
  "staff_dead_money": [ … ]
}
```

Each list holds the league's rows of one table, in primary-key order. **Each row has the
table's columns as stored** (`backend/app/models.py` documents them): ids are the
database's, and rows refer to each other by them. For example, `players[].team_id` is a
`teams[].id` (`null` for a free agent), `games[].home_team_id` is a team, `contracts[]` and
`player_ratings[]` belong to a `player_id`, and `games[]` and `awards[]` to a `season_id`.
Times are ISO 8601 strings in UTC, and money is whole dollars.

| Key | What |
|---|---|
| `league` | Its name, salary cap, settings (draft clock, daily advance, veto window), men's or women's |
| `conferences`, `divisions`, `teams` | The structure, and each team's identity (city, nickname, colors, stadium) |
| `players`, `player_ratings` | Everyone (on a team, a free agent, a draft prospect, or retired), and the 24 ratings |
| `contracts`, `dead_money` | Every contract, past and present, and cap charges left behind |
| `depth_charts` | Each team's saved depth chart |
| `seasons`, `games`, `team_game_stats`, `playoff_seeds` | Every season, its schedule and results, team box scores, and playoff seeding |
| `awards` | MVP, offensive and defensive player and rookie of the year, by season |
| `draft_picks`, `trades` | Picks (made and to come) and completed trades |
| `staff`, `staff_seasons`, `staff_dead_money` | Every coach, scout and trainer (on a team, out of work, or retired), each one's seasons (the team's record, playoff wins, titles, Coach of the Year), and what teams still owe staff they let go |
| `hall_of_fame`, `retired_numbers` | Each year's Hall of Fame ballot (`inducted` marks the members; the rest came close), and numbers teams retired |

## What's left out

- **People:** accounts, emails, members and roles, invites, notifications, and who runs
  which team. The `league` row has no owner and no public-link token.
- **Private plans:** game plans (each manager's own), and trade offers with their notes.
- **The big logs:** play-by-play (`games.play_log`), per-player game stats, and offseason
  logs. A game can be replayed from its seed; these can be large.
- **Working state:** background jobs and Coach Mode games in progress.

## Versions

`version` changes only when a row's meaning changes. Columns can be added within a
version, so read the ones you need and ignore the rest.
