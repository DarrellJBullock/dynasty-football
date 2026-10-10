"""Fictional league definition and name pools. No real teams or players."""

LEAGUE_NAME = "Dynasty Football League"
LEAGUE_ABBREVIATION = "DFL"
SALARY_CAP = 255_000_000
START_YEAR = 2026
REGULAR_SEASON_WEEKS = 17

# (city, nickname, abbreviation, primary, secondary, stadium)
TeamDef = tuple[str, str, str, str, str, str]

CONFERENCES: dict[tuple[str, str], dict[str, list[TeamDef]]] = {
    ("Atlantic Conference", "ATL"): {
        "North": [
            ("Hartford", "Ironclads", "HFD", "#1F3A5F", "#C9A227", "Foundry Field"),
            ("Providence", "Anchors", "PRO", "#0B5563", "#E8E2D0", "Harborlight Stadium"),
            ("Albany", "Sentinels", "ALB", "#5B2A86", "#F2C14E", "Capitol Grounds"),
            ("Burlington", "Lumberjacks", "BUR", "#2D6A4F", "#D4A373", "Timberline Park"),
        ],
        "East": [
            ("Richmond", "Foxhounds", "RIC", "#9B2226", "#E9D8A6", "Riverbend Stadium"),
            ("Norfolk", "Squall", "NOR", "#023E8A", "#90E0EF", "Tidewater Dome"),
            ("Charleston", "Marauders", "CHS", "#3D2645", "#F07167", "Battery Point Field"),
            ("Savannah", "Gators", "SAV", "#386641", "#F4A259", "Live Oak Stadium"),
        ],
        "South": [
            ("Orlando", "Comets", "ORL", "#3A0CA3", "#F72585", "Starlight Arena"),
            ("Birmingham", "Forge", "BHM", "#6C757D", "#E85D04", "Ironworks Field"),
            ("Memphis", "Kings", "MEM", "#4C1D95", "#FBBF24", "Bluff City Stadium"),
            ("Louisville", "Thoroughbreds", "LOU", "#7F1D1D", "#D6CCC2", "Derby Park"),
        ],
        "West": [
            ("Columbus", "Arsenal", "CLB", "#14213D", "#FCA311", "Armory Field"),
            ("Omaha", "Stampede", "OMA", "#6F1D1B", "#BB9457", "Prairie Bowl"),
            ("St. Louis", "Aviators", "STL", "#003049", "#EAE2B7", "Gateway Stadium"),
            ("Milwaukee", "Frost", "MIL", "#1D3557", "#A8DADC", "Lakefront Field"),
        ],
    },
    ("Pacific Conference", "PAC"): {
        "North": [
            ("Portland", "Rainmakers", "POR", "#264653", "#2A9D8F", "Cascade Field"),
            ("Boise", "Summit", "BOI", "#0F4C5C", "#E36414", "Basin Stadium"),
            ("Spokane", "Wildfire", "SPO", "#9D0208", "#FFBA08", "Falls Park"),
            ("Anchorage", "Glaciers", "ANC", "#0077B6", "#CAF0F8", "Aurora Dome"),
        ],
        "East": [
            ("Colorado Springs", "Peaks", "CSP", "#3C096C", "#C77DFF", "Front Range Field"),
            ("Salt Lake", "Bison", "SLC", "#582F0E", "#B6AD90", "Wasatch Stadium"),
            ("Albuquerque", "Roadrunners", "ABQ", "#BC3908", "#F6AA1C", "Mesa Grande Field"),
            ("Tulsa", "Twisters", "TUL", "#2B2D42", "#EF233C", "Route 66 Stadium"),
        ],
        "South": [
            ("San Antonio", "Vaqueros", "SAN", "#3E1F47", "#E0A458", "Mission Field"),
            ("El Paso", "Scorpions", "ELP", "#A4161A", "#161A1D", "Sun Bowl Park"),
            ("Austin", "Armadillos", "AUS", "#BF5700", "#333D29", "Capital City Field"),
            ("Oklahoma City", "Wranglers", "OKC", "#1B4965", "#CAE9FF", "Red Earth Stadium"),
        ],
        "West": [
            ("Sacramento", "Gold", "SAC", "#2F3E46", "#E9C46A", "Delta Park"),
            ("Fresno", "Sunhawks", "FRE", "#E76F51", "#264653", "Valley Stadium"),
            ("San Diego", "Tritons", "SDG", "#005F73", "#94D2BD", "Coronado Field"),
            ("Honolulu", "Breakers", "HON", "#0081A7", "#FED9B7", "Pali Stadium"),
        ],
    },
}

