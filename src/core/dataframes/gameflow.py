from lcu_driver.connection import Connection
import os, pandas, sys
from urllib.parse import urljoin
from typing import Any
wd = os.getcwd()
if not wd in sys.path:
    sys.path.append(os.getcwd()) #确保在“src”文件夹的父级目录运行此代码（Make sure this program is run under the parent folder of the "src" folder）
from src.utils.logging import LogManager
from src.utils.patch import Patch
from src.utils.summoner import get_info
from src.core.config.const import BOT_UUID
from src.core.config.localization import team_colors_int, krarities
from src.core.config.headers import champSelect_player_header, inGame_player_header
from src.core.config.headers import LoLGame_info_header as LoLGame_stat_header
from src.core.dataframes.matchHistory import get_LoLGame_info, sort_LoLGame_info

async def get_gameflow_phase(connection: Connection) -> str: #设计该函数的原因是通过“GET lol-gameflow/v1/gameflow-phase”获得的游戏状态不一定真实，特别是在调用“POST /lol-lobby/v1/lobby/custom/cancel-champ-select”之后（The reason why this function is designed is that the in-game status returned by the API "GET /lol-gameflow/v1/gameflow-phase" may be unreal, especially when "POST /lol-lobby/v1/lobby/custom/cancel-champ-select" is called）
    gameflow_phase: str = await (await connection.request("GET", "/lol-gameflow/v1/gameflow-phase")).json()
    if gameflow_phase in {"None", "Lobby", "Matchmaking"}:
        lobby_information: dict[str, Any] = await (await connection.request("GET", "/lol-lobby/v2/lobby")).json()
        search_info: dict[str, Any] = await (await connection.request("GET", "/lol-matchmaking/v1/search")).json()
        champ_select_session: dict[str, Any] = await (await connection.request("GET", "/lol-champ-select/v1/session")).json()
        champ_select_session_teamBuilder: dict[str, Any] = await (await connection.request("GET", "/lol-lobby-team-builder/champ-select/v1/session")).json()
        gameflow_session: dict[str, Any] = await (await connection.request("GET", "/lol-gameflow/v1/session")).json() #从2026赛季开始，在完成一局游戏后，通过“再来一局”进入小队并在进入下一局游戏之前，游戏会话不会更新。因此，本函数不再依赖游戏会话来判断主召唤师的游戏阶段（Starting from Season 2026, after the summoner finishes a game and clicks "PLAY AGAIN" button, before he enters the next game, gameflow session won't update. Therefore, this function no longer relies on this session to judge the main summoner's gameflow phase）
        inLobby: bool = not "errorCode" in lobby_information
        inQueue: bool = not "errorCode" in search_info and search_info["searchState"] == "Searching"
        inChampSelect: bool = not "errorCode" in champ_select_session or not "errorCode" in champ_select_session_teamBuilder
        # inGame: bool = not "errorCode" in gameflow_session
        if inChampSelect:
            gameflow_phase = "ChampSelect"
        # elif inGame and len(gameflow_session["gameData"]["playerChampionSelections"]) > 0:
        #     gameflow_phase = "Reconnect"
        elif inQueue:
            gameflow_phase = "Matchmaking"
        elif inLobby:
            gameflow_phase = "Lobby"
    return gameflow_phase

