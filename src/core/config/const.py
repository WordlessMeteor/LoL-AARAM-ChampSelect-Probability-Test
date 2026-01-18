BOT_UUID: str = "00000000-0000-0000-0000-000000000000"
ALL_GAMEFLOW_PHASES: list[str] = ["None", "Lobby", "Matchmaking", "ReadyCheck", "CheckedIntoTournament", "ChampSelect", "GameStart", "InProgress", "Reconnect", "WaitingForStats", "PreEndOfGame", "EndOfGame", "FailedToLaunch", "TerminatedInError"]
BOT_DIFFICULTY_LIST: list[str] = ["NONE", "TUTORIAL", "INTRO", "EASY", "MEDIUM", "HARD", "UBER", "RSWARMINTRO", "RSINTRO", "RSBEGINNER", "RSINTERMEDIATE"]
SPECTATOR_POLICY_LIST: list[str] = ["LobbyAllowed", "FriendsAllowed", "AllAllowed", "NotAllowed"]
GLOBAL_RESPONSE_LAG: float = 0.2