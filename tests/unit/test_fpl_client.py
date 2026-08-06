from unittest.mock import MagicMock
import pytest
from ingestion.fpl_client import (
    FPLClient, BootstrapStaticResponse, FPLFixture, FPLEntry, EntryPicksResponse
)

def test_get_bootstrap_static():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "elements": [
            {
                "id": 1,
                "web_name": "Saka",
                "first_name": "Bukayo",
                "second_name": "Saka",
                "team": 1,
                "element_type": 3,
                "now_cost": 85,
                "status": "a",
                "chance_of_playing_next_round": 100,
                "chance_of_playing_this_round": 100,
                "news": None
            }
        ],
        "teams": [
            {
                "id": 1,
                "name": "Arsenal",
                "short_name": "ARS",
                "code": 11
            }
        ]
    }
    mock_client.get.return_value = mock_response
    
    client = FPLClient(client=mock_client)
    res = client.get_bootstrap_static()
    
    assert isinstance(res, BootstrapStaticResponse)
    assert len(res.elements) == 1
    assert res.elements[0].web_name == "Saka"
    assert res.teams[0].short_name == "ARS"
    mock_client.get.assert_called_once_with("https://fantasy.premierleague.com/api/bootstrap-static/")

def test_get_fixtures():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "id": 101,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "team_h_difficulty": 2,
            "team_a_difficulty": 3,
            "kickoff_time": "2026-08-11T19:00:00Z",
            "finished": True
        }
    ]
    mock_client.get.return_value = mock_response
    
    client = FPLClient(client=mock_client)
    res = client.get_fixtures()
    
    assert isinstance(res, list)
    assert len(res) == 1
    assert isinstance(res[0], FPLFixture)
    assert res[0].id == 101
    mock_client.get.assert_called_once_with("https://fantasy.premierleague.com/api/fixtures/")

def test_get_entry():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": 12345,
        "player_first_name": "Arsene",
        "player_last_name": "Wenger",
        "name": "Invincibles"
    }
    mock_client.get.return_value = mock_response
    
    client = FPLClient(client=mock_client)
    res = client.get_entry(12345)
    
    assert isinstance(res, FPLEntry)
    assert res.id == 12345
    assert res.player_first_name == "Arsene"
    mock_client.get.assert_called_once_with("https://fantasy.premierleague.com/api/entry/12345/")

def test_get_entry_picks():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "picks": [
            {
                "element": 1,
                "position": 1,
                "is_captain": False,
                "is_vice": True
            }
        ],
        "entry_history": {
            "event": 1,
            "bank": 5,
            "value": 1000
        }
    }
    mock_client.get.return_value = mock_response
    
    client = FPLClient(client=mock_client)
    res = client.get_entry_picks(12345, 1)
    
    assert isinstance(res, EntryPicksResponse)
    assert len(res.picks) == 1
    assert res.picks[0].element == 1
    assert res.entry_history.bank == 5
    mock_client.get.assert_called_once_with("https://fantasy.premierleague.com/api/entry/12345/event/1/picks/")


def test_get_my_team():
    from ingestion.fpl_client import MyTeamResponse
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "picks": [
            {
                "element": 4,
                "position": 3,
                "is_captain": True,
                "is_vice_captain": False
            }
        ],
        "transfers": {
            "bank": 15,
            "value": 1005
        }
    }
    mock_client.get.return_value = mock_response

    client = FPLClient(client=mock_client)
    res = client.get_my_team(12345, "pl_profile=dummy_session")

    assert isinstance(res, MyTeamResponse)
    assert len(res.picks) == 1
    assert res.picks[0].element == 4
    assert res.picks[0].is_vice is False
    assert res.transfers.bank == 15
    mock_client.get.assert_called_once_with(
        "https://fantasy.premierleague.com/api/my-team/12345/",
        headers={"Cookie": "pl_profile=dummy_session"}
    )


def test_fpl_pick_vice_captain_validator():
    from ingestion.fpl_client import FPLPick
    
    # Test mapping of is_vice_captain to is_vice
    pick_dict = {
        "element": 10,
        "position": 1,
        "is_captain": False,
        "is_vice_captain": True
    }
    pick = FPLPick.model_validate(pick_dict)
    assert pick.is_vice is True

    # Test standard is_vice
    pick_dict_std = {
        "element": 10,
        "position": 1,
        "is_captain": False,
        "is_vice": True
    }
    pick_std = FPLPick.model_validate(pick_dict_std)
    assert pick_std.is_vice is True