async def get_champ_select_session(connection: Connection) -> dict[str, Any]: #设计该函数的原因是在创建随机自定义房间然后通过接口删除房间和匹配状态后，用户会仍然处于英雄选择阶段，但是无法在客户端内进行操作。这时，往往通过传统的接口获取不到英雄选择会话，而通过阵容匹配接口可以获取到。另一方面，传统自定义对局的英雄选择阶段无法通过阵容匹配接口获取其会话，不然清一色地用阵容匹配接口就完事了（The reason why this function is designed is that when the user creates an all random custom lobby, starts the champ select stage and then delete this lobby and the matchmaking state through API, the user is still in a champ select stage, but can't do anything through the client. In that case, the champ select session can't be obtained by the legacy endpoint, but can be obtained by the team-builder endpoint. On the other hand, the champ select session of a legacy custom game can't be obtained through the team-builder endpoint, or I would simply use that endpoint）
    champ_select_session: dict[str, Any] = await (await connection.request("GET", "/lol-lobby-team-builder/champ-select/v1/session")).json()
    if "errorCode" in champ_select_session and champ_select_session["httpStatus"] == 404 and champ_select_session["message"] == "No champ select session in progress.":
        champ_select_session = await (await connection.request("GET", "/lol-champ-select/v1/session")).json()
    return champ_select_session

async def update_champ_select_session(connection: Connection, old_session: dict[str, Any], force_update: bool = False, max_retry: int | None = None) -> dict[str, Any]:
    '''
    更新英雄选择会话。<br>Update the champ select session.
    
    :param connection: 通过lcu_driver库创建的连接对象。<br>A Connection object created through lcu-driver library.
    :type connection: lcu_driver.connection.Connection
    :param old_session: 旧的英雄选择会话。<br>The old champ select session.<br>如果旧的会话是异常会话，则直接返回，因为没有更新的必要。<br>If the old session is an error session, then it'll be directly returned, for there's no need to update it.
    :type old_session: dict[str, Any]
    :param force_update: 是否通过交换两个召唤师技能的顺序来强制更新英雄选择会话。默认为假。<br>Whether to force the champ select session to update by swapping the order of two summoner spells. False by default.
    :type force_update: bool
    :param max_retry: 最大尝试次数。如果未指定，则始终尝试更新。<br>The limit of attempts. If unspecified, the function will insist on updating.
    :type max_retry: int
    :return: 新的英雄选择会话，或者旧的异常会话。<br>The new champ select session or an old error session.
    :rtype: dict[str, Any]
    '''
    if "errorCode" in old_session:
        return old_session
    if force_update:
        mySelection: dict[str, int] = await (await connection.request("GET", "/lol-champ-select/v1/session/my-selection")).json()
        body: dict[str, int] = {"spell1Id": mySelection["spell2Id"], "spell2Id": mySelection["spell1Id"]}
        response: dict[str, Any] | None = await (await connection.request("PATCH", "/lol-champ-select/v1/session/my-selection", data = body)).json() #通过更新召唤师技能来更新英雄选择会话（Update the champ select session by updating the summoner spells）
        body = {"spell1Id": mySelection["spell1Id"], "spell2Id": mySelection["spell2Id"]}
        response: dict[str, Any] | None = await (await connection.request("PATCH", "/lol-champ-select/v1/session/my-selection", data = body)).json() #还原召唤师技能顺序（Restore the original order of summoner spells）
    count: int = 0 #尝试次数（Number of attempts）
    while True:
        count += 1
        new_session: dict[str, Any] = await (await connection.request("GET", "/lol-champ-select/v1/session")).json()
        if new_session != old_session or max_retry != None and count > max_retry:
            break
    return new_session

async def get_champSelect_localPlayer(connection: Connection, current_puuid: str) -> dict[str, Any]: #已弃用（Deprecated）
    champ_select_session: dict[str, Any] = await get_champ_select_session(connection)
    players: list[dict[str, Any]] = champ_select_session["myTeam"] + champ_select_session["theirTeam"]
    for player in players:
        if player["puuid"] == current_puuid:
            return player
    else:
        return {}

