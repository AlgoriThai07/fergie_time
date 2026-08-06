"""
Create a mock squad for a given FPL Entry ID in the local database.

Since the FPL API does not publish a manager's squad picks until after
the Gameweek 1 deadline has passed (which is in August), the live
picks endpoint (/event/1/picks/) returns a 404 for everyone during pre-season.

This script manually seeds a mock squad of 15 players for your FPL Entry ID
in the database, allowing you to test the GET /squad/{user_id} endpoint locally.
"""

import sys

from db.models import Player, User, UserSquad
from db.session import get_db_session

# Use 1160158 as default, or take from command line argument
FPL_ENTRY_ID = 1160158
if len(sys.argv) > 1:
    try:
        FPL_ENTRY_ID = int(sys.argv[1])
    except ValueError:
        print("Please provide a valid integer for the FPL Entry ID.")
        sys.path.exit(1)

GAMEWEEK = 1


def seed_mock_squad():
    with get_db_session() as session:
        # 1. Create or get user
        user = session.query(User).filter_by(fpl_entry_id=FPL_ENTRY_ID).first()
        if not user:
            user = User(fpl_entry_id=FPL_ENTRY_ID)
            session.add(user)
            session.flush()
            print(f"Created User in DB with FPL Entry ID: {FPL_ENTRY_ID}")
        else:
            print(f"Found existing User in DB with FPL Entry ID: {FPL_ENTRY_ID}")

        # 2. Clear any existing mock squad entries for this user and gameweek
        session.query(UserSquad).filter_by(user_id=user.id, gameweek=GAMEWEEK).delete()
        session.flush()

        # 3. Fetch a valid squad of 15 players ensuring team constraints
        # (max 3 per team)
        all_players = session.query(Player).all()
        gkps, defs, mids, fwds = [], [], [], []
        team_counts = {}

        for p in all_players:
            count = team_counts.get(p.team_id, 0)
            if count >= 3:
                continue

            if p.position == "GKP" and len(gkps) < 2:
                gkps.append(p)
                team_counts[p.team_id] = count + 1
            elif p.position == "DEF" and len(defs) < 5:
                defs.append(p)
                team_counts[p.team_id] = count + 1
            elif p.position == "MID" and len(mids) < 5:
                mids.append(p)
                team_counts[p.team_id] = count + 1
            elif p.position == "FWD" and len(fwds) < 3:
                fwds.append(p)
                team_counts[p.team_id] = count + 1

        players = gkps + defs + mids + fwds

        if (
            len(players) < 15
            or len(gkps) < 2
            or len(defs) < 5
            or len(mids) < 5
            or len(fwds) < 3
        ):
            print(
                "Error: Not enough players of each position in the database. "
                "Please run the ingestion task first."
            )
            return

        # 4. Insert squad entries (11 starting, 4 bench)
        for i, player in enumerate(players):
            is_starting = i < 11
            is_captain = i == 0
            is_vice = i == 1

            squad_entry = UserSquad(
                user_id=user.id,
                gameweek=GAMEWEEK,
                player_id=player.id,
                is_starting=is_starting,
                is_captain=is_captain,
                is_vice=is_vice,
            )
            session.add(squad_entry)
            print(
                f"  - Added {player.name} "
                f"({player.position}, {player.team.short_name}) - "
                f"{'Starting' if is_starting else 'Bench'}"
            )

        session.commit()
        print(
            f"\nSuccess! Mock squad seeded for FPL Entry ID {FPL_ENTRY_ID} "
            f"for Gameweek {GAMEWEEK}."
        )
        print(
            f"You can now test the API endpoint at: http://localhost:8000/squad/{FPL_ENTRY_ID}"
        )


if __name__ == "__main__":
    seed_mock_squad()
