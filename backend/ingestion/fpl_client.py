import httpx
from pydantic import BaseModel


class FPLTeam(BaseModel):
    id: int
    name: str
    short_name: str
    code: int


class FPLPlayer(BaseModel):
    id: int
    web_name: str
    first_name: str
    second_name: str
    team: int
    element_type: int
    now_cost: int
    status: str
    chance_of_playing_next_round: int | None = None
    chance_of_playing_this_round: int | None = None
    news: str | None = None


class BootstrapStaticResponse(BaseModel):
    elements: list[FPLPlayer]
    teams: list[FPLTeam]


class FPLFixtureStatValue(BaseModel):
    value: int
    element: int


class FPLFixtureStat(BaseModel):
    identifier: str
    h: list[FPLFixtureStatValue] = []
    a: list[FPLFixtureStatValue] = []


class FPLFixture(BaseModel):
    id: int
    event: int | None = None
    team_h: int
    team_a: int
    team_h_difficulty: int
    team_a_difficulty: int
    kickoff_time: str | None = None
    finished: bool
    stats: list[FPLFixtureStat] = []


class FPLEntry(BaseModel):
    id: int
    player_first_name: str
    player_last_name: str
    name: str


class FPLPick(BaseModel):
    element: int
    position: int
    is_captain: bool
    is_vice: bool


class FPLEntryHistory(BaseModel):
    event: int
    bank: int
    value: int


class EntryPicksResponse(BaseModel):
    picks: list[FPLPick]
    entry_history: FPLEntryHistory | None = None


class FPLClient:
    """Read-only FPL API client wrapper."""

    BASE_URL = "https://fantasy.premierleague.com/api"

    def __init__(self, client: httpx.Client | None = None):
        # Allow passing an existing client for testing/mocking
        self.client = client or httpx.Client(
            headers={"User-Agent": "FergieTime FPL Agent/0.1.0"}
        )

    def get_bootstrap_static(self) -> BootstrapStaticResponse:
        """Fetch general FPL data including players (elements) and teams."""
        url = f"{self.BASE_URL}/bootstrap-static/"
        response = self.client.get(url)
        response.raise_for_status()
        return BootstrapStaticResponse.model_validate(response.json())

    def get_fixtures(self) -> list[FPLFixture]:
        """Fetch all fixtures for the season."""
        url = f"{self.BASE_URL}/fixtures/"
        response = self.client.get(url)
        response.raise_for_status()
        return [FPLFixture.model_validate(f) for f in response.json()]

    def get_entry(self, team_id: int) -> FPLEntry:
        """Fetch general manager/entry information for a given team ID."""
        url = f"{self.BASE_URL}/entry/{team_id}/"
        response = self.client.get(url)
        response.raise_for_status()
        return FPLEntry.model_validate(response.json())

    def get_entry_picks(self, team_id: int, gameweek: int) -> EntryPicksResponse:
        """Fetch squad picks for a manager in a specific gameweek."""
        url = f"{self.BASE_URL}/entry/{team_id}/event/{gameweek}/picks/"
        response = self.client.get(url)
        response.raise_for_status()
        return EntryPicksResponse.model_validate(response.json())