async def get_champSelect_player(connection: Connection, cellId: int | None = None) -> dict[str, Any]:
    '''
    从英雄选择会话中提取某个槽位的玩家信息。<br>Get the information of a player with some `cellId` from the champ select session.
    
    :param connection: 通过lcu_driver库创建的连接对象。<br>A Connection object created through lcu-driver library.
    :type connection: lcu_driver.connection.Connection
    :param cellId: 同extract_champSelect_player函数。<br>Same as in `extract_champSelect_player` function.
    :type cellId: int
    :return: 同extract_champSelect_player函数。<br>Same as in `extract_champSelect_player` function.
    :rtype: dict[str, Any]
    '''
    champ_select_session: dict[str, Any] = await get_champ_select_session(connection)
    if "errorCode" in champ_select_session:
        return {}
    else:
        #参数预处理（Parameter pre-process）
        if cellId == None:
            cellId = champ_select_session["localPlayerCellId"]
        return extract_champSelect_player(champ_select_session, cellId = cellId)

def extract_champSelect_player(champ_select_session: dict[str, Any], cellId: int | None = None) -> dict[str, Any]:
    '''
    从英雄选择会话中提取某个槽位的玩家信息。离线使用。<br>Get the information of a player with some `cellId` from the champ select session. For offline use.
    
    :param champ_select_session: 英雄选择会话。<br>Champ select session.
    :type champ_select_session: dict[str, Any]
    :param cellId: 待提取信息的玩家的槽位序号。<br>The cellId of the player to extract the information.<br>如果不指定，则默认获取用户的信息。<br>If unspecified, the function will return the information of the user itself.
    :type cellId: int
    :return: 指定槽位序号的玩家信息。<br>Information of the player with specified `cellId`.
    :rtype: dict[str, Any]
    '''
    #参数预处理（Parameter pre-process）
    if cellId == None:
        cellId = champ_select_session["localPlayerCellId"]
    players: list[dict[str, Any]] = champ_select_session["myTeam"] + champ_select_session["theirTeam"]
    player_cellId_map: dict[int, dict[str, Any]] = {player["cellId"]: player for player in players}
    if cellId in player_cellId_map:
        return player_cellId_map[cellId]
    else:
        return {}

