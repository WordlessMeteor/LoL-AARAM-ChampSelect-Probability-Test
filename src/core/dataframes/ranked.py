from lcu_driver.connection import Connection
import json, os, pandas, sys, time
from typing import Any
wd = os.getcwd()
if not wd in sys.path:
    sys.path.append(os.getcwd()) #确保在“src”文件夹的父级目录运行此代码（Make sure this program is run under the parent folder of the "src" folder）
from src.utils.logging import LogManager
from src.utils.summoner import get_info
from src.core.config.headers import game_leaderboard_header
from src.core.config.localization import queueTypes, tiers, ratedTiers

async def sort_game_leaderboard(connection: Connection, queueTypes_list: list[str] | None = None, puuids: list[str] | None = None, log: LogManager | None = None, verbose: bool = True) -> pandas.DataFrame:
    if queueTypes_list == None:
        queueTypes_list = []
    if puuids == None:
        puuids = []
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    if queueTypes_list == []:
        challenger_ladder_queueTypes: list[str] = await (await connection.request("GET", "/lol-ranked/v1/challenger-ladders-enabled")).json()
        topRated_ladder_queueTypes: list[str] = await (await connection.request("GET", "/lol-ranked/v1/top-rated-ladders-enabled")).json()
        queueTypes_list = challenger_ladder_queueTypes + topRated_ladder_queueTypes
    game_leaderboard_header_keys: list[str] = list(game_leaderboard_header.keys())
    game_leaderboard_data: dict[str, list[Any]] = {}
    for i in range(len(game_leaderboard_header_keys)):
        key: str = game_leaderboard_header_keys[i]
        game_leaderboard_data[key] = []
    for queueType in queueTypes_list:
        params: dict[str, str] = {"queueType": queueType, "puuids": json.dumps(puuids, ensure_ascii = False)}
        game_leaderboard: dict[str, dict[str, Any]] = await (await connection.request("GET", "/lol-ranked/v1/social-leaderboard-ranked-queue-stats-for-puuids", params = params)).json()
        for participant_puuid_iter in game_leaderboard:
            participant_leaderboard: dict[str, Any] = game_leaderboard[participant_puuid_iter]
            participantInfo: dict[str, Any] = await get_info(connection, participant_puuid_iter)
            if participantInfo["info_got"]:
                participantInfo_body: dict[str, Any] = participantInfo["body"]
                for i in range(len(game_leaderboard_header_keys)):
                    key: str = game_leaderboard_header_keys[i]
                    if i <= 3:
                        game_leaderboard_data[key].append(participantInfo_body[key])
                    elif i <= 15:
                        if i == 4: #分级（`division`）
                            game_leaderboard_data[key].append("" if participant_leaderboard["division"] == "NA" else participant_leaderboard["division"])
                        elif i == 11: #战区（`queueType`）
                            game_leaderboard_data[key].append(queueTypes[participant_leaderboard["queueType"]])
                        elif i == 13: #段位（`ratedTier`）
                            game_leaderboard_data[key].append(ratedTiers[participant_leaderboard["ratedTier"]])
                        elif i == 14: #段位（`tier`）
                            game_leaderboard_data[key].append(tiers[participant_leaderboard["tier"]])
                        else:
                            game_leaderboard_data[key].append(participant_leaderboard[key])
                    elif i == 16: #段位（`tier / ratedTier`）
                        game_leaderboard_data[key].append(ratedTiers[participant_leaderboard["ratedTier"]] if queueType in topRated_ladder_queueTypes else tiers[participant_leaderboard["tier"]])
                    elif i == 17: #胜点（`leaguePoints / ratedRating`）
                        game_leaderboard_data[key].append(participant_leaderboard["ratedRating"] if queueType in topRated_ladder_queueTypes else participant_leaderboard["leaguePoints"])
                    elif i == 18: #获取时间戳（`timestamp`）
                        game_leaderboard_data[key].append(time.time())
                    else: #获取时间（`time`）
                        game_leaderboard_data[key].append(time.strftime("%Y年%m月%d日%H时%M分%S秒", time.localtime()))
            else:
                logPrint(participantInfo["message"], verbose = verbose)
    game_leaderboard_statistics_output_order: list[int] = [11, 1, 2, 3, 0, 16, 4, 17, 15, 7, 5, 9, 10, 8, 19]
    game_leaderboard_data_organized: dict[str, Any] = {}
    for i in game_leaderboard_statistics_output_order:
        key: str = game_leaderboard_header_keys[i]
        game_leaderboard_data_organized[key] = game_leaderboard_data[key]
    game_leaderboard_df: pandas.DataFrame = pandas.DataFrame(data = game_leaderboard_data_organized)
    for column in game_leaderboard_df:
        if game_leaderboard_df[column].dtype == "bool":
            game_leaderboard_df[column] = game_leaderboard_df[column].astype(str)
            game_leaderboard_df[column] = list(map(lambda x: "√" if x == "True" else "", game_leaderboard_df[column].to_list()))
    game_leaderboard_df = pandas.concat([pandas.DataFrame([game_leaderboard_header])[game_leaderboard_df.columns], game_leaderboard_df], ignore_index = True)
    return game_leaderboard_df