FIRST_NAMES = [
    "Aaron", "Adrian", "Alec", "Andre", "Austin", "Blake", "Brandon", "Brock", "Caleb",
    "Cam", "Carter", "Chase", "Cole", "Colton", "Corey", "Dalton", "Damon", "Darius",
    "Dante", "Davion", "Dean", "Derek", "Devin", "Dillon", "Dominic", "Drew", "Dylan",
    "Eli", "Elijah", "Emmett", "Ethan", "Evan", "Gabe", "Garrett", "Grant", "Hayden",
    "Hunter", "Isaiah", "Jace", "Jalen", "Jamal", "Jared", "Jaylen", "Jordan", "Josiah",
    "Julian", "Kaden", "Keegan", "Keith", "Kendrick", "Kevin", "Kobe", "Landon", "Lane",
    "Levi", "Logan", "Lucas", "Malik", "Marcus", "Mason", "Micah", "Miles", "Nate",
    "Nolan", "Omar", "Owen", "Parker", "Preston", "Quinn", "Reed", "Reggie", "Rhett",
    "Roman", "Ryder", "Sam", "Shane", "Silas", "Spencer", "Terrell", "Trent", "Trey",
    "Tristan", "Ty", "Tyrese", "Vance", "Victor", "Wade", "Wes", "Xavier", "Zane",
]

LAST_NAMES = [
    "Abernathy", "Alder", "Ashford", "Barlow", "Beckett", "Bellamy", "Blackwell", "Boone",
    "Brannigan", "Brooks", "Calloway", "Carver", "Castillo", "Cole", "Crenshaw", "Dawson",
    "Delacroix", "Draper", "Easton", "Ellery", "Fairbanks", "Fenwick", "Fletcher", "Garrison",
    "Grady", "Graves", "Hale", "Hargrove", "Hawthorne", "Holloway", "Ingram", "Jennings",
    "Kessler", "Kingsley", "Lancaster", "Langford", "Lowell", "Maddox", "Mercer", "Merritt",
    "Monroe", "Nash", "Okafor", "Oakley", "Pemberton", "Prescott", "Quarles", "Radcliffe",
    "Ramsey", "Redding", "Rowan", "Sawyer", "Sinclair", "Slade", "Stanton", "Sterling",
    "Stroud", "Talbot", "Thorne", "Underwood", "Vance", "Vaughn", "Whitaker", "Whitlock",
    "Winslow", "Wolfe", "Yarbrough", "York", "Zeller", "Adebayo", "Mbeki", "Nakamura",
    "Okonkwo", "Petrovic", "Reyes", "Salazar", "Tuilagi", "Vasquez", "Fonoti", "Haddad",
]

COLLEGES = [
    "Lakeshore State", "Northern Plains", "Coastal Carolina Tech", "Red River", "Summit Valley",
    "Great Basin", "Ozark Mountain", "Gulfport A&M", "Tri-County", "Cedar Ridge",
    "Bayou State", "High Desert", "Iron Range", "Piedmont", "Sierra Pacific",
    "Blue Ridge", "Prairie View Tech", "Cumberland", "Tidewater", "Columbia Basin",
]

# Extra identities so custom leagues can have up to 40 teams.
EXTRA_TEAMS: list[TeamDef] = [
    ("Wichita", "Windjammers", "WIC", "#003566", "#FFC300", "Plains Arena"),
    ("Des Moines", "Dragoons", "DSM", "#540B0E", "#E09F3E", "Capital Hill Field"),
    ("Little Rock", "Rangers", "LRK", "#3A5A40", "#DAD7CD", "Riverfront Stadium"),
    ("Chattanooga", "Choo Choos", "CHA", "#7209B7", "#4CC9F0", "Lookout Park"),
    ("Knoxville", "Mountaineers", "KNX", "#FB8500", "#023047", "Smoky Ridge Field"),
    ("Reno", "Rollers", "RNO", "#14213D", "#E5E5E5", "High Sierra Dome"),
    ("Tucson", "Thunderbirds", "TUC", "#9E2A2B", "#FFF3B0", "Saguaro Stadium"),
    ("Madison", "Marshals", "MSN", "#283618", "#FEFAE0", "Isthmus Field"),
]

# All fictional team identities, in default-league order, then extras.
TEAM_POOL: list[TeamDef] = [
    team for divisions in CONFERENCES.values() for teams in divisions.values() for team in teams
] + EXTRA_TEAMS

CONFERENCE_NAMES: list[tuple[str, str]] = [
    ("Atlantic Conference", "ATL"), ("Pacific Conference", "PAC"),
    ("Central Conference", "CEN"), ("Frontier Conference", "FRO"),
]
DIVISION_NAMES = ["North", "East", "South", "West"]