async def sort_ChampSelect_players(connection: Connection, LoLChampions: dict[int, dict[str, Any]], championSkins: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], wardSkins: dict[int, dict[str, Any]], playerMode: int = 1, log: LogManager = LogManager(), verbose: bool = True) -> pandas.DataFrame: #以下代码来自聊天服务脚本（The following code come from Customized Program 16）
    logPrint = log.logPrint
    champSelect_player_header_keys: list[str] = list(champSelect_player_header.keys())
    champSelect_player_data: dict[str, list[Any]] = {}
    for i in range(len(champSelect_player_header_keys)):
        key: str = champSelect_player_header_keys[i]
        champSelect_player_data[key] = []
    #所需数据初始化（Initialization of needed data）
    champ_select_session: dict[str, Any] = await get_champ_select_session(connection)
    if playerMode == 1:
        players: list[dict[str, Any]] = champ_select_session["myTeam"] + champ_select_session["theirTeam"]
    elif playerMode == 2:
        players = champ_select_session["myTeam"]
    elif playerMode == 3:
        players = champ_select_session["theirTeam"]
    else:
        players = []
    #数据整理核心部分（Data assignment - core part）
    for player in players:
        if player["nameVisibilityType"] != "HIDDEN":
            player_info_recapture: int = 0
            player_info: dict[str, Any] = await get_info(connection, player["puuid"])
            while not player_info["info_got"] and player_info["body"]["httpStatus"] != 404 and player_info_recapture < 3:
                logPrint(player_info["message"], verbose = verbose)
                player_info_recapture += 1
                logPrint("槽位序号为%d的玩家信息（玩家通用唯一识别码：%s）获取失败！正在第%d次尝试重新获取该玩家信息……\nInformation of player (puuid: %s, cellId: %d) capture failed! Recapturing this player's information ... Times tried: %d" %(player["cellId"], player["puuid"], player_info_recapture, player["puuid"], player["cellId"], player_info_recapture), verbose = verbose)
                player_info = await get_info(connection, player["puuid"])
            if not player_info["info_got"]:
                logPrint(player_info["message"], verbose = verbose)
                logPrint("槽位序号为%d的玩家信息（玩家通用唯一识别码：%s）获取失败！\nInformation of player (puuid: %s, cellId: %d) capture failed!" %(player["cellId"], player["puuid"], player["puuid"], player["cellId"]), verbose = verbose)
        for i in range(len(champSelect_player_header_keys)):
            key: str = champSelect_player_header_keys[i]
            if i <= 22:
                if i in {4, 5, 20}: #召唤师信息相关键（Summoner information-related keys）
                    champSelect_player_data[key].append(player[key] if player["nameVisibilityType"] == "HIDDEN" else player_info["body"][key] if player_info["info_got"] else "")
                else:
                    champSelect_player_data[key].append(player[key])
            else:
                if i == 23: #阵营名称（`team_color`）
                    champSelect_player_data[key].append(team_colors_int[player["team"]])
                elif i <= 25: #选用英雄相关键（Champion-related keys）
                    champSelect_player_data[key].append(LoLChampions[player["championId"]][key.split()[1]] if player["championId"] in LoLChampions else "")
                elif i <= 27: #声明英雄相关键（Champion pick intent-related keys）
                    champSelect_player_data[key].append(LoLChampions[player["championPickIntent"]][key.split()[1]] if player["championPickIntent"] in LoLChampions else "")
                elif i <= 37: #选用皮肤相关键（selected skin-related keys）
                    selectedSkinId = player["selectedSkinId"]
                    if selectedSkinId in championSkins and key.split()[1] in championSkins[selectedSkinId]:
                        if i == 28 or i == 29:
                            champSelect_player_data[key].append(championSkins[selectedSkinId][key.split()[1]])
                        elif i == 35:
                            champSelect_player_data[key].append(krarities[championSkins[selectedSkinId][key.split()[1]]])
                        else:
                            iconPath: str = championSkins[selectedSkinId][key.split()[1]]
                            champSelect_player_data[key].append("" if iconPath == "" else urljoin(connection.address, iconPath))
                    else:
                        champSelect_player_data[key].append("")
                elif i <= 39: #召唤师技能1相关键（Summoner spell 1-related keys）
                    if player["spell1Id"] in spells:
                        if i == 38:
                            champSelect_player_data[key].append(spells[player["spell1Id"]][key.split()[1]])
                        else:
                            iconPath = spells[player["spell1Id"]][key.split()[1]]
                            champSelect_player_data[key].append("" if iconPath == "" else urljoin(connection.address, iconPath))
                    else:
                        champSelect_player_data[key].append("")
                elif i <= 41: #召唤师技能2相关键（Summoner spell 2-related keys）
                    if player["spell2Id"] in spells:
                        if i == 40:
                            champSelect_player_data[key].append(spells[player["spell2Id"]][key.split()[1]])
                        else:
                            iconPath = spells[player["spell2Id"]][key.split()[1]]
                            champSelect_player_data[key].append("" if iconPath == "" else urljoin(connection.address, iconPath))
                    else:
                        champSelect_player_data[key].append("")
                else: #饰品相关键（Ward-related keys）
                    if player["wardSkinId"] in wardSkins:
                        if i == 44 or i == 45:
                            iconPath = wardSkins[player["wardSkinId"]][key.split()[1]]
                            champSelect_player_data[key].append("" if iconPath == "" else urljoin(connection.address, iconPath))
                        elif i == 47:
                            champSelect_player_data[key].append(wardSkins[player["wardSkinId"]]["rarities"][0]["rarity"])
                        else:
                            champSelect_player_data[key].append(wardSkins[player["wardSkinId"]][key.split()[1]])
                    else:
                        champSelect_player_data[key].append("")
    #数据框列序整理（Dataframe column ordering）
    champSelect_player_statistics_output_order: list[int] = [21, 23, 1, 4, 20, 5, 13, 19, 15, 10, 9, 8, 7, 0, 6, 2, 24, 25, 3, 26, 27, 17, 38, 39, 18, 40, 41, 16, 28, 29, 35, 30, 31, 32, 33, 34, 36, 37, 22, 42, 43, 47, 46, 44, 45, 14, 11, 12]
    champSelect_player_data_organized: dict[str, list[Any]] = {}
    for i in champSelect_player_statistics_output_order:
        key: str = champSelect_player_header_keys[i]
        champSelect_player_data_organized[key] = champSelect_player_data[key]
    champSelect_player_df: pandas.DataFrame = pandas.DataFrame(data = champSelect_player_data_organized)
    for column in champSelect_player_df:
        if champSelect_player_df[column].dtype == "bool":
            champSelect_player_df[column] = champSelect_player_df[column].astype(str)
            champSelect_player_df[column] = list(map(lambda x: "√" if x == "True" else "", champSelect_player_df[column].to_list()))
    champSelect_player_df = pandas.concat([pandas.DataFrame([champSelect_player_header])[champSelect_player_df.columns], champSelect_player_df], ignore_index = True)
    return champSelect_player_df

async def sort_inGame_players(connection: Connection, LoLChampions: dict[int, dict[str, Any]], championSkins: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], log: LogManager = LogManager(), verbose: bool = True) -> pandas.DataFrame:
    logPrint = log.logPrint
    inGame_player_header_keys: list[str] = list(inGame_player_header.keys())
    inGame_player_data: dict[str, list[Any]] = {}
    for i in range(len(inGame_player_header_keys)):
        key: str = inGame_player_header_keys[i]
        inGame_player_data[key] = []
    gameflow_phase: str = await (await connection.request("GET", "/lol-gameflow/v1/gameflow-phase")).json()
    if gameflow_phase in {"InProgress", "Reconnect"}:
        gameflow_session: dict[str, Any] = await (await connection.request("GET", "/lol-gameflow/v1/session")).json()
        playerChampionSelections: dict[str, dict[str, Any]] = {player["puuid"]: player for player in gameflow_session["gameData"]["playerChampionSelections"]}
        teamOne: list[dict[str, Any]] = gameflow_session["gameData"]["teamOne"]
        teamTwo: list[dict[str, Any]] = gameflow_session["gameData"]["teamTwo"]
        for player in teamOne + teamTwo:
            loadout: dict[str, Any] = {}
            if "puuid" in player:
                player_info_recapture: int = 0
                player_info: dict[str, list[Any]] = await get_info(connection, player["puuid"])
                while not player_info["info_got"] and player_info["body"]["httpStatus"] != 404 and player_info_recapture < 3:
                    logPrint(player_info["message"], verbose = verbose)
                    player_info_recapture += 1
                    logPrint("参与者序号为%d的玩家信息（玩家通用唯一识别码：%s）获取失败！正在第%d次尝试重新获取该玩家信息……\nInformation of player (puuid: %s, teamParticipantId: %d) capture failed! Recapturing this player's information ... Times tried: %d" %(player["teamParticipantId"], player["puuid"], player_info_recapture, player["puuid"], player["teamParticipantId"], player_info_recapture), verbose = verbose)
                    player_info = await get_info(connection, player["puuid"])
                if not player_info["info_got"]:
                    logPrint(player_info["message"], verbose = verbose)
                    logPrint("参与者序号为%d的玩家信息（玩家通用唯一识别码：%s）获取失败！\nInformation of player (puuid: %s, teamParticipantId: %d) capture failed!" %(player["teamParticipantId"], player["puuid"], player["puuid"], player["teamParticipantId"]), verbose = verbose)
                loadout_got: bool = player["puuid"] in playerChampionSelections
                if loadout_got:
                    loadout = playerChampionSelections[player["puuid"]]
            else:
                loadout_got = False
            for i in range(len(inGame_player_header_keys)):
                key: str = inGame_player_header_keys[i]
                if i <= 28:
                    if i == 11: #阵营代号（`teamId`）
                        inGame_player_data[key].append(100 if player in teamOne else 200 if player in teamTwo else "")
                    elif i == 12 or i == 13: #英雄相关键（Champion-related keys）
                        inGame_player_data[key].append(LoLChampions[player["championId"]][key.split()[1]] if player["championId"] in LoLChampions else "")
                    elif i >= 14 and i <= 23: #上次选用皮肤相关键（Last selected skin-related keys）
                        lastSelectedSkinIndex: int = 0 if player["lastSelectedSkinIndex"] == 0 else player["championId"] * 1000 + player["lastSelectedSkinIndex"] #仅考虑非经典皮肤。下同（Only considering non-classic skins. So does the following）
                        if lastSelectedSkinIndex != 0 and lastSelectedSkinIndex in championSkins and key.split()[1] in championSkins[lastSelectedSkinIndex]:
                            if i == 21: #上次选用皮肤品质（`lastSelectedSkin rarity`）
                                inGame_player_data[key].append(krarities[championSkins[lastSelectedSkinIndex][key.split()[1]]])
                            else:
                                inGame_player_data[key].append(championSkins[lastSelectedSkinIndex][key.split()[1]])
                        else:
                            inGame_player_data[key].append("")
                    elif i == 24 or i == 25: #召唤师图标相关键（Profile icon-related keys）
                        inGame_player_data[key].append(summonerIcons[player["profileIconId"]].get(key.split()[1], "") if player["profileIconId"] in summonerIcons else "")
                    elif i == 26 or i == 27: #召唤师信息相关键（Summoner information-related keys）
                        inGame_player_data[key].append(player_info["body"][key] if "puuid" in player and player_info["info_got"] else "")
                    elif i == 28: #电脑玩家（`isHumanoid`）
                        inGame_player_data[key].append(not "puuid" in player or player["puuid"] == BOT_UUID)
                    else:
                        inGame_player_data[key].append(player.get(key, "")) #人类玩家和电脑玩家的数据格式不同（The formats of human and bot players' data aren't the same）
                else:
                    if loadout_got:
                        if i >= 32 and i <= 41: #选用皮肤相关键（Selected skin-related keys）
                            selectedSkinIndex: int = 0 if loadout["selectedSkinIndex"] == 0 else player["championId"] * 1000 + loadout["selectedSkinIndex"]
                            if selectedSkinIndex != 0 and selectedSkinIndex in championSkins and key.split()[1] in championSkins[selectedSkinIndex]:
                                if i == 39: #上次选用皮肤品质（`selectedSkin rarity`）
                                    inGame_player_data[key].append(krarities[championSkins[selectedSkinIndex][key.split()[1]]])
                                else:
                                    inGame_player_data[key].append(championSkins[selectedSkinIndex][key.split()[1]])
                            else:
                                inGame_player_data[key].append("")
                        elif i >= 42: #召唤师技能相关键（Summoner spell-related keys）
                            spellId: int = loadout["%sId" %(key.split()[0])]
                            inGame_player_data[key].append(spells[spellId][key.split()[1]] if spellId in spells else "")
                        else:
                            inGame_player_data[key].append(loadout[key])
                    else:
                        inGame_player_data[key].append("")
    inGame_player_statistics_output_order: list[int] = [11, 26, 27, 7, 3, 24, 9, 10, 28, 12, 13, 42, 44, 4, 5, 15, 33]
    inGame_player_data_organized: dict[str, list[Any]] = {}
    for i in inGame_player_statistics_output_order:
        key: str = inGame_player_header_keys[i]
        inGame_player_data_organized[key] = inGame_player_data[key]
    inGame_player_df: pandas.DataFrame = pandas.DataFrame(data = inGame_player_data_organized)
    for column in inGame_player_df:
        if inGame_player_df[column].dtype == "bool":
            inGame_player_df[column] = inGame_player_df[column].astype(str)
            inGame_player_df[column] = list(map(lambda x: "√" if x == "True" else "", inGame_player_df[column].to_list()))
    inGame_player_df = pandas.concat([pandas.DataFrame([inGame_player_header])[inGame_player_df.columns], inGame_player_df], ignore_index = True)
    return inGame_player_df

async def sort_postgame_players(connection: Connection, gameId: int, queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], puuid: str | list[str] = "", useAllVersions: bool = False, versionList: list[Patch] | None = None, locale: str = "en_US", log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any], pandas.DataFrame]:
    if versionList == None:
        versionList = []
    if log == None:
        log = LogManager()
    puuidList: list[str] = [puuid] if isinstance(puuid, str) else puuid
    status, LoLGame_info = await get_LoLGame_info(connection, gameId, log = log)
    if status == 200:
        LoLGame_info_df: pandas.DataFrame = sort_LoLGame_info(LoLGame_info, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments, gameIndex = 1, current_puuid = puuidList, useAllVersions = useAllVersions, versionList = versionList, locale = locale, sortStats = False, log = log, verbose = verbose)[0]
    else:
        LoLGame_stat_header_keys: list[str] = list(LoLGame_stat_header.keys())
        LoLGame_info_data: dict[str, list[Any]] = {}
        for i in range(len(LoLGame_stat_header)):
            key: str = LoLGame_stat_header_keys[i]
            LoLGame_info_data[key] = []
        #数据框列排序（Dataframe column sorting）
        LoLGame_info_statistics_output_order: list[int] = [42, 210, 16, 225, 26, 20, 27, 25, 24, 22, 19, 31, 35, 36, 220, 221, 223, 224, 45, 38, 39, 156, 157, 158, 159, 160, 161, 162, 192, 204, 193, 205, 194, 206, 195, 207, 196, 208, 197, 209, 72, 50, 43, 212, 213, 216, 217, 46, 141, 142, 74, 71, 75, 54, 53, 58, 57, 56, 55, 51, 145, 131, 84, 150, 135, 143, 137, 112, 78, 147, 136, 111, 77, 146, 73, 48, 47, 139, 144, 138, 113, 79, 148, 49, 151, 154, 153, 132, 152, 61, 214, 62, 215, 140, 80, 82, 81, 149, 63, 76, 188, 190, 176, 170, 177, 171, 178, 172, 179, 173, 180, 174, 181, 175, 44, 52, 134, 59, 60, 218, 133, 237, 231, 226, 284, 227, 271, 239, 236, 240, 232, 274, 263, 249, 279, 265, 272, 267, 251, 243, 276, 266, 250, 242, 275, 238, 229, 228, 269, 273, 268, 252, 244, 277, 230, 280, 283, 282, 264, 281, 233, 234, 270, 245, 247, 246, 285, 278, 235, 241, 287, 298, 292, 286, 345, 346, 348, 288, 332, 300, 297, 301, 293, 335, 324, 310, 340, 326, 333, 328, 312, 304, 337, 327, 311, 303, 336, 299, 290, 289, 330, 334, 329, 313, 305, 338, 291, 341, 344, 343, 325, 342, 294, 295, 349, 331, 306, 307, 308, 347, 339, 296, 302]
        LoLGame_info_data_organized: dict[str, list[Any]] = {}
        for i in LoLGame_info_statistics_output_order:
            key: str = LoLGame_stat_header_keys[i]
            LoLGame_info_data_organized[key] = LoLGame_info_data[key]
        LoLGame_info_df = pandas.DataFrame(data = LoLGame_info_data_organized)
        LoLGame_info_df = pandas.concat([pandas.DataFrame([LoLGame_stat_header])[LoLGame_info_df.columns], LoLGame_info_df], ignore_index = True)
    LoLGame_info_df = LoLGame_info_df.transpose()
    return (status, LoLGame_info, LoLGame_info_df)
