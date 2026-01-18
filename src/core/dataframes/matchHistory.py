from lcu_driver.connection import Connection
import os, pandas, re, requests, time, sys
from urllib.parse import urljoin
from typing import Any
wd = os.getcwd()
if not wd in sys.path:
    sys.path.append(os.getcwd()) #确保在“src”文件夹的父级目录运行此代码（Make sure this program is run under the parent folder of the "src" folder）
from src.utils.summoner import get_info, get_info_name
from src.utils.logging import LogManager
from src.utils.format import lcuTimestamp
from src.utils.patch import Patch, FindPostPatch
from src.utils.webRequest import requestUrl, SGPSession
from src.core.config.headers import LoLHistory_header, LoLGame_info_header, LoLGame_timeline_header, LoLGame_event_header, TFTHistory_header, TFTGame_info_header
from src.core.config.localization import language_cdragon, gamemaps, tiers, gameTypes_history, team_colors_int, endOfGameResults, lanes, roles, subteam_colors, augment_rarity, eventTypes_lcu, buildingTypes, laneTypes, monsterSubTypes, monsterTypes, towerTypes, traitStyles, rarities

async def get_LoLHistory(connection: Connection, puuid: str, begIndex: int = 0, endIndex: int = 500, log: LogManager | None = None, verbose: bool = True) -> tuple[bool, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logInput = log.logInput
    logPrint = log.logPrint
    count: int = 0 #存储内部服务器错误次数（Stores the times of internal server error）
    error_occurred: bool = False
    LoLHistory_get: bool = False
    while True:
        count += 1
        LoLHistory: dict[str, Any] = await (await connection.request("GET", f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex={begIndex}&endIndex={endIndex}")).json()
        if count > 3:
            logPrint("英雄联盟对局记录获取失败！请等待官方修复对局记录服务！\nLoL match history capture failure! Please wait for Tencent to fix the match history service!", verbose = verbose)
            break
        if "errorCode" in LoLHistory:
            logPrint(LoLHistory, verbose = verbose)
            if LoLHistory["httpStatus"] == 400:
                if "Error getting match list for summoner" in LoLHistory["message"]:
                    LoLHistory_url: str = "%s/lol-match-history/v1/products/lol/%s/matches?begIndex=0&endIndex=200" %(connection.address, puuid)
                    logPrint("请打开以下网址，输入如下所示的用户名和密码，打开后在命令行中按回车键继续（Please open the following website, type in the username and password accordingly and press Enter to continue）：\n网址（URL）：\t\t%s\n用户名（Username）：\triot\n密码（Password）：\t%s\n或者输入空格分隔的两个自然数以重新指定对局索引下限和上限。\nOr submit two nonnegative integers split by space to respecify the begIndex and endIndex." %(LoLHistory_url, connection.auth_key))
                    cont: str = logInput()
                    if cont == "":
                        continue
                    else:
                        try:
                            begIndex, endIndex = map(int, cont.split())
                        except:
                            break
                        else:
                            continue
                elif "body was empty" in LoLHistory["message"]:
                    logPrint("这位召唤师从5月1日起就没有进行过任何英雄联盟对局。\nThis summoner hasn't played any LoL game yet since May 1st.", verbose = verbose)
                    break
            elif LoLHistory["httpStatus"] == 500:
                if "500 Internal Server Error" in LoLHistory["message"]:
                    if not error_occurred:
                        logPrint("您所在大区的对局记录服务异常。尝试重新获取数据……\nThe match history service provided on your server isn't in place. Trying to recapture the history data ...", verbose = verbose)
                        error_occurred = True
            logPrint(f"正在进行第{count}次尝试……\nTimes tried: No. {count} ...", verbose = verbose)
        else:
            LoLHistory_get = True
            break
    return (LoLHistory_get, LoLHistory)

async def get_LoLGame_info(connection: Connection, matchId: int, log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    count: int = 0
    error1_hint_printed: bool = False
    error2_hint_printed: bool = False
    while True:
        count += 1
        LoLGame_info: dict[str, Any] = await (await connection.request("GET", f"/lol-match-history/v1/games/{matchId}")).json()
        #尝试修复错误（Try to fix the error）
        if "errorCode" in LoLGame_info:
            logPrint(LoLGame_info, verbose = verbose)
            status: int = LoLGame_info["httpStatus"]
            if count > 3:
                logPrint(f"对局{matchId}信息获取失败！\nMatch {matchId} information capture failure!", verbose = verbose)
                break
            if status == 401: #{'errorCode': 'RPC_ERROR', 'httpStatus': 401, 'implementationDetails': {}, 'message': '{"status":{"message":"Unauthorized","status_code":401}}'}
                logPrint("未授权。请检查服务器状态。\nUnauthorized. Please check the server status.")
                break
            elif status == 403: #{'errorCode': 'RPC_ERROR', 'httpStatus': 403, 'implementationDetails': {}, 'message': '{"status":{"message":"Forbidden","status_code":403}}'}
                logPrint(f"拒绝访问。\nPermission denied.", verbose = verbose)
                break
            elif status == 404:
                logPrint(f"未找到序号为{matchId}的回放文件！将忽略该序号。\nMatch file with matchId {matchId} not found! The program will ignore this matchId.", verbose = verbose)
                break
            elif status == 415:
                if LoLGame_info["message"] == "could not convert GAMHS data to match-history format":
                    logPrint(f"对局{matchId}信息不可用。请检查该对局是否为云顶之弈对局。\nMatch {matchId} information not available. Please check if it's a TFT match.", verbose = verbose)
                break
            elif status == 500:
                if "500 Internal Server Error" in LoLGame_info["message"]:
                    if not error1_hint_printed:
                        logPrint("您所在大区的对局记录服务异常。尝试重新获取数据……\nThe match history service provided on your server isn't in place. Trying to recapture the history data ...", verbose = verbose)
                        error1_hint_printed = True
            elif status == 503:
                if "Service Unavailable - Connection retries limit exceeded. Response timed out" in LoLGame_info["message"]:
                    if not error2_hint_printed:
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
                        error2_hint_printed = True
            elif status == 504:
                if "Connection timed out after " in LoLGame_info["message"]:
                    logPrint("对局信息保存超时！请检查网速状况！\nGame information saving operation timed out after 20000 milliseconds with 0 bytes received! Please check the netspeed!", verbose = verbose)
                    break
            logPrint(f"正在第{count}次尝试获取对局{matchId}信息……\nTimes trying to capture Match {matchId}: No. {count} ...", verbose = verbose)
        else:
            status = 200
            break
    return (status, LoLGame_info)

async def get_game_info_sgp(connection: Connection, session: SGPSession, matchId: str, checkLoL: bool = True, checkTFT: bool = True, skipTFT: bool = False, log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    status: int = -1
    game_info: dict[str, Any] = {}
    #检查英雄联盟对局（Check LoL match）
    if checkLoL:
        count: int = 0
        while True:
            count += 1
            game_info = (await session.request(connection, "GET", f"/match-history-query/v1/products/lol/{matchId}/SUMMARY")).json()
            #尝试修复错误（Try to fix the error）
            if "errorCode" in game_info:
                logPrint(game_info, verbose = verbose)
                status = game_info["httpStatus"]
                if count > 3:
                    logPrint(f"英雄联盟对局{matchId}信息获取失败！\nLoL match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 404:
                    if game_info["errorCode"] == "RESOURCE_NOT_FOUND" and game_info["message"] == "match file not found":
                        logPrint(f"未找到序号为{matchId}的英雄联盟回放文件！\nLoL match file with matchId {matchId} not found!", verbose = verbose)
                        checkTFT = True
                        break
                logPrint(f"正在第{count}次尝试获取英雄联盟对局{matchId}信息……\nTimes trying to capture LoL Match {matchId}: No. {count} ...", verbose = verbose)
            elif "status" in game_info and isinstance(game_info["status"], dict) and all(_ in ["message", "status_code"] for _ in game_info["status"]):
                logPrint(game_info, verbose = verbose)
                status = game_info["status"]["status_code"]
                if count > 3:
                    logPrint(f"英雄联盟对局{matchId}信息获取失败！\nLoL match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 503:
                    if game_info["status"]["message"] == "Service Unavailable - Connection retries limit exceeded. Response timed out.":
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
            else:
                status = 200
                break
    #检查云顶之弈对局（Check TFT match）
    if not skipTFT and checkTFT:
        count: int = 0
        while True:
            count += 1
            game_info = (await session.request(connection, "GET", f"/match-history-query/v1/products/tft/{matchId}/SUMMARY")).json()
            #尝试修复错误（Try to fix the error）
            if "errorCode" in game_info:
                logPrint(game_info, verbose = verbose)
                status = game_info["httpStatus"]
                if count > 3:
                    logPrint(f"云顶之弈对局{matchId}信息获取失败！\nTFT match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 404:
                    if game_info["errorCode"] == "RESOURCE_NOT_FOUND" and game_info["message"] == "match file not found":
                        logPrint(f"未找到序号为{matchId}的云顶之弈回放文件！\nTFT match file with matchId {matchId} not found!", verbose = verbose)
                        break
                logPrint(f"正在第{count}次尝试获取云顶之弈对局{matchId}信息……\nTimes trying to capture TFT Match {matchId}: No. {count} ...", verbose = verbose)
            elif "status" in game_info and isinstance(game_info["status"], dict) and all(_ in ["message", "status_code"] for _ in game_info["status"]):
                logPrint(game_info, verbose = verbose)
                status = game_info["status"]["status_code"]
                if count > 3:
                    logPrint(f"云顶之弈对局{matchId}信息获取失败！\nTFT match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 503:
                    if game_info["status"]["message"] == "Service Unavailable - Connection retries limit exceeded. Response timed out.":
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
            else:
                status = 200
                break
    return (status, game_info)

async def get_LoLGame_timeline(connection: Connection, matchId: int, log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    count: int = 0
    error1_hint_printed: bool = False
    error2_hint_printed: bool = False
    while True:
        count += 1
        LoLGame_timeline: dict[str, Any] = await (await connection.request("GET", f"/lol-match-history/v1/game-timelines/{matchId}")).json()
        if "errorCode" in LoLGame_timeline:
            logPrint(LoLGame_timeline, verbose = verbose)
            status: int = LoLGame_timeline["httpStatus"]
            if count > 3:
                logPrint(f"对局{matchId}时间轴获取失败！\nMatch {matchId} timeline capture failure!", verbose = verbose)
                break
            if status == 401:
                logPrint("未授权。请检查服务器状态。\nUnauthorized. Please check the server status.")
                break
            elif status == 403:
                logPrint(f"拒绝访问。\nPermission denied.", verbose = verbose)
                break
            elif status == 404:
                logPrint(f"未找到序号为{matchId}的回放文件！将忽略该序号。\nMatch file with matchId {matchId} not found! The program will ignore this matchId.", verbose = verbose)
                break
            elif status == 415:
                if "could not convert GAMHS data to match-history format" in LoLGame_timeline["message"]:
                    # if LoLGame_info["gameMode"] == "CHERRY":
                    #     logPrint("斗魂竞技场模式不支持查询时间轴！\nTimeline crawling isn't supported in CHERRY matches!", verbose = verbose)
                    # else:
                        logPrint("时间轴加载失败。\nFailed to load timeline.", verbose = verbose)
                break
            elif status == 500:
                if "500 Internal Server Error" in LoLGame_timeline["message"] or "Missing a closing quotation mark in string" in LoLGame_timeline["message"]:
                    if not error1_hint_printed:
                        logPrint("您所在大区的对局记录服务异常。尝试重新获取数据……\nThe match history service provided on your server isn't in place. Trying to recapture the history data ...", verbose = verbose)
                        error1_hint_printed = True
            elif status == 503:
                if "Service Unavailable - Connection retries limit exceeded. Response timed out" in LoLGame_timeline["message"]:
                    if not error2_hint_printed:
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
                        error2_hint_printed = True
            elif status == 504:
                if "Connection timed out after " in LoLGame_timeline["message"]:
                    logPrint("对局时间轴保存超时！请检查网速状况！\nGame timeline saving operation timed out after 20000 milliseconds with 0 bytes received! Please check the netspeed!", verbose = verbose)
                    break
            logPrint(f"正在第{count}次尝试获取对局{matchId}时间轴……\nTimes trying to capture Match {matchId} timeline: No. {count} ...", verbose = verbose)
        else:
            status = 200
            break
    return (status, LoLGame_timeline)

async def get_game_timeline_sgp(connection: Connection, session: SGPSession, matchId: str, checkLoL: bool = True, checkTFT: bool = False, log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    status: int = -1
    game_timeline: dict[str, Any] = {}
    #检查英雄联盟对局（Check LoL match）
    if checkLoL:
        count: int = 0
        while True:
            count += 1
            game_timeline = (await session.request(connection, "GET", f"/match-history-query/v1/products/lol/{matchId}/DETAILS")).json()
            #尝试修复错误（Try to fix the error）
            if "errorCode" in game_timeline:
                logPrint(game_timeline, verbose = verbose)
                status = game_timeline["httpStatus"]
                if count > 3:
                    logPrint(f"英雄联盟对局{matchId}时间轴获取失败！\nLoL match {matchId} timeline capture failure!", verbose = verbose)
                    break
                if status == 404:
                    if game_timeline["errorCode"] == "RESOURCE_NOT_FOUND" and game_timeline["message"] == "match file not found":
                        logPrint(f"未找到序号为{matchId}的英雄联盟回放文件！\nLoL match file with matchId {matchId} not found!", verbose = verbose)
                        break
                logPrint(f"正在第{count}次尝试获取英雄联盟对局{matchId}时间轴……\nTimes trying to capture LoL Match {matchId}: No. {count} ...", verbose = verbose)
            elif "status" in game_timeline and isinstance(game_timeline["status"], dict) and all(_ in ["message", "status_code"] for _ in game_timeline["status"]):
                logPrint(game_timeline, verbose = verbose)
                status = game_timeline["status"]["status_code"]
                if count > 3:
                    logPrint(f"英雄联盟对局{matchId}时间轴获取失败！\nLoL match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 503:
                    if game_timeline["status"]["message"] == "Service Unavailable - Connection retries limit exceeded. Response timed out.":
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
            else:
                status = 200
                break
    #检查云顶之弈对局（Check TFT match）
    if checkTFT:
        count: int = 0
        while True:
            count += 1
            game_timeline = (await session.request(connection, "GET", f"/match-history-query/v1/products/tft/{matchId}/DETAILS")).json()
            #尝试修复错误（Try to fix the error）
            if "errorCode" in game_timeline:
                logPrint(game_timeline, verbose = verbose)
                status = game_timeline["httpStatus"]
                if count > 3:
                    logPrint(f"云顶之弈对局{matchId}信息获取失败！\nTFT match {matchId} timeline capture failure!", verbose = verbose) #DETAILS接口返回的内容实际上和SUMMARY接口是一样的（The DETAILS endpoint returns the semantically same content as the SUMMARY endpoint）
                    break
                if status == 404:
                    if game_timeline["errorCode"] == "RESOURCE_NOT_FOUND" and game_timeline["message"] == "match file not found":
                        logPrint(f"未找到序号为{matchId}的云顶之弈回放文件！\nTFT match file with matchId {matchId} not found!", verbose = verbose)
                        break
                logPrint(f"正在第{count}次尝试获取云顶之弈对局{matchId}信息……\nTimes trying to capture TFT Match {matchId}: No. {count} ...", verbose = verbose)
            elif "status" in game_timeline and isinstance(game_timeline["status"], dict) and all(_ in ["message", "status_code"] for _ in game_timeline["status"]):
                logPrint(game_timeline, verbose = verbose)
                status = game_timeline["status"]["status_code"]
                if count > 3:
                    logPrint(f"云顶之弈对局{matchId}信息获取失败！\nTFT match {matchId} information capture failure!", verbose = verbose)
                    break
                if status == 503:
                    if game_timeline["status"]["message"] == "Service Unavailable - Connection retries limit exceeded. Response timed out.":
                        logPrint("访问频繁。尝试重新获取数据……\nConnection retries limit exceeded! Trying to recapture the match data ...", verbose = verbose)
            else:
                status = 200
                break
    return (status, game_timeline)

async def get_TFTHistory(connection: Connection, puuid: str, begin: int = 0, count: int = 500, log: LogManager | None = None, verbose: bool = True) -> tuple[bool, dict[str, Any]]:
    if log == None:
        log = LogManager()
    logInput = log.logInput
    logPrint = log.logPrint
    error_count = 0 #存储内部服务器错误次数（Stores the times of internal server error）
    error_occurred = False
    TFTHistory_get = False
    while True:
        error_count += 1
        TFTHistory: dict[str, Any] = await (await connection.request("GET", f"/lol-match-history/v1/products/tft/{puuid}/matches?begin={begin}&count={count}")).json()
        if error_count > 3:
            logPrint("云顶之弈对局记录获取失败！请等待官方修复对局记录服务！\nTFT match history capture failure! Please wait for Tencent to fix the match history service!", verbose = verbose)
            break
        if "errorCode" in TFTHistory:
            logPrint(TFTHistory, verbose = verbose)
            if TFTHistory["httpStatus"] == 400: #以下接口固定返回异常信息（The following endpoint always returns an error）：/lol-match-history/v1/products/tft/current-summoner/matches?begin=0&count=500
                if "Error getting match list for summoner" in TFTHistory["message"]:
                    TFTHistory_url = "%s/lol-match-history/v1/products/tft/%s/matches?begin=0&count=200" %(connection.address, puuid)
                    logPrint("请打开以下网址，输入如下所示的用户名和密码，打开后在命令行中按回车键继续，或输入任意字符以切换召唤师（Please open the following website, type in the username and password accordingly and press Enter to continue or input anything to switch to another summoner）：\n网址（URL）：\t\t%s\n用户名（Username）：\triot\n密码（Password）：\t%s\n或者输入空格分隔的两个自然数以重新指定对局索引下限和对局数。\nOr submit two nonnegative integers split by space to respecify the begin and count." %(TFTHistory_url, connection.auth_key))
                    cont = logInput()
                    if cont == "":
                        continue
                    else:
                        try:
                            begin, count = map(int, cont.split())
                        except ValueError:
                            break
                        else:
                            continue
                elif "body was empty" in TFTHistory["message"]:
                    logPrint("这位召唤师从5月1日起就没有进行过任何云顶之弈对局。\nThis summoner hasn't played any TFT game yet since May 1st.", verbose = verbose)
                    break
            elif TFTHistory["httpStatus"] == 500:
                if "500 Internal Server Error" in TFTHistory["message"]:
                    if not error_occurred:
                        logPrint("您所在大区的对局记录服务异常。尝试重新获取数据……\nThe match history service provided on your server isn't in place. Trying to recapture the history data ...", verbose = verbose)
                        error_occurred = True
            logPrint("正在进行第%d次尝试……\nTimes trying: No. %d ..." %(error_count, error_count), verbose = verbose)
        else:
            TFTHistory_get = True
            break
    return (TFTHistory_get, TFTHistory)

async def get_TFTGame_info(matchId: int, log: LogManager | None = None, verbose: bool = True) -> tuple[int, dict[str, Any]]: #需要通过SGP API实现（Implemented through SGP API）
    if log == None:
        log = LogManager()
    pass

async def reconstruct_LoLHistory(connection: Connection, LoLMatchIDs: list[int], puuid: str | list[str], queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], useAllVersions: bool = True, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]: #参数顺序遵循一个原则：首先是连接信息和数据字典，然后是数据资源字典，最后是一些附加参数（The order of parameters follow a principle: first connection and the data dictionary, then data resource dictionaries and finally some supplemental parameters）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [puuid] if isinstance(puuid, str) else puuid
    current_versions: dict[str, str] = {"queue": "", "summonerIcon": "", "spell": "", "LoLChampion": "", "LoLItem": "", "summonerIcon": "", "perk": "", "perkstyle": "", "CherryAugment": ""}
    unmapped_keys: dict[str, set[int]] = {"queue": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    LoLHistory_header_keys: list[str] = list(LoLHistory_header.keys())
    LoLHistory_data: dict[str, list[Any]] = {}
    for i in range(len(LoLHistory_header_keys)):
        key = LoLHistory_header_keys[i]
        LoLHistory_data[key] = []
    current_puuid_list: list[str] = []
    current_summonerName_list: list[str] = []
    for current_puuid in puuidList:
        info: dict[str, Any] = await get_info(connection, current_puuid)
        if info["info_got"]:
            current_puuid_list.append(info["body"]["puuid"])
            current_summonerName_list.append(get_info_name(info["body"]))
        else:
            logPrint(info["body"], verbose = verbose)
            logPrint(info["message"], verbose = verbose)
    if len(current_puuid_list) == 0:
        logPrint("召唤师信息获取失败。函数将返回空白表。\nSummoner information capture failed! An empty dataframe will be returned instead.", verbose = verbose)
    else:
        #开始赋值（Begin assignment）
        for i in range(len(LoLMatchIDs)): #对于对局记录而言，每场对局对应一条记录（For match history, each record represents a match）
            matchId: int = LoLMatchIDs[i]
            status, LoLGame_info = await get_LoLGame_info(connection, matchId, log = log)
            if status != 200:
                continue
            version: str = LoLGame_info["gameVersion"]
            bigVersion: str = ".".join(version.split(".")[:2])
            #定位该召唤师（Find the index of this player in a match）
            participantIndices: list[int] = []
            for participantIndex in range(len(LoLGame_info["participantIdentities"])):
                if LoLGame_info["participantIdentities"][participantIndex]["player"]["puuid"] in current_puuid_list or LoLGame_info["participantIdentities"][participantIndex]["player"]["gameName"] + "#" + LoLGame_info["participantIdentities"][participantIndex]["player"]["tagLine"] in current_summonerName_list:
                    participantIndices.append(participantIndex)
            if len(participantIndices) == 0:
                logPrint("[%d/%d]对局%d不包括主召唤师。已跳过该对局。\nMatch %d doesn't contain the main summoner. Skipped this match." %(i + 1, len(LoLMatchIDs), matchId, matchId), verbose = verbose)
                continue
            #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
            if useAllVersions:
                ##游戏模式（Game mode）
                queueIds_match_list: list[int] = [LoLGame_info["queueId"]]
                for j in queueIds_match_list:
                    if not j in queues and current_versions["queue"] != bigVersion:
                        queuePatch_adopted: str = bigVersion
                        queue_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, queue_recapture, queuePatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, queuePatch_adopted, queue_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                                queue: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                queuePatch_deserted: str = queuePatch_adopted
                                queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                                queue_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if queue_recapture < 3:
                                    queue_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                                queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                                current_versions["queue"] = queuePatch_adopted
                                unmapped_keys["queue"].clear()
                                break
                        break
                ##召唤师图标（Summoner icon）
                summonerIconIds_match_list: list[int] = sorted(set(map(lambda x: LoLGame_info["participantIdentities"][x]["player"]["profileIcon"], participantIndices)))
                for j in summonerIconIds_match_list:
                    if not j in summonerIcons and current_versions["summonerIcon"] != bigVersion:
                        summonerIconPatch_adopted: str = bigVersion
                        summonerIcon_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）召唤师图标信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师图标信息……\nSummoner icon information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to summoner icons of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, summonerIcon_recapture, summonerIconPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-icons.json" %(summonerIconPatch_adopted, language_cdragon[locale]), session, log)
                                summonerIcon: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                summonerIconPatch_deserted: str = summonerIconPatch_adopted
                                summonerIconPatch_adopted = FindPostPatch(Patch(summonerIconPatch_adopted), versionList)
                                summonerIcon_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIconPatch_deserted, summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_deserted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if summonerIcon_recapture < 3:
                                    summonerIcon_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师图标信息……\nYour network environment is abnormal! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师图标信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the summoner icon (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的召唤师图标信息。\nSummoner icon information changed to Patch %s." %(summonerIconPatch_adopted, summonerIconPatch_adopted), verbose = verbose)
                                summonerIcons = {int(summonerIcon_iter["id"]): summonerIcon_iter for summonerIcon_iter in summonerIcon}
                                current_versions["summonerIcon"] = summonerIconPatch_adopted
                                unmapped_keys["summonerIcon"].clear()
                                break
                        break
                ##英雄：包含选用英雄和禁用英雄（LoL champions, which contain picked and banned ones）
                LoLChampionIds_match_list: list[int] = sorted(set(map(lambda x: LoLGame_info["participants"][x]["championId"], participantIndices)))
                for j in LoLChampionIds_match_list:
                    if not j in LoLChampions and current_versions["LoLChampion"] != bigVersion:
                        LoLChampionPatch_adopted: str = bigVersion
                        LoLChampion_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄信息……\nLoL champion information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL champions of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, LoLChampion_recapture, LoLChampionPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/champion-summary.json" %(LoLChampionPatch_adopted, language_cdragon[locale]), session, log)
                                LoLChampion: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                LoLChampionPatch_deserted: str = LoLChampionPatch_adopted
                                LoLChampionPatch_adopted = FindPostPatch(Patch(LoLChampionPatch_adopted), versionList)
                                LoLChampion_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampionPatch_deserted, LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_deserted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if LoLChampion_recapture < 3:
                                    LoLChampion_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄信息……\nYour network environment is abnormal! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL champion (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的英雄信息。\nLoL champion information changed to Patch %s." %(LoLChampionPatch_adopted, LoLChampionPatch_adopted), verbose = verbose)
                                LoLChampions = {int(LoLChampion_iter["id"]): LoLChampion_iter for LoLChampion_iter in LoLChampion}
                                current_versions["LoLChampion"] = LoLChampionPatch_adopted
                                unmapped_keys["LoLChampion"].clear()
                                break
                        break
                ##召唤师技能（Summoner spells）
                spellIds_match_list: list[int] = sorted(set(map(lambda x: LoLGame_info["participants"][x]["spell1Id"], participantIndices))) + sorted(set(map(lambda x: LoLGame_info["participants"][x]["spell2Id"], participantIndices))) #一般情况下，一名玩家不可能带两个相同的召唤师技能（Normally, a player can't take two same spells）
                for j in spellIds_match_list:
                    if not j in spells and current_versions["spell"] != bigVersion and j != 0: #需要注意电脑玩家的召唤师技能序号都是0（Note that Spell Ids of bot players are both 0s）
                        spellPatch_adopted: str = bigVersion
                        spell_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）召唤师技能信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师技能信息……\nSpell information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to spells of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, spell_recapture, spellPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, spellPatch_adopted, spell_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-spells.json" %(spellPatch_adopted, language_cdragon[locale]), session, log)
                                spell: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                spellPatch_deserted: str = spellPatch_adopted
                                spellPatch_adopted = FindPostPatch(Patch(spellPatch_adopted), versionList)
                                spell_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to spells of Patch %s ... Times tried: %d." %(spellPatch_deserted, spell_recapture, spellPatch_adopted, spellPatch_deserted, spellPatch_adopted, spell_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if spell_recapture < 3:
                                    spell_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师技能信息……\nYour network environment is abnormal! Changing to spells of Patch %s ... Times tried: %d." %(spell_recapture, spellPatch_adopted, spellPatch_adopted, spell_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师技能信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the spell (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的召唤师技能信息。\nSpell information changed to Patch %s." %(spellPatch_adopted, spellPatch_adopted), verbose = verbose)
                                spells = {int(spell_iter["id"]): spell_iter for spell_iter in spell}
                                current_versions["spell"] = spellPatch_adopted
                                unmapped_keys["spell"].clear()
                                break
                        break
                ##英雄联盟装备（LoL items）
                LoLItemIds_match_list: list[int] = sorted(set(itemId for s in [set(map(lambda x: LoLGame_info["participants"][x]["stats"].get(key, 0), participantIndices)) for key in ["item0", "item1", "item2", "item3", "item4", "item5", "item6", "roleBoundItem"]] for itemId in s))
                for j in LoLItemIds_match_list:
                    if not j in LoLItems and current_versions["LoLItem"] != bigVersion and j != 0: #空装备序号是0（The itemId of an empty item is 0）
                        LoLItemPatch_adopted: str = bigVersion
                        LoLItem_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）英雄联盟装备信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nLoL item information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL items of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, LoLItem_recapture, LoLItemPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/items.json" %(LoLItemPatch_adopted, language_cdragon[locale]), session, log)
                                LoLItem: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                LoLItemPatch_deserted: str = LoLItemPatch_adopted
                                LoLItemPatch_adopted = FindPostPatch(Patch(LoLItemPatch_adopted), versionList)
                                LoLItem_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItemPatch_deserted, LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_deserted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if LoLItem_recapture < 3:
                                    LoLItem_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nYour network environment is abnormal! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄联盟装备信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL item (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的英雄联盟装备信息。\nLoL item information changed to Patch %s." %(LoLItemPatch_adopted, LoLItemPatch_adopted), verbose = verbose)
                                LoLItems = {int(LoLItem_iter["id"]): LoLItem_iter for LoLItem_iter in LoLItem}
                                current_versions["LoLItem"] = LoLItemPatch_adopted
                                unmapped_keys["LoLItem"].clear()
                                break
                        break
                ##符文（Perks）
                perkIds_match_list: list[int] = sorted(set(perkId for s in [set(map(lambda x: LoLGame_info["participants"][x]["stats"]["perk" + str(j)], participantIndices)) for j in range(6)] for perkId in s))
                for j in perkIds_match_list:
                    if not j in perks and current_versions["perk"] != bigVersion and j != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                        perkPatch_adopted: str = bigVersion
                        perk_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）基石符文信息（%d）获取失败！正在第%d次尝试改用%s版本的基石符文信息……\nPerk information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perks of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, perk_recapture, perkPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, perkPatch_adopted, perk_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perks.json" %(perkPatch_adopted, language_cdragon[locale]), session, log)
                                perk: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                perkPatch_deserted: str = perkPatch_adopted
                                perkPatch_adopted = FindPostPatch(Patch(perkPatch_adopted), versionList)
                                perk_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkPatch_deserted, perk_recapture, perkPatch_adopted, perkPatch_deserted, perkPatch_adopted, perk_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if perk_recapture < 3:
                                    perk_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的基石符文信息……\nYour network environment is abnormal! Changing to perks of Patch %s ... Times tried: %d." %(perk_recapture, perkPatch_adopted, perkPatch_adopted, perk_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的基石符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perk (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的基石符文信息。\nPerk information changed to Patch %s." %(perkPatch_adopted, perkPatch_adopted), verbose = verbose)
                                perks = {int(perk_iter["id"]): perk_iter for perk_iter in perk}
                                current_versions["perk"] = perkPatch_adopted
                                unmapped_keys["perk"].clear()
                                break
                        break
                ##符文系（Perkstyles）
                perkstyleIds_match_list: list[int] = sorted(list(set(map(lambda x: LoLGame_info["participants"][x]["stats"]["perkPrimaryStyle"], participantIndices)) | set(map(lambda x: LoLGame_info["participants"][x]["stats"]["perkSubStyle"], participantIndices))))
                for j in perkstyleIds_match_list:
                    if not j in perkstyles and current_versions["perkstyle"] != bigVersion and j != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                        perkstylePatch_adopted: str = bigVersion
                        perkstyle_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）符文系信息（%d）获取失败！正在第%d次尝试改用%s版本的符文系信息……\nPerkstyle information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perkstyles of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, perkstyle_recapture, perkstylePatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perkstyles.json" %(perkstylePatch_adopted, language_cdragon[locale]), session, log)
                                perkstyle: dict[str, Any] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                perkstylePatch_deserted: str = perkstylePatch_adopted
                                perkstylePatch_adopted = FindPostPatch(Patch(perkstylePatch_adopted), versionList)
                                perkstyle_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkstylePatch_deserted, perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_deserted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if perkstyle_recapture < 3:
                                    perkstyle_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的符文系信息……\nYour network environment is abnormal! Changing to perkstyles of Patch %s ... Times tried: %d." %(perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的符文系信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perkstyle (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的符文系信息。\nPerkstyle information changed to Patch %s." %(perkstylePatch_adopted, perkstylePatch_adopted), verbose = verbose)
                                perkstyles = {int(perkstyle_iter["id"]): perkstyle_iter for perkstyle_iter in perkstyle["styles"]}
                                current_versions["perkstyle"] = perkstylePatch_adopted
                                unmapped_keys["perkstyle"].clear()
                                break
                        break
                ##斗魂竞技场强化符文（Cherry augments）
                CherryAugmentIds_match_list: list[int] = sorted(set(augmentId for s in [set(map(lambda x: LoLGame_info["participants"][x]["stats"]["playerAugment" + str(j)], participantIndices)) for j in range(1, 7)] for augmentId in s))
                for j in CherryAugmentIds_match_list:
                    if not j in CherryAugments and current_versions["CherryAugment"] != bigVersion and j != 0:
                        CherryAugmentPatch_adopted: str = bigVersion
                        CherryAugment_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%d）获取失败！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nAugment information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to Cherry augments of Patch %s ... Times tried: %d." %(i + 1, len(LoLMatchIDs), matchId, j, CherryAugment_recapture, CherryAugmentPatch_adopted, j, i + 1, len(LoLMatchIDs), matchId, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/cherry-augments.json" %(CherryAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                CherryAugment: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                CherryAugmentPatch_deserted: str = CherryAugmentPatch_adopted
                                CherryAugmentPatch_adopted = FindPostPatch(Patch(CherryAugmentPatch_adopted), versionList)
                                CherryAugment_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugmentPatch_deserted, CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_deserted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if CherryAugment_recapture < 3:
                                    CherryAugment_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nYour network environment is abnormal! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the Cherry augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(LoLMatchIDs), matchId, j, j, i + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的斗魂竞技场强化符文信息。\nCherry augment information changed to Patch %s." %(CherryAugmentPatch_adopted, CherryAugmentPatch_adopted), verbose = verbose)
                                CherryAugments = {int(CherryAugment_iter["id"]): CherryAugment_iter for CherryAugment_iter in CherryAugment}
                                current_versions["CherryAugment"] = CherryAugmentPatch_adopted
                                unmapped_keys["CherryAugment"].clear()
                                break
                        break
            #下面开始整理数据（Sorts out the data）
            for participantIndex in participantIndices:
                generate_LoLHistory_records(LoLHistory_data, LoLGame_info, participantIndex, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments, gameIndex = i + 1, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, log = log, verbose = verbose)
            logPrint('对局记录重查进度（Match history recheck process）：%d/%d\t对局序号（MatchID）： %s' %(i + 1, len(LoLMatchIDs), matchId), print_time = True, verbose = verbose)
    LoLHistory_statistics_output_order: list[int] = [0, 25, 19, 26, 5, 3, 13, 4, 11, 6, 14, 10, 15, 9, 35, 36, 45, 38, 39, 157, 158, 159, 160, 161, 162, 163, 212, 214, 216, 61, 221, 134]
    LoLHistory_data_organized: dict[str, list[Any]] = {}
    for i in LoLHistory_statistics_output_order:
        key: str = LoLHistory_header_keys[i]
        LoLHistory_data_organized[key] = LoLHistory_data[key]
    LoLHistory_df: pandas.DataFrame = pandas.DataFrame(data = LoLHistory_data_organized)
    for column in LoLHistory_df:
        if LoLHistory_df[column].dtype == "bool":
            LoLHistory_df[column] = LoLHistory_df[column].astype(str)
            LoLHistory_df[column] = list(map(lambda x: "√" if x == "True" else "", LoLHistory_df[column].to_list()))
    LoLHistory_df = pandas.concat([pandas.DataFrame([LoLHistory_header])[LoLHistory_df.columns], LoLHistory_df], ignore_index = True)
    return (LoLHistory_df, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments)

async def reconstruct_TFTHistory(connection: Connection, TFTMatchIDs: list[int], puuid: str | list[str], queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], useAllVersions: bool = False, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] = {}, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if log == None:
        log = LogManager()
    #注意到infos没有做类似处理。因此，一旦出现不同函数调用间共享了infos参数……这是好事啊！（Note that `infos` parameter isn't processed in this manner. Hence, once it's shared between different function calls ... well, that's exactly what I want）
    logPrint = log.logPrint
    puuidList: list[str] = [puuid] if isinstance(puuid, str) else puuid
    current_versions: dict[str, str] = {"queue": "", "TFTAugment": "", "TFTChampion": "", "TFTItem": "", "TFTCompanion": "", "TFTTrait": ""}
    unmapped_keys: dict[str, set[str]] = {"queue": set(), "TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*")
    TFTHistory_header_keys: list[str] = list(TFTHistory_header.keys())
    TFTHistory_data: dict[str, list[Any]] = {}
    for i in range(len(TFTHistory_header)): #云顶之弈对局信息各项目初始化（Initialize every feature / column of TFT match information）
        key = TFTHistory_header_keys[i]
        TFTHistory_data[key] = []
    current_puuid_list: list[str] = []
    current_summonerName_list: list[str] = []
    for current_puuid in puuidList:
        info: dict[str, Any] = await get_info(connection, current_puuid)
        if info["info_got"]:
            current_puuid_list.append(info["body"]["puuid"])
            current_summonerName_list.append(get_info_name(info["body"]))
        else:
            logPrint(info["body"], verbose = verbose)
            logPrint(info["message"], verbose = verbose)
    if len(current_puuid_list) == 0:
        logPrint("召唤师信息获取失败。函数将返回空白表。\nSummoner information capture failed! An empty dataframe will be returned instead.", verbose = verbose)
    else:
        for i in range(len(TFTMatchIDs)):
            matchId: int = TFTMatchIDs[i]
            status, TFTGame_info = await get_TFTGame_info(matchId, log = log)
            if status != 200:
                continue
            TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
            participantIndices: list[int] = []
            if bool(TFTHistoryJson):
                for participantIndex in range(len(TFTHistoryJson["participants"])):
                    if TFTHistoryJson["participants"][participantIndex]["puuid"] in current_puuid_list:
                        participantIndices.append(participantIndex)
                if len(participantIndices) == 0:
                    logPrint("[%d/%d]对局%d不包括主召唤师。已跳过该对局。\nMatch %d doesn't contain the main summoner. Skipped this match." %(i + 1, len(TFTMatchIDs), matchId, matchId), verbose = verbose)
                    continue
            else:
                logPrint("[%d/%d]对局%d数据不存在。已跳过该对局。\nMatch %d doesn't exist. Skipped this match." %(i + 1, len(TFTMatchIDs), matchId, matchId), verbose = verbose)
                continue
            TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
            TFTGamePatch: str = ".".join(TFTGameVersion.split(".")[:2]) #由于需要通过这部分代码事先获取所有对局的版本，因此无论如何，这部分代码都要放在与从CommunityDragon重新获取云顶之弈数据相关的代码前面（Since game patches are captured here, by all means should this part of code be in front of the code relevant to regetting TFT data from CommunityDragon）
            TFTPlayer: dict[str, Any] = TFTHistoryJson["participants"][participantIndex]
            #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
            if useAllVersions:
                ##游戏模式（Game mode）
                queueIds_match_list: list[int] = [TFTGame_info["queue_id"]]
                for j in queueIds_match_list:
                    if not j in queues and current_versions["queue"] != TFTGamePatch:
                        queuePatch_adopted: str = TFTGamePatch
                        queue_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, queue_recapture, queuePatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], queuePatch_adopted, queue_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                                queue: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                queuePatch_deserted: str = queuePatch_adopted
                                queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                                queue_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if queue_recapture < 3:
                                    queue_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                                queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                                current_versions["queue"] = queuePatch_adopted
                                unmapped_keys["queue"].clear()
                                break
                        break
                ##云顶之弈强化符文（TFT augments）
                TFTAugmentIds_match_list: list[str] = sorted(set(augmentId for lst in list(map(lambda x: TFTHistoryJson["participants"][x]["augments"] if "augments" in TFTHistoryJson["participants"][x] else [], participantIndices)) for augmentId in lst)) #`if "augments" in x`的作用是防止早期云顶之弈对局无强化符文导致程序报错（`if "augments" in x` is used here because some early TFT matches don't contain augments and result in KeyErrors consequently）
                for j in TFTAugmentIds_match_list:
                    if not j in TFTAugments and current_versions["TFTAugment"] != TFTGamePatch:
                        TFTAugmentPatch_adopted: str = TFTGamePatch
                        TFTAugment_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nAugment information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT augments of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, TFTAugment_recapture, TFTAugmentPatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                TFT: dict[str, Any] = response.json()
                            except requests.exceptions.JSONDecodeError: #存在版本合并更新的情况（Situation like merged update exists）
                                TFTAugmentPatch_deserted: str = TFTAugmentPatch_adopted
                                TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                TFTAugment_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                            except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                if TFTAugment_recapture < 3:
                                    TFTAugment_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                unmapped_keys["TFTAugment"].clear()
                                break
                        break
                ##云顶之弈小小英雄（TFT companions）
                TFTCompanionIds_match_list: list[str] = sorted(set(map(lambda x: TFTHistoryJson["participants"][x]["companion"]["content_ID"], participantIndices)))
                for j in TFTCompanionIds_match_list:
                    if not j in TFTCompanions and current_versions["TFTCompanion"] != TFTGamePatch:
                        TFTCompanionPatch_adopted: str = TFTGamePatch
                        TFTCompanion_recapture = 1
                        logPrint("第%d/%d场对局（对局序号：%d）小小英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的小小英雄信息……\nTFT companion information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT companions of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, TFTCompanion_recapture, TFTCompanionPatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/companions.json" %(TFTCompanionPatch_adopted, language_cdragon[locale]), session, log)
                                TFTCompanion: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTCompanionPatch_deserted: str = TFTCompanionPatch_adopted
                                TFTCompanionPatch_adopted = FindPostPatch(Patch(TFTCompanionPatch_adopted), versionList)
                                TFTCompanion_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTCompanionPatch_deserted, TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_deserted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTCompanion_recapture < 3:
                                    TFTCompanion_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的小小英雄信息……\nYour network environment is abnormal! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的小小英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the companion (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的小小英雄信息。\nTFT companion information changed to Patch %s." %(TFTCompanionPatch_adopted, TFTCompanionPatch_adopted), verbose = verbose)
                                TFTCompanions = {companion_iter["contentId"]: companion_iter for companion_iter in TFTCompanion}
                                current_versions["TFTCompanion"] = TFTCompanionPatch_adopted
                                unmapped_keys["TFTCompanion"].clear()
                                break
                        break
                ##云顶之弈羁绊（TFT Traits）
                TFTTraitIds_match_list: list[str] = sorted(set(traitId for s in [set(map(lambda x: x["name"], TFTHistoryJson["participants"][j]["traits"])) for j in participantIndices] for traitId in s))
                for j in TFTTraitIds_match_list:
                    if not j in TFTTraits and current_versions["TFTTrait"] != TFTGamePatch:
                        TFTTraitPatch_adopted: str = TFTGamePatch
                        TFTTrait_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）羁绊信息（%s）获取失败！正在第%d次尝试改用%s版本的羁绊信息……\nTFT trait information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT traits of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, TFTTrait_recapture, TFTTraitPatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tfttraits.json" %(TFTTraitPatch_adopted, language_cdragon[locale]), session, log)
                                TFTTrait: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTTraitPatch_deserted: str = TFTTraitPatch_adopted
                                TFTTraitPatch_adopted = FindPostPatch(Patch(TFTTraitPatch_adopted), versionList)
                                TFTTrait_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTraitPatch_deserted, TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_deserted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTTrait_recapture < 3:
                                    TFTTrait_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的羁绊信息……\nYour network environment is abnormal! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的羁绊信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the trait (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的羁绊信息。\nTFT trait information changed to Patch %s." %(TFTTraitPatch_adopted, TFTTraitPatch_adopted), verbose = verbose)
                                TFTTraits = {}
                                for trait_iter in TFTTrait:
                                    trait_id: str = trait_iter["trait_id"]
                                    conditional_trait_sets: dict[str, Any] = {}
                                    if "conditional_trait_sets" in trait_iter: #在英雄联盟第13赛季之前，CommunityDragon数据库中记录的羁绊信息无conditional_trait_sets项（Before Season 13, `conditional_trait_sets` item is absent from tfttraits from CommunityDragon database）
                                        for conditional_trait_set in trait_iter["conditional_trait_sets"]:
                                            style_idx = conditional_trait_set["style_idx"]
                                            conditional_trait_sets[style_idx] = conditional_trait_set
                                    trait_iter["conditional_trait_sets"] = conditional_trait_sets
                                    TFTTraits[trait_id] = trait_iter
                                current_versions["TFTTrait"] = TFTTraitPatch_adopted
                                unmapped_keys["TFTTrait"].clear()
                                break
                        break
                ##云顶之弈英雄（TFT champions）
                TFTChampionIds_match_list: list[str] = sorted(set(championId for s in [set(map(lambda x: x["character_id"], TFTHistoryJson["participants"][j]["units"])) for j in participantIndices] for championId in s))
                for j in TFTChampionIds_match_list:
                    if not j in TFTChampions and not j.lower() in set(map(lambda x: x.lower(), TFTChampions.keys())) and current_versions["TFTChampion"] != TFTGamePatch:
                        TFTChampionPatch_adopted: str = TFTGamePatch
                        TFTChampion_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的棋子信息……\nTFT champion (%s) information of Match %d / %d (matchId: %d) capture failed! Changing to TFT champions of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, TFTChampion_recapture, TFTChampionPatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftchampions.json" %(TFTChampionPatch_adopted, language_cdragon[locale]), session, log)
                                TFTChampion: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTChampionPatch_deserted: str = TFTChampionPatch_adopted
                                TFTChampionPatch_adopted = FindPostPatch(Patch(TFTChampionPatch_adopted), versionList)
                                TFTChampion_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampionPatch_deserted, TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_deserted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTChampion_recapture < 3:
                                    TFTChampion_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的棋子信息……\nYour network environment is abnormal! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）将采用原始数据！\nNetwork error! The original data will be used for Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的棋子信息。\nTFT champion information changed to Patch %s." %(TFTChampionPatch_adopted, TFTChampionPatch_adopted), verbose = verbose)
                                TFTChampions = {}
                                if Patch(TFTChampionPatch_adopted) < Patch("13.17"): #从13.17版本开始，CommunityDragon数据库中关于云顶之弈棋子的数据格式发生微调（Since Patch 13.17, the format of TFT Champion data in CommunityDragon database has been modified）
                                    for TFTChampion_iter in TFTChampion:
                                        champion_name: str = TFTChampion_iter["character_id"]
                                        TFTChampions[champion_name] = TFTChampion_iter
                                else:
                                    for TFTChampion_iter in TFTChampion:
                                        champion_name = TFTChampion_iter["name"]
                                        TFTChampions[champion_name] = TFTChampion_iter["character_record"] #请注意该语句与4行之前的语句的差异，并看看一开始准备数据文件时使用的是哪一种——其实你应该猜的出来（Have you noticed the difference between this statement and the statement that is 4 lines above from this statement? Also, check which statement I chose for the beginning, when I prepared the data resources. Actually, you should be able to speculate it without referring to the code）
                                current_versions["TFTChampion"] = TFTChampionPatch_adopted
                                unmapped_keys["TFTChampion"].clear()
                                break
                        break
                ##云顶之弈装备（TFT items）
                s: set[str] = set()
                for j in participantIndices:
                    for unit in TFTHistoryJson["participants"][j]["units"]:
                        if "itemNames" in unit:
                            s |= set(unit["itemNames"])
                        elif "items" in unit:
                            s |= set(unit["items"])
                TFTItemIds_match_list: list[str] = sorted(s)
                for j in TFTItemIds_match_list:
                    if not j in TFTItems and not j in TFTAugments:
                        if current_versions["TFTItem"] != TFTGamePatch:
                            TFTItemPatch_adopted: str = TFTGamePatch
                            TFTItem_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）装备信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nTFT item information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT items of Patch %s ... Times tried: %d." %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, TFTItem_recapture, TFTItemPatch_adopted, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftitems.json" %(TFTItemPatch_adopted, language_cdragon[locale]), session, log)
                                    TFTItem: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    TFTItemPatch_deserted: str = TFTItemPatch_adopted
                                    TFTItemPatch_adopted = FindPostPatch(Patch(TFTItemPatch_adopted), versionList)
                                    TFTItem_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItemPatch_deserted, TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_deserted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if TFTItem_recapture < 3:
                                        TFTItem_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nYour network environment is abnormal! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的装备信息（%d）将采用原始数据！\nNetwork error! The original data will be used for the item (%d) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的云顶之弈装备信息。\nTFT item information changed to Patch %s." %(TFTItemPatch_adopted, TFTItemPatch_adopted), verbose = verbose)
                                    TFTItems = {TFTItem_iter["nameId"]: TFTItem_iter for TFTItem_iter in TFTItem}
                                    current_versions["TFTItem"] = TFTItemPatch_adopted
                                    unmapped_keys["TFTItem"].clear()
                                    break
                        #由于云顶之弈基础数据中也包含装备信息，这里将重新获取对局版本的云顶之弈基础数据（Because TFT basic data contain item data, here the program recaptures TFT basic data of the match version）
                        if current_versions["TFTAugment"] != TFTGamePatch:
                            TFTAugmentPatch_adopted = TFTGamePatch
                            TFTAugment_recapture = 1
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                    TFT = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    TFTAugmentPatch_deserted = TFTAugmentPatch_adopted
                                    TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                    TFTAugment_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                    if TFTAugment_recapture < 3:
                                        TFTAugment_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                    TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                    current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                    unmapped_keys["TFTAugment"].clear()
                                    break
                        break
            for participantIndex in participantIndices:
                await generate_TFTHistory_records(connection, TFTHistory_data, TFTGame_info, participantIndex, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits, gameIndex = i + 1, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, useInfoDict = useInfoDict, infos = infos, log = log, verbose = verbose)
            logPrint('对局记录重查进度（Match history recheck process）：%d/%d\t对局序号（MatchID）： %s' %(i + 1, len(TFTMatchIDs), matchId), print_time = True, verbose = verbose)
    TFTHistory_statistics_output_order: list[int] = [0, 46, 47, 5, 14, 15, 16, 6, 10, 18, 8, 17, 7, 13, 12, 11, 306, 304, 40, 33, 34, 35, 38, 52, 53, 49, 36, 50, 42, 54, 41, 39, 44, 45, 23, 24, 25, 149, 147, 148, 202, 205, 208, 154, 152, 153, 211, 214, 217, 159, 157, 158, 220, 223, 226, 164, 162, 163, 229, 232, 235, 169, 167, 168, 238, 241, 244, 174, 172, 173, 247, 250, 253, 179, 177, 178, 256, 259, 262, 184, 182, 183, 265, 268, 271, 189, 187, 188, 274, 277, 280, 194, 192, 193, 283, 286, 289, 199, 197, 198, 292, 295, 298, 60, 56, 57, 58, 59, 67, 63, 64, 65, 66, 74, 70, 71, 72, 73, 81, 77, 78, 79, 80, 88, 84, 85, 86, 87, 95, 91, 92, 93, 94, 102, 98, 99, 100, 101, 109, 105, 106, 107, 108, 116, 112, 113, 114, 115, 123, 119, 120, 121, 122, 130, 126, 127, 128, 129, 137, 133, 134, 135, 136, 144, 140, 141, 142, 143]
    TFTHistory_data_organized: dict[str, list[Any]] = {}
    for i in TFTHistory_statistics_output_order:
        key = TFTHistory_header_keys[i]
        TFTHistory_data_organized[key] = TFTHistory_data[key]
    TFTHistory_df: pandas.DataFrame = pandas.DataFrame(data = TFTHistory_data_organized)
    for column in TFTHistory_df:
        if TFTHistory_df[column].dtype == "bool":
            TFTHistory_df[column] = TFTHistory_df[column].astype(str)
            TFTHistory_df[column] = list(map(lambda x: "√" if x == "True" else "", TFTHistory_df[column].to_list()))
    TFTHistory_df = pandas.concat([pandas.DataFrame([TFTHistory_header])[TFTHistory_df.columns], TFTHistory_df], ignore_index = True)
    return (TFTHistory_df, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits)

def generate_LoLHistory_records(LoLHistory_data: dict[str, Any], LoLGame_info: dict[str, Any], participantIndex: int, queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], gameIndex: int = 1, unmapped_keys: dict[str, set[Any]] | None = None, useAllVersions: bool = False, log: LogManager | None = None, verbose: bool = True) -> dict[str, list[int | str | bool]]: #由于字典作为参数的引用传递特性，在使用该函数时可以不用将返回结果保存到一个变量中（Due to the pass-by-reference feature of a dictionary parameter, the result returned by this function doesn't have to be stored as a variable）
    if unmapped_keys == None:
        unmapped_keys = {"queue": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    matchId: int = LoLGame_info["gameId"]
    version: str = LoLGame_info["gameVersion"]
    stats: dict[str, int | bool] = LoLGame_info["participants"][participantIndex]["stats"]
    timeline: dict[str, Any] = LoLGame_info["participants"][participantIndex]["timeline"]
    LoLHistory_header_keys: list[str] = list(LoLHistory_header.keys())
    for i in range(len(LoLHistory_header_keys)):
        key = LoLHistory_header_keys[i]
        if i == 0:
            LoLHistory_data[key].append(gameIndex)
        elif i <= 15:
            if i == 1: #对局终止情况（`endOfGameResult`）
                LoLHistory_data[key].append(endOfGameResults[LoLGame_info["endOfGameResult"]])
            elif i == 3: #对局创建日期（`gameCreationDate`）
                LoLHistory_data[key].append(LoLGame_info["gameCreationDate"][:10] + " " + LoLGame_info["gameCreationDate"][11:23])
            elif i == 8: #游戏类型（`gameType`）
                LoLHistory_data[key].append(gameTypes_history[LoLGame_info["gameType"]])
            elif i == 13: #持续时长（`gameDuration_norm`）
                LoLHistory_data[key].append("%d:%02d" %(LoLGame_info["gameDuration"] // 60, LoLGame_info["gameDuration"] % 60))
            elif i == 14: #游戏模式名称（`gameModeName`）
                LoLHistory_data[key].append("自定义" if LoLGame_info["queueId"] == 0 else queues[LoLGame_info["queueId"]]["name"] if LoLGame_info["queueId"] in queues else "")
            elif i == 15: #地图名称（`mapName`）
                mapName: str = gamemaps[LoLGame_info["mapId"]]["zh_CN"]
                if LoLGame_info["mapId"] == 12:
                    if "mapskin_map12_bloom" in LoLGame_info["gameModeMutators"]:
                        mapName = "莲华栈桥"
                    elif "mapskin_ha_bilgewater" in LoLGame_info["gameModeMutators"]:
                        mapName = "屠夫之桥"
                    elif "mapskin_ha_crepe" in LoLGame_info["gameModeMutators"]:
                        mapName = "进步之桥"
                    else:
                        mapName = "嚎哭深渊"
                LoLHistory_data[key].append(mapName)
            else:
                LoLHistory_data[key].append(LoLGame_info[key])
        elif i <= 28:
            if i >= 27: #召唤师图标相关键（Summoner icon-related keys）
                profileIconId: int = LoLGame_info["participantIdentities"][participantIndex]["player"]["profileIcon"]
                if profileIconId == -1:
                    LoLHistory_data[key].append(profileIconId if i == 27 else "")
                elif profileIconId in summonerIcons:
                    LoLHistory_data[key].append(summonerIcons[profileIconId].get(key.split("_")[-1], profileIconId if i == 27 else ""))
                else:
                    if not profileIconId in unmapped_keys["summonerIcon"]:
                        if useAllVersions:
                            unmapped_keys["summonerIcon"].add(profileIconId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）召唤师图标信息（%d）获取失败！将采用原始数据！\n[%d. %s] Summoner icon information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, profileIconId, i, key, profileIconId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(profileIconId if i == 27 else "")
            else:
                LoLHistory_data[key].append(LoLGame_info["participantIdentities"][participantIndex]["player"][key])
        elif i <= 42:
            if i == 30: #最高段位（`highestAchievedSeasonTier`）
                LoLHistory_data[key].append(tiers[LoLGame_info["participants"][participantIndex]["highestAchievedSeasonTier"]])
            elif i >= 35 and i <= 37: #英雄相关键（Champion-related keys）
                championId: int = LoLGame_info["participants"][participantIndex][key.split("_")[0] + "Id"]
                if championId in LoLChampions:
                    LoLHistory_data[key].append(LoLChampions[championId][key.split("_")[1]])
                else: #在国服体验服的对局序号为696083511的对局中，出现了英雄序号为37225015（In a match with matchId 696083511 on Chinese PBE, there's a champion with championId 37225015）
                    if not championId in unmapped_keys["LoLChampion"]:
                        if useAllVersions:
                            unmapped_keys["LoLChampion"].add(championId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）英雄信息（%d）获取失败！将采用原始数据！\n[%d. %s] Champion information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, championId, i, key, championId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(championId if i == 35 else "")
            elif i >= 38 and i <= 41: #召唤师技能相关键（Summoner spell-related keys）
                spellId: int = LoLGame_info["participants"][participantIndex][key.split("_")[0] + "Id"]
                if spellId == 0:
                    LoLHistory_data[key].append(spellId if i <= 39 else "")
                elif spellId in spells:
                    LoLHistory_data[key].append(spells[spellId][key.split("_")[1]])
                else:
                    if not spellId in unmapped_keys["spell"]:
                        if useAllVersions:
                            unmapped_keys["spell"].add(spellId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）召唤师技能信息（%d）获取失败！将采用原始数据！\n[%d. %s] Spell information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, spellId, i, key, spellId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(spellId if i <= 39 else "")
            elif i == 42: #阵营（`team_color`）
                LoLHistory_data[key].append(team_colors_int[LoLGame_info["participants"][participantIndex]["teamId"]])
            else:
                LoLHistory_data[key].append(LoLGame_info["participants"][participantIndex][key])
        elif i <= 221:
            if i == 132: #角色绑定装备：临时应付正式服15.24版本、测试服16.1版本的情形（`roleBoundItem`: a temporary solution to handle the period when Live is v25.24 and PBE is 16.1）
                LoLHistory_data[key].append(stats.get("roleBoundItem", ""))
            elif i >= 157 and i <= 170: #英雄联盟装备相关键（LoLItems-related keys）
                itemId: int = stats[key.split("_")[0]]
                if itemId == 0:
                    LoLHistory_data[key].append("")
                elif itemId in LoLItems:
                    LoLHistory_data[key].append(LoLItems[itemId][key.split("_")[-1]])
                else:
                    if not itemId in unmapped_keys["LoLItem"]:
                        if useAllVersions:
                            unmapped_keys["LoLItem"].add(itemId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%d）获取失败！将采用原始数据！\n[%d. %s] LoL item information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, itemId, i, key, itemId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(itemId if i <= 163 else "")
            elif i >= 171 and i <= 188: #符文相关键（Perks-related keys）
                if i <= 176:
                    perkId: int = stats[key[:5]]
                    if perkId == 0:
                        LoLHistory_data[key].append("")
                    elif perkId in perks:
                        perk_EndOfGameStatDescs = "".join(list(map(lambda x: x + "。", perks[perkId]["endOfGameStatDescs"])))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar1@", str(stats[key[:5] + "Var1"]))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar2@", str(stats[key[:5] + "Var2"]))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar3@", str(stats[key[:5] + "Var3"]))
                        LoLHistory_data[key].append(perk_EndOfGameStatDescs)
                    else:
                        if not perkId in unmapped_keys["perk"]:
                            if useAllVersions:
                                unmapped_keys["perk"].add(perkId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Runes information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkId, i, key, perkId, matchId, version), verbose = verbose)
                        LoLHistory_data[key].append("")
                else:
                    perkId = stats[key.split("_")[0]]
                    if perkId == 0:
                        LoLHistory_data[key].append("")
                    elif perkId in perks:
                        LoLHistory_data[key].append(perks[perkId][key.split("_")[-1]])
                    else:
                        if not perkId in unmapped_keys["perk"]:
                            if useAllVersions:
                                unmapped_keys["perk"].add(perkId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Runes information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkId, i, key, perkId, matchId, version), verbose = verbose)
                        LoLHistory_data[key].append(perkId if i <= 182 else "")
            elif i >= 189 and i <= 192: #符文系相关键（Perkstyles-related keys）
                perkstyleId: int = stats[key.split("_")[0]]
                if perkstyleId == 0:
                    LoLHistory_data[key].append("")
                elif perkstyleId in perkstyles:
                    LoLHistory_data[key].append(perkstyles[perkstyleId][key.split("_")[-1]])
                else:
                    if not perkstyleId in unmapped_keys["perkstyle"]:
                        if useAllVersions:
                            unmapped_keys["perkstyle"].add(perkstyleId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）符文系信息（%d）获取失败！将采用原始数据！\n[%d. %s] Perkstyle information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkstyleId, i, key, perkstyleId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(perkstyleId if (i - 189) % 2 == 0 else "")
            elif i >= 193 and i <= 210: #强化符文相关键（Augment-related keys）
                CherryAugmentId: int = stats[key.split("_")[0]]
                if CherryAugmentId == 0:
                    LoLHistory_data[key].append("")
                elif CherryAugmentId in CherryAugments:
                    if i <= 198: #强化符文名称（`nameTRA`）
                        LoLHistory_data[key].append(CherryAugments[CherryAugmentId][key.split("_")[-1]])
                    elif i <= 204: #强化符文图标路径（`augmentIconPath`）
                        LoLHistory_data[key].append(CherryAugments[CherryAugmentId]["augmentSmallIconPath"].replace("_small.png", "_large.png"))
                    else: #强化符文等级（`rarity`）
                        LoLHistory_data[key].append(augment_rarity[CherryAugments[CherryAugmentId][key.split("_")[-1]]])
                else:
                    if not CherryAugmentId in unmapped_keys["CherryAugment"]:
                        if useAllVersions:
                            unmapped_keys["CherryAugment"].add(CherryAugmentId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）强化符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Cherry augment information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, CherryAugmentId, i, key, CherryAugmentId, matchId, version), verbose = verbose)
                    LoLHistory_data[key].append(CherryAugmentId if i <= 198 else "")
            elif i == 211: #子阵营（`playerSubteamColor`）
                LoLHistory_data[key].append(subteam_colors[stats["playerSubteamId"]])
            elif i == 212 or i == 213: #角色绑定装备相关键（Role bound item-related keys）
                if "roleBoundItem" in stats:
                    roleBoundItemId: int = stats["roleBoundItem"]
                    if roleBoundItemId == 0:
                        LoLHistory_data[key].append("")
                    elif roleBoundItemId in LoLItems:
                        LoLHistory_data[key].append(LoLItems[roleBoundItemId][key.split("_")[-1]])
                    else:
                        if not roleBoundItemId in unmapped_keys["LoLItem"]:
                            if useAllVersions:
                                unmapped_keys["LoLItem"].add(roleBoundItemId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%d）获取失败！将采用原始数据！\n[%d. %s] LoL item information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, roleBoundItemId, i, key, roleBoundItemId, matchId, version), verbose = verbose)
                        LoLHistory_data[key].append(roleBoundItemId if i == 212 else "")
                else:
                    LoLHistory_data[key].append("")
            elif i == 214: #击杀/死亡/助攻（`K/D/A`）
                LoLHistory_data[key].append("/".join([str(stats["kills"]), str(stats["deaths"]), str(stats["assists"])]))
            elif i == 215: #战损比（`KDA`）
                LoLHistory_data[key].append((stats["kills"] + stats["assists"]) / max(1, stats["deaths"]))
            elif i == 216: #补刀（`CS`）
                LoLHistory_data[key].append(stats["neutralMinionsKilled"] + stats["totalMinionsKilled"])
            elif i == 217: #分均经济（`GPM`）
                LoLHistory_data[key].append(0 if LoLGame_info["gameDuration"] == 0 else stats["goldEarned"] * 60 / LoLGame_info["gameDuration"])
            elif i == 218: #金币利用率（`GUE` - Gold Utilization Efficiency）
                LoLHistory_data[key].append(0 if stats["goldEarned"] == 0 else stats["goldSpent"] / stats["goldEarned"])
            elif i == 219: #分均补刀（`CSPM`）
                LoLHistory_data[key].append(0 if LoLGame_info["gameDuration"] == 0 else (stats["neutralMinionsKilled"] + stats["totalMinionsKilled"]) * 60 / LoLGame_info["gameDuration"])
            elif i == 220: #伤害转化率（`D/G`）
                LoLHistory_data[key].append(0 if stats["goldEarned"] == 0 else stats["totalDamageDealtToChampions"] / stats["goldEarned"])
            elif i == 221: #胜负（`result`）
                LoLHistory_data[key].append("被终止" if LoLGame_info["endOfGameResult"] == "Abort_AntiCheatExit" else "胜利" if stats["win"] else "失败")
            else:
                LoLHistory_data[key].append(stats[key])
        else: #时间轴相关键（Timeline-related keys）
            LoLHistory_data[key].append(lanes[timeline[key]] if i == 222 else roles[timeline[key]])
    return LoLHistory_data

async def sort_LoLHistory(connection: Connection, LoLHistory: dict[str, Any], queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], useAllVersions: bool = False, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:  #当数据转换出现无法匹配的情况时，重新获取对局版本的数据资源。目前只应用于查战绩脚本和自定义脚本11（When dismatch happens during data conversion, get the data resources of the game version. Only applied to Customized Programs 05 and 11 only）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    current_versions: dict[str, str] = {"queue": "", "summonerIcon": "", "spell": "", "LoLChampion": "", "LoLItem": "", "summonerIcon": "", "perk": "", "perkstyle": "", "CherryAugment": ""}
    unmapped_keys: dict[str, set[int]] = {"queues": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    LoLHistory_header_keys: list[str] = list(LoLHistory_header.keys())
    LoLHistory_data: dict[str, list[Any]] = {}
    games: list[dict[str, Any]] = LoLHistory["games"]["games"]
    for i in range(len(LoLHistory_header_keys)):
        key = LoLHistory_header_keys[i]
        LoLHistory_data[key] = []
    for i in range(len(games)):
        game: dict[str, Any] = games[i]
        version: str = game["gameVersion"]
        bigVersion: str = ".".join(version.split(".")[:2])
        #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
        if useAllVersions:
            ##游戏模式（Game mode）
            queueIds_match_list: list[int] = [game["queueId"]]
            for j in queueIds_match_list:
                if not j in queues and current_versions["queue"] != bigVersion:
                    queuePatch_adopted: str = bigVersion
                    queue_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, queue_recapture, queuePatch_adopted, j, i + 1, len(games), game["gameId"], queuePatch_adopted, queue_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                            queue: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            queuePatch_deserted: str = queuePatch_adopted
                            queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                            queue_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if queue_recapture < 3:
                                queue_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                            queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                            current_versions["queue"] = queuePatch_adopted
                            unmapped_keys["queue"].clear()
                            break
                    break
            ##召唤师图标（Summoner icon）
            summonerIconIds_match_list: list[int] = sorted(set(map(lambda x: x["player"]["profileIcon"], game["participantIdentities"])))
            for j in summonerIconIds_match_list:
                if not j in summonerIcons and current_versions["summonerIcon"] != bigVersion:
                    summonerIconPatch_adopted: str = bigVersion
                    summonerIcon_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）召唤师图标信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师图标信息……\nSummoner icon information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to summoner icons of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, summonerIcon_recapture, summonerIconPatch_adopted, j, i + 1, len(games), game["gameId"], summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-icons.json" %(summonerIconPatch_adopted, language_cdragon[locale]), session, log)
                            summonerIcon: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            summonerIconPatch_deserted: str = summonerIconPatch_adopted
                            summonerIconPatch_adopted = FindPostPatch(Patch(summonerIconPatch_adopted), versionList)
                            summonerIcon_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(summonerIconPatch_deserted, summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_deserted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if summonerIcon_recapture < 3:
                                summonerIcon_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师图标信息……\nYour network environment is abnormal! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师图标信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the summoner icon (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的召唤师图标信息。\nSummoner icon information changed to Patch %s." %(summonerIconPatch_adopted, summonerIconPatch_adopted), verbose = verbose)
                            summonerIcons = {int(summonerIcon_iter["id"]): summonerIcon_iter for summonerIcon_iter in summonerIcon}
                            current_versions["summonerIcon"] = summonerIconPatch_adopted
                            unmapped_keys["summonerIcon"].clear()
                            break
                    break #切换版本只需一次即可。如果对局版本还不对，那就不用再找下去了（The version of data resources only needs changing once. If data resources of the version of this match don't match all the game data, then there's no need of retrying）
            ##英雄：包含选用英雄和禁用英雄（LoL champions, which contain picked and banned ones）
            LoLChampionIds_match_list: list[int] = sorted(set(map(lambda x: x["championId"], game["participants"])))
            for j in LoLChampionIds_match_list:
                if not j in LoLChampions and current_versions["LoLChampion"] != bigVersion:
                    LoLChampionPatch_adopted: str = bigVersion
                    LoLChampion_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄信息……\nLoL champion information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL champions of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, LoLChampion_recapture, LoLChampionPatch_adopted, j, i + 1, len(games), game["gameId"], LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/champion-summary.json" %(LoLChampionPatch_adopted, language_cdragon[locale]), session, log)
                            LoLChampion: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            LoLChampionPatch_deserted: str = LoLChampionPatch_adopted
                            LoLChampionPatch_adopted = FindPostPatch(Patch(LoLChampionPatch_adopted), versionList)
                            LoLChampion_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampionPatch_deserted, LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_deserted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if LoLChampion_recapture < 3:
                                LoLChampion_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄信息……\nYour network environment is abnormal! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL champion (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的英雄信息。\nLoL champion information changed to Patch %s." %(LoLChampionPatch_adopted, LoLChampionPatch_adopted), verbose = verbose)
                            LoLChampions = {int(LoLChampion_iter["id"]): LoLChampion_iter for LoLChampion_iter in LoLChampion}
                            current_versions["LoLChampion"] = LoLChampionPatch_adopted
                            unmapped_keys["LoLChampion"].clear() #切换版本时，未对应的键应当清空。下同（When the version is switched, the unmapped keys should be cleared. This applies to other data resources）
                            break
                    break
            ##召唤师技能（Summoner spells）
            spellIds_match_list: list[int] = sorted(set(map(lambda x: x["spell1Id"], game["participants"])) | set(map(lambda x: x["spell2Id"], game["participants"])))
            for j in spellIds_match_list:
                if not j in spells and current_versions["spell"] != bigVersion and j != 0: #需要注意电脑玩家的召唤师技能序号都是0（Note that Spell Ids of bot players are both 0s）
                    spellPatch_adopted: str = bigVersion
                    spell_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）召唤师技能信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师技能信息……\nSpell information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to spells of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, spell_recapture, spellPatch_adopted, j, i + 1, len(games), game["gameId"], spellPatch_adopted, spell_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-spells.json" %(spellPatch_adopted, language_cdragon[locale]), session, log)
                            spell: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            spellPatch_deserted: str = spellPatch_adopted
                            spellPatch_adopted = FindPostPatch(Patch(spellPatch_adopted), versionList)
                            spell_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to spells of Patch %s ... Times tried: %d." %(spellPatch_deserted, spell_recapture, spellPatch_adopted, spellPatch_deserted, spellPatch_adopted, spell_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if spell_recapture < 3:
                                spell_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师技能信息……\nYour network environment is abnormal! Changing to spells of Patch %s ... Times tried: %d." %(spell_recapture, spellPatch_adopted, spellPatch_adopted, spell_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师技能信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the spell (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的召唤师技能信息。\nSpell information changed to Patch %s." %(spellPatch_adopted, spellPatch_adopted), verbose = verbose)
                            spells = {int(spell_iter["id"]): spell_iter for spell_iter in spell}
                            current_versions["spell"] = spellPatch_adopted
                            unmapped_keys["spell"].clear()
                            break
                    break
            ##英雄联盟装备（LoL items）
            LoLItemIds_match_list: list[int] = sorted(set(map(lambda x: x["stats"]["item0"], game["participants"])) | set(map(lambda x: x["stats"]["item1"], game["participants"])) | set(map(lambda x: x["stats"]["item2"], game["participants"])) | set(map(lambda x: x["stats"]["item3"], game["participants"])) | set(map(lambda x: x["stats"]["item4"], game["participants"])) | set(map(lambda x: x["stats"]["item5"], game["participants"])) | set(map(lambda x: x["stats"]["item6"], game["participants"])) | set(map(lambda x: x["stats"].get("roleBoundItem", 0), game["participants"])))
            for j in LoLItemIds_match_list:
                if not j in LoLItems and current_versions["LoLItem"] != bigVersion and j != 0: #空装备序号是0（The itemId of an empty item is 0）
                    LoLItemPatch_adopted: str = bigVersion
                    LoLItem_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）英雄联盟装备信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nLoL item information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL items of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, LoLItem_recapture, LoLItemPatch_adopted, j, i + 1, len(games), game["gameId"], LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/items.json" %(LoLItemPatch_adopted, language_cdragon[locale]), session, log)
                            LoLItem: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            LoLItemPatch_deserted: str = LoLItemPatch_adopted
                            LoLItemPatch_adopted = FindPostPatch(Patch(LoLItemPatch_adopted), versionList)
                            LoLItem_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItemPatch_deserted, LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_deserted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if LoLItem_recapture < 3:
                                LoLItem_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nYour network environment is abnormal! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄联盟装备信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL item (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的英雄联盟装备信息。\nLoL item information changed to Patch %s." %(LoLItemPatch_adopted, LoLItemPatch_adopted), verbose = verbose)
                            LoLItems = {int(LoLItem_iter["id"]): LoLItem_iter for LoLItem_iter in LoLItem}
                            current_versions["LoLItem"] = LoLItemPatch_adopted
                            unmapped_keys["LoLItem"].clear()
                            break
                    break
            ##符文（Perks）
            perkIds_match_list: list[int] = sorted(set(perk for s in [set(map(lambda x: x["stats"]["perk" + str(i)], game["participants"])) for i in range(6)] for perk in s))
            for j in perkIds_match_list:
                if not j in perks and current_versions["perk"] != bigVersion and j != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                    perkPatch_adopted: str = bigVersion
                    perk_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）基石符文信息（%d）获取失败！正在第%d次尝试改用%s版本的基石符文信息……\nPerk information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perks of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, perk_recapture, perkPatch_adopted, j, i + 1, len(games), game["gameId"], perkPatch_adopted, perk_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perks.json" %(perkPatch_adopted, language_cdragon[locale]), session, log)
                            perk: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            perkPatch_deserted: str = perkPatch_adopted
                            perkPatch_adopted = FindPostPatch(Patch(perkPatch_adopted), versionList)
                            perk_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkPatch_deserted, perk_recapture, perkPatch_adopted, perkPatch_deserted, perkPatch_adopted, perk_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if perk_recapture < 3:
                                perk_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的基石符文信息……\nYour network environment is abnormal! Changing to perks of Patch %s ... Times tried: %d." %(perk_recapture, perkPatch_adopted, perkPatch_adopted, perk_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的基石符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perk (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的基石符文信息。\nPerk information changed to Patch %s." %(perkPatch_adopted, perkPatch_adopted), verbose = verbose)
                            perks = {int(perk_iter["id"]): perk_iter for perk_iter in perk}
                            current_versions["perk"] = perkPatch_adopted
                            unmapped_keys["perk"].clear()
                            break
                    break
            ##符文系（Perkstyles）
            perkstyleIds_match_list: list[int] = sorted(list(set(map(lambda x: x["stats"]["perkPrimaryStyle"], game["participants"])) | set(map(lambda x: x["stats"]["perkSubStyle"], game["participants"]))))
            for j in perkstyleIds_match_list:
                if not j in perkstyles and current_versions["perkstyle"] != bigVersion and j != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                    perkstylePatch_adopted: str = bigVersion
                    perkstyle_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）符文系信息（%d）获取失败！正在第%d次尝试改用%s版本的符文系信息……\nPerkstyle information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perkstyles of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, perkstyle_recapture, perkstylePatch_adopted, j, i + 1, len(games), game["gameId"], perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perkstyles.json" %(perkstylePatch_adopted, language_cdragon[locale]), session, log)
                            perkstyle: dict[str, Any] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            perkstylePatch_deserted: str = perkstylePatch_adopted
                            perkstylePatch_adopted = FindPostPatch(Patch(perkstylePatch_adopted), versionList)
                            perkstyle_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkstylePatch_deserted, perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_deserted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if perkstyle_recapture < 3:
                                perkstyle_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的符文系信息……\nYour network environment is abnormal! Changing to perkstyles of Patch %s ... Times tried: %d." %(perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的符文系信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perkstyle (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的符文系信息。\nPerkstyle information changed to Patch %s." %(perkstylePatch_adopted, perkstylePatch_adopted), verbose = verbose)
                            perkstyles = {int(perkstyle_iter["id"]): perkstyle_iter for perkstyle_iter in perkstyle["styles"]}
                            current_versions["perkstyle"] = perkstylePatch_adopted
                            unmapped_keys["perkstyle"].clear()
                            break
                    break
            ##斗魂竞技场强化符文（Cherry augments）
            CherryAugmentIds_match_list: list[int] = sorted(set(augment for s in [set(map(lambda x: x["stats"]["playerAugment" + str(i)], game["participants"])) for i in range(1, 7)] for augment in s))
            for j in CherryAugmentIds_match_list:
                if not j in CherryAugments and current_versions["CherryAugment"] != bigVersion and j != 0:
                    CherryAugmentPatch_adopted: str = bigVersion
                    CherryAugment_recapture: int = 1
                    logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%d）获取失败！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nAugment information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to Cherry augments of Patch %s ... Times tried: %d." %(i + 1, len(games), game["gameId"], j, CherryAugment_recapture, CherryAugmentPatch_adopted, j, i + 1, len(games), game["gameId"], CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/cherry-augments.json" %(CherryAugmentPatch_adopted, language_cdragon[locale]), session, log)
                            CherryAugment: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            CherryAugmentPatch_deserted: str = CherryAugmentPatch_adopted
                            CherryAugmentPatch_adopted = FindPostPatch(Patch(CherryAugmentPatch_adopted), versionList)
                            CherryAugment_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugmentPatch_deserted, CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_deserted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if CherryAugment_recapture < 3:
                                CherryAugment_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nYour network environment is abnormal! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the Cherry augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(games), game["gameId"], j, j, i + 1, len(games), game["gameId"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的斗魂竞技场强化符文信息。\nCherry augment information changed to Patch %s." %(CherryAugmentPatch_adopted, CherryAugmentPatch_adopted), verbose = verbose)
                            CherryAugments = {int(CherryAugment_iter["id"]): CherryAugment_iter for CherryAugment_iter in CherryAugment}
                            current_versions["CherryAugment"] = CherryAugmentPatch_adopted
                            unmapped_keys["CherryAugment"].clear()
                            break
                    break
        #下面开始整理数据（Sorts out the data）
        generate_LoLHistory_records(LoLHistory_data, game, 0, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments, gameIndex = i + 1, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, log = log, verbose = verbose)
        print("对局记录查询进度（Match history query process）：%d/%d\t对局序号（MatchId）：%d" %(i + 1, len(games), game["gameId"]), end = "\r")
    LoLHistory_statistics_output_order: list[int] = [0, 25, 19, 26, 5, 3, 13, 4, 11, 6, 14, 10, 15, 9, 35, 36, 45, 38, 39, 157, 158, 159, 160, 161, 162, 163, 212, 214, 216, 61, 221, 134]
    LoLHistory_data_organized: dict[str, list[Any]] = {}
    for i in LoLHistory_statistics_output_order:
        key: str = LoLHistory_header_keys[i]
        LoLHistory_data_organized[key] = LoLHistory_data[key]
    LoLHistory_df: pandas.DataFrame = pandas.DataFrame(data = LoLHistory_data_organized)
    for column in LoLHistory_df:
        if LoLHistory_df[column].dtype == "bool":
            LoLHistory_df[column] = LoLHistory_df[column].astype(str)
            LoLHistory_df[column] = list(map(lambda x: "√" if x == "True" else "", LoLHistory_df[column].to_list()))
    LoLHistory_df = pandas.concat([pandas.DataFrame([LoLHistory_header])[LoLHistory_df.columns], LoLHistory_df], ignore_index = True)
    #LoLHistory_df.apply(lambda x: pandas.Series([-3], index = ["K/D/A"]))
    return (LoLHistory_df, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments)
    LoLHistory_web_display_order: list[int] = [0, 25, 19, 26, 5, 3, 13, 4, 11, 6, 14, 10, 15, 9, 35, 36, 37, 45, 40, 41, 164, 165, 166, 167, 168, 169, 170, 213, 214, 216, 61, 221, 134]
    LoLHistory_data_organized_web: dict[str, list[Any]] = {}
    for i in LoLHistory_web_display_order:
        key: str = LoLHistory_header_keys[i]
        if i in [28, 37, 40, 41, 164, 165, 166, 167, 168, 169, 170, 183, 184, 185, 186, 187, 188, 190, 192, 199, 200, 201, 202, 203, 204, 213]: #转换路径（Transform the paths）
            LoLHistory_data_organized_web[key] = list(map(lambda x: "" if x == "" else urljoin(connection.address, x), LoLHistory_data[key]))
        else:
            LoLHistory_data_organized_web[key] = LoLHistory_data[key]
    LoLHistory_df_web: pandas.DataFrame = pandas.DataFrame(data = LoLHistory_data_organized_web)
    LoLHistory_df_web = pandas.concat([pandas.DataFrame([LoLHistory_header])[LoLHistory_df_web.columns], LoLHistory_df_web], ignore_index = True)
    LoLHistory_htmltable: str = LoLHistory_df_web.to_html(escape = False)

def generate_LoLGameInfo_records(LoLGame_info_data: dict[str, list[Any]], LoLGame_info: dict[str, Any], participantIndex: int, queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], gameIndex: int = 1, current_puuid: str | list[str] = "", bans: list[dict[str, int]] | None = None, legacy_banData_appended: dict[int, bool] | None = None, unmapped_keys: dict[str, set[int]] | None = None, useAllVersions: bool = False, log: LogManager | None = None, verbose: bool = True) -> dict[str, list[Any]]:
    if bans == None:
        bans = []
    if legacy_banData_appended == None:
        legacy_banData_appended = {100: False, 200: False}
    if unmapped_keys == None:
        unmapped_keys = {"queue": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [current_puuid] if isinstance(current_puuid, str) else current_puuid
    LoLGame_info_header_keys: list[str] = list(LoLGame_info_header.keys())
    matchId: int = LoLGame_info["gameId"]
    version: str = LoLGame_info["gameVersion"]
    mapName: str = gamemaps[LoLGame_info["mapId"]]["zh_CN"]
    stats: dict[str, int | bool] = LoLGame_info["participants"][participantIndex]["stats"]
    timeline: dict[str, Any] = LoLGame_info["participants"][participantIndex]["timeline"]
    bans_team100: list[dict[str, int]] = []
    bans_team200: list[dict[str, int]] = []
    for i in range(len(LoLGame_info["teams"])):
        if LoLGame_info["teams"][i]["teamId"] == 100:
            bans_team100 = LoLGame_info["teams"][i]["bans"]
        elif LoLGame_info["teams"][i]["teamId"] == 200:
            bans_team200 = LoLGame_info["teams"][i]["bans"]
    current_participant_found: bool = False
    for participant in LoLGame_info["participantIdentities"]:
        for puuid in puuidList:
            if participant["player"]["puuid"] == puuid:
                current_participantId: int = participant["participantId"]
                current_participant_found: bool = True
                break #注意，这里是找到一个对应的玩家通用唯一识别码，即找到一名玩家就退出循环。因为传入玩家通用唯一识别码的主要目的是区别敌我，而如果自己的多个账号在一场对局中同时出现，需要选择一个账号所在阵营视为友方。这里选择的是第一个账号所在阵营（Note that once a puuid, or a player is found, the program exits the loop. This is because the main purpose of passing the puuid is to distinguish the ally team and the enemy team. If the user's multiple accounts are present in a match at the same time, the ally team should be the team of one account. Here we take the team of the account first found in the match as the ally team）
        if current_participant_found:
            break
    if current_participant_found:
        for participant in LoLGame_info["participants"]:
            if participant["participantId"] == current_participantId:
                current_participant = participant
                break
    else:
        current_participantId = 0 #如果出现数据异常，也认为目标玩家不存在于该对局中（If an error occurs to the data, consider this player isn't in this match）
    team_participants: list[dict[str, Any]] = [participant for participant in LoLGame_info["participants"] if LoLGame_info["gameMode"] == "CHERRY" and participant["stats"]["playerSubteamId"] == stats["playerSubteamId"] or LoLGame_info["gameMode"] != "CHERRY" and participant["teamId"] == LoLGame_info["participants"][participantIndex]["teamId"]] #存储对局信息中同一队伍的玩家。斗魂竞技场对局应该使用子阵营（Store the participants of the same team from the game information. Subteam should be used to evaluate a player）
    if LoLGame_info["mapId"] == 12:
        if "mapskin_map12_bloom" in LoLGame_info["gameModeMutators"]:
            mapName = "莲华栈桥"
        elif "mapskin_ha_bilgewater" in LoLGame_info["gameModeMutators"]:
            mapName = "屠夫之桥"
        elif "mapskin_ha_crepe" in LoLGame_info["gameModeMutators"]:
            mapName = "进步之桥"
        else:
            mapName = "嚎哭深渊"
    for i in range(len(LoLGame_info_header_keys)):
        key: str = LoLGame_info_header_keys[i]
        if i == 0: #游戏序号（`gameIndex`）
            LoLGame_info_data[key].append(gameIndex)
        elif i <= 15:
            if i == 1: #对局终止情况（`endOfGameResult`）
                LoLGame_info_data[key].append(endOfGameResults[LoLGame_info["endOfGameResult"]])
            elif i == 3: #创建日期（`gameCreationDate`）
                LoLGame_info_data[key].append(LoLGame_info["gameCreationDate"][:10] + " " + LoLGame_info["gameCreationDate"][11:23])
            elif i == 8: #游戏类型（`gameType`）
                LoLGame_info_data[key].append(gameTypes_history[LoLGame_info["gameType"]])
            elif i == 13: #持续时长（`gameDuration_norm`）
                LoLGame_info_data[key].append("%d:%02d" %(LoLGame_info["gameDuration"] // 60, LoLGame_info["gameDuration"] % 60))
            elif i == 14: #游戏模式名称（`gameModeName`）
                LoLGame_info_data[key].append("自定义" if LoLGame_info["queueId"] == 0 else queues[LoLGame_info["queueId"]]["name"] if LoLGame_info["queueId"] in queues else "")
            elif i == 15: #地图名称（`mapName`）
                LoLGame_info_data[key].append(mapName)
            else:
                LoLGame_info_data[key].append(LoLGame_info[key])
        elif i == 16: #玩家序号（`participantId`）
            LoLGame_info_data[key].append(LoLGame_info["participantIdentities"][participantIndex]["participantId"])
        elif i <= 29:
            if i >= 28: #召唤师图标相关键（Profile icon-related keys）
                profileIconId: int = LoLGame_info["participantIdentities"][participantIndex]["player"]["profileIcon"]
                if profileIconId == -1: #早期存在一个空图标（There was once an empty icon, which is transparent）
                    LoLGame_info_data[key].append(profileIconId if i == 27 else "")
                elif profileIconId in summonerIcons:
                    LoLGame_info_data[key].append(summonerIcons[profileIconId].get(key.split("_")[-1], profileIconId if i == 28 else ""))
                else:
                    if not profileIconId in unmapped_keys["summonerIcon"]:
                        if useAllVersions:
                            unmapped_keys["summonerIcon"].add(profileIconId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）召唤师图标信息（%d）获取失败！将采用原始数据！\n[%d. %s] Summoner icon information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, profileIconId, i, key, profileIconId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(profileIconId if i == 28 else "")
            else:
                LoLGame_info_data[key].append(LoLGame_info["participantIdentities"][participantIndex]["player"][key])
        elif i <= 42:
            if i == 31: #最高段位（`highestAchievedSeasonTier`）
                LoLGame_info_data[key].append(tiers[LoLGame_info["participants"][participantIndex]["highestAchievedSeasonTier"]])
            elif i >= 35 and i <= 37: #选用英雄序号相关键（`championId`-related keys）
                championId: int = LoLGame_info["participants"][participantIndex][key.split("_")[0] + "Id"]
                if championId in LoLChampions:
                    LoLGame_info_data[key].append(LoLChampions[championId][key.split("_")[-1]])
                else:
                    if not championId in unmapped_keys["LoLChampion"]:
                        if useAllVersions:
                            unmapped_keys["LoLChampion"].add(championId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）英雄信息（%d）获取失败！将采用原始数据！\n[%d. %s] Champion information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, championId, i, key, championId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(championId if i == 35 else "")
            elif i >= 38 and i <= 41: #召唤师技能序号相关键（SpellIds-related keys）
                spellId: int = LoLGame_info["participants"][participantIndex][key.split("_")[0] + "Id"]
                if spellId == 0: #2024年更新人机对战之前，在对局记录中记录的电脑玩家的召唤师技能序号都是0。在加载界面，玩家总是会看到电脑玩家携带了净化和惩戒，在进游戏后即表现为正常（Before Co-op vs. AI was updated in 2024, spellIds of all bots recorded in the match history are 0. In the loading screen, player always saw the bot players taking Cleanse and Smite, while the spells became normal after players enter the game）
                    LoLGame_info_data[key].append(spellId if i <= 39 else "")
                elif spellId in spells:
                    LoLGame_info_data[key].append(spells[spellId][key.split("_")[-1]])
                else:
                    if not spellId in unmapped_keys["spell"]:
                        if useAllVersions:
                            unmapped_keys["spell"].add(spellId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）召唤师技能信息（%d）获取失败！将采用原始数据！\n[%d. %s] Spell information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, spellId, i, key, spellId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(spellId if i <= 39 else "")
            elif i == 42: #阵营（`team_color`）
                LoLGame_info_data[key].append(team_colors_int[LoLGame_info["participants"][participantIndex]["teamId"]])
            else:
                LoLGame_info_data[key].append(LoLGame_info["participants"][participantIndex][key])
        elif i <= 221:
            if i == 132: #角色绑定装备：临时应付正式服15.24版本、测试服16.1版本的情形（`roleBoundItem`: a temporary solution to handle the period when Live is v25.24 and PBE is 16.1）
                LoLGame_info_data[key].append(stats.get("roleBoundItem", ""))
            elif i >= 157 and i <= 170: #英雄联盟装备相关键（LoLItems-related keys）
                itemId: int = stats[key.split("_")[0]]
                if itemId == 0:
                    LoLGame_info_data[key].append("")
                elif itemId in LoLItems:
                    LoLGame_info_data[key].append(LoLItems[itemId][key.split("_")[-1]])
                else:
                    if not itemId in unmapped_keys["LoLItem"]:
                        if useAllVersions:
                            unmapped_keys["LoLItem"].add(itemId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%d）获取失败！将采用原始数据！\n[%d. %s] LoL item information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, itemId, i, key, itemId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(itemId if i <= 163 else "")
            elif i >= 171 and i <= 188: #符文相关键（Perks-related keys）
                if i <= 176:
                    perkId: int = stats[key[:5]]
                    if perkId == 0:
                        LoLGame_info_data[key].append("")
                    elif perkId in perks:
                        perk_EndOfGameStatDescs = "".join(list(map(lambda x: x + "。", perks[perkId]["endOfGameStatDescs"])))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar1@", str(stats[key[:5] + "Var1"]))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar2@", str(stats[key[:5] + "Var2"]))
                        perk_EndOfGameStatDescs = perk_EndOfGameStatDescs.replace("@eogvar3@", str(stats[key[:5] + "Var3"]))
                        LoLGame_info_data[key].append(perk_EndOfGameStatDescs)
                    else:
                        if not perkId in unmapped_keys["perk"]:
                            if useAllVersions:
                                unmapped_keys["perk"].add(perkId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Runes information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkId, i, key, perkId, matchId, version), verbose = verbose)
                        LoLGame_info_data[key].append("")
                else:
                    perkId = stats[key.split("_")[0]]
                    if perkId == 0:
                        LoLGame_info_data[key].append("")
                    elif perkId in perks:
                        LoLGame_info_data[key].append(perks[perkId][key.split("_")[-1]])
                    else:
                        if not perkId in unmapped_keys["perk"]:
                            if useAllVersions:
                                unmapped_keys["perk"].add(perkId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Runes information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkId, i, key, perkId, matchId, version), verbose = verbose)
                        LoLGame_info_data[key].append(perkId if i <= 182 else "")
            elif i >= 189 and i <= 192: #符文系相关键（Perkstyles-related keys）
                perkstyleId: int = stats[key.split("_")[0]]
                if perkstyleId == 0:
                    LoLGame_info_data[key].append("")
                elif perkstyleId in perkstyles:
                    LoLGame_info_data[key].append(perkstyles[perkstyleId][key.split("_")[-1]])
                else:
                    if not perkstyleId in unmapped_keys["perkstyle"]:
                        if useAllVersions:
                            unmapped_keys["perkstyle"].add(perkstyleId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）符文系信息（%d）获取失败！将采用原始数据！\n[%d. %s] Perkstyle information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, perkstyleId, i, key, perkstyleId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(perkstyleId if (i - 189) % 2 == 0 else "")
            elif i >= 193 and i <= 210: #强化符文相关键（Augment-related keys）
                CherryAugmentId: int = stats[key.split("_")[0]]
                if CherryAugmentId == 0:
                    LoLGame_info_data[key].append("")
                elif CherryAugmentId in CherryAugments:
                    if i <= 198: #强化符文名称（`nameTRA`）
                        LoLGame_info_data[key].append(CherryAugments[CherryAugmentId][key.split("_")[-1]])
                    elif i <= 204: #强化符文图标路径（`augmentIconPath`）
                        LoLGame_info_data[key].append(CherryAugments[CherryAugmentId]["augmentSmallIconPath"].replace("_small.png", "_large.png"))
                    else: #强化符文等级（`rarity`）
                        LoLGame_info_data[key].append(augment_rarity[CherryAugments[CherryAugmentId][key.split("_")[-1]]])
                else:
                    if not CherryAugmentId in unmapped_keys["CherryAugment"]:
                        if useAllVersions:
                            unmapped_keys["CherryAugment"].add(CherryAugmentId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）强化符文信息（%d）获取失败！将采用原始数据！\n[%d. %s] Cherry augment information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, CherryAugmentId, i, key, CherryAugmentId, matchId, version), verbose = verbose)
                    LoLGame_info_data[key].append(CherryAugmentId if i <= 198 else "")
            elif i == 211: #子阵营（`playerSubteamColor`）
                LoLGame_info_data[key].append(subteam_colors[stats["playerSubteamId"]])
            elif i == 212 or i == 213: #角色绑定装备相关键（Role bound item-related keys）
                if "roleBoundItem" in stats:
                    roleBoundItemId: int = stats["roleBoundItem"]
                    if roleBoundItemId == 0:
                        LoLGame_info_data[key].append("")
                    elif roleBoundItemId in LoLItems:
                        LoLGame_info_data[key].append(LoLItems[roleBoundItemId][key.split("_")[-1]])
                    else:
                        if not roleBoundItemId in unmapped_keys["LoLItem"]:
                            if useAllVersions:
                                unmapped_keys["LoLItem"].add(roleBoundItemId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%d）获取失败！将采用原始数据！\n[%d. %s] LoL item information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, roleBoundItemId, i, key, roleBoundItemId, matchId, version), verbose = verbose)
                        LoLGame_info_data[key].append(roleBoundItemId if i == 212 else "")
                else:
                    LoLGame_info_data[key].append("")
            elif i == 214: #击杀/死亡/助攻（`K/D/A`）
                LoLGame_info_data[key].append("/".join([str(stats["kills"]), str(stats["deaths"]), str(stats["assists"])]))
            elif i == 215: #战损比（`KDA`）
                LoLGame_info_data[key].append((stats["kills"] + stats["assists"]) / max(1, stats["deaths"]))
            elif i == 216: #补刀（`CS`）
                LoLGame_info_data[key].append(stats["neutralMinionsKilled"] + stats["totalMinionsKilled"])
            elif i == 217: #分均经济（`GPM`）
                LoLGame_info_data[key].append(0 if LoLGame_info["gameDuration"] == 0 else stats["goldEarned"] * 60 / LoLGame_info["gameDuration"])
            elif i == 218: #金币利用率（`GUE` - Gold Utilization Efficiency）
                LoLGame_info_data[key].append(0 if stats["goldEarned"] == 0 else stats["goldSpent"] / stats["goldEarned"])
            elif i == 219: #分均补刀（`CSPM`）
                LoLGame_info_data[key].append(0 if LoLGame_info["gameDuration"] == 0 else (stats["neutralMinionsKilled"] + stats["totalMinionsKilled"]) * 60 / LoLGame_info["gameDuration"])
            elif i == 220: #伤害转化率（`D/G`）
                LoLGame_info_data[key].append(0 if stats["goldEarned"] == 0 else stats["totalDamageDealtToChampions"] / stats["goldEarned"])
            elif i == 221: #胜负（`win/lose`）
                LoLGame_info_data[key].append("被终止" if LoLGame_info["endOfGameResult"] == "Abort_AntiCheatExit" else "胜利" if stats["win"] else "失败")
            else:
                LoLGame_info_data[key].append(stats[key])
        elif i <= 225:
            if bans == []: #修改说明：以前判断禁用数据是否为空是通过禁用模式进行的，如果禁用模式是经典策略就记录禁用信息，否则直接追加空值到列表中。但是在终极魔典中，先前版本记录禁用信息，后来却不记录了。因此，这里判断禁用数据是否为空，直接通过判断bans是否为空【Modification note: To judge whether the ban information of a match is empty, banMode (teams\bans) is used: if banMode is StandardBanStrategy, record the ban information; otherwise, append empty values to the list (by player_count times). But in Ultbook, ban information is recorded in previous versions but not anymore recorded later. Therefore, to judge whether the ban information is empty, whether the variable bans is empty is directly checked】
                LoLGame_info_data[key].append("")
            else:
                if LoLGame_info["queueId"] == 0:
                    if LoLGame_info["participants"][participantIndex]["teamId"] == 100:
                        if not legacy_banData_appended[100]:
                            if i == 222:
                                LoLGame_info_data[key].append(list(map(lambda x: x["championId"], bans_team100)))
                            else:
                                championIds: list[int] = list(map(lambda x: x["championId"], bans_team100))
                                to_append: list[str | int] = []
                                for championId in championIds:
                                    if championId in LoLChampions:
                                        to_append.append(LoLChampions[championId][key.split("_")[-1]])
                                    else:
                                        if not championId in unmapped_keys["LoLChampion"]:
                                            if useAllVersions:
                                                unmapped_keys["LoLChampion"].add(championId)
                                            logPrint("【%d. %s】对局%d（对局版本：%s）英雄信息（%d）获取失败！将采用原始数据！\n[%d. %s] Champion information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, championId, i, key, championId, matchId, version), verbose = verbose)
                                        to_append.append(championId if i == 223 else "")
                                LoLGame_info_data[key].append(to_append)
                            legacy_banData_appended[100] = True
                        else:
                            LoLGame_info_data[key].append("")
                    if LoLGame_info["participants"][participantIndex]["teamId"] == 200:
                        if not legacy_banData_appended[200]:
                            if i == 222:
                                LoLGame_info_data[key].append(list(map(lambda x: x["championId"], bans_team200)))
                            else:
                                championIds = list(map(lambda x: x["championId"], bans_team200))
                                to_append = []
                                for championId in championIds:
                                    if championId in LoLChampions:
                                        to_append.append(LoLChampions[championId][key.split("_")[-1]])
                                    else:
                                        if not championId in unmapped_keys["LoLChampion"]:
                                            if useAllVersions:
                                                unmapped_keys["LoLChampion"].add(championId)
                                            logPrint("【%d. %s】对局%d（对局版本：%s）英雄信息（%d）获取失败！将采用原始数据！\n[%d. %s] Champion information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, championId, i, key, championId, matchId, version), verbose = verbose)
                                        to_append.append(championId if i == 223 else "")
                                LoLGame_info_data[key].append(to_append)
                            legacy_banData_appended[200] = True
                        else:
                            LoLGame_info_data[key].append("")
                else:
                    if bans[participantIndex]["championId"] == -1:
                        LoLGame_info_data[key].append("")
                    else:
                        if i == 222:
                            LoLGame_info_data[key].append(bans[participantIndex]["championId"])
                        else:
                            championId = bans[participantIndex]["championId"]
                            if championId in LoLChampions:
                                LoLGame_info_data[key].append(LoLChampions[championId][key.split("_")[-1]])
                            else:
                                if not championId in unmapped_keys["LoLChampion"]:
                                    if useAllVersions:
                                        unmapped_keys["LoLChampion"].add(championId)
                                    logPrint("【%d. %s】对局%d（对局版本：%s）英雄信息（%d）获取失败！将采用原始数据！\n[%d. %s] Champion information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, championId, i, key, championId, matchId, version), verbose = verbose)
                                LoLGame_info_data[key].append(championId if i == 223 else "")
        elif i <= 227: #时间轴相关键（Timeline-related keys）
            LoLGame_info_data[key].append(lanes[timeline[key]] if i == 226 else roles[timeline[key]])
        elif i == 228: #是否队友？（`isAlly`）
            LoLGame_info_data[key].append(current_participantId != 0 and (LoLGame_info["gameMode"] == "CHERRY" and stats["playerSubteamId"] == current_participant["stats"]["playerSubteamId"] or LoLGame_info["gameMode"] != "CHERRY" and LoLGame_info["participants"][participantIndex]["teamId"] == current_participant["teamId"]))
        else: #对局信息转换键（Keys transformed according to game information）
            subkey = key.split("_")[0]
            if key.endswith("_percent"): #团队占比键（Team percentage keys）
                if i == 287: #参团率（`KP_percent`）
                    self_stat: int | float = stats["kills"] + stats["assists"]
                    total_stat = sum(map(lambda x: x["stats"]["kills"], team_participants))
                elif i == 288: #补刀数占比（`CS_percent`）
                    self_stat = stats["totalMinionsKilled"] + stats["neutralMinionsKilled"]
                    total_stat = sum(map(lambda x: x["stats"]["totalMinionsKilled"] + x["stats"]["neutralMinionsKilled"], team_participants))
                else:
                    self_stat = stats[subkey]
                    total_stat = sum(map(lambda x: x["stats"][subkey], team_participants))
                value = 0 if total_stat == 0 else self_stat / total_stat
                LoLGame_info_data[key].append(value)
            else: #位次键（Order keys）
                if i == 348: #战损比位次（`KDA_order`）
                    self_stat = (stats["kills"] + stats["assists"]) / max(1, stats["deaths"])
                    stat_list = sorted(map(lambda x: (x["stats"]["kills"] + x["stats"]["assists"]) / max(1, x["stats"]["deaths"]), team_participants), reverse = True)
                elif i == 349: #参团率位次（`KP_order`）
                    self_stat = stats["kills"] + stats["assists"]
                    stat_list = sorted(map(lambda x: x["stats"]["kills"] + x["stats"]["assists"], team_participants), reverse = True)
                elif i == 350: #补刀数位次（`CS_order`）
                    self_stat = stats["totalMinionsKilled"] + stats["neutralMinionsKilled"]
                    stat_list = sorted(map(lambda x: x["stats"]["totalMinionsKilled"] + x["stats"]["neutralMinionsKilled"], team_participants), reverse = True)
                elif i == 351: #伤害转化率位次（`D/G_order`）
                    self_stat = 0 if stats["goldEarned"] == 0 else stats["totalDamageDealtToChampions"] / stats["goldEarned"]
                    stat_list = sorted(map(lambda x: 0 if x["stats"]["goldEarned"] == 0 else x["stats"]["totalDamageDealtToChampions"] / x["stats"]["goldEarned"], team_participants), reverse = True)
                elif i == 352: #金币利用率位次（`GUE_order`）
                    self_stat = 0 if stats["goldEarned"] == 0 else stats["goldSpent"] / stats["goldEarned"]
                    stat_list = sorted(map(lambda x: 0 if x["stats"]["goldEarned"] == 0 else x["stats"]["goldSpent"] / x["stats"]["goldEarned"], team_participants), reverse = True)
                else:
                    self_stat = stats[subkey]
                    stat_list = sorted(map(lambda x: x["stats"][subkey], team_participants), reverse = i != 295) #死亡次数越低，死亡位次越小（For deaths, the lower the number of deaths is, the smaller the death order is）
                LoLGame_info_data[key].append(0 if len(set(stat_list)) == 1 else stat_list.index(self_stat) + 1) #当所有人的数据一样时，则不用比较位次（When some stat of every player is the same, there's no need to compare it）
    return LoLGame_info_data

def sort_LoLGame_info(LoLGame_info: dict[str, Any], queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], gameIndex: int = 1, current_puuid: str | list[str] = "", useAllVersions: bool = True, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, sortStats: bool = False, LoLGame_stat_data: dict[str, list[Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if LoLGame_stat_data == None:
        LoLGame_stat_data = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [current_puuid] if isinstance(current_puuid, str) else current_puuid
    current_versions: dict[str, str] = {"queue": "", "summonerIcon": "", "spell": "", "LoLChampion": "", "LoLItem": "", "summonerIcon": "", "perk": "", "perkstyle": "", "CherryAugment": ""}
    unmapped_keys: dict[str, set[int]] = {"queue": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    version: str = LoLGame_info["gameVersion"]
    bigVersion: str = ".".join(version.split(".")[:2])
    matchId: int = LoLGame_info["gameId"]
    LoLGame_info_header_keys: list[str] = list(LoLGame_info_header.keys())
    LoLGame_info_data: dict[str, list[Any]] = {} #这里将对局的数据放在一个字典中，键为统计量，值为由所有玩家的数据组成的列表（Here the whole match data are stored in a dictionary whose keys are statistics and values are lists composed of corresponding data of all players）
    #整理对局禁用信息（Sort out the team ban information）
    bans_team100: list[dict[str, int]] = LoLGame_info["teams"][0]["bans"]
    try:
        bans_team200: list[dict[str, int]] = LoLGame_info["teams"][1]["bans"]
    except IndexError:
        bans: list[dict[str, int]] = bans_team100 #空对局也会进入历史记录。空对局定义为完成选英雄但是无法正常进入游戏，而后游戏不存在的对局。而训练模式的空对局只有一方，因此LoLGame_info["teams"]中只有一个元素（Empty matches are included in the match history. An empty match is defined as the matches which can't be launched after the ChmpSlct period. Since an empty match of Practice Tool has only one team, there's only 1 element in LoLGame_info["teams"]）
    else:
        bans = bans_team100 + bans_team200
    if LoLGame_info["gameMode"] == "CHERRY" and Patch("14.8") < Patch(version):
        bans_tmp: list[dict[str, int]] = bans[:]
        bans = []
        emptyBan: dict[str, int] = {"championId": -1, "pickTurn": 0} #定义一个初始化禁用字典，用于后续数据框填充空值（Define an initialized banning dictionary so that empty values are appended to the dataframe at certain times subsequently）
        playerSubteam: dict[int, list[int]] = {} #存储不同子阵营的玩家，键是子阵营序号，值是该子阵营中的玩家的API序号列表（Stores different subteams' players. Keys are playerSubteamIds, and values are index lists from API for players in the subteams）
        for i in range(len(LoLGame_info["participants"])):
            bans.append(emptyBan.copy())
            playerSubteamId: int = LoLGame_info["participants"][i]["stats"]["playerSubteamId"]
            if not playerSubteamId in playerSubteam:
                playerSubteam[playerSubteamId] = []
            playerSubteam[playerSubteamId].append(i)
        if Patch("14.12") < Patch(version):
            participantBanIds: list[int] = []
            for i in sorted(playerSubteam.keys()):
                participantBanIds += [playerSubteam[i][0], playerSubteam[i][1]] #这里默认采用某个子阵营在API中记录的第一名玩家作为该子阵营的先选者。这可能与实际选用顺序有出入（Here the first player of a subteam recorded in API is considered as the player that picks a champion first. This player may not be the real first player.）
        else:
            participantBanIds = [playerSubteam[i][0] for i in sorted(playerSubteam.keys())] #这里默认采用某个子阵营在API中记录的第一名玩家作为禁用英雄的玩家。这可能与实际禁用英雄的玩家有出入（Here the first player of a subteam recorded in API is considered as the player that banned some champion. This player may not be the real player that banned it）
        for i in range(len(participantBanIds)):
            bans[participantBanIds[i]] = bans_tmp[i]
    legacy_banData_appended: dict[int, bool] = {100: False, 200: False} #自定义对局中的征召模式是由每个阵营的1号选手禁用3个英雄，所以当禁用信息添加到一个阵营的第一名玩家后，后续玩家不需要再添加禁用信息。这个字典就是用来判断这一点的（Draft mode in custom matches is performed by the first player of each team banning 3 champions, so if the ban information is added into the first player, the subsequent player in the same team doesn't need to add this information. That's what this dictionary is used for）
    #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
    if useAllVersions:
        ##游戏模式（Game mode）
        queueIds_match_list: list[int] = [LoLGame_info["queueId"]]
        for i in queueIds_match_list:
            if not i in queues and current_versions["queue"] != bigVersion:
                queuePatch_adopted: str = bigVersion
                queue_recapture: int = 1
                logPrint("对局%d游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(matchId, i, queue_recapture, queuePatch_adopted, i, matchId, queuePatch_adopted, queue_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                        queue: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        queuePatch_deserted: str = queuePatch_adopted
                        queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                        queue_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if queue_recapture < 3:
                            queue_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game mode (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                        queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                        current_versions["queue"] = queuePatch_adopted
                        unmapped_keys["queue"].clear()
                        break
                break
        ##召唤师图标（Summoner icon）
        summonerIconIds_match_list: list[int] = sorted(set(map(lambda x: x["player"]["profileIcon"], LoLGame_info["participantIdentities"])))
        for i in summonerIconIds_match_list:
            if not i in summonerIcons and current_versions["summonerIcon"] != bigVersion:
                summonerIconPatch_adopted: str = bigVersion
                summonerIcon_recapture: int = 1
                logPrint("对局%d召唤师图标信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师图标信息……\nSummoner icon information (%d) of Match %d capture failed! Changing to summoner icons of Patch %s ... Times tried: %d." %(matchId, i, summonerIcon_recapture, summonerIconPatch_adopted, i, matchId, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-icons.json" %(summonerIconPatch_adopted, language_cdragon[locale]), session, log)
                        summonerIcon: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        summonerIconPatch_deserted: str = summonerIconPatch_adopted
                        summonerIconPatch_adopted = FindPostPatch(Patch(summonerIconPatch_adopted), versionList)
                        summonerIcon_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIconPatch_deserted, summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_deserted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if summonerIcon_recapture < 3:
                            summonerIcon_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师图标信息……\nYour network environment is abnormal! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的召唤师图标信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the summoner icon (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的召唤师图标信息。\nSummoner icon information changed to Patch %s." %(summonerIconPatch_adopted, summonerIconPatch_adopted), verbose = verbose)
                        summonerIcons = {int(summonerIcon_iter["id"]): summonerIcon_iter for summonerIcon_iter in summonerIcon}
                        current_versions["summonerIcon"] = summonerIconPatch_adopted
                        unmapped_keys["summonerIcon"].clear()
                        break
                break
        ##英雄：包含选用英雄和禁用英雄（LoL champions, which contain picked and banned ones）
        LoLChampionIds_match_list: list[int] = sorted(set(map(lambda x: x["championId"], LoLGame_info["participants"])) | set(map(lambda x: x["championId"], bans)))
        for i in LoLChampionIds_match_list:
            if not i in LoLChampions and current_versions["LoLChampion"] != bigVersion:
                LoLChampionPatch_adopted: str = bigVersion
                LoLChampion_recapture: int = 1
                logPrint("对局%d英雄信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄信息……\nLoL champion information (%d) of Match %d capture failed! Changing to LoL champions of Patch %s ... Times tried: %d." %(matchId, i, LoLChampion_recapture, LoLChampionPatch_adopted, i, matchId, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/champion-summary.json" %(LoLChampionPatch_adopted, language_cdragon[locale]), session, log)
                        LoLChampion: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        LoLChampionPatch_deserted: str = LoLChampionPatch_adopted
                        LoLChampionPatch_adopted = FindPostPatch(Patch(LoLChampionPatch_adopted), versionList)
                        LoLChampion_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampionPatch_deserted, LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_deserted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if LoLChampion_recapture < 3:
                            LoLChampion_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄信息……\nYour network environment is abnormal! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL champion (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的英雄信息。\nLoL champion information changed to Patch %s." %(LoLChampionPatch_adopted, LoLChampionPatch_adopted), verbose = verbose)
                        LoLChampions = {int(LoLChampion_iter["id"]): LoLChampion_iter for LoLChampion_iter in LoLChampion}
                        current_versions["LoLChampion"] = LoLChampionPatch_adopted
                        unmapped_keys["LoLChampion"].clear()
                        break
                break
        ##召唤师技能（Summoner spells）
        spellIds_match_list: list[int] = sorted(set(map(lambda x: x["spell1Id"], LoLGame_info["participants"])) | set(map(lambda x: x["spell2Id"], LoLGame_info["participants"])))
        for i in spellIds_match_list:
            if not i in spells and current_versions["spell"] != bigVersion and i != 0: #需要注意电脑玩家的召唤师技能序号都是0（Note that Spell Ids of bot players are both 0s）
                spellPatch_adopted: str = bigVersion
                spell_recapture: int = 1
                logPrint("对局%d召唤师技能信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师技能信息……\nSpell information (%d) of Match %d capture failed! Changing to spells of Patch %s ... Times tried: %d." %(matchId, i, spell_recapture, spellPatch_adopted, i, matchId, spellPatch_adopted, spell_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-spells.json" %(spellPatch_adopted, language_cdragon[locale]), session, log)
                        spell: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        spellPatch_deserted: str = spellPatch_adopted
                        spellPatch_adopted = FindPostPatch(Patch(spellPatch_adopted), versionList)
                        spell_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to spells of Patch %s ... Times tried: %d." %(spellPatch_deserted, spell_recapture, spellPatch_adopted, spellPatch_deserted, spellPatch_adopted, spell_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if spell_recapture < 3:
                            spell_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师技能信息……\nYour network environment is abnormal! Changing to spells of Patch %s ... Times tried: %d." %(spell_recapture, spellPatch_adopted, spellPatch_adopted, spell_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的召唤师技能信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the spell (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的召唤师技能信息。\nSpell information changed to Patch %s." %(spellPatch_adopted, spellPatch_adopted), verbose = verbose)
                        spells = {int(spell_iter["id"]): spell_iter for spell_iter in spell}
                        current_versions["spell"] = spellPatch_adopted
                        unmapped_keys["spell"].clear()
                        break
                break
        ##英雄联盟装备（LoL items）
        #接下来查询具体的对局信息，使用的可能并不是历史记录中记载的对局序号形成的列表。考虑实际使用需求，这里对于装备的合适版本信息采取的思路是默认从最新版本开始获取，如果有装备不存在于最新版本的装备信息，则获取游戏信息中存储的版本对应的装备信息。该思路仍然有问题，详见后续关于美测服的装备获取的注释（The next step is to capture the information for each specific match, which may not originate from the matchIDs recorded in the match history. Considering the practical use, here the stream of thought for an appropriate version for items is to get items' information from the latest patch, and if some item doesn't exist in the items information of the latest patch, then get the items of the version corresponding to the game according to gameVersion recorded in the match information. There's a flaw of this idea. Please refer to the annotation regarding PBE data crawling for further solution）
        LoLItemIds_match_list: list[int] = sorted(set(item for s in [set(map(lambda x: x["stats"].get(key, 0), LoLGame_info["participants"])) for key in ["item0", "item1", "item2", "item3", "item4", "item5", "item6", "roleBoundItem"]] for item in s)) #该表达式等价于以下表达式（This expression is equivalent to the following expression）：`LoLItemIds_match_list = sorted(set(map(lambda x: x["stats"]["item0"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item1"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item2"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item3"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item4"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item5"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item6"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["roleBoundItem"], LoLGame_info["participants"])))`
        for i in LoLItemIds_match_list:
            if not i in LoLItems and current_versions["LoLItem"] != bigVersion and i != 0: #空装备序号是0（The itemId of an empty item is 0）
                LoLItemPatch_adopted: str = bigVersion
                LoLItem_recapture: int = 1
                logPrint("对局%d英雄联盟装备信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nLoL item information (%d) of Match %d capture failed! Changing to LoL items of Patch %s ... Times tried: %d." %(matchId, i, LoLItem_recapture, LoLItemPatch_adopted, i, matchId, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/items.json" %(LoLItemPatch_adopted, language_cdragon[locale]), session, log)
                        LoLItem: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        LoLItemPatch_deserted: str = LoLItemPatch_adopted
                        LoLItemPatch_adopted = FindPostPatch(Patch(LoLItemPatch_adopted), versionList)
                        LoLItem_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItemPatch_deserted, LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_deserted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if LoLItem_recapture < 3:
                            LoLItem_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nYour network environment is abnormal! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的英雄联盟装备信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL item (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的英雄联盟装备信息。\nLoL item information changed to Patch %s." %(LoLItemPatch_adopted, LoLItemPatch_adopted), verbose = verbose)
                        LoLItems = {int(LoLItem_iter["id"]): LoLItem_iter for LoLItem_iter in LoLItem}
                        current_versions["LoLItem"] = LoLItemPatch_adopted
                        unmapped_keys["LoLItem"].clear()
                        break
                break
        ##符文（Perks）
        perkIds_match_list: list[int] = sorted(set(perk for s in [set(map(lambda x: x["stats"]["perk" + str(i)], LoLGame_info["participants"])) for i in range(6)] for perk in s))
        for i in perkIds_match_list:
            if not i in perks and current_versions["perk"] != bigVersion and i != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                perkPatch_adopted: str = bigVersion
                perk_recapture: int = 1
                logPrint("对局%d基石符文信息（%d）获取失败！正在第%d次尝试改用%s版本的基石符文信息……\nPerk information (%d) of Match %d capture failed! Changing to perks of Patch %s ... Times tried: %d." %(matchId, i, perk_recapture, perkPatch_adopted, i, matchId, perkPatch_adopted, perk_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perks.json" %(perkPatch_adopted, language_cdragon[locale]), session, log)
                        perk: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        perkPatch_deserted: str = perkPatch_adopted
                        perkPatch_adopted = FindPostPatch(Patch(perkPatch_adopted), versionList)
                        perk_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkPatch_deserted, perk_recapture, perkPatch_adopted, perkPatch_deserted, perkPatch_adopted, perk_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if perk_recapture < 3:
                            perk_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的基石符文信息……\nYour network environment is abnormal! Changing to perks of Patch %s ... Times tried: %d." %(perk_recapture, perkPatch_adopted, perkPatch_adopted, perk_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的基石符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perk (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的基石符文信息。\nPerk information changed to Patch %s." %(perkPatch_adopted, perkPatch_adopted), verbose = verbose)
                        perks = {int(perk_iter["id"]): perk_iter for perk_iter in perk}
                        current_versions["perk"] = perkPatch_adopted
                        unmapped_keys["perk"].clear()
                        break
                break
        ##符文系（Perkstyles）
        perkstyleIds_match_list: list[int] = sorted(list(set(map(lambda x: x["stats"]["perkPrimaryStyle"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["perkSubStyle"], LoLGame_info["participants"]))))
        for i in perkstyleIds_match_list:
            if not i in perkstyles and current_versions["perkstyle"] != bigVersion and i != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                perkstylePatch_adopted: str = bigVersion
                perkstyle_recapture = 1
                logPrint("对局%d符文系信息（%d）获取失败！正在第%d次尝试改用%s版本的符文系信息……\nPerkstyle information (%d) of Match %d capture failed! Changing to perkstyles of Patch %s ... Times tried: %d." %(matchId, i, perkstyle_recapture, perkstylePatch_adopted, i, matchId, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perkstyles.json" %(perkstylePatch_adopted, language_cdragon[locale]), session, log)
                        perkstyle: dict[str, Any] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        perkstylePatch_deserted: str = perkstylePatch_adopted
                        perkstylePatch_adopted = FindPostPatch(Patch(perkstylePatch_adopted), versionList)
                        perkstyle_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkstylePatch_deserted, perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_deserted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if perkstyle_recapture < 3:
                            perkstyle_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的符文系信息……\nYour network environment is abnormal! Changing to perkstyles of Patch %s ... Times tried: %d." %(perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的符文系信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perkstyle (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的符文系信息。\nPerkstyle information changed to Patch %s." %(perkstylePatch_adopted, perkstylePatch_adopted), verbose = verbose)
                        perkstyles = {int(perkstyle_iter["id"]): perkstyle_iter for perkstyle_iter in perkstyle["styles"]}
                        current_versions["perkstyle"] = perkstylePatch_adopted
                        unmapped_keys["perkstyle"].clear()
                        break
                break
        ##斗魂竞技场强化符文（Cherry augments）
        CherryAugmentIds_match_list: list[int] = sorted(set(augment for s in [set(map(lambda x: x["stats"]["playerAugment" + str(i)], LoLGame_info["participants"])) for i in range(1, 7)] for augment in s)) #该表达式等价于以下表达式（This expression is equivalent to the following expression）：CherryAugmentIds_match_list = sorted(list(set(map(lambda x: x["stats"]["playerAugment1"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment2"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment3"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment4"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment5"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment6"], LoLGame_info["participants"]))))
        for i in CherryAugmentIds_match_list:
            if not i in CherryAugments and current_versions["CherryAugment"] != bigVersion and i != 0:
                CherryAugmentPatch_adopted: str = bigVersion
                CherryAugment_recapture: int = 1
                logPrint("对局%d强化符文信息（%d）获取失败！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nAugment information (%d) of Match %d capture failed! Changing to Cherry augments of Patch %s ... Times tried: %d." %(matchId, i, CherryAugment_recapture, CherryAugmentPatch_adopted, i, matchId, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/cherry-augments.json" %(CherryAugmentPatch_adopted, language_cdragon[locale]), session, log)
                        CherryAugment: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        CherryAugmentPatch_deserted: str = CherryAugmentPatch_adopted
                        CherryAugmentPatch_adopted = FindPostPatch(Patch(CherryAugmentPatch_adopted), versionList)
                        CherryAugment_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugmentPatch_deserted, CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_deserted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if CherryAugment_recapture < 3:
                            CherryAugment_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nYour network environment is abnormal! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the Cherry augment (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的斗魂竞技场强化符文信息。\nCherry augment information changed to Patch %s." %(CherryAugmentPatch_adopted, CherryAugmentPatch_adopted), verbose = verbose)
                        CherryAugments = {int(CherryAugment_iter["id"]): CherryAugment_iter for CherryAugment_iter in CherryAugment}
                        current_versions["CherryAugment"] = CherryAugmentPatch_adopted
                        unmapped_keys["CherryAugment"].clear()
                        break
                break
    #下面开始整理数据（Sorts out the data）
    for i in range(len(LoLGame_info_header)): #考虑到i按照代码中LoLGame_info_header的键的顺序遍历字典，可以将中间同一级别的属性按照相同方法输出。于是有了接下来的一些判断语句（Considering variable i traverses the dictionary following the order of LoLGame_info_header's keys, attributes under the same level can be output in the same manner. That's why there're several If-statements in the following code）
        key: str = LoLGame_info_header_keys[i]
        LoLGame_info_data[key] = [] #各项目初始化（Initialize every feature / column）
    for i in range(len(LoLGame_info["participantIdentities"])): #对于对局信息而言，每个玩家对应一条记录（For match information, each record represents a player）
        generate_LoLGameInfo_records(LoLGame_info_data, LoLGame_info, i, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments, gameIndex = gameIndex, current_puuid = puuidList, bans = bans, legacy_banData_appended = legacy_banData_appended, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, log = log, verbose = verbose)
        if sortStats and LoLGame_info["participantIdentities"][i]["player"]["puuid"] in puuidList: #这个if语句块是适配查战绩脚本而做的修改（This if-block is a modification made to adapt to Customized Program 05）
            for j in range(len(LoLGame_info_header_keys)):
                key = LoLGame_info_header_keys[j]
                LoLGame_stat_data[key].append(LoLGame_info_data[key][-1]) #直接添加最近一次追加的数据，以简化代码（Directly append the recently appended data to simplify the code）
    #数据框列排序（Dataframe column sorting）
    LoLGame_info_statistics_output_order: list[int] = [42, 211, 16, 228, 26, 20, 27, 25, 24, 22, 19, 31, 35, 36, 223, 224, 226, 227, 45, 38, 39, 157, 158, 159, 160, 161, 162, 163, 212, 193, 205, 194, 206, 195, 207, 196, 208, 197, 209, 198, 210, 72, 50, 43, 215, 216, 219, 220, 46, 142, 143, 74, 71, 75, 54, 53, 58, 57, 56, 55, 51, 146, 131, 84, 151, 136, 144, 138, 112, 78, 148, 137, 111, 77, 147, 73, 48, 47, 140, 145, 139, 113, 79, 149, 49, 152, 155, 154, 133, 153, 61, 217, 62, 218, 141, 80, 82, 81, 150, 63, 76, 189, 191, 177, 171, 178, 172, 179, 173, 180, 174, 181, 175, 182, 176, 44, 52, 135, 59, 60, 221, 134, 240, 234, 229, 287, 230, 274, 242, 239, 243, 235, 277, 266, 252, 282, 268, 275, 270, 254, 246, 279, 269, 253, 245, 278, 241, 232, 231, 272, 276, 271, 255, 247, 280, 233, 283, 286, 285, 267, 284, 236, 237, 273, 248, 250, 249, 288, 281, 238, 244, 290, 301, 295, 289, 348, 349, 351, 291, 335, 303, 300, 304, 296, 338, 327, 313, 343, 329, 336, 331, 315, 307, 340, 330, 314, 306, 339, 302, 293, 292, 333, 337, 332, 316, 308, 341, 294, 344, 347, 346, 328, 345, 297, 298, 352, 334, 309, 310, 311, 350, 342, 299, 305]
    LoLGame_info_data_organized: dict[str, list[Any]] = {}
    for i in LoLGame_info_statistics_output_order:
        key: str = LoLGame_info_header_keys[i]
        LoLGame_info_data_organized[key] = LoLGame_info_data[key]
    LoLGame_info_df: pandas.DataFrame = pandas.DataFrame(data = LoLGame_info_data_organized)
    for column in LoLGame_info_df:
        if LoLGame_info_df[column].dtype == "bool":
            LoLGame_info_df[column] = LoLGame_info_df[column].astype(str)
            LoLGame_info_df[column] = list(map(lambda x: "√" if x == "True" else "", LoLGame_info_df[column].to_list()))
    LoLGame_info_df = pandas.concat([pandas.DataFrame([LoLGame_info_header])[LoLGame_info_df.columns], LoLGame_info_df], ignore_index = True)
    return (LoLGame_info_df, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments)

async def sort_LoLGame_stats(connection: Connection, LoLMatchIDs: list[int], queues: dict[int, dict[str, Any]], summonerIcons: dict[int, dict[str, Any]], LoLChampions: dict[int, dict[str, Any]], spells: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], perks: dict[int, dict[str, Any]], perkstyles: dict[int, dict[str, Any]], CherryAugments: dict[int, dict[str, Any]], puuid: str | list[str] = "", excluded_reserve: bool = False, save_self: bool = True, save_other: bool = False, save_bot: bool = False, useAllVersions: bool = True, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, log: LogManager | None = None, verbose: bool = True) -> pandas.DataFrame: #和sort_LoLGame_info函数不同的是，该函数从对局序号得到玩家战绩数据框，而sort_LoLGame_info函数是伴随着对局信息数据框的形成而形成的（The difference of this function from `sort_LoLGame_info` is that this function returns the player stats dataframe based on matchIds, while this dataframe is formed along the formation of matgch information dataframe in `sort_LoLGame_info`）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [puuid] if isinstance(puuid, str) else puuid
    current_versions: dict[str, str] = {"queue": "", "summonerIcon": "", "spell": "", "LoLChampion": "", "LoLItem": "", "summonerIcon": "", "perk": "", "perkstyle": "", "CherryAugment": ""}
    unmapped_keys: dict[str, set[int]] = {"queue": set(), "summonerIcon": set(), "spell": set(), "LoLChampion": set(), "LoLItem": set(), "summonerIcon": set(), "perk": set(), "perkstyle": set(), "CherryAugment": set()}
    error_LoLMatchIDs: list[int] = [] #记录实际存在但未如期获取的对局序号（Records the LoL matches that really exist but fail to be fetched）
    matches_to_remove: list[int] = [] #记录获取成功但不包含主玩家的对局序号（Records the matches that are fetched successfully but don't contain the main player）
    #开始获取各对局内的玩家信息。数据结构参考/lol-match-history/v1/recently-played-summoners（Begin to capture the players' information in each match. The data structure refers to "/lol-match-history/v1/recently-played-summoners"）
    LoLGame_info_header_keys: list[str] = list(LoLGame_info_header.keys())
    LoLGame_stat_data: dict[str, list[Any]] = {}
    for i in range(len(LoLGame_info_header_keys)):
        key: str = LoLGame_info_header_keys[i]
        LoLGame_stat_data[key] = []
    for matchId in LoLMatchIDs:
        status, LoLGame_info = await get_LoLGame_info(connection, matchId, log = log)
        
        if "errorCode" in LoLGame_info:
            logPrint(LoLGame_info, verbose = verbose)
            error_LoLMatchIDs.append(matchId)
        else:
            version: str = LoLGame_info["gameVersion"]
            bigVersion: str = ".".join(version.split(".")[:2])
            #整理对局禁用信息（Sort out the team ban information）
            bans_team100: list[dict[str, int]] = LoLGame_info["teams"][0]["bans"]
            try:
                bans_team200: list[dict[str, int]] = LoLGame_info["teams"][1]["bans"]
            except IndexError:
                bans: list[dict[str, int]] = bans_team100 #空对局也会进入历史记录。空对局定义为完成选英雄但是无法正常进入游戏，而后游戏不存在的对局。而训练模式的空对局只有一方，因此LoLGame_info["teams"]中只有一个元素（Empty matches are included in the match history. An empty match is defined as the matches which can't be launched after the ChmpSlct period. Since an empty match of Practice Tool has only one team, there's only 1 element in LoLGame_info["teams"]）
            else:
                bans = bans_team100 + bans_team200
            if LoLGame_info["gameMode"] == "CHERRY" and Patch("14.8") < Patch(version):
                bans_tmp: list[dict[str, int]] = bans[:]
                bans = []
                emptyBan: dict[str, int] = {"championId": -1, "pickTurn": 0} #定义一个初始化禁用字典，用于后续数据框填充空值（Define an initialized banning dictionary so that empty values are appended to the dataframe at certain times subsequently）
                playerSubteam: dict[int, list[int]] = {} #存储不同子阵营的玩家，键是子阵营序号，值是该子阵营中的玩家的API序号列表（Stores different subteams' players. Keys are playerSubteamIds, and values are index lists from API for players in the subteams）
                for i in range(len(LoLGame_info["participants"])):
                    bans.append(emptyBan.copy())
                    playerSubteamId: int = LoLGame_info["participants"][i]["stats"]["playerSubteamId"]
                    if not playerSubteamId in playerSubteam:
                        playerSubteam[playerSubteamId] = []
                    playerSubteam[playerSubteamId].append(i)
                if Patch("14.12") < Patch(version):
                    participantBanIds: list[int] = []
                    for i in sorted(playerSubteam.keys()):
                        participantBanIds += [playerSubteam[i][0], playerSubteam[i][1]] #这里默认采用某个子阵营在API中记录的第一名玩家作为该子阵营的先选者。这可能与实际选用顺序有出入（Here the first player of a subteam recorded in API is considered as the player that picks a champion first. This player may not be the real first player.）
                else:
                    participantBanIds = [playerSubteam[i][0] for i in sorted(playerSubteam.keys())] #这里默认采用某个子阵营在API中记录的第一名玩家作为禁用英雄的玩家。这可能与实际禁用英雄的玩家有出入（Here the first player of a subteam recorded in API is considered as the player that banned some champion. This player may not be the real player that banned it）
                for i in range(len(participantBanIds)):
                    bans[participantBanIds[i]] = bans_tmp[i]
            legacy_banData_appended: dict[int, bool] = {100: False, 200: False} #自定义对局中的征召模式是由每个阵营的1号选手禁用3个英雄，所以当禁用信息添加到一个阵营的第一名玩家后，后续玩家不需要再添加禁用信息。这个字典就是用来判断这一点的（Draft mode in custom matches is performed by the first player of each team banning 3 champions, so if the ban information is added into the first player, the subsequent player in the same team doesn't need to add this information. That's what this dictionary is used for）
            if excluded_reserve or len(set(puuidList) & set(map(lambda x: x["player"]["puuid"], LoLGame_info["participantIdentities"]))) != 0: #之所以使用玩家通用唯一识别码，而不是用召唤师名称来识别对局是否包含主玩家，是因为该玩家可能使用过改名卡。这里也没有选择帐户序号，这是因为保存在对局中的各玩家的帐户序号竟然是0！（The reason why the puuid instead of the displayName or summonerName is used to identify whether the matches contain the main player is that the player may have used name changing card. AccountId isn't chosen here, because all players' accountIds saved in the match fetched from 127 API is 0, to my surprise!）
                if useAllVersions:
                    #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
                    ##游戏模式（Game mode）
                    queueIds_match_list: list[int] = [LoLGame_info["queueId"]]
                    for i in queueIds_match_list:
                        if not i in queues and current_versions["queue"] != bigVersion:
                            queuePatch_adopted = bigVersion
                            queue_recapture = 1
                            logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, queue_recapture, queuePatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, queuePatch_adopted, queue_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                                    queue: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    queuePatch_deserted: str = queuePatch_adopted
                                    queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                                    queue_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if queue_recapture < 3:
                                        queue_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game mode (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                                    queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                                    current_versions["queue"] = queuePatch_adopted
                                    unmapped_keys["queue"].clear()
                                    break
                            break
                    ##召唤师图标（Summoner icon）
                    summonerIconIds_match_list: list[int] = sorted(set(map(lambda x: x["player"]["profileIcon"], LoLGame_info["participantIdentities"])))
                    for i in summonerIconIds_match_list:
                        if not i in summonerIcons and current_versions["summonerIcon"] != bigVersion:
                            summonerIconPatch_adopted: str = bigVersion
                            summonerIcon_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）召唤师图标信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师图标信息……\nSummoner icon information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to summoner icons of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, summonerIcon_recapture, summonerIconPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-icons.json" %(summonerIconPatch_adopted, language_cdragon[locale]), session, log)
                                    summonerIcon: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    summonerIconPatch_deserted: str = summonerIconPatch_adopted
                                    summonerIconPatch_adopted = FindPostPatch(Patch(summonerIconPatch_adopted), versionList)
                                    summonerIcon_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(summonerIconPatch_deserted, summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_deserted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if summonerIcon_recapture < 3:
                                        summonerIcon_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师图标信息……\nYour network environment is abnormal! Changing to summoner icons of Patch %s ... Times tried: %d." %(summonerIcon_recapture, summonerIconPatch_adopted, summonerIconPatch_adopted, summonerIcon_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师图标信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the summoner icon (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的召唤师图标信息。\nSummoner icon information changed to Patch %s." %(summonerIconPatch_adopted, summonerIconPatch_adopted), verbose = verbose)
                                    summonerIcons = {int(summonerIcon_iter["id"]): summonerIcon_iter for summonerIcon_iter in summonerIcon}
                                    current_versions["summonerIcon"] = summonerIconPatch_adopted
                                    unmapped_keys["summonerIcon"].clear()
                                    break
                            break
                    ##英雄：包含选用英雄和禁用英雄（LoL champions, which contain picked and banned ones）
                    LoLChampionIds_match_list: list[int] = sorted(set(map(lambda x: x["championId"], LoLGame_info["participants"])) | set(map(lambda x: x["championId"], bans)))
                    for i in LoLChampionIds_match_list:
                        if not i in LoLChampions and current_versions["LoLChampion"] != bigVersion:
                            LoLChampionPatch_adopted: str = bigVersion
                            LoLChampion_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄信息……\nLoL champion information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, LoLChampion_recapture, LoLChampionPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/champion-summary.json" %(LoLChampionPatch_adopted, language_cdragon[locale]), session, log)
                                    LoLChampion: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    LoLChampionPatch_deserted: str = LoLChampionPatch_adopted
                                    LoLChampionPatch_adopted = FindPostPatch(Patch(LoLChampionPatch_adopted), versionList)
                                    LoLChampion_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampionPatch_deserted, LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_deserted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if LoLChampion_recapture < 3:
                                        LoLChampion_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄信息……\nYour network environment is abnormal! Changing to LoL champions of Patch %s ... Times tried: %d." %(LoLChampion_recapture, LoLChampionPatch_adopted, LoLChampionPatch_adopted, LoLChampion_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL champion (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的英雄信息。\nLoL champion information changed to Patch %s." %(LoLChampionPatch_adopted, LoLChampionPatch_adopted), verbose = verbose)
                                    LoLChampions = {int(LoLChampion_iter["id"]): LoLChampion_iter for LoLChampion_iter in LoLChampion}
                                    current_versions["LoLChampion"] = LoLChampionPatch_adopted
                                    unmapped_keys["LoLChampion"].clear()
                                    break
                            break
                    ##召唤师技能（Summoner spells）
                    spellIds_match_list: list[int] = sorted(set(map(lambda x: x["spell1Id"], LoLGame_info["participants"])) | set(map(lambda x: x["spell2Id"], LoLGame_info["participants"])))
                    for i in spellIds_match_list:
                        if not i in spells and current_versions["spell"] != bigVersion and i != 0: #需要注意电脑玩家的召唤师技能序号都是0（Note that Spell Ids of bot players are both 0s）
                            spellPatch_adopted: str = bigVersion
                            spell_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）召唤师技能信息（%d）获取失败！正在第%d次尝试改用%s版本的召唤师技能信息……\nSpell information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to spells of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, spell_recapture, spellPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, spellPatch_adopted, spell_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/summoner-spells.json" %(spellPatch_adopted, language_cdragon[locale]), session, log)
                                    spell: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    spellPatch_deserted: str = spellPatch_adopted
                                    spellPatch_adopted = FindPostPatch(Patch(spellPatch_adopted), versionList)
                                    spell_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to spells of Patch %s ... Times tried: %d." %(spellPatch_deserted, spell_recapture, spellPatch_adopted, spellPatch_deserted, spellPatch_adopted, spell_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if spell_recapture < 3:
                                        spell_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的召唤师技能信息……\nYour network environment is abnormal! Changing to spells of Patch %s ... Times tried: %d." %(spell_recapture, spellPatch_adopted, spellPatch_adopted, spell_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的召唤师技能信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the spell (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的召唤师技能信息。\nSpell information changed to Patch %s." %(spellPatch_adopted, spellPatch_adopted), verbose = verbose)
                                    spells = {int(spell_iter["id"]): spell_iter for spell_iter in spell}
                                    current_versions["spell"] = spellPatch_adopted
                                    unmapped_keys["spell"].clear()
                                    break
                            break
                    ##英雄联盟装备（LoL items）
                    LoLItemIds_match_list: list[int] = sorted(set(item for s in [set(map(lambda x: x["stats"].get(key, 0), LoLGame_info["participants"])) for key in ["item0", "item1", "item2", "item3", "item4", "item5", "item6", "roleBoundItem"]] for item in s)) #该表达式等价于以下表达式（This expression is equivalent to the following expression）：`LoLItemIds_match_list = sorted(set(map(lambda x: x["stats"]["item0"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item1"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item2"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item3"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item4"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item5"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["item6"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["roleBoundItem"], LoLGame_info["participants"])))`
                    for i in LoLItemIds_match_list:
                        if not i in LoLItems and current_versions["LoLItem"] != bigVersion and i != 0: #空装备序号是0（The itemId of an empty item is 0）
                            LoLItemPatch_adopted: str = bigVersion
                            LoLItem_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）英雄联盟装备信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nLoL item information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, LoLItem_recapture, LoLItemPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/items.json" %(LoLItemPatch_adopted, language_cdragon[locale]), session, log)
                                    LoLItem: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    LoLItemPatch_deserted: str = LoLItemPatch_adopted
                                    LoLItemPatch_adopted = FindPostPatch(Patch(LoLItemPatch_adopted), versionList)
                                    LoLItem_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItemPatch_deserted, LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_deserted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if LoLItem_recapture < 3:
                                        LoLItem_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nYour network environment is abnormal! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的英雄联盟装备信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL item (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的英雄联盟装备信息。\nLoL item information changed to Patch %s." %(LoLItemPatch_adopted, LoLItemPatch_adopted), verbose = verbose)
                                    LoLItems = {int(LoLItem_iter["id"]): LoLItem_iter for LoLItem_iter in LoLItem}
                                    current_versions["LoLItem"] = LoLItemPatch_adopted
                                    unmapped_keys["LoLItem"].clear()
                                    break
                            break
                    ##符文（Perks）
                    perkIds_match_list: list[int] = sorted(set(perk for s in [set(map(lambda x: x["stats"]["perk" + str(i)], LoLGame_info["participants"])) for i in range(6)] for perk in s))
                    for i in perkIds_match_list:
                        if not i in perks and current_versions["perk"] != bigVersion and i != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                            perkPatch_adopted: str = bigVersion
                            perk_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）基石符文信息（%d）获取失败！正在第%d次尝试改用%s版本的基石符文信息……\nPerk information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perks of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, perk_recapture, perkPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, perkPatch_adopted, perk_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perks.json" %(perkPatch_adopted, language_cdragon[locale]), session, log)
                                    perk: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    perkPatch_deserted = perkPatch_adopted
                                    perkPatch_adopted = FindPostPatch(Patch(perkPatch_adopted), versionList)
                                    perk_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkPatch_deserted, perk_recapture, perkPatch_adopted, perkPatch_deserted, perkPatch_adopted, perk_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if perk_recapture < 3:
                                        perk_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的基石符文信息……\nYour network environment is abnormal! Changing to perks of Patch %s ... Times tried: %d." %(perk_recapture, perkPatch_adopted, perkPatch_adopted, perk_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的基石符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perk (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的基石符文信息。\nPerk information changed to Patch %s." %(perkPatch_adopted, perkPatch_adopted), verbose = verbose)
                                    perks = {int(perk_iter["id"]): perk_iter for perk_iter in perk}
                                    current_versions["perk"] = perkPatch_adopted
                                    unmapped_keys["perk"].clear()
                                    break
                            break
                    ##符文系（Perkstyles）
                    perkstyleIds_match_list: list[int] = sorted(list(set(map(lambda x: x["stats"]["perkPrimaryStyle"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["perkSubStyle"], LoLGame_info["participants"]))))
                    for i in perkstyleIds_match_list:
                        if not i in perkstyles and current_versions["perkstyle"] != bigVersion and i != 0: #在一些非常规模式（如新手训练）的对局中，玩家可能没有携带任何符文（In matches with unconventional game mode (e.g. TUTORIAL), maybe the player doesn't take any runes）
                            perkstylePatch_adopted: str = bigVersion
                            perkstyle_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）符文系信息（%d）获取失败！正在第%d次尝试改用%s版本的符文系信息……\nPerkstyle information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to perkstyles of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, perkstyle_recapture, perkstylePatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/perkstyles.json" %(perkstylePatch_adopted, language_cdragon[locale]), session, log)
                                    perkstyle: dict[str, Any] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    perkstylePatch_deserted = perkstylePatch_adopted
                                    perkstylePatch_adopted = FindPostPatch(Patch(perkstylePatch_adopted), versionList)
                                    perkstyle_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to perks of Patch %s ... Times tried: %d." %(perkstylePatch_deserted, perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_deserted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if perkstyle_recapture < 3:
                                        perkstyle_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的符文系信息……\nYour network environment is abnormal! Changing to perkstyles of Patch %s ... Times tried: %d." %(perkstyle_recapture, perkstylePatch_adopted, perkstylePatch_adopted, perkstyle_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的符文系信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the perkstyle (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的符文系信息。\nPerkstyle information changed to Patch %s." %(perkstylePatch_adopted, perkstylePatch_adopted), verbose = verbose)
                                    perkstyles = {int(perkstyle_iter["id"]): perkstyle_iter for perkstyle_iter in perkstyle["styles"]}
                                    current_versions["perkstyle"] = perkstylePatch_adopted
                                    unmapped_keys["perkstyle"].clear()
                                    break
                            break
                    ##斗魂竞技场强化符文（Cherry augments）
                    CherryAugmentIds_match_list: list[int] = sorted(set(augment for s in [set(map(lambda x: x["stats"]["playerAugment" + str(i)], LoLGame_info["participants"])) for i in range(1, 7)] for augment in s)) #该表达式等价于以下表达式（This expression is equivalent to the following expression）：CherryAugmentIds_match_list = sorted(list(set(map(lambda x: x["stats"]["playerAugment1"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment2"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment3"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment4"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment5"], LoLGame_info["participants"])) | set(map(lambda x: x["stats"]["playerAugment6"], LoLGame_info["participants"]))))
                    for i in CherryAugmentIds_match_list:
                        if not i in CherryAugments and current_versions["CherryAugment"] != bigVersion and i != 0:
                            CherryAugmentPatch_adopted: str = bigVersion
                            CherryAugment_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%d）获取失败！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nAugment information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to Cherry augments of Patch %s ... Times tried: %d." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, CherryAugment_recapture, CherryAugmentPatch_adopted, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/cherry-augments.json" %(CherryAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                    CherryAugment: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    CherryAugmentPatch_deserted: str = CherryAugmentPatch_adopted
                                    CherryAugmentPatch_adopted = FindPostPatch(Patch(CherryAugmentPatch_adopted), versionList)
                                    CherryAugment_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugmentPatch_deserted, CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_deserted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if CherryAugment_recapture < 3:
                                        CherryAugment_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的斗魂竞技场强化符文信息……\nYour network environment is abnormal! Changing to Cherry augments of Patch %s ... Times tried: %d." %(CherryAugment_recapture, CherryAugmentPatch_adopted, CherryAugmentPatch_adopted, CherryAugment_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the Cherry augment (%s) of Match %d / %d (matchId: %d)!" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, i, i, LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的斗魂竞技场强化符文信息。\nCherry augment information changed to Patch %s." %(CherryAugmentPatch_adopted, CherryAugmentPatch_adopted), verbose = verbose)
                                    CherryAugments = {int(CherryAugment_iter["id"]): CherryAugment_iter for CherryAugment_iter in CherryAugment}
                                    current_versions["CherryAugment"] = CherryAugmentPatch_adopted
                                    unmapped_keys["CherryAugment"].clear()
                                    break
                            break
                #下面开始整理数据（Sorts out the data）
                for i in range(len(LoLGame_info["participants"])):
                    if not (not save_bot and LoLGame_info["participantIdentities"][i]["player"]["puuid"] == "00000000-0000-0000-0000-000000000000" or not save_self and LoLGame_info["participantIdentities"][i]["player"]["puuid"] in puuidList or not save_other and not LoLGame_info["participantIdentities"][i]["player"]["puuid"] in puuidList):
                        generate_LoLGameInfo_records(LoLGame_stat_data, LoLGame_info, i, queues, summonerIcons, LoLChampions, spells, LoLItems, perks, perkstyles, CherryAugments, gameIndex = LoLMatchIDs.index(matchId) + 1, current_puuid = puuidList, bans = bans, legacy_banData_appended = legacy_banData_appended, unmapped_keys = unmapped_keys, useAllVersions = True, log = log, verbose = verbose)
                if excluded_reserve:
                    logPrint("[%d/%d]对局%d不包含主玩家。已保留该对局。\nMatch %d doesn't contain the main player but is reserved." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, matchId), print_time = True, verbose = verbose)
                else:
                    logPrint("加载进度（Loading process）：%d/%d\t对局序号（MatchID）： %s" %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId), print_time = True, verbose = verbose)
            else:
                matches_to_remove.append(matchId)
                logPrint("[%d/%d]对局%d不包含主玩家。已移除该对局。\nMatch %d doesn't contain the main player and is deprecated." %(LoLMatchIDs.index(matchId) + 1, len(LoLMatchIDs), matchId, matchId), print_time = True, verbose = verbose)
    if len(error_LoLMatchIDs) > 0:
        logPrint("警告：以下%d场对局获取失败。\nWarning: The following %d match(es) fail to be fetched." %(len(error_LoLMatchIDs), len(error_LoLMatchIDs)), verbose = verbose)
        logPrint(error_LoLMatchIDs, verbose = verbose)
    if len(matches_to_remove) > 0:
        logPrint("注意：以下%d场对局因不包含主玩家而被移除。\nAttention: The following %d match(es) are removed because they don't contain the main player." %(len(matches_to_remove), len(matches_to_remove)), verbose = verbose)
        logPrint(matches_to_remove, verbose = verbose)
    LoLGame_stat_statistics_output_order: list[int] = [0, 16, 26, 20, 27, 25, 24, 31, 5, 3, 13, 4, 11, 6, 14, 10, 15, 9, 42, 211, 228, 35, 36, 223, 224, 226, 227, 45, 38, 39, 157, 158, 159, 160, 161, 162, 163, 212, 193, 205, 194, 206, 195, 207, 196, 208, 197, 209, 198, 210, 72, 50, 43, 214, 215, 216, 219, 220, 46, 142, 143, 74, 71, 75, 54, 53, 58, 57, 56, 55, 51, 146, 131, 84, 151, 136, 144, 138, 112, 78, 148, 137, 111, 77, 147, 73, 48, 47, 140, 145, 139, 113, 79, 149, 49, 152, 155, 154, 133, 153, 61, 217, 62, 218, 141, 80, 82, 81, 150, 63, 76, 189, 191, 177, 171, 178, 172, 179, 173, 180, 174, 181, 175, 182, 176, 44, 52, 135, 59, 60, 221, 134, 240, 234, 229, 287, 230, 274, 242, 239, 243, 235, 277, 266, 252, 282, 268, 275, 270, 254, 246, 279, 269, 253, 245, 278, 241, 232, 231, 272, 276, 271, 255, 247, 280, 233, 283, 286, 285, 267, 284, 236, 237, 273, 248, 250, 249, 288, 281, 238, 244, 290, 301, 295, 289, 348, 349, 351, 291, 335, 303, 300, 304, 296, 338, 327, 313, 343, 329, 336, 331, 315, 307, 340, 330, 314, 306, 339, 302, 293, 292, 333, 337, 332, 316, 308, 341, 294, 344, 347, 346, 328, 345, 297, 298, 352, 334, 309, 310, 311, 350, 342, 299, 305]
    LoLGame_stat_data_organized: dict[str, list[Any]] = {}
    for i in LoLGame_stat_statistics_output_order:
        key = LoLGame_info_header_keys[i]
        LoLGame_stat_data_organized[key] = LoLGame_stat_data[key]
    LoLGame_stat_df: pandas.DataFrame = pandas.DataFrame(data = LoLGame_stat_data_organized)
    logPrint("正在优化逻辑值显示……\nOptimizing the display of boolean values ...", verbose = verbose)
    for column in LoLGame_stat_df:
        if LoLGame_stat_df[column].dtype == "bool":
            LoLGame_stat_df[column] = LoLGame_stat_df[column].astype(str)
            LoLGame_stat_df[column] = list(map(lambda x: "√" if x == "True" else "", LoLGame_stat_df[column].to_list()))
    logPrint("逻辑值显示优化完成！\nBoolean value display optimization finished!", verbose = verbose)
    LoLGame_stat_df = pandas.concat([pandas.DataFrame([LoLGame_info_header])[LoLGame_stat_df.columns], LoLGame_stat_df], ignore_index = True)
    return LoLGame_stat_df

def sort_LoLGame_timeline(LoLGame_timeline: dict[str, Any], LoLGame_info: dict[str, Any], LoLChampions: dict[int, dict[str, Any]], LoLItems: dict[int, dict[str, Any]], useAllVersions: bool = False, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, pandas.DataFrame, dict[int, dict[str, Any]]]: #对局时间轴的整理依赖于对局信息（Sorting out match timeline relies on the match information）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    current_versions: dict[str, str] = {"LoLItem": ""}
    unmapped_keys: dict[str, set[int]] = {"LoLItem": set()}
    #准备LoLGame_info的相关变量（Prepare variables related to `LoLGame_info`）
    matchId: int = LoLGame_info["gameId"]
    player_count: int = len(LoLGame_info["participantIdentities"])
    version: str = LoLGame_info["gameVersion"]
    bigVersion: str = ".".join(version.split(".")[:2])
    #整理时间轴（Sort out timeline）
    LoLGame_timeline_header_keys: list[str] = list(LoLGame_timeline_header.keys())
    LoLGame_timeline_data: dict[str, list[Any]] = {}
    frames: list[dict[str, Any]] = LoLGame_timeline["frames"]
    for i in range(len(LoLGame_timeline_header)): #注意由于对局信息和对局时间轴是绑定在一起的，所以这里会用到构建LoLGame_info_df时的一些变量，包括player_count（Note that since the match information and match timeline are tied together, some variables during the creation of "LoLGame_info_df" will be reused in the following code, including player_count）
        key: str = LoLGame_timeline_header_keys[i]
        LoLGame_timeline_data[key] = []
        if i <= 2:
            if i == 2: #时间（`time`）
                for j in range(len(frames)):
                    LoLGame_timeline_data[key].append(lcuTimestamp(frames[j]["timestamp"] // 1000)) #使用lcuTimestamp函数将时间戳转化为时间（Use function lcuTimestamp to convert timestamp into time）
                    for k in range(player_count - 1):
                        LoLGame_timeline_data[key].append("") #考虑到每个时间戳和事件对应多个不同的玩家，只需要输出一次时间戳和事件，剩余部分为空，以保证表格对齐（Considering each timestamp and each event correspond to multiple participants, they only need to be output once, while the rest assigned by empty strings, so as to align the table）
            else:
                for j in range(len(frames)):
                    LoLGame_timeline_data[key].append(frames[j][key])
                    for k in range(player_count - 1):
                        LoLGame_timeline_data[key].append("")
        elif i == 3: #玩家序号（`participantID`）
            for j in range(len(frames)):
                for k in range(player_count):
                    LoLGame_timeline_data[key].append(k + 1)
        elif i <= 8:
            if i == 4: #阵营代号（`teamId`）
                for j in range(len(frames)):
                    for k in range(player_count):
                        LoLGame_timeline_data[key].append(LoLGame_info["participants"][k]["teamId"])
            elif i == 5: #阵营代号（`team_color`）
                for j in range(len(frames)):
                    for k in range(player_count):
                        LoLGame_timeline_data[key].append(team_colors_int[LoLGame_info["participants"][k]["teamId"]])
            elif i == 6: #召唤师名称（`summonerName`）
                for j in range(len(frames)):
                    for k in range(player_count):
                        player = LoLGame_info["participantIdentities"][k]["player"]
                        LoLGame_timeline_data[key].append(player["summonerName"] if player["gameName"] == "" and player["tagLine"] == "" else player["gameName"] + "#" + player["tagLine"])
            else: #选用英雄相关键（Champion-related keys）
                for j in range(len(frames)):
                    for k in range(player_count):
                        try:
                            LoLGame_timeline_data[key].append(LoLChampions[LoLGame_info["participants"][k]["championId"]][key.split("_")[1]])
                        except KeyError:
                            LoLGame_timeline_data[key].append("")
        else:
            if i == 14: #当前位置坐标（`position`）
                for j in range(len(frames)):
                    for k in range(player_count):
                        try:
                            position = frames[j]["participantFrames"][str(k + 1)][key]
                            LoLGame_timeline_data[key].append("(%d, %d)" %(position["x"], position["y"]))
                        except KeyError:
                            LoLGame_timeline_data[key].append("")
            else:
                for j in range(len(frames)):
                    for k in range(player_count):
                        try:
                            LoLGame_timeline_data[key].append(frames[j]["participantFrames"][str(k + 1)][key])
                        except KeyError: #部分自定义对局存在后续事件无内容的情况，即participantFrames为空（Some custom matches don't have anything in later events, namely the "participantFrames" parameter is empty. More details in PBE1-4422435386）
                            LoLGame_timeline_data[key].append("")
    LoLGame_timeline_statistics_output_order: list[int] = [1, 2, 0, 5, 3, 6, 7, 8, 12, 17, 14, 13, 11, 9, 16, 10, 15]
    LoLGame_timeline_data_organized: dict[str, list[Any]] = {}
    for i in LoLGame_timeline_statistics_output_order:
        key: str = LoLGame_timeline_header_keys[i]
        LoLGame_timeline_data_organized[key] = LoLGame_timeline_data[key]
    LoLGame_timeline_df: pandas.DataFrame = pandas.DataFrame(data = LoLGame_timeline_data_organized)
    LoLGame_timeline_df = pandas.concat([pandas.DataFrame([LoLGame_timeline_header])[LoLGame_timeline_df.columns], LoLGame_timeline_df], ignore_index = True)
    #整理事件（Sort out events）
    LoLGame_event_header_keys: list[str] = list(LoLGame_event_header.keys())
    LoLGame_event_data: dict[str, list[Any]] = {}
    events: dict[int, dict[str, Any]] = {}
    for frame in frames:
        for event in frame["events"]:
            events[event["timestamp"]] = event
    #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
    if useAllVersions:
        ##英雄联盟装备（LoL items）
        LoLItemIds_match_list: list[int] = sorted(set(map(lambda x: x["itemId"], events.values())))
        for i in LoLItemIds_match_list:
            if not i in LoLItems and current_versions["LoLItem"] != bigVersion and i != 0: #空装备序号是0（The itemId of an empty item is 0）
                LoLItemPatch_adopted: str = bigVersion
                LoLItem_recapture: int = 1
                logPrint("对局%d英雄联盟装备信息（%d）获取失败！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nLoL item information (%d) of Match %d capture failed! Changing to LoL items of Patch %s ... Times tried: %d." %(matchId, i, LoLItem_recapture, LoLItemPatch_adopted, i, matchId, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                while True:
                    try:
                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/items.json" %(LoLItemPatch_adopted, language_cdragon[locale]), session, log)
                        LoLItem: list[dict[str, Any]] = response.json()
                    except requests.exceptions.JSONDecodeError:
                        LoLItemPatch_deserted: str = LoLItemPatch_adopted
                        LoLItemPatch_adopted = FindPostPatch(Patch(LoLItemPatch_adopted), versionList)
                        LoLItem_recapture = 1
                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItemPatch_deserted, LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_deserted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                    except requests.exceptions.RequestException:
                        if LoLItem_recapture < 3:
                            LoLItem_recapture += 1
                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的英雄联盟装备信息……\nYour network environment is abnormal! Changing to LoL items of Patch %s ... Times tried: %d." %(LoLItem_recapture, LoLItemPatch_adopted, LoLItemPatch_adopted, LoLItem_recapture), verbose = verbose)
                        else:
                            logPrint("网络环境异常！对局%d的英雄联盟装备信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the LoL item (%s) of Match %d!" %(matchId, i, i, matchId), verbose = verbose)
                            break
                    else:
                        logPrint("已改用%s版本的英雄联盟装备信息。\nLoL item information changed to Patch %s." %(LoLItemPatch_adopted, LoLItemPatch_adopted), verbose = verbose)
                        LoLItems = {int(LoLItem_iter["id"]): LoLItem_iter for LoLItem_iter in LoLItem}
                        current_versions["LoLItem"] = LoLItemPatch_adopted
                        unmapped_keys["LoLItem"].clear()
                        break
                break
    for i in range(len(LoLGame_event_header)):
        key: str = LoLGame_event_header_keys[i]
        LoLGame_event_data[key] = []
    for timestamp in sorted(events.keys()):
        event: dict[str, Any] = events[timestamp]
        for i in range(len(LoLGame_event_header)):
            key = LoLGame_event_header_keys[i]
            if i <= 14:
                if i == 1: #被摧毁的建筑物类型（`buildingTypes`）
                    LoLGame_event_data[key].append(buildingTypes[event[key]])
                elif i == 4: #线路位置（`laneType`）
                    LoLGame_event_data[key].append(laneTypes[event[key]])
                elif i == 5: #野区生物亚型（`monsterSubType`）
                    LoLGame_event_data[key].append(monsterSubTypes[event[key]])
                elif i == 6: #野区生物类型（`monsterType`）
                    LoLGame_event_data[key].append(monsterTypes[event[key]])
                elif i == 8: #位置坐标（`position`）
                    LoLGame_event_data[key].append("(%s, %s)" %(event[key]["x"], event[key]["y"]))
                elif i == 12: #防御塔类型（`towerType`）
                    LoLGame_event_data[key].append(towerTypes[event[key]])
                elif i == 13:
                    LoLGame_event_data[key].append(eventTypes_lcu[event[key]])
                else:
                    LoLGame_event_data[key].append(event[key])
            else:
                if i <= 17: #助攻者相关键（Assistant-related keys）
                    if i == 15: #助攻者英雄（`assistingChampion`）
                        LoLGame_event_data[key].append(list(map(lambda x: x if x == 0 else LoLChampions[LoLGame_info["participants"][x - 1]["championId"]]["name"] if LoLGame_info["participants"][x - 1]["championId"] in LoLChampions else "", event["assistingParticipantIds"])))
                    elif i == 16: #助攻者英雄代号（`assistingChampionAlias`）
                        LoLGame_event_data[key].append(list(map(lambda x: "" if x == 0 else LoLChampions[LoLGame_info["participants"][x - 1]["championId"]]["alias"] if LoLGame_info["participants"][x - 1]["championId"] in LoLChampions else "", event["assistingParticipantIds"])))
                    else: #助攻者召唤师名（`assistingParticipantSummonerName`）
                        LoLGame_event_data[key].append(list(map(lambda x: "" if x == 0 else LoLGame_info["participantIdentities"][x - 1]["player"]["summonerName"] if LoLGame_info["participantIdentities"][x - 1]["player"]["gameName"] == "" and LoLGame_info["participantIdentities"][x - 1]["player"]["tagLine"] == "" else LoLGame_info["participantIdentities"][x - 1]["player"]["gameName"] + "#" + LoLGame_info["participantIdentities"][x - 1]["player"]["tagLine"], event["assistingParticipantIds"])))
                elif i == 18: #获得的装备（`item`）
                    itemId: int = event["itemId"]
                    if itemId == 0:
                        LoLGame_event_data[key].append("")
                    elif itemId in LoLItems:
                        LoLGame_event_data[key].append(LoLItems[itemId]["name"])
                    else:
                        if not itemId in unmapped_keys["LoLItem"]:
                            if useAllVersions:
                                unmapped_keys["LoLItem"].add(itemId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%d）获取失败！将采用原始数据！\n[%d. %s] LoL item information (%d) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, matchId, version, itemId, i, key, itemId, matchId, version), verbose = verbose)
                        LoLGame_event_data[key].append(itemId)
                elif i >= 19 and i <= 21: #击杀者相关键（Killer-related keys）
                    if event["killerId"] == 0:
                        LoLGame_event_data[key].append("")
                    else:
                        if i == 19: #击杀者英雄（`killerChampion`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["killerId"] - 1]["championId"]]["name"] if LoLGame_info["participants"][event["killerId"] - 1]["championId"] in LoLChampions else "")
                        elif i == 20: #击杀者英雄代号（`killerChampionAlias`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["killerId"] - 1]["championId"]]["alias"] if LoLGame_info["participants"][event["killerId"] - 1]["championId"] in LoLChampions else "")
                        else: #击杀者召唤师名（`killerParticipantSummonerName`）
                            killedParticipant = LoLGame_info["participantIdentities"][event["killerId"] - 1]["player"]
                            LoLGame_event_data[key].append(killedParticipant["summonerName"] if killedParticipant["gameName"] == "" and killedParticipant["tagLine"] == "" else killedParticipant["gameName"] + "#" + killedParticipant["tagLine"])
                elif i >= 22 and i <= 24: #参与者相关键（Participant-related keys）
                    if event["participantId"] == 0:
                        LoLGame_event_data[key].append("")
                    else:
                        if i == 22: #参与者英雄（`participantChampion`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["participantId"] - 1]["championId"]]["name"] if LoLGame_info["participants"][event["participantId"] - 1]["championId"] in LoLChampions else "")
                        elif i == 23: #参与者英雄代号（`participantChampionAlias`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["participantId"] - 1]["championId"]]["alias"] if LoLGame_info["participants"][event["participantId"] - 1]["championId"] in LoLChampions else "")
                        else: #参与者召唤师名（`participantSummonerName`）
                            participant = LoLGame_info["participantIdentities"][event["participantId"] - 1]["player"]
                            LoLGame_event_data[key].append(participant["summonerName"] if participant["gameName"] == "" and participant["tagLine"] == "" else participant["gameName"] + "#" + participant["tagLine"])
                elif i == 25: #阵营（`team_color`）
                    LoLGame_event_data[key].append(team_colors_int[event["teamId"]])
                elif i == 26: #时间（`time`）
                    LoLGame_event_data[key].append(lcuTimestamp(event["timestamp"] // 1000))
                else: #被杀者相关键（Victim-related keys）
                    if event["victimId"] == 0:
                        LoLGame_event_data[key].append("")
                    else:
                        if i == 27: #被杀者英雄（`victimChampion`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["victimId"] - 1]["championId"]]["name"] if LoLGame_info["participants"][event["victimId"] - 1]["championId"] in LoLChampions else "")
                        elif i == 28: #被杀者英雄代号（`victimChampionAlias`）
                            LoLGame_event_data[key].append(LoLChampions[LoLGame_info["participants"][event["victimId"] - 1]["championId"]]["alias"] if LoLGame_info["participants"][event["victimId"] - 1]["championId"] in LoLChampions else "")
                        else: #被杀者召唤师名（`victimParticipantSummonerName`）
                            victimParticipant = LoLGame_info["participantIdentities"][event["victimId"] - 1]["player"]
                            LoLGame_event_data[key].append(victimParticipant["summonerName"] if victimParticipant["gameName"] == "" and victimParticipant["tagLine"] == "" else victimParticipant["gameName"] + "#" + victimParticipant["tagLine"])
    LoLGame_event_statistics_output_order: list[int] = [11, 26, 8, 13, 3, 19, 20, 21, 14, 27, 28, 29, 0, 15, 16, 17, 6, 5, 25, 4, 1, 12]
    LoLGame_event_data_organized: dict[str, list[Any]] = {}
    for i in LoLGame_event_statistics_output_order:
        key: str = LoLGame_event_header_keys[i]
        LoLGame_event_data_organized[key] = LoLGame_event_data[key]
    LoLGame_event_df: pandas.DataFrame = pandas.DataFrame(data = LoLGame_event_data_organized)
    LoLGame_event_df = pandas.concat([pandas.DataFrame([LoLGame_event_header])[LoLGame_event_df.columns], LoLGame_event_df], ignore_index = True)
    return (LoLGame_timeline_df, LoLGame_event_df, LoLItems)

async def generate_TFTHistory_records(connection: Connection, TFTHistory_data: dict[str, list[Any]], TFTGame_info: dict[str, Any], participantIndex: int, queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], gameIndex: int = 1, unmapped_keys: dict[str, set[Any]] | None = None, useAllVersions: bool = False, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> dict[str, list[int | str]]:
    if unmapped_keys == None:
        unmapped_keys = {"queue": set(), "TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    if infos == None:
        infos = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    TFTHistory_header_keys: list[str] = list(TFTHistory_header.keys())
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*")
    TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
    if participantIndex == -1: #对局数据记录存在异常时的处理（Exception of match data recording exception）
        for i in range(len(TFTHistory_header)):
            key: str = TFTHistory_header_keys[i]
            if i == 0: #游戏序号（`gameIndex`）
                TFTHistory_data[key].append(gameIndex)
            elif i == 5: #对局序号（`game_id`）
                TFTHistory_data[key].append(TFTGame_info["metadata"]["match_id"].split("_")[1])
            elif i == 14: #对局创建时间（`gameCreationDate`）
                game_datetime = TFTGame_info["metadata"]["timestamp"]
                game_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(game_datetime // 1000))
                game_date_fraction = game_datetime / 1000 - game_datetime // 1000
                to_append = game_date + ("{0:.3}".format(game_date_fraction))[1:5]
                TFTHistory_data[key].append(to_append)
            elif i in {51, 304}:
                TFTHistory_data[key].append(False)
            else:
                TFTHistory_data[key].append("")
    else:
        TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
        TFTPlayer: dict[str, Any] = TFTHistoryJson["participants"][participantIndex]
        TFTPlayer_Traits: list[dict[str, Any]] = TFTPlayer["traits"]
        TFTPlayer_Units: list[dict[str, Any]] = TFTPlayer["units"]
        TFTPlayer_info_got: bool = False
        TFTPlayer_info_body: dict[str, Any] = {}
        if TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000": #在云顶之弈（新手教程）中，无法通过电脑玩家的玩家通用唯一识别码（00000000-0000-0000-0000-000000000000）来查询其召唤师名称和序号（Summoner names and IDs of bot players in TFT (Tutorial) can't be searched for according to their puuid: 00000000-0000-0000-0000-000000000000）
            if "riotIdGameName" in TFTPlayer and "riotIdTagline" in TFTPlayer:
                TFTPlayer_summonerName: str = "%s#%s" %(TFTPlayer["riotIdGameName"], TFTPlayer["riotIdTagline"])
            else:
                if useInfoDict and TFTPlayer["puuid"] in infos:
                    TFTPlayer_info_body = infos[TFTPlayer["puuid"]]
                    TFTPlayer_summonerName = get_info_name(TFTPlayer_info_body)
                    TFTPlayer_info_got = True
                else:
                    TFTPlayer_info_recapture = 0
                    TFTPlayer_info = await get_info(connection, TFTPlayer["puuid"])
                    while not TFTPlayer_info["info_got"] and TFTPlayer_info["body"]["httpStatus"] != 404 and TFTPlayer_info_recapture < 3:
                        logPrint(TFTPlayer_info["body"], verbose = verbose)
                        TFTPlayer_info_recapture += 1
                        logPrint("对局%d玩家信息（玩家通用唯一识别码：%s）获取失败！正在第%d次尝试重新获取该玩家信息……\nInformation of player (puuid: %s) in Match %d capture failed! Recapturing this player's information ... Times tried: %d." %(TFTHistoryJson["game_id"], TFTPlayer["puuid"], TFTPlayer_info_recapture, TFTPlayer["puuid"], TFTHistoryJson["game_id"], TFTPlayer_info_recapture), verbose = verbose)
                        TFTPlayer_info = await get_info(connection, TFTPlayer["puuid"])
                    if TFTPlayer_info["info_got"]:
                        TFTPlayer_info_body = TFTPlayer_info["body"]
                        if useInfoDict:
                            infos[TFTPlayer["puuid"]] = TFTPlayer_info_body
                        TFTPlayer_summonerName = get_info_name(TFTPlayer_info_body)
                    else:
                        logPrint(TFTPlayer_info["body"], verbose = verbose)
                        logPrint("对局%d玩家信息（玩家通用唯一识别码：%s）获取失败！\nInformation of player (puuid: %s) in Match %d capture failed!" %(TFTHistoryJson["game_id"], TFTPlayer["puuid"], TFTPlayer["puuid"], TFTHistoryJson["game_id"]), verbose = verbose)
                    TFTPlayer_info_got = TFTPlayer_info["info_got"]
        for i in range(len(TFTHistory_header)):
            key = TFTHistory_header_keys[i]
            if i == 0: #游戏序号（`gameIndex`）
                TFTHistory_data[key].append(gameIndex)
            elif i <= 18:
                if i == 1: #对局终止情况（`endOfGameResult`）
                    TFTHistory_data[key].append(endOfGameResults[TFTHistoryJson["endOfGameResult"]] if "endOfGameResult" in TFTHistoryJson else "")
                elif i in {2, 3, 8, 9}:
                    TFTHistory_data[key].append(TFTHistoryJson.get(key, "")) #14.6版本之前的云顶之弈对局信息中没有这些键（Those keys don't exist in information of TFT matches before Patch 14.6）
                elif i == 3: #对局序号（`gameId`）
                    TFTHistory_data[key].append(TFTHistoryJson.get("gameId", "")) #云顶之弈第10赛季及之前无gameId这一键（Before and including TFT Set10, there's not a "gameId" key）
                elif i == 7: #对局版本（`game_version`）
                    TFTHistory_data[key].append(TFTGameVersion)
                elif i == 12: #数据版本名称（`tft_set_core_name`）
                    TFTHistory_data[key].append(TFTHistoryJson.get("tft_set_core_name", "")) #在云顶之弈第7赛季之前，TFTHistoryJson中无tft_set_core_name这一键（Before TFTSet7, tft_set_core_name isn't present as a key of `TFTHistoryJson`）
                elif i == 14: #对局创建时间（`gameCreationDate`）
                    if "gameCreation" in TFTHistoryJson:
                        gameCreation: int = int(TFTHistoryJson["gameCreation"])
                        gameCreationDate: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(gameCreation // 1000))
                        gameCreationDate_fraction: float = gameCreation / 1000 - gameCreation // 1000
                        to_append: str | int = gameCreationDate + ("{0:.3}".format(gameCreationDate_fraction))[1:5]
                    else:
                        to_append = ""
                    TFTHistory_data[key].append(to_append)
                elif i == 15: #对局结算时间（`gameDate`）
                    game_datetime: int = int(TFTHistoryJson["game_datetime"])
                    game_date: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(game_datetime // 1000))
                    game_date_fraction: float = game_datetime / 1000 - game_datetime // 1000
                    to_append = game_date + ("{0:.3}".format(game_date_fraction))[1:5]
                    TFTHistory_data[key].append(to_append)
                elif i == 16: #持续时长（`gameLength`）
                    TFTHistory_data[key].append("%d:%02d" %(int(TFTHistoryJson["game_length"]) // 60, int(TFTHistoryJson["game_length"]) % 60))
                elif i == 17: #地图名称（`mapName`）
                    TFTHistory_data[key].append(gamemaps[TFTHistoryJson["mapId"]]["zh_CN"] if "mapId" in TFTHistoryJson else "")
                elif i == 18: #游戏模式名称（`gameModeName`）
                    TFTHistory_data[key].append(queues[TFTHistoryJson["queue_id"]]["description"] if TFTHistoryJson["queue_id"] in queues else "")
                else:
                    TFTHistory_data[key].append(TFTHistoryJson[key])
            elif i <= 54: #对于一些容易产生争议和报错的情况，引入to_append变量以简化代码。下同（Variable `to_append` is introduced to simplify the code in case of some controversy that produces errors easily. So does the following）
                if i == 19: #玩家序号（`participantId`）
                    TFTHistory_data[key].append(participantIndex + 1)
                elif i >= 20 and i <= 28: #强化符文相关键（Augment-related keys）
                    if "augments" in TFTPlayer:
                        augment_index: int = (i - 20) % 3
                        subkey_index: int = (i - 20) // 3
                        if augment_index < len(TFTPlayer["augments"]):
                            TFTAugmentId: str = TFTPlayer["augments"][augment_index]
                            if subkey_index == 0:
                                to_append = TFTAugmentId
                            elif TFTAugmentId in TFTAugments:
                                to_append = TFTAugments[TFTAugmentId][key.split()[-1]]
                            else:
                                if not TFTAugmentId in unmapped_keys["TFTAugment"]:
                                    if useAllVersions:
                                        unmapped_keys["TFTAugment"].add(TFTAugmentId)
                                    logPrint("【%d. %s】对局%d（对局版本：%s）强化符文信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT augment information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTAugmentId, i, key, TFTAugmentId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                                to_append = TFTAugmentId if subkey_index == 1 else ""
                        else:
                            to_append = ""
                    else:
                        to_append = "" #云顶之弈刚出的时候，没有强化符文的概念（The concept of "augment" didn't appear at the beginning of TFT）
                    TFTHistory_data[key].append(to_append)
                elif i >= 29 and i <= 35: #小小英雄相关键（Companion-related keys）
                    TFTCompanionId: str = TFTPlayer["companion"]["content_ID"]
                    if i <= 32:
                        to_append = TFTPlayer["companion"][key.split()[-1]]
                    elif TFTCompanionId in TFTCompanions:
                        to_append = TFTCompanions[TFTCompanionId][key.split()[-1]] if i <= 34 else rarities[TFTCompanions[TFTCompanionId][key.split()[-1]]]
                    else:
                        if not TFTCompanionId in unmapped_keys["TFTCompanion"]:
                            if useAllVersions:
                                unmapped_keys["TFTCompanion"].add(TFTCompanionId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）小小英雄信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT companion information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTCompanionId, i, key, TFTCompanionId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                        to_append = TFTCompanionId if i == 33 else ""
                    TFTHistory_data[key].append(to_append)
                elif i == 45: #通关人机对战（`pve_wonrun`）
                    to_append = "" if not "pve_wonrun" in TFTPlayer else "√" if TFTPlayer["pve_wonrun"] else "×"
                    TFTHistory_data[key].append(to_append)
                elif i == 46 or i == 47: #玩家昵称和昵称编号（`riotIdGameName` and `riotIdTagline`）
                    if key in TFTPlayer:
                        to_append = TFTPlayer[key]
                    else:
                        if TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000" and TFTPlayer_info_got:
                            to_append = TFTPlayer_info_body["gameName"] if i == 46 else TFTPlayer_info_body["tagLine"]
                        else:
                            to_append = ""
                    TFTHistory_data[key].append(to_append)
                elif i == 51: #胜利（`win`）
                    TFTHistory_data[key].append(TFTPlayer.get("win", False))
                elif i == 52: #存活回合（`last_round_format`）
                    lastRound: int = TFTPlayer["last_round"]
                    if lastRound <= 3:
                        bigRound: int = 1
                        smallRound: int = lastRound
                    else:
                        bigRound = (lastRound + 3) // 7 + 1
                        smallRound = (lastRound + 3) % 7 + 1
                    to_append = "%d-%d" %(bigRound, smallRound)
                    TFTHistory_data[key].append(to_append)
                elif i == 53: #存活时长（`time_eliminated_norm`）
                    to_append = "%d:%02d" %(int(TFTPlayer["time_eliminated"]) // 60, int(TFTPlayer["time_eliminated"]) % 60)
                    TFTHistory_data[key].append(to_append)
                elif i == 54: #结果（`result`）
                    to_append = "" if not "win" in TFTPlayer else "胜利" if TFTPlayer["win"] else "失败"
                    if "endOfGameResult" in TFTHistoryJson and TFTHistoryJson["endOfGameResult"] == "Abort_AntiCheatExit":
                        to_append = "被终止"
                    TFTHistory_data[key].append(to_append)
                else:
                    to_append = TFTPlayer.get(key, "")
                    TFTHistory_data[key].append(to_append)
            elif i <= 145: #云顶之弈羁绊相关键（TFT trait-related keys）
                trait_index: int = (i - 55) // 7
                subkey_index = (i - 55) % 7
                if trait_index < len(TFTPlayer_Traits): #在这个小于的问题上纠结了很久[敲打]——下标是从0开始的。假设API上记录了n个羁绊，那么当程序正在获取第n个羁绊时，就会引起下标越界的问题。所以这里不能使用小于等于号（I stuck at this less than sign for too long xD - note that the index begins from 0. Suppose there're totally n traits recorded in LCU API. Then, when the program is trying to capture the n-th trait, it'll throw an IndexError. That's why the "less than or equal to" sign can't be used here）
                    TFTTrait_iter: dict[str, Any] = TFTPlayer_Traits[trait_index]
                    TFTTraitId: str = TFTTrait_iter["name"]
                    if TFTTraitId == "TemplateTrait": #CommunityDragon数据库中没有收录模板羁绊的数据（Data about TemplateTrait aren't archived in CommunityDragon database）
                        if subkey_index == 4 and TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000": #在艾欧尼亚的对局序号为4959597974的对局中，存在一个模板羁绊，没有tier_total这个键（There exists a TemplateTrait without the key `tier_total` in an Ionia match with matchId 4959597974）
                            if "riotIdGameName" in TFTPlayer and "riotIdTagline" in TFTPlayer or TFTPlayer_info_got:
                                logPrint("警告：对局%d中玩家%s（玩家通用唯一识别码：%s）的第%d个羁绊是模板羁绊！\nWarning: Trait No. %d of the player %s (puuid: %s) in the match %d is TemplateTrait." %(TFTHistoryJson["game_id"], TFTPlayer_summonerName, TFTPlayer["puuid"], trait_index + 1, trait_index + 1, TFTPlayer_summonerName, TFTPlayer["puuid"], TFTHistoryJson["game_id"]), verbose = verbose)
                            to_append = ""
                        else:
                            to_append = TFTTraitId if subkey_index == 5 else "" if subkey_index == 6 else TFTTrait_iter[key.split()[-1]]
                    else:
                        if subkey_index <= 4:
                            if subkey_index == 2:
                                to_append = traitStyles[TFTTrait_iter[key.split()[-1]]]
                            else:
                                to_append = TFTTrait_iter[key.split()[-1]]
                        elif TFTTraitId in TFTTraits:
                            to_append = TFTTraits[TFTTraitId][key.split()[-1]]
                        else:
                            if not TFTTraitId in unmapped_keys["TFTTrait"]:
                                if useAllVersions:
                                    unmapped_keys["TFTTrait"].add(TFTTraitId)
                                logPrint("【%d. %s】对局%d（对局版本：%s）羁绊信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT trait information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTTraitId, i, key, TFTTraitId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                            to_append = TFTTraitId if subkey_index == 5 else ""
                else:
                    to_append = ""
                TFTHistory_data[key].append(to_append)
            elif i <= 299:
                if i <= 200: #云顶之弈英雄相关键（TFT champion-related keys）
                    unit_index: int = (i - 146) // 5
                    subkey_index = (i - 146) % 5
                    if unit_index < len(TFTPlayer_Units):
                        TFTChampion_iter: dict[str, Any] = TFTPlayer_Units[unit_index]
                        TFTChampionId: str = TFTChampion_iter["character_id"]
                        if subkey_index >= 3:
                            #character_id_lower: str = TFTPlayer_Units[unit_index]["character_id"].lower()
                            #TFTChampion_keys_lower: list[str] = list(map(lambda x: x.lower(), list(TFTChampions.keys())))
                            if TFTChampionId in TFTChampions:
                                to_append = TFTChampions[TFTChampionId][key.split()[-1]]
                            elif TFTChampionId.lower() in set(map(lambda x: x.lower(), TFTChampions.keys())): #在获取艾欧尼亚对局序号为8390690410的英雄信息时，由于雷克塞的英雄序号大小写的原因，会引发键异常（KeyError is caused due to the case of "RekSai" string when the program is getting data from an Ionia match with matchId 8390690410）
                                TFTChampion_index: int = list(map(lambda x: x.lower(), TFTChampions.keys())).index(TFTChampionId.lower())
                                to_append = list(TFTChampions.values())[TFTChampion_index][key.split()[-1]]
                            else:
                                if not TFTChampionId in unmapped_keys["TFTCompanion"]:
                                    if useAllVersions:
                                        unmapped_keys["TFTCompanion"].add(TFTChampionId)
                                    logPrint("【%d. %s】对局%d（对局版本：%s）棋子信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT champion information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTChampionId, i, key, TFTChampionId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                                to_append = TFTChampionId if subkey_index == 3 else ""
                        else:
                            to_append = TFTPlayer_Units[unit_index][key.split()[-1]]
                    else:
                        to_append = ""
                    TFTHistory_data[key].append(to_append)
                else:
                    unit_index = (i - 201) // 9
                    item_index: int = (i - 201) // 3 % 3
                    subkey_index = (i - 201) % 3
                    if unit_index < len(TFTPlayer_Units): #很少有英雄单位可以有3个装备（Merely do champion units have full items）
                        if "itemNames" in TFTPlayer_Units[unit_index] and item_index < len(TFTPlayer_Units[unit_index]["itemNames"]):
                            TFTItemId: str = TFTPlayer_Units[unit_index]["itemNames"][item_index]
                            if subkey_index == 0:
                                to_append = TFTItemId
                            elif TFTItemId in TFTItems:
                                to_append = TFTItems[TFTItemId][key.split()[-1]]
                            elif TFTItemId in TFTAugments: #云顶之弈基础数据文件中存在部分云顶之弈装备数据文件中没有的装备（Some items are present in the TFT basic data file but absent from the TFT item data file）
                                item_basic_dict: dict[str, str] = {"nameId": "apiName", "name": "name", "squareIconPath": "icon"} #云顶之弈装备数据文件和云顶之弈基础数据文件的格式不一致（The formats between TFT basic data and TFT item data are different）
                                to_append = TFTAugments[TFTItemId][item_basic_dict[key.split()[-1]]]
                            else:
                                if not TFTItemId in unmapped_keys["TFTItem"]:
                                    if useAllVersions:
                                        unmapped_keys["TFTItem"].add(TFTItemId)
                                    logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT item information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTItemId, i, key, TFTItemId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                                to_append = TFTItemId if subkey_index == 1 else ""
                        elif "items" in TFTPlayer_Units[unit_index] and item_index < len(TFTPlayer_Units[unit_index]["items"]): #在12.4版本之前，装备是通过序号而不是接口名称在LCU API中被存储的（Before Patch 12.4, items are stored via itemIDs instead of itemNames）
                            TFTItemId = TFTPlayer_Units[unit_index]["items"][item_index]
                            if subkey_index == 0:
                                to_append = TFTItemId
                            elif TFTItemId in TFTItems:
                                to_append = TFTItems[TFTItemId][key.split()[-1]]
                            elif TFTItemId in TFTAugments:
                                item_basic_dict = {"nameId": "apiName", "name": "name", "squareIconPath": "icon"}
                                to_append = TFTAugments[TFTItemId][item_basic_dict[key.split()[-1]]]
                            else:
                                if not TFTItemId in unmapped_keys["TFTItem"]:
                                    if useAllVersions:
                                        unmapped_keys["TFTItem"].add(TFTItemId)
                                    logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT item information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTGame_info["json"]["game_id"], TFTGameVersion, TFTItemId, i, key, TFTItemId, TFTGame_info["json"]["game_id"], TFTGameVersion), verbose = verbose)
                                to_append = TFTItemId if subkey_index == 1 else ""
                        else:
                            to_append = ""
                    else:
                        to_append = ""
                    TFTHistory_data[key].append(to_append)
            else:
                TFTHistory_data[key].append(TFTGame_info["metadata"][key])
    return TFTHistory_data

async def sort_TFTHistory(connection: Connection, TFTHistory: dict[str, Any], puuid: str, queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], useAllVersions: bool = False, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]: #云顶之弈对局记录包含全部信息，所以需要传入玩家通用唯一识别码来定位主召唤师（TFT match history contains all information, so puuid is needed to locate the main summoner）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if infos == None:
        infos = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    current_versions: dict[str, str] = {"TFTAugment": "", "TFTChampion": "", "TFTItem": "", "TFTCompanion": "", "TFTTrait": ""}
    unmapped_keys: dict[str, set[Any]] = {"TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    TFTHistoryList: list[dict[str, Any]] = TFTHistory["games"]
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*") #云顶之弈的对局版本信息是一串字符串，从中识别四位对局版本（TFT match version is a long string, from which the 4-number version is identified）
    TFT_main_player_indices: list[int] = [] #云顶之弈对局记录中记录了所有玩家的数据，但是在历史记录的工作表中只要显示主召唤师的数据，因此必须知道每场对局中主召唤师的索引（Each match in TFT history records all players' data, but only the main player's data are needed to display in the match history worksheet, so the index of the main player in each match is necessary）
    for game in TFTHistoryList:
        try:
            for i in range(len(game["json"]["participants"])):
                if game["json"]["participants"][i]["puuid"] == puuid:
                    TFT_main_player_indices.append(i)
                    break
            else: #在美测服的对局序号为4420772721的对局中，不存在Volibear  PBE6玩家。这是极少见的情况，如果没有此处的判断，一旦发生这种情况，就会引起下标越界的错误（Player "Volibear  PBE6" is absent from a PBE match with matchId 4420772721, which is quite rare. Nevertheless, once it happens, an IndexError that list index out of range will be definitely thrown）
                TFT_main_player_indices.append(-1)
        except TypeError: #在艾欧尼亚的对局序号为8346130449的对局中，不存在玩家。这可能是因为系统维护的原因，所有人未正常进入对局，但是对局确实创建了（There doesn't exist any player in an HN1 match with matchId 8346130499. This may be due to system mainteinance, which causes all players to fail to start the game, even if the match itself has been created）
            TFT_main_player_indices.append(-1) #当主玩家索引为-1时，表示本场对局存在异常（Main player index being -1 represents an abnormal match）
    TFTHistory_header_keys: list[str] = list(TFTHistory_header.keys())
    TFTHistory_data: dict[str, list[Any]] = {}
    for i in range(len(TFTHistory_header)): #云顶之弈对局信息各项目初始化（Initialize every feature / column of TFT match information）
        key: str = TFTHistory_header_keys[i]
        TFTHistory_data[key] = []
    for i in range(len(TFTHistoryList)): #由于不同对局意味着不同版本，不同版本的云顶之弈数据相差较大，所以为了使得一次获取的版本能够尽可能用到多个对局中，第一层迭代器应当是对局序号（Because different matches mean different patches, and TFT data differ greatly among different patches, to make a recently captured version of TFT data applicable in as more matches as possible, the first iterator should be the ID of the matches）
        TFTGame_info: dict[str, Any] = TFTHistoryList[i]
        TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
        participantIndex: int = TFT_main_player_indices[i]
        # if bool(TFTHistoryJson):
        #     for j in range(len(TFTHistoryJson["participants"])):
        #         if TFTHistoryJson["participants"][j]["puuid"] == puuid:
        #             participantIndex = j
        #             break
        #     else:
        #         participantIndex = -1
        # else:
        #     participantIndex = -1
        if participantIndex != -1:
            TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
            TFTGamePatch: str = ".".join(TFTGameVersion.split(".")[:2]) #由于需要通过这部分代码事先获取所有对局的版本，因此无论如何，这部分代码都要放在与从CommunityDragon重新获取云顶之弈数据相关的代码前面（Since game patches are captured here, by all means should this part of code be in front of the code relevant to regetting TFT data from CommunityDragon）
            TFTPlayer: dict[str, Any] = TFTHistoryJson["participants"][participantIndex]
            TFTPlayer_Traits: list[dict[str, Any]] = TFTPlayer["traits"]
            TFTPlayer_Units: list[dict[str, Any]] = TFTPlayer["units"]
            if useAllVersions:
                #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
                ##游戏模式（Game mode）
                queueIds_match_list: list[int] = [TFTHistoryJson["queue_id"]]
                for j in queueIds_match_list:
                    if not j in queues and current_versions["queue"] != TFTGamePatch:
                        queuePatch_adopted: str = TFTGamePatch
                        queue_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, queue_recapture, queuePatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], queuePatch_adopted, queue_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                                queue: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                queuePatch_deserted: str = queuePatch_adopted
                                queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                                queue_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if queue_recapture < 3:
                                    queue_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                                queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                                current_versions["queue"] = queuePatch_adopted
                                unmapped_keys["queue"].clear()
                                break
                        break
                ##云顶之弈强化符文（TFT augments）
                TFTAugmentIds_match_list: list[str] = sorted(set(TFTPlayer.get("augments", []))) #部分云顶之弈对局无强化符文（Some TFT matches don't contain augments）
                for j in TFTAugmentIds_match_list:
                    if not j in TFTAugments and current_versions["TFTAugment"] != TFTGamePatch:
                        TFTAugmentPatch_adopted: str = TFTGamePatch
                        TFTAugment_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nAugment information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT augments of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, TFTAugment_recapture, TFTAugmentPatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                TFT: dict[str, Any] = response.json()
                            except requests.exceptions.JSONDecodeError: #存在版本合并更新的情况（Situation like merged update exists）
                                TFTAugmentPatch_deserted: str = TFTAugmentPatch_adopted
                                TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                TFTAugment_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                            except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                if TFTAugment_recapture < 3:
                                    TFTAugment_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                unmapped_keys["TFTAugment"].clear()
                                break
                        break
                ##云顶之弈小小英雄（TFT companions）
                TFTCompanionIds_match_list: list[str] = [TFTPlayer["companion"]["content_ID"]]
                for j in TFTCompanionIds_match_list:
                    if not j in TFTCompanions and current_versions["TFTCompanion"] != TFTGamePatch:
                        TFTCompanionPatch_adopted: str = TFTGamePatch
                        TFTCompanion_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）小小英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的小小英雄信息……\nTFT companion information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT companions of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, TFTCompanion_recapture, TFTCompanionPatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/companions.json" %(TFTCompanionPatch_adopted, language_cdragon[locale]), session, log)
                                TFTCompanion: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTCompanionPatch_deserted: str = TFTCompanionPatch_adopted
                                TFTCompanionPatch_adopted = FindPostPatch(Patch(TFTCompanionPatch_adopted), versionList)
                                TFTCompanion_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTCompanionPatch_deserted, TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_deserted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTCompanion_recapture < 3:
                                    TFTCompanion_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的小小英雄信息……\nYour network environment is abnormal! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的小小英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the companion (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的小小英雄信息。\nTFT companion information changed to Patch %s." %(TFTCompanionPatch_adopted, TFTCompanionPatch_adopted), verbose = verbose)
                                TFTCompanions = {companion_iter["contentId"]: companion_iter for companion_iter in TFTCompanion}
                                current_versions["TFTCompanion"] = TFTCompanionPatch_adopted
                                unmapped_keys["TFTCompanion"].clear()
                                break
                        break
                ##云顶之弈羁绊（TFT Traits）
                TFTTraitIds_match_list: list[str] = sorted(set(map(lambda x: x["name"], TFTPlayer_Traits)))
                for j in TFTTraitIds_match_list:
                    if not j in TFTTraits and current_versions["TFTTrait"] != TFTGamePatch:
                        TFTTraitPatch_adopted: str = TFTGamePatch
                        TFTTrait_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）羁绊信息（%s）获取失败！正在第%d次尝试改用%s版本的羁绊信息……\nTFT trait information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT traits of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, TFTTrait_recapture, TFTTraitPatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tfttraits.json" %(TFTTraitPatch_adopted, language_cdragon[locale]), session, log)
                                TFTTrait: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTTraitPatch_deserted: str = TFTTraitPatch_adopted
                                TFTTraitPatch_adopted = FindPostPatch(Patch(TFTTraitPatch_adopted), versionList)
                                TFTTrait_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTraitPatch_deserted, TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_deserted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTTrait_recapture < 3:
                                    TFTTrait_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的羁绊信息……\nYour network environment is abnormal! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的羁绊信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the trait (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的羁绊信息。\nTFT trait information changed to Patch %s." %(TFTTraitPatch_adopted, TFTTraitPatch_adopted), verbose = verbose)
                                TFTTraits = {}
                                for trait_iter in TFTTrait:
                                    trait_id: str = trait_iter["trait_id"]
                                    conditional_trait_sets = {}
                                    if "conditional_trait_sets" in trait_iter: #在英雄联盟第13赛季之前，CommunityDragon数据库中记录的羁绊信息无conditional_trait_sets项（Before Season 13, `conditional_trait_sets` item is absent from tfttraits from CommunityDragon database）
                                        for conditional_trait_set in trait_iter["conditional_trait_sets"]:
                                            style_idx: str = conditional_trait_set["style_idx"]
                                            conditional_trait_sets[style_idx] = conditional_trait_set
                                    trait_iter["conditional_trait_sets"] = conditional_trait_sets
                                    TFTTraits[trait_id] = trait_iter
                                current_versions["TFTTrait"] = TFTTraitPatch_adopted
                                unmapped_keys["TFTTrait"].clear()
                                break
                        break
                ##云顶之弈英雄（TFT champions）
                TFTChampionIds_match_list: list[str] = sorted(set(map(lambda x: x["character_id"], TFTPlayer_Units)))
                for j in TFTChampionIds_match_list:
                    if not j in TFTChampions and not j.lower() in set(map(lambda x: x.lower(), TFTChampions.keys())) and current_versions["TFTChampion"] != TFTGamePatch:
                        TFTChampionPatch_adopted: str = TFTGamePatch
                        TFTChampion_recapture: int = 1
                        logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的棋子信息……\nTFT champion (%s) information of Match %d / %d (matchId: %d) capture failed! Changing to TFT champions of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, TFTChampion_recapture, TFTChampionPatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftchampions.json" %(TFTChampionPatch_adopted, language_cdragon[locale]), session, log)
                                TFTChampion: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTChampionPatch_deserted: str = TFTChampionPatch_adopted
                                TFTChampionPatch_adopted = FindPostPatch(Patch(TFTChampionPatch_adopted), versionList)
                                TFTChampion_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampionPatch_deserted, TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_deserted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTChampion_recapture < 3:
                                    TFTChampion_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的棋子信息……\nYour network environment is abnormal! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）将采用原始数据！\nNetwork error! The original data will be used for Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的棋子信息。\nTFT champion information changed to Patch %s." %(TFTChampionPatch_adopted, TFTChampionPatch_adopted), verbose = verbose)
                                TFTChampions = {}
                                if Patch(TFTChampionPatch_adopted) < Patch("13.17"): #从13.17版本开始，CommunityDragon数据库中关于云顶之弈棋子的数据格式发生微调（Since Patch 13.17, the format of TFT Champion data in CommunityDragon database has been modified）
                                    for TFTChampion_iter in TFTChampion:
                                        champion_name: str = TFTChampion_iter["character_id"]
                                        TFTChampions[champion_name] = TFTChampion_iter
                                else:
                                    for TFTChampion_iter in TFTChampion:
                                        champion_name = TFTChampion_iter["name"]
                                        TFTChampions[champion_name] = TFTChampion_iter["character_record"] #请注意该语句与4行之前的语句的差异，并看看一开始准备数据文件时使用的是哪一种——其实你应该猜的出来（Have you noticed the difference between this statement and the statement that is 4 lines above from this statement? Also, check which statement I chose for the beginning, when I prepared the data resources. Actually, you should be able to speculate it without referring to the code）
                                current_versions["TFTChampion"] = TFTChampionPatch_adopted
                                unmapped_keys["TFTChampion"].clear()
                                break
                        break
                ##云顶之弈装备（TFT items）
                s: set[str] = set()
                for unit in TFTPlayer_Units:
                    if "itemNames" in unit:
                        s |= set(unit["itemNames"])
                    elif "items" in unit:
                        s |= set(unit["items"])
                    else:
                        s |= set()
                TFTItemIds_match_list: list[str] = sorted(s)
                for j in TFTItemIds_match_list:
                    if not j in TFTItems and not j in TFTAugments:
                        if current_versions["TFTItem"] != TFTGamePatch:
                            TFTItemPatch_adopted: str = TFTGamePatch
                            TFTItem_recapture: int = 1
                            logPrint("第%d/%d场对局（对局序号：%d）装备信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nTFT item information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT items of Patch %s ... Times tried: %d." %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, TFTItem_recapture, TFTItemPatch_adopted, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftitems.json" %(TFTItemPatch_adopted, language_cdragon[locale]), session, log)
                                    TFTItem: list[dict[str, Any]] = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    TFTItemPatch_deserted: str = TFTItemPatch_adopted
                                    TFTItemPatch_adopted = FindPostPatch(Patch(TFTItemPatch_adopted), versionList)
                                    TFTItem_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItemPatch_deserted, TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_deserted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                except requests.exceptions.RequestException:
                                    if TFTItem_recapture < 3:
                                        TFTItem_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nYour network environment is abnormal! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的装备信息（%d）将采用原始数据！\nNetwork error! The original data will be used for the item (%d) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的云顶之弈装备信息。\nTFT item information changed to Patch %s." %(TFTItemPatch_adopted, TFTItemPatch_adopted), verbose = verbose)
                                    TFTItems = {TFTItem_iter["nameId"]: TFTItem_iter for TFTItem_iter in TFTItem}
                                    current_versions["TFTItem"] = TFTItemPatch_adopted
                                    unmapped_keys["TFTItem"].clear()
                                    break
                        #由于云顶之弈基础数据中也包含装备信息，这里将重新获取对局版本的云顶之弈基础数据（Because TFT basic data contain item data, here the program recaptures TFT basic data of the match version）
                        if current_versions["TFTAugment"] != TFTGamePatch:
                            TFTAugmentPatch_adopted = TFTGamePatch
                            TFTAugment_recapture = 1
                            while True:
                                try:
                                    response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                    TFT = response.json()
                                except requests.exceptions.JSONDecodeError:
                                    TFTAugmentPatch_deserted = TFTAugmentPatch_adopted
                                    TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                    TFTAugment_recapture = 1
                                    logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                    if TFTAugment_recapture < 3:
                                        TFTAugment_recapture += 1
                                        logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                    else:
                                        logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"], j, j, i + 1, len(TFTHistoryList), TFTHistoryJson["game_id"]), verbose = verbose)
                                        break
                                else:
                                    logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                    TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                    current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                    unmapped_keys["TFTAugment"].clear()
                                    break
                        break
        await generate_TFTHistory_records(connection, TFTHistory_data, TFTGame_info, participantIndex, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits, gameIndex = i + 1, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, useInfoDict = useInfoDict, infos = infos, log = log, verbose = verbose)
    TFTHistory_statistics_output_order: list[int] = [0, 46, 47, 5, 14, 15, 16, 6, 10, 18, 8, 17, 7, 13, 12, 11, 306, 304, 40, 33, 34, 35, 38, 52, 53, 49, 36, 50, 42, 54, 41, 39, 44, 45, 23, 24, 25, 149, 147, 148, 202, 205, 208, 154, 152, 153, 211, 214, 217, 159, 157, 158, 220, 223, 226, 164, 162, 163, 229, 232, 235, 169, 167, 168, 238, 241, 244, 174, 172, 173, 247, 250, 253, 179, 177, 178, 256, 259, 262, 184, 182, 183, 265, 268, 271, 189, 187, 188, 274, 277, 280, 194, 192, 193, 283, 286, 289, 199, 197, 198, 292, 295, 298, 60, 56, 57, 58, 59, 67, 63, 64, 65, 66, 74, 70, 71, 72, 73, 81, 77, 78, 79, 80, 88, 84, 85, 86, 87, 95, 91, 92, 93, 94, 102, 98, 99, 100, 101, 109, 105, 106, 107, 108, 116, 112, 113, 114, 115, 123, 119, 120, 121, 122, 130, 126, 127, 128, 129, 137, 133, 134, 135, 136, 144, 140, 141, 142, 143]
    TFTHistory_data_organized: dict[str, list[Any]] = {}
    for i in TFTHistory_statistics_output_order:
        key: str = TFTHistory_header_keys[i]
        TFTHistory_data_organized[key] = TFTHistory_data[key]
    TFTHistory_df: pandas.DataFrame = pandas.DataFrame(data = TFTHistory_data_organized)
    for column in TFTHistory_df:
        if TFTHistory_df[column].dtype == "bool":
            TFTHistory_df[column] = TFTHistory_df[column].astype(str)
            TFTHistory_df[column] = list(map(lambda x: "√" if x == "True" else "", TFTHistory_df[column].to_list()))
    TFTHistory_df = pandas.concat([pandas.DataFrame([TFTHistory_header])[TFTHistory_df.columns], TFTHistory_df], ignore_index = True)
    return (TFTHistory_df, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits)

async def generate_TFTGameInfo_records(connection: Connection, TFTGame_info_data: dict[str, list[Any]], TFTGame_info: dict[str, Any], participantIndex: int, queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], gameIndex: int = 1, current_puuid: str | list[str] = "", unmapped_keys: dict[str, set[Any]] | None = None, useAllVersions: bool = True, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> dict[str, list[Any]]: #这里传入的玩家通用唯一识别码参数仅用于辨别双人作战模式中的队友（Here the puuid parameter is only used to distinguish the ally from others in Double Up mode）
    if unmapped_keys == None:
        unmapped_keys = {"queue": set(), "TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    if infos == None:
        infos = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [current_puuid] if isinstance(current_puuid, str) else current_puuid
    TFTGame_info_header_keys: list[str] = list(TFTGame_info_header.keys())
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*")
    TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
    TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
    TFTPlayer: dict[str, Any] = TFTHistoryJson["participants"][participantIndex]
    TFTPlayer_Traits: list[dict[str, Any]] = TFTPlayer["traits"]
    TFTPlayer_Units: list[dict[str, Any]] = TFTPlayer["units"]
    current_participant_found: bool = False
    for participant in TFTHistoryJson["participants"]:
        for puuid in puuidList:
            if participant["puuid"] == puuid:
                current_participant: dict[str, Any] = participant
                current_participant_found = True
                break
        if current_participant_found:
            break
    TFTPlayer_info_got: bool = False
    TFTPlayer_info_body: dict[str, Any] = {}
    if TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000":
        if "riotIdGameName" in TFTPlayer and "riotIdTagline" in TFTPlayer:
            TFTPlayer_summonerName: str = "%s#%s" %(TFTPlayer["riotIdGameName"], TFTPlayer["riotIdTagline"])
        else:
            if useInfoDict and TFTPlayer["puuid"] in infos:
                TFTPlayer_info_body: dict[str, Any] = infos[TFTPlayer["puuid"]]
                TFTPlayer_summonerName = get_info_name(TFTPlayer_info_body)
                TFTPlayer_info_got = True
            else:
                TFTPlayer_info_recapture: int = 0
                TFTPlayer_info: dict[str, Any] = await get_info(connection, TFTPlayer["puuid"])
                while not TFTPlayer_info["info_got"] and TFTPlayer_info["body"]["httpStatus"] != 404 and TFTPlayer_info_recapture < 3:
                    logPrint(TFTPlayer_info["message"], verbose = verbose)
                    TFTPlayer_info_recapture += 1
                    logPrint("对局%d玩家信息（玩家通用唯一识别码：%s）获取失败！正在第%d次尝试重新获取该玩家信息……\nInformation of player (puuid: %s) in Match %d capture failed! Recapturing this player's information ... Times tried: %d." %(TFTHistoryJson["game_id"], TFTPlayer["puuid"], TFTPlayer_info_recapture, TFTPlayer["puuid"], TFTHistoryJson["game_id"], TFTPlayer_info_recapture), verbose = verbose)
                    TFTPlayer_info = await get_info(connection, TFTPlayer["puuid"])
                if TFTPlayer_info["info_got"]:
                    TFTPlayer_info_body = TFTPlayer_info["body"]
                    if useInfoDict:
                        infos[TFTPlayer["puuid"]] = TFTPlayer_info_body
                    TFTPlayer_summonerName = get_info_name(TFTPlayer_info_body)
                else:
                    logPrint(TFTPlayer_info["message"], verbose = verbose)
                    logPrint("对局%d玩家信息（玩家通用唯一识别码：%s）获取失败！\nInformation of player (puuid: %s) in Match %d capture failed!" %(TFTHistoryJson["game_id"], TFTPlayer["puuid"], TFTPlayer["puuid"], TFTHistoryJson["game_id"]), verbose = verbose)
                TFTPlayer_info_got = TFTPlayer_info["info_got"]
    for i in range(len(TFTGame_info_header)):
        key: str = TFTGame_info_header_keys[i]
        if i == 0: #游戏序号（`gameIndex`）
            TFTGame_info_data[key].append(gameIndex)
        elif i <= 18:
            if i == 1: #对局终止情况（`endOfGameResult`）
                TFTGame_info_data[key].append(endOfGameResults[TFTHistoryJson["endOfGameResult"]] if "endOfGameResult" in TFTHistoryJson else "")
            elif i in {2, 3, 8, 9}:
                TFTGame_info_data[key].append(TFTHistoryJson.get(key, "")) #14.6版本之前的云顶之弈对局信息中没有这些键（Those keys don't exist in information of TFT matches before Patch 14.6）
            elif i == 7: #对局版本（`game_version`）
                TFTGame_info_data[key].append(TFTGameVersion)
            elif i == 12: #数据版本名称（`tft_set_core_name`）
                TFTGame_info_data[key].append(TFTHistoryJson.get("tft_set_core_name", "")) #在云顶之弈第7赛季之前，TFTHistoryJson中无tft_set_core_name这一键（Before TFTSet7, tft_set_core_name isn't present as a key of `TFTHistoryJson`）
            elif i == 14: #对局创建时间（`gameCreationDate`）
                if "gameCreation" in TFTHistoryJson:
                    gameCreation = int(TFTHistoryJson["gameCreation"])
                    gameCreationDate = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(gameCreation // 1000))
                    gameCreationDate_fraction = gameCreation / 1000 - gameCreation // 1000
                    to_append: str | int = gameCreationDate + ("{0:.3}".format(gameCreationDate_fraction))[1:5]
                else:
                    to_append = ""
                TFTGame_info_data[key].append(to_append)
            elif i == 15: #对局结算时间（`gameDate`）
                game_datetime = int(TFTHistoryJson["game_datetime"])
                game_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(game_datetime // 1000))
                game_date_fraction = game_datetime / 1000 - game_datetime // 1000
                to_append = game_date + ("{0:.3}".format(game_date_fraction))[1:5]
                TFTGame_info_data[key].append(to_append)
            elif i == 16: #持续时长（`gameLength`）
                TFTGame_info_data[key].append("%d:%02d" %(int(TFTHistoryJson["game_length"]) // 60, int(TFTHistoryJson["game_length"]) % 60))
            elif i == 17: #地图名称（`mapName`）
                TFTGame_info_data[key].append(gamemaps[TFTHistoryJson["mapId"]]["zh_CN"] if "mapId" in TFTHistoryJson else "")
            elif i == 18: #游戏模式名称（`gameModeName`）
                TFTGame_info_data[key].append(queues[TFTHistoryJson["queue_id"]]["description"] if TFTHistoryJson["queue_id"] in queues else "")
            else:
                TFTGame_info_data[key].append(TFTHistoryJson[key])
        elif i <= 55:
            if i == 19: #玩家序号（`participantId`）
                TFTGame_info_data[key].append(participantIndex + 1)
            elif i >= 20 and i <= 28: #强化符文相关键（Augment-related keys）
                if "augments" in TFTPlayer:
                    augment_index: int = (i - 20) % 3
                    subkey_index: int = (i - 20) // 3
                    if augment_index < len(TFTPlayer["augments"]):
                        TFTAugmentId: str = TFTPlayer["augments"][augment_index]
                        if subkey_index == 0:
                            to_append = TFTAugmentId
                        elif TFTAugmentId in TFTAugments:
                            to_append = TFTAugments[TFTAugmentId][key.split()[-1]]
                        else:
                            if not TFTAugmentId in unmapped_keys["TFTAugment"]:
                                if useAllVersions:
                                    unmapped_keys["TFTAugment"].add(TFTAugmentId)
                                logPrint("【%d. %s】对局%d（对局版本：%s）强化符文信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT augment information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTAugmentId, i, key, TFTAugmentId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                            to_append = TFTAugmentId if subkey_index == 1 else ""
                    else:
                        to_append = ""
                else:
                    to_append = "" #云顶之弈刚出的时候，没有强化符文的概念（The concept of "augment" didn't appear at the beginning of TFT）
                TFTGame_info_data[key].append(to_append)
            elif i >= 29 and i <= 35: #小小英雄相关键（Companion-related keys）
                TFTCompanionId: str = TFTPlayer["companion"]["content_ID"]
                if i <= 32:
                    to_append = TFTPlayer["companion"][key.split()[-1]]
                elif TFTCompanionId in TFTCompanions:
                    to_append = TFTCompanions[TFTCompanionId][key.split()[-1]] if i <= 34 else rarities[TFTCompanions[TFTCompanionId][key.split()[-1]]]
                else:
                    if not TFTCompanionId in unmapped_keys["TFTCompanion"]:
                        if useAllVersions:
                            unmapped_keys["TFTCompanion"].add(TFTCompanionId)
                        logPrint("【%d. %s】对局%d（对局版本：%s）小小英雄信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT companion information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTCompanionId, i, key, TFTCompanionId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                    to_append = TFTCompanionId if i == 33 else ""
                TFTGame_info_data[key].append(to_append)
            elif i == 45: #通关人机对战（`pve_wonrun`）
                to_append = "" if not "pve_wonrun" in TFTPlayer else "√" if TFTPlayer["pve_wonrun"] else "×"
                TFTGame_info_data[key].append(to_append)
            elif i == 46 or i == 47: #玩家昵称和昵称编号（`riotIdGameName` and `riotIdTagline`）
                if key in TFTPlayer:
                    to_append = TFTPlayer[key]
                else:
                    if TFTPlayer["puuid"] in infos:
                        TFTPlayer_info_body = infos[TFTPlayer["puuid"]]
                        to_append = TFTPlayer_info_body["gameName"] if i == 46 else TFTPlayer_info_body["tagLine"]
                    else:
                        if TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000" and TFTPlayer_info_got:
                            to_append = TFTPlayer_info_body["gameName"] if i == 46 else TFTPlayer_info_body["tagLine"]
                        else:
                            to_append = ""
                TFTGame_info_data[key].append(to_append)
            elif i == 51: #胜利（`win`）
                TFTGame_info_data[key].append(TFTPlayer.get("win", False))
            elif i == 52: #存活回合（`last_round_format`）
                lastRound: int = TFTPlayer["last_round"]
                if lastRound <= 3:
                    bigRound: int = 1
                    smallRound: int = lastRound
                else:
                    bigRound = (lastRound + 3) // 7 + 1
                    smallRound = (lastRound + 3) % 7 + 1
                to_append = "%d-%d" %(bigRound, smallRound)
                TFTGame_info_data[key].append(to_append)
            elif i == 53: #存活时长（`time_eliminated_norm`）
                to_append = "%d:%02d" %(int(TFTPlayer["time_eliminated"]) // 60, int(TFTPlayer["time_eliminated"]) % 60)
                TFTGame_info_data[key].append(to_append)
            elif i == 54: #结果（`result`）
                to_append = "" if not "win" in TFTPlayer else "胜利" if TFTPlayer["win"] else "失败"
                if "endOfGameResult" in TFTHistoryJson and TFTHistoryJson["endOfGameResult"] == "Abort_AntiCheatExit":
                    to_append = "被终止"
                TFTGame_info_data[key].append(to_append)
            elif i == 55: #是否队友（`isAlly`）
                TFTGame_info_data[key].append(current_participant_found and "partner_group_id" in TFTPlayer and TFTPlayer["partner_group_id"] == current_participant["partner_group_id"])
            else:
                to_append = TFTPlayer.get(key, "")
                TFTGame_info_data[key].append(to_append)
        elif i <= 146: #云顶之弈羁绊相关键（TFT trait-related keys）
            trait_index: int = (i - 56) // 7
            subkey_index = (i - 56) % 7
            if trait_index < len(TFTPlayer_Traits): #在这个小于的问题上纠结了很久[敲打]——下标是从0开始的。假设API上记录了n个羁绊，那么当程序正在获取第n个羁绊时，就会引起下标越界的问题。所以这里不能使用小于等于号（I stuck at this less than sign for too long xD - note that the index begins from 0. Suppose there're totally n traits recorded in LCU API. Then, when the program is trying to capture the n-th trait, it'll throw an IndexError. That's why the "less than or equal to" sign can't be used here）
                TFTTrait_iter: dict[str, Any] = TFTPlayer_Traits[trait_index]
                TFTTraitId: str = TFTTrait_iter["name"]
                if TFTTraitId == "TemplateTrait": #CommunityDragon数据库中没有收录模板羁绊的数据（Data about TemplateTrait aren't archived in CommunityDragon database）
                    if subkey_index == 4 and TFTPlayer["puuid"] != "00000000-0000-0000-0000-000000000000": #在艾欧尼亚的对局序号为4959597974的对局中，存在一个模板羁绊，没有tier_total这个键（There exists a TemplateTrait without the key `tier_total` in an Ionia match with matchId 4959597974）
                        if "riotIdGameName" in TFTPlayer and "riotIdTagline" in TFTPlayer or TFTPlayer_info_got:
                            logPrint("警告：对局%d中玩家%s（玩家通用唯一识别码：%s）的第%d个羁绊是模板羁绊！\nWarning: Trait No. %d of the player %s (puuid: %s) in the match %d is TemplateTrait." %(TFTHistoryJson["game_id"], TFTPlayer_summonerName, TFTPlayer["puuid"], trait_index + 1, trait_index + 1, TFTPlayer_summonerName, TFTPlayer["puuid"], TFTHistoryJson["game_id"]), verbose = verbose)
                        to_append = ""
                    else:
                        to_append = TFTTraitId if subkey_index == 5 else "" if subkey_index == 6 else TFTTrait_iter[key.split()[-1]]
                else:
                    if subkey_index <= 4:
                        if subkey_index == 2:
                            to_append = traitStyles[TFTTrait_iter[key.split()[-1]]]
                        else:
                            to_append = TFTTrait_iter[key.split()[-1]]
                    elif TFTTraitId in TFTTraits:
                        to_append = TFTTraits[TFTTraitId][key.split()[-1]]
                    else:
                        if not TFTTraitId in unmapped_keys["TFTTrait"]:
                            if useAllVersions:
                                unmapped_keys["TFTTrait"].add(TFTTraitId)
                            logPrint("【%d. %s】对局%d（对局版本：%s）羁绊信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT trait information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTTraitId, i, key, TFTTraitId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                        to_append = TFTTraitId if subkey_index == 5 else ""
            else:
                to_append = ""
            TFTGame_info_data[key].append(to_append)
        elif i <= 300:
            if i <= 201: #云顶之弈英雄相关键（TFT champion-related keys）
                unit_index: int = (i - 147) // 5
                subkey_index = (i - 147) % 5
                if unit_index < len(TFTPlayer_Units):
                    TFTChampion_iter: dict[str, Any] = TFTPlayer_Units[unit_index]
                    TFTChampionId = TFTChampion_iter["character_id"]
                    if subkey_index >= 3:
                        #character_id_lower = TFTPlayer_Units[unit_index]["character_id"].lower()
                        #TFTChampion_keys_lower = list(map(lambda x: x.lower(), list(TFTChampions.keys())))
                        if TFTChampionId in TFTChampions:
                            to_append = TFTChampions[TFTChampionId][key.split()[-1]]
                        elif TFTChampionId.lower() in set(map(lambda x: x.lower(), TFTChampions.keys())): #在获取艾欧尼亚对局序号为8390690410的英雄信息时，由于雷克塞的英雄序号大小写的原因，会引发键异常（KeyError is caused due to the case of "RekSai" string when the program is getting data from an Ionia match with matchId 8390690410）
                            TFTChampion_index: int = list(map(lambda x: x.lower(), TFTChampions.keys())).index(TFTChampionId.lower())
                            to_append = list(TFTChampions.values())[TFTChampion_index][key.split()[-1]]
                        else:
                            if not TFTChampionId in unmapped_keys["TFTCompanion"]:
                                if useAllVersions:
                                    unmapped_keys["TFTCompanion"].add(TFTChampionId)
                                logPrint("【%d. %s】对局%d（对局版本：%s）棋子信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT champion information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTChampionId, i, key, TFTChampionId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                            to_append = TFTChampionId if subkey_index == 3 else ""
                    else:
                        to_append = TFTPlayer_Units[unit_index][key.split()[-1]]
                else:
                    to_append = ""
                TFTGame_info_data[key].append(to_append)
            else:
                unit_index = (i - 202) // 9
                item_index = (i - 202) // 3 % 3
                subkey_index = (i - 202) % 3
                if unit_index < len(TFTPlayer_Units): #很少有英雄单位可以有3个装备（Merely do champion units have full items）
                    if "itemNames" in TFTPlayer_Units[unit_index] and item_index < len(TFTPlayer_Units[unit_index]["itemNames"]):
                        TFTItemId = TFTPlayer_Units[unit_index]["itemNames"][item_index]
                        if subkey_index == 0:
                            to_append = TFTItemId
                        elif TFTItemId in TFTItems:
                            to_append = TFTItems[TFTItemId][key.split()[-1]]
                        elif TFTItemId in TFTAugments: #云顶之弈基础数据文件中存在部分云顶之弈装备数据文件中没有的装备（Some items are present in the TFT basic data file but absent from the TFT item data file）
                            item_basic_dict: dict[str, str] = {"nameId": "apiName", "name": "name", "squareIconPath": "icon"} #云顶之弈装备数据文件和云顶之弈基础数据文件的格式不一致（The formats between TFT basic data and TFT item data are different）
                            to_append = TFTAugments[TFTItemId][item_basic_dict[key.split()[-1]]]
                        else:
                            if not TFTItemId in unmapped_keys["TFTItem"]:
                                if useAllVersions:
                                    unmapped_keys["TFTItem"].add(TFTItemId)
                                logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT item information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTItemId, i, key, TFTItemId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                            to_append = TFTItemId if subkey_index == 1 else ""
                    elif "items" in TFTPlayer_Units[unit_index] and item_index < len(TFTPlayer_Units[unit_index]["items"]): #在12.4版本之前，装备是通过序号而不是接口名称在LCU API中被存储的（Before Patch 12.4, items are stored via itemIDs instead of itemNames）
                        TFTItemId = TFTPlayer_Units[unit_index]["items"][item_index]
                        if subkey_index == 0:
                            to_append = TFTItemId
                        elif TFTItemId in TFTItems:
                            to_append = TFTItems[TFTItemId][key.split()[-1]]
                        elif TFTItemId in TFTAugments:
                            item_basic_dict = {"nameId": "apiName", "name": "name", "squareIconPath": "icon"}
                            to_append = TFTAugments[TFTItemId][item_basic_dict[key.split()[-1]]]
                        else:
                            if not TFTItemId in unmapped_keys["TFTItem"]:
                                if useAllVersions:
                                    unmapped_keys["TFTItem"].add(TFTItemId)
                                logPrint("【%d. %s】对局%d（对局版本：%s）装备信息（%s）获取失败！将采用原始数据！\n[%d. %s] TFT item information (%s) of Match %d (gameVersion: %s) capture failed! The original data will be used for this match!" %(i, key, TFTHistoryJson["game_id"], TFTGameVersion, TFTItemId, i, key, TFTItemId, TFTHistoryJson["game_id"], TFTGameVersion), verbose = verbose)
                            to_append = TFTItemId if subkey_index == 1 else ""
                    else:
                        to_append = ""
                else:
                    to_append = ""
                TFTGame_info_data[key].append(to_append)
        else:
            TFTGame_info_data[key].append(TFTGame_info["metadata"][key])
    return TFTGame_info_data

async def sort_TFTGame_info(connection: Connection, TFTGame_info: dict[str, Any], queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], gameIndex: int = 1, current_puuid: str | list[str] = "", save_self: bool = True, useAllVersions: bool = True, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] | None = None, sortStats: bool = False, TFTGame_stat_data: dict[str, list[Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> tuple[pandas.DataFrame, dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]: #本函数体中涉及召唤师信息的获取，因此需要定义为协程（This function body involves getting summoner information, so this function is defined as an async function）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if infos == None:
        infos = {}
    if TFTGame_stat_data == None:
        TFTGame_stat_data = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [current_puuid] if isinstance(current_puuid, str) else current_puuid
    current_versions: dict[str, str] = {"TFTAugment": "", "TFTChampion": "", "TFTItem": "", "TFTCompanion": "", "TFTTrait": ""}
    unmapped_keys: dict[str, set[Any]] = {"TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*")
    TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
    TFTGame_info_header_keys: list[str] = list(TFTGame_info_header.keys())
    TFTGame_info_data: dict[str, list[Any]] = {} #云顶之弈没有独立的LCU API以供查询对局信息。这里将每场对局的与玩家有关的数据视为对局信息（There's not any available LCU API for TFT match information query. Here any information relevant to participants is regarded as TFT game information）
    for i in range(len(TFTGame_info_header_keys)):
        key: str = TFTGame_info_header_keys[i]
        TFTGame_info_data[key] = []
    if bool(TFTHistoryJson): #该条件等价于（This condition is equivalent to）：`TFT_main_player_indices[i] == -1`
        TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
        TFTGamePatch: str = ".".join(TFTGameVersion.split(".")[:2]) #由于需要通过这部分代码事先获取所有对局的版本，因此无论如何，这部分代码都要放在与从CommunityDragon重新获取云顶之弈数据相关的代码前面（Since game patches are captured here, by all means should this part of code be in front of the code relevant to regetting TFT data from CommunityDragon）
        #下面针对每场对局建立总的数据资源异常处理机制（Builds the summarized data resource exceptional handling mechanism for each match）
        if useAllVersions:
            ##游戏模式（Game mode）
            queueIds_match_list: list[int] = [TFTHistoryJson["queue_id"]]
            for i in queueIds_match_list:
                if not i in queues and current_versions["queue"] != TFTGamePatch:
                    queuePatch_adopted: str = TFTGamePatch
                    queue_recapture: int = 1
                    logPrint("对局%d游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, queue_recapture, queuePatch_adopted, i, TFTHistoryJson["game_id"], queuePatch_adopted, queue_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                            queue: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            queuePatch_deserted: str = queuePatch_adopted
                            queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                            queue_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if queue_recapture < 3:
                                queue_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！对局%d的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                            queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                            current_versions["queue"] = queuePatch_adopted
                            unmapped_keys["queue"].clear()
                            break
                    break
            ##云顶之弈强化符文（TFT augments）
            TFTAugmentIds_match_list: list[str] = sorted(set(augment for lst in list(map(lambda x: x["augments"] if "augments" in x else [], TFTHistoryJson["participants"])) for augment in lst)) #`if "augments" in x`的作用是防止早期云顶之弈对局无强化符文导致程序报错（`if "augments" in x` is used here because some early TFT matches don't contain augments and result in KeyErrors consequently）
            for i in TFTAugmentIds_match_list:
                if not i in TFTAugments and current_versions["TFTAugment"] != TFTGamePatch:
                    TFTAugmentPatch_adopted: str = TFTGamePatch
                    TFTAugment_recapture: int = 1
                    logPrint("对局%d强化符文信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nAugment information (%s) of Match %d capture failed! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, TFTAugment_recapture, TFTAugmentPatch_adopted, i, TFTHistoryJson["game_id"], TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                            TFT: dict[str, Any] = response.json()
                        except requests.exceptions.JSONDecodeError: #存在版本合并更新的情况（Situation like merged update exists）
                            TFTAugmentPatch_deserted: str = TFTAugmentPatch_adopted
                            TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                            TFTAugment_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                        except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                            if TFTAugment_recapture < 3:
                                TFTAugment_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！对局%d的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                            TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                            current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                            unmapped_keys["TFTAugment"].clear()
                            break
                    break
            ##云顶之弈小小英雄（TFT companions）
            TFTCompanionIds_match_list: list[str] = sorted(set(map(lambda x: x["companion"]["content_ID"], TFTHistoryJson["participants"])))
            for i in TFTCompanionIds_match_list:
                if not i in TFTCompanions and current_versions["TFTCompanion"] != TFTGamePatch:
                    TFTCompanionPatch_adopted: str = TFTGamePatch
                    TFTCompanion_recapture: int = 1
                    logPrint("对局%d小小英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的小小英雄信息……\nTFT companion information (%s) of Match %d capture failed! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, TFTCompanion_recapture, TFTCompanionPatch_adopted, i, TFTHistoryJson["game_id"], TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/companions.json" %(TFTCompanionPatch_adopted, language_cdragon[locale]), session, log)
                            TFTCompanion: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            TFTCompanionPatch_deserted: str = TFTCompanionPatch_adopted
                            TFTCompanionPatch_adopted = FindPostPatch(Patch(TFTCompanionPatch_adopted), versionList)
                            TFTCompanion_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTCompanionPatch_deserted, TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_deserted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if TFTCompanion_recapture < 3:
                                TFTCompanion_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的小小英雄信息……\nYour network environment is abnormal! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！对局%d的小小英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the companion (%s) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的小小英雄信息。\nTFT companion information changed to Patch %s." %(TFTCompanionPatch_adopted, TFTCompanionPatch_adopted), verbose = verbose)
                            TFTCompanions = {companion_iter["contentId"]: companion_iter for companion_iter in TFTCompanion}
                            current_versions["TFTCompanion"] = TFTCompanionPatch_adopted
                            unmapped_keys["TFTCompanion"].clear()
                            break
                    break
            ##云顶之弈羁绊（TFT Traits）
            TFTTraitIds_match_list: list[str] = sorted(set(trait for s in [set(map(lambda x: x["name"], participant["traits"])) for participant in TFTHistoryJson["participants"]] for trait in s))
            for i in TFTTraitIds_match_list:
                if not i in TFTTraits and current_versions["TFTTrait"] != TFTGamePatch:
                    TFTTraitPatch_adopted: str = TFTGamePatch
                    TFTTrait_recapture: int = 1
                    logPrint("对局%d羁绊信息（%s）获取失败！正在第%d次尝试改用%s版本的羁绊信息……\nTFT trait information (%s) of Match %d capture failed! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, TFTTrait_recapture, TFTTraitPatch_adopted, i, TFTHistoryJson["game_id"], TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tfttraits.json" %(TFTTraitPatch_adopted, language_cdragon[locale]), session, log)
                            TFTTrait: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            TFTTraitPatch_deserted: str = TFTTraitPatch_adopted
                            TFTTraitPatch_adopted = FindPostPatch(Patch(TFTTraitPatch_adopted), versionList)
                            TFTTrait_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTraitPatch_deserted, TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_deserted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if TFTTrait_recapture < 3:
                                TFTTrait_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的羁绊信息……\nYour network environment is abnormal! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！对局%d的羁绊信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the trait (%s) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的羁绊信息。\nTFT trait information changed to Patch %s." %(TFTTraitPatch_adopted, TFTTraitPatch_adopted), verbose = verbose)
                            TFTTraits = {}
                            for trait_iter in TFTTrait:
                                trait_id: str = trait_iter["trait_id"]
                                conditional_trait_sets = {}
                                if "conditional_trait_sets" in trait_iter: #在英雄联盟第13赛季之前，CommunityDragon数据库中记录的羁绊信息无conditional_trait_sets项（Before Season 13, `conditional_trait_sets` item is absent from tfttraits from CommunityDragon database）
                                    for conditional_trait_set in trait_iter["conditional_trait_sets"]:
                                        style_idx: str = conditional_trait_set["style_idx"]
                                        conditional_trait_sets[style_idx] = conditional_trait_set
                                trait_iter["conditional_trait_sets"] = conditional_trait_sets
                                TFTTraits[trait_id] = trait_iter
                            current_versions["TFTTrait"] = TFTTraitPatch_adopted
                            unmapped_keys["TFTTrait"].clear()
                            break
                    break
            ##云顶之弈英雄（TFT champions）
            TFTChampionIds_match_list: list[str] = sorted(set(champion for s in [set(map(lambda x: x["character_id"], participant["units"])) for participant in TFTHistoryJson["participants"]] for champion in s))
            for i in TFTChampionIds_match_list:
                if not i in TFTChampions and not i.lower() in set(map(lambda x: x.lower(), TFTChampions.keys())) and current_versions["TFTChampion"] != TFTGamePatch:
                    TFTChampionPatch_adopted: str = TFTGamePatch
                    TFTChampion_recapture: int = 1
                    logPrint("对局%d英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的棋子信息……\nTFT champion (%s) information of Match %d capture failed! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, TFTChampion_recapture, TFTChampionPatch_adopted, i, TFTHistoryJson["game_id"], TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                    while True:
                        try:
                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftchampions.json" %(TFTChampionPatch_adopted, language_cdragon[locale]), session, log)
                            TFTChampion: list[dict[str, Any]] = response.json()
                        except requests.exceptions.JSONDecodeError:
                            TFTChampionPatch_deserted = TFTChampionPatch_adopted
                            TFTChampionPatch_adopted = FindPostPatch(Patch(TFTChampionPatch_adopted), versionList)
                            TFTChampion_recapture = 1
                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampionPatch_deserted, TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_deserted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                        except requests.exceptions.RequestException:
                            if TFTChampion_recapture < 3:
                                TFTChampion_recapture += 1
                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的棋子信息……\nYour network environment is abnormal! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                            else:
                                logPrint("网络环境异常！对局%d将采用原始数据！\nNetwork error! The original data will be used for Match %d!" %(TFTHistoryJson["game_id"], TFTHistoryJson["game_id"]), verbose = verbose)
                                break
                        else:
                            logPrint("已改用%s版本的棋子信息。\nTFT champion information changed to Patch %s." %(TFTChampionPatch_adopted, TFTChampionPatch_adopted), verbose = verbose)
                            TFTChampions = {}
                            if Patch(TFTChampionPatch_adopted) < Patch("13.17"): #从13.17版本开始，CommunityDragon数据库中关于云顶之弈棋子的数据格式发生微调（Since Patch 13.17, the format of TFT Champion data in CommunityDragon database has been modified）
                                for TFTChampion_iter in TFTChampion:
                                    champion_name: str = TFTChampion_iter["character_id"]
                                    TFTChampions[champion_name] = TFTChampion_iter
                            else:
                                for TFTChampion_iter in TFTChampion:
                                    champion_name = TFTChampion_iter["name"]
                                    TFTChampions[champion_name] = TFTChampion_iter["character_record"] #请注意该语句与4行之前的语句的差异，并看看一开始准备数据文件时使用的是哪一种——其实你应该猜的出来（Have you noticed the difference between this statement and the statement that is 4 lines above from this statement? Also, check which statement I chose for the beginning, when I prepared the data resources. Actually, you should be able to speculate it without referring to the code）
                            current_versions["TFTChampion"] = TFTChampionPatch_adopted
                            unmapped_keys["TFTChampion"].clear()
                            break
                    break
            ##云顶之弈装备（TFT items）
            s: set[str] = set()
            for participant in TFTHistoryJson["participants"]:
                for unit in participant["units"]:
                    if "itemNames" in unit:
                        s |= set(unit["itemNames"])
                    elif "items" in unit:
                        s |= set(unit["items"])
                    else:
                        s |= set()
            TFTItemIds_match_list: list[str] = sorted(s)
            for i in TFTItemIds_match_list:
                if not i in TFTItems and not i in TFTAugments:
                    if current_versions["TFTItem"] != TFTGamePatch:
                        TFTItemPatch_adopted: str = TFTGamePatch
                        TFTItem_recapture: int = 1
                        logPrint("对局%d装备信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nTFT item information (%s) of Match %d capture failed! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTHistoryJson["game_id"], i, TFTItem_recapture, TFTItemPatch_adopted, i, TFTHistoryJson["game_id"], TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftitems.json" %(TFTItemPatch_adopted, language_cdragon[locale]), session, log)
                                TFTItem: list[dict[str, Any]] = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTItemPatch_deserted: str = TFTItemPatch_adopted
                                TFTItemPatch_adopted = FindPostPatch(Patch(TFTItemPatch_adopted), versionList)
                                TFTItem_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItemPatch_deserted, TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_deserted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                            except requests.exceptions.RequestException:
                                if TFTItem_recapture < 3:
                                    TFTItem_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nYour network environment is abnormal! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！对局%d的装备信息（%d）将采用原始数据！\nNetwork error! The original data will be used for the item (%d) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的云顶之弈装备信息。\nTFT item information changed to Patch %s." %(TFTItemPatch_adopted, TFTItemPatch_adopted), verbose = verbose)
                                TFTItems = {TFTItem_iter["nameId"]: TFTItem_iter for TFTItem_iter in TFTItem}
                                current_versions["TFTItem"] = TFTItemPatch_adopted
                                unmapped_keys["TFTItem"].clear()
                                break
                    #由于云顶之弈基础数据中也包含装备信息，这里将重新获取对局版本的云顶之弈基础数据（Because TFT basic data contain item data, here the program recaptures TFT basic data of the match version）
                    if current_versions["TFTAugment"] != TFTGamePatch:
                        TFTAugmentPatch_adopted = TFTGamePatch
                        TFTAugment_recapture = 1
                        while True:
                            try:
                                response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                TFT = response.json()
                            except requests.exceptions.JSONDecodeError:
                                TFTAugmentPatch_deserted = TFTAugmentPatch_adopted
                                TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                TFTAugment_recapture = 1
                                logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                            except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                if TFTAugment_recapture < 3:
                                    TFTAugment_recapture += 1
                                    logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                else:
                                    logPrint("网络环境异常！对局%d的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d!" %(TFTHistoryJson["game_id"], i, i, TFTHistoryJson["game_id"]), verbose = verbose)
                                    break
                            else:
                                logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                unmapped_keys["TFTAugment"].clear()
                                break
                    break
        #下面开始整理数据（Sorts out the data）
        for i in range(len(TFTHistoryJson["participants"])):
            if save_self or TFTHistoryJson["participants"][i]["puuid"] in puuidList:
                await generate_TFTGameInfo_records(connection, TFTGame_info_data, TFTGame_info, i, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits, gameIndex = gameIndex, current_puuid = puuidList, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, useInfoDict = useInfoDict, infos = infos, log = log, verbose = verbose)
                if sortStats and TFTHistoryJson["participants"][i]["puuid"] in puuidList: #这个if语句块是适配自定义脚本20而做的修改（This if-block is a modification made to adapt to Customized Program 20）
                    for j in range(len(TFTGame_info_header_keys)):
                        key: str = TFTGame_info_header_keys[j]
                        TFTGame_stat_data[key].append(TFTGame_info_data[key][-1]) #直接添加最近一次追加的数据，以简化代码（Directly append the recently appended data to simplify the code）
    TFTGame_info_statistics_output_order: list[int] = [40, 19, 55, 46, 47, 43, 33, 34, 35, 38, 52, 53, 49, 36, 50, 42, 54, 41, 39, 44, 45, 23, 24, 25, 150, 148, 149, 203, 206, 209, 155, 153, 154, 212, 215, 218, 160, 158, 159, 221, 224, 227, 165, 163, 164, 230, 233, 236, 170, 168, 169, 239, 242, 245, 175, 173, 174, 248, 251, 254, 180, 178, 179, 257, 260, 263, 185, 183, 184, 266, 269, 272, 190, 188, 189, 275, 278, 281, 195, 193, 194, 284, 287, 290, 200, 198, 199, 293, 296, 299, 61, 57, 58, 59, 60, 68, 64, 65, 66, 67, 75, 71, 72, 73, 74, 82, 78, 79, 80, 81, 89, 85, 86, 87, 88, 96, 92, 93, 94, 95, 103, 99, 100, 101, 102, 110, 106, 107, 108, 109, 117, 113, 114, 115, 116, 124, 120, 121, 122, 123, 131, 127, 128, 129, 130, 138, 134, 135, 136, 137, 145, 141, 142, 143, 144]
    TFTGame_info_data_organized: dict[str, list[Any]] = {}
    for i in TFTGame_info_statistics_output_order:
        key: str = TFTGame_info_header_keys[i]
        TFTGame_info_data_organized[key] = TFTGame_info_data[key]
    TFTGame_info_df: pandas.DataFrame = pandas.DataFrame(data = TFTGame_info_data_organized)
    for column in TFTGame_info_df:
        if TFTGame_info_df[column].dtype == "bool":
            TFTGame_info_df[column] = TFTGame_info_df[column].astype(str)
            TFTGame_info_df[column] = list(map(lambda x: "√" if x == "True" else "", TFTGame_info_df[column].to_list()))
    TFTGame_info_df = pandas.concat([pandas.DataFrame([TFTGame_info_header])[TFTGame_info_df.columns], TFTGame_info_df], ignore_index = True)
    TFTGame_info_df = TFTGame_info_df.stack().unstack(0)
    return (TFTGame_info_df, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits)

async def sort_TFTGame_stats(connection: Connection, TFTMatchIDs: list[int], TFTHistory: dict[str, Any], queues: dict[int, dict[str, Any]], TFTAugments: dict[str, dict[str, Any]], TFTChampions: dict[str, dict[str, Any]], TFTItems: dict[str, dict[str, Any]], TFTCompanions: dict[str, dict[str, Any]], TFTTraits: dict[str, dict[str, Any]], puuid: str | list[str] = "", excluded_reserve: bool = False, save_self: bool = True, save_other: bool = False, save_bot: bool = False, useAllVersions: bool = True, versionList: list[Patch] | None = None, locale: str = "en_US", session: requests.Session | None = None, useInfoDict: bool = False, infos: dict[str, dict[str, Any]] | None = None, log: LogManager | None = None, verbose: bool = True) -> pandas.DataFrame: #和sort_LoLGame_stats函数不同的是，根据对局序号查询云顶之弈对局信息需要借助SGP API，所以这里做了一处优化：如果某场对局在一个给定的对局记录中已经存在，则直接使用该对局记录中的数据。这就是参数表中引入TFTHistory的原因（The difference of this function from `sort_LoLGame_stats` is that SGP API is used to query TFT match information. Hence, this function performs an optimization: if a match exists in a specified match history, then query the match history instead. This is why `TFTHistory` appears in the parameter list）
    if versionList == None:
        versionList = []
    if session == None:
        session = requests.Session()
    if infos == None:
        infos = {}
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    puuidList: list[str] = [puuid] if isinstance(puuid, str) else puuid
    current_versions: dict[str, str] = {"TFTAugment": "", "TFTChampion": "", "TFTItem": "", "TFTCompanion": "", "TFTTrait": ""}
    unmapped_keys: dict[str, set[Any]] = {"TFTAugment": set(), "TFTChampion": set(), "TFTItem": set(), "TFTCompanion": set(), "TFTTrait": set()}
    version_re = re.compile(r"\d*\.\d*\.\d*\.\d*")
    error_TFTMatchIDs: list[int] = [] #记录实际存在但未如期获取的对局序号（Records the matches that really exist but fail to be fetched）
    matches_not_found: list[int] = [] #记录系统已经删除但是不报异常的对局序号（Records the matches deleted from the database but still existing in the match history）
    matches_to_remove: list[int] = [] #记录获取成功但不包含主玩家的对局序号（Records the matches that are fetched successfully but don't contain the main player）
    #开始获取各对局内的玩家信息（Begin to capture the players' information in each match）
    TFTGame_info_header_keys: list[str] = list(TFTGame_info_header.keys())
    TFTGame_stat_data: dict[str, list[Any]] = {}
    for i in range(len(TFTGame_info_header_keys)):
        key: str = TFTGame_info_header_keys[i]
        TFTGame_stat_data[key] = []
    for matchId in TFTMatchIDs:
        for i in range(len(TFTHistory["games"])):
            if int(TFTHistory["games"][i]["metadata"]["match_id"].split("_")[1]) == matchId:
                TFTGame_info: dict[str, Any] = TFTHistory["games"][i]
                break
        else:
            status, TFTGame_info = await get_TFTGame_info(matchId, log = log)
        
        if "errorCode" in TFTGame_info:
            logPrint(TFTGame_info, verbose = verbose)
            error_TFTMatchIDs.append(matchId)
        else:
            TFTHistoryJson: dict[str, Any] = TFTGame_info["json"]
            if bool(TFTHistoryJson):
                TFTGameVersion: str = version_re.search(TFTHistoryJson["game_version"]).group()
                TFTGamePatch: str = ".".join(TFTGameVersion.split(".")[:2])
                if excluded_reserve or len(set(puuidList) & set(map(lambda x: x["puuid"], TFTHistoryJson["participants"]))) != 0:
                    if useAllVersions:
                        ##游戏模式（Game mode）
                        queueIds_match_list: list[int] = [TFTHistoryJson["queue_id"]]
                        for j in queueIds_match_list:
                            if not j in queues and current_versions["queue"] != TFTGamePatch:
                                queuePatch_adopted: str = TFTGamePatch
                                queue_recapture: int = 1
                                logPrint("第%d/%d场对局（对局序号：%d）游戏模式信息（%d）获取失败！正在第%d次尝试改用%s版本的游戏模式信息……\nGame mode information (%d) of Match %d / %d (matchId: %d) capture failed! Changing to game modes of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, queue_recapture, queuePatch_adopted, j, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], queuePatch_adopted, queue_recapture), verbose = verbose)
                                while True:
                                    try:
                                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/queues.json" %(queuePatch_adopted, language_cdragon[locale]), session, log)
                                        queue: list[dict[str, Any]] = response.json()
                                    except requests.exceptions.JSONDecodeError:
                                        queuePatch_deserted: str = queuePatch_adopted
                                        queuePatch_adopted = FindPostPatch(Patch(queuePatch_adopted), versionList)
                                        queue_recapture = 1
                                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to game modes of Patch %s ... Times tried: %d." %(queuePatch_deserted, queue_recapture, queuePatch_adopted, queuePatch_deserted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                    except requests.exceptions.RequestException:
                                        if queue_recapture < 3:
                                            queue_recapture += 1
                                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的游戏模式信息……\nYour network environment is abnormal! Changing to game modes of Patch %s ... Times tried: %d." %(queue_recapture, queuePatch_adopted, queuePatch_adopted, queue_recapture), verbose = verbose)
                                        else:
                                            logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的游戏模式信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the game modes (%s) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], j, j, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                            break
                                    else:
                                        logPrint("已改用%s版本的游戏模式信息。\nGame mode information changed to Patch %s." %(queuePatch_adopted, queuePatch_adopted), verbose = verbose)
                                        queues = {queue_iter["id"]: queue_iter for queue_iter in queue}
                                        current_versions["queue"] = queuePatch_adopted
                                        unmapped_keys["queue"].clear()
                                        break
                                break
                        ##云顶之弈强化符文（TFT augments）
                        TFTAugmentIds_match_list: list[str] = sorted(set(augment for lst in list(map(lambda x: x["augments"] if "augments" in x else [], TFTHistoryJson["participants"])) for augment in lst)) #`if "augments" in x`的作用是防止早期云顶之弈对局无强化符文导致程序报错（`if "augments" in x` is used here because some early TFT matches don't contain augments and result in KeyErrors consequently）
                        for i in TFTAugmentIds_match_list:
                            if not i in TFTAugments and current_versions["TFTAugment"] != TFTGamePatch:
                                TFTAugmentPatch_adopted: str = TFTGamePatch
                                TFTAugment_recapture: int = 1
                                logPrint("第%d/%d场对局（对局序号：%d）强化符文信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nAugment information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, TFTAugment_recapture, TFTAugmentPatch_adopted, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                while True:
                                    try:
                                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                        TFT: dict[str, Any] = response.json()
                                    except requests.exceptions.JSONDecodeError: #存在版本合并更新的情况（Situation like merged update exists）
                                        TFTAugmentPatch_deserted: str = TFTAugmentPatch_adopted
                                        TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                        TFTAugment_recapture = 1
                                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                    except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                        if TFTAugment_recapture < 3:
                                            TFTAugment_recapture += 1
                                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                        else:
                                            logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                            break
                                    else:
                                        logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                        TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                        current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                        unmapped_keys["TFTAugment"].clear()
                                        break
                                break
                        ##云顶之弈小小英雄（TFT companions）
                        TFTCompanionIds_match_list: list[str] = sorted(set(map(lambda x: x["companion"]["content_ID"], TFTHistoryJson["participants"])))
                        for i in TFTCompanionIds_match_list:
                            if not i in TFTCompanions and current_versions["TFTCompanion"] != TFTGamePatch:
                                TFTCompanionPatch_adopted: str = TFTGamePatch
                                TFTCompanion_recapture: int = 1
                                logPrint("第%d/%d场对局（对局序号：%d）小小英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的小小英雄信息……\nTFT companion information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, TFTCompanion_recapture, TFTCompanionPatch_adopted, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                                while True:
                                    try:
                                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/companions.json" %(TFTCompanionPatch_adopted, language_cdragon[locale]), session, log)
                                        TFTCompanion: list[dict[str, Any]] = response.json()
                                    except requests.exceptions.JSONDecodeError:
                                        TFTCompanionPatch_deserted: str = TFTCompanionPatch_adopted
                                        TFTCompanionPatch_adopted = FindPostPatch(Patch(TFTCompanionPatch_adopted), versionList)
                                        TFTCompanion_recapture = 1
                                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTCompanionPatch_deserted, TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_deserted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                                    except requests.exceptions.RequestException:
                                        if TFTCompanion_recapture < 3:
                                            TFTCompanion_recapture += 1
                                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的小小英雄信息……\nYour network environment is abnormal! Changing to TFT companions of Patch %s ... Times tried: %d." %(TFTCompanion_recapture, TFTCompanionPatch_adopted, TFTCompanionPatch_adopted, TFTCompanion_recapture), verbose = verbose)
                                        else:
                                            logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的小小英雄信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the companion (%s) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                            break
                                    else:
                                        logPrint("已改用%s版本的小小英雄信息。\nTFT companion information changed to Patch %s." %(TFTCompanionPatch_adopted, TFTCompanionPatch_adopted), verbose = verbose)
                                        TFTCompanions = {companion_iter["contentId"]: companion_iter for companion_iter in TFTCompanion}
                                        current_versions["TFTCompanion"] = TFTCompanionPatch_adopted
                                        unmapped_keys["TFTCompanion"].clear()
                                        break
                                break
                        ##云顶之弈羁绊（TFT Traits）
                        TFTTraitIds_match_list: list[str] = sorted(set(trait for s in [set(map(lambda x: x["name"], participant["traits"])) for participant in TFTHistoryJson["participants"]] for trait in s))
                        for i in TFTTraitIds_match_list:
                            if not i in TFTTraits and current_versions["TFTTrait"] != TFTGamePatch:
                                TFTTraitPatch_adopted: str = TFTGamePatch
                                TFTTrait_recapture: int = 1
                                logPrint("第%d/%d场对局（对局序号：%d）羁绊信息（%s）获取失败！正在第%d次尝试改用%s版本的羁绊信息……\nTFT trait information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, TFTTrait_recapture, TFTTraitPatch_adopted, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                                while True:
                                    try:
                                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tfttraits.json" %(TFTTraitPatch_adopted, language_cdragon[locale]), session, log)
                                        TFTTrait: list[dict[str, Any]] = response.json()
                                    except requests.exceptions.JSONDecodeError:
                                        TFTTraitPatch_deserted: str = TFTTraitPatch_adopted
                                        TFTTraitPatch_adopted = FindPostPatch(Patch(TFTTraitPatch_adopted), versionList)
                                        TFTTrait_recapture = 1
                                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTraitPatch_deserted, TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_deserted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                                    except requests.exceptions.RequestException:
                                        if TFTTrait_recapture < 3:
                                            TFTTrait_recapture += 1
                                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的羁绊信息……\nYour network environment is abnormal! Changing to TFT traits of Patch %s ... Times tried: %d." %(TFTTrait_recapture, TFTTraitPatch_adopted, TFTTraitPatch_adopted, TFTTrait_recapture), verbose = verbose)
                                        else:
                                            logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的羁绊信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the trait (%s) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                            break
                                    else:
                                        logPrint("已改用%s版本的羁绊信息。\nTFT trait information changed to Patch %s." %(TFTTraitPatch_adopted, TFTTraitPatch_adopted), verbose = verbose)
                                        TFTTraits = {}
                                        for trait_iter in TFTTrait:
                                            trait_id: str = trait_iter["trait_id"]
                                            conditional_trait_sets = {}
                                            if "conditional_trait_sets" in trait_iter: #在英雄联盟第13赛季之前，CommunityDragon数据库中记录的羁绊信息无conditional_trait_sets项（Before Season 13, `conditional_trait_sets` item is absent from tfttraits from CommunityDragon database）
                                                for conditional_trait_set in trait_iter["conditional_trait_sets"]:
                                                    style_idx: str = conditional_trait_set["style_idx"]
                                                    conditional_trait_sets[style_idx] = conditional_trait_set
                                            trait_iter["conditional_trait_sets"] = conditional_trait_sets
                                            TFTTraits[trait_id] = trait_iter
                                        current_versions["TFTTrait"] = TFTTraitPatch_adopted
                                        unmapped_keys["TFTTrait"].clear()
                                        break
                                break
                        ##云顶之弈英雄（TFT champions）
                        TFTChampionIds_match_list: list[str] = sorted(set(champion for s in [set(map(lambda x: x["character_id"], participant["units"])) for participant in TFTHistoryJson["participants"]] for champion in s))
                        for i in TFTChampionIds_match_list:
                            if not i in TFTChampions and not i.lower() in map(lambda x: x.lower(), TFTChampions.keys()) and current_versions["TFTChampion"] != TFTGamePatch:
                                TFTChampionPatch_adopted: str = TFTGamePatch
                                TFTChampion_recapture: int = 1
                                logPrint("第%d/%d场对局（对局序号：%d）英雄信息（%s）获取失败！正在第%d次尝试改用%s版本的棋子信息……\nTFT champion (%s) information of Match %d / %d (matchId: %d) capture failed! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, TFTChampion_recapture, TFTChampionPatch_adopted, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                                while True:
                                    try:
                                        response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftchampions.json" %(TFTChampionPatch_adopted, language_cdragon[locale]), session, log)
                                        TFTChampion: list[dict[str, Any]] = response.json()
                                    except requests.exceptions.JSONDecodeError:
                                        TFTChampionPatch_deserted: str = TFTChampionPatch_adopted
                                        TFTChampionPatch_adopted = FindPostPatch(Patch(TFTChampionPatch_adopted), versionList)
                                        TFTChampion_recapture = 1
                                        logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampionPatch_deserted, TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_deserted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                                    except requests.exceptions.RequestException:
                                        if TFTChampion_recapture < 3:
                                            TFTChampion_recapture += 1
                                            logPrint("网络环境异常！正在第%d次尝试改用%s版本的棋子信息……\nYour network environment is abnormal! Changing to TFT champions of Patch %s ... Times tried: %d." %(TFTChampion_recapture, TFTChampionPatch_adopted, TFTChampionPatch_adopted, TFTChampion_recapture), verbose = verbose)
                                        else:
                                            logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）将采用原始数据！\nNetwork error! The original data will be used for Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                            break
                                    else:
                                        logPrint("已改用%s版本的棋子信息。\nTFT champion information changed to Patch %s." %(TFTChampionPatch_adopted, TFTChampionPatch_adopted), verbose = verbose)
                                        TFTChampions = {}
                                        if Patch(TFTChampionPatch_adopted) < Patch("13.17"): #从13.17版本开始，CommunityDragon数据库中关于云顶之弈小小英雄的数据格式发生微调（Since Patch 13.17, the format of TFT Champion data in CommunityDragon database has been modified）
                                            for TFTChampion_iter in TFTChampion:
                                                champion_name: str = TFTChampion_iter["character_id"]
                                                TFTChampions[champion_name] = TFTChampion_iter
                                        else:
                                            for TFTChampion_iter in TFTChampion:
                                                champion_name = TFTChampion_iter["name"]
                                                TFTChampions[champion_name] = TFTChampion_iter["character_record"] #请注意该语句与4行之前的语句的差异，并看看一开始准备数据文件时使用的是哪一种——其实你应该猜的出来（Have you noticed the difference between this statement and the statement that is 4 lines above from this statement? Also, check which statement I chose for the beginning, when I prepared the data resources. Actually, you should be able to speculate it without referring to the code）
                                        current_versions["TFTChampion"] = TFTChampionPatch_adopted
                                        unmapped_keys["TFTChampion"].clear()
                                        break
                                break
                        ##云顶之弈装备（TFT items）
                        s: set[str] = set()
                        for participant in TFTHistoryJson["participants"]:
                            for unit in participant["units"]:
                                if "itemNames" in unit:
                                    s |= set(unit["itemNames"])
                                elif "items" in unit:
                                    s |= set(unit["items"])
                                else:
                                    s |= set()
                        TFTItemIds_match_list: list[str] = sorted(s)
                        for i in TFTItemIds_match_list:
                            if not i in TFTItems and not i in TFTAugments:
                                if current_versions["TFTItem"] != TFTGamePatch:
                                    TFTItemPatch_adopted: str = TFTGamePatch
                                    TFTItem_recapture: int = 1
                                    logPrint("第%d/%d场对局（对局序号：%d）装备信息（%s）获取失败！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nTFT item information (%s) of Match %d / %d (matchId: %d) capture failed! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, TFTItem_recapture, TFTItemPatch_adopted, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                    while True:
                                        try:
                                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/plugins/rcp-be-lol-game-data/global/%s/v1/tftitems.json" %(TFTItemPatch_adopted, language_cdragon[locale]), session, log)
                                            TFTItem: list[dict[str, Any]] = response.json()
                                        except requests.exceptions.JSONDecodeError:
                                            TFTItemPatch_deserted = TFTItemPatch_adopted
                                            TFTItemPatch_adopted = FindPostPatch(Patch(TFTItemPatch_adopted), versionList)
                                            TFTItem_recapture = 1
                                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItemPatch_deserted, TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_deserted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                        except requests.exceptions.RequestException:
                                            if TFTItem_recapture < 3:
                                                TFTItem_recapture += 1
                                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈装备信息……\nYour network environment is abnormal! Changing to TFT items of Patch %s ... Times tried: %d." %(TFTItem_recapture, TFTItemPatch_adopted, TFTItemPatch_adopted, TFTItem_recapture), verbose = verbose)
                                            else:
                                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的装备信息（%d）将采用原始数据！\nNetwork error! The original data will be used for the item (%d) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                                break
                                        else:
                                            logPrint("已改用%s版本的云顶之弈装备信息。\nTFT item information changed to Patch %s." %(TFTItemPatch_adopted, TFTItemPatch_adopted), verbose = verbose)
                                            TFTItems = {TFTItem_iter["nameId"]: TFTItem_iter for TFTItem_iter in TFTItem}
                                            current_versions["TFTItem"] = TFTItemPatch_adopted
                                            unmapped_keys["TFTItem"].clear()
                                            break
                                #由于云顶之弈基础数据中也包含装备信息，这里将重新获取对局版本的云顶之弈基础数据（Because TFT basic data contain item data, here the program recaptures TFT basic data of the match version）
                                if current_versions["TFTAugment"] != TFTGamePatch:
                                    TFTAugmentPatch_adopted = TFTGamePatch
                                    TFTAugment_recapture = 1
                                    while True:
                                        try:
                                            response, status, session = requestUrl("GET", "https://raw.communitydragon.org/%s/cdragon/tft/%s.json" %(TFTAugmentPatch_adopted, language_cdragon[locale]), session, log)
                                            TFT = response.json()
                                        except requests.exceptions.JSONDecodeError:
                                            TFTAugmentPatch_deserted = TFTAugmentPatch_adopted
                                            TFTAugmentPatch_adopted = FindPostPatch(Patch(TFTAugmentPatch_adopted), versionList)
                                            TFTAugment_recapture = 1
                                            logPrint("%s版本文件不存在！正在第%s次尝试转至%s版本……\n%s patch file doesn't exist! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugmentPatch_deserted, TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_deserted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                        except requests.exceptions.RequestException: #如果重新获取数据的过程中出现网络异常，那么暂时先将原始数据导入工作表中（If a network error occurs when recapturing the data, then temporarily export the initial data into the worksheet）
                                            if TFTAugment_recapture < 3:
                                                TFTAugment_recapture += 1
                                                logPrint("网络环境异常！正在第%d次尝试改用%s版本的云顶之弈强化符文信息……\nYour network environment is abnormal! Changing to TFT augments of Patch %s ... Times tried: %d." %(TFTAugment_recapture, TFTAugmentPatch_adopted, TFTAugmentPatch_adopted, TFTAugment_recapture), verbose = verbose)
                                            else:
                                                logPrint("网络环境异常！第%d/%d场对局（对局序号：%d）的强化符文信息（%s）将采用原始数据！\nNetwork error! The original data will be used for the augment (%s) of Match %d / %d (matchId: %d)!" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"], i, i, TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), TFTHistoryJson["game_id"]), verbose = verbose)
                                                break
                                        else:
                                            logPrint("已改用%s版本的云顶之弈强化符文信息。\nTFT augment information changed to Patch %s." %(TFTAugmentPatch_adopted, TFTAugmentPatch_adopted), verbose = verbose)
                                            TFTAugments = {item["apiName"]: item for item in TFT["items"]}
                                            current_versions["TFTAugment"] = TFTAugmentPatch_adopted
                                            unmapped_keys["TFTAugment"].clear()
                                            break
                                break
                    for i in range(len(TFTHistoryJson["participants"])):
                        if not (not save_bot and TFTHistoryJson["participants"][i]["puuid"] == "00000000-0000-0000-0000-000000000000" or not save_self and TFTHistoryJson["participants"][i]["puuid"] in puuidList or not save_other and not TFTHistoryJson["participants"][i]["puuid"] in puuidList):
                            await generate_TFTGameInfo_records(connection, TFTGame_stat_data, TFTGame_info, i, queues, TFTAugments, TFTChampions, TFTItems, TFTCompanions, TFTTraits, gameIndex = TFTMatchIDs.index(matchId) + 1, current_puuid = puuidList, unmapped_keys = unmapped_keys, useAllVersions = useAllVersions, useInfoDict = useInfoDict, infos = infos, log = log, verbose = verbose)
                    if excluded_reserve:
                        logPrint("[%d/%d]对局%d不包含主玩家。已保留该对局。\nMatch %d doesn't contain the main player but is reserved." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), matchId, matchId), print_time = True, verbose = verbose)
                    else:
                        logPrint("加载进度（Loading process）：%d/%d\t对局序号（MatchID）： %s" %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), matchId), print_time = True, verbose = verbose)
                else:
                    matches_to_remove.append(matchId)
                    logPrint("[%d/%d]对局%d不包含主玩家。已移除该对局。\nMatch %d doesn't contain the main player and is deprecated." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), matchId, matchId), print_time = True, verbose = verbose)
            else:
                matches_not_found.append(matchId)
                logPrint("[%d/%d]对局%d数据不可用。\nMatch %d data not available." %(TFTMatchIDs.index(matchId) + 1, len(TFTMatchIDs), matchId, matchId), print_time = True, verbose = verbose)
    if len(error_TFTMatchIDs) > 0:
        logPrint("警告：以下%d场对局获取失败。\nWarning: The following %d match(es) fail to be fetched." %(len(error_TFTMatchIDs), len(error_TFTMatchIDs)), verbose = verbose)
        logPrint(error_TFTMatchIDs, verbose = verbose)
    if len(matches_to_remove) > 0:
        logPrint("注意：以下%d场对局因不包含主玩家而被移除。\nAttention: The following %d match(es) are removed because they don't contain the main player." %(len(matches_to_remove), len(matches_to_remove)), verbose = verbose)
        logPrint(matches_to_remove, verbose = verbose)
    if len(matches_not_found) > 0:
        logPrint("注意：以下%d场对局数据不可用。\nAttention: The following %d match(es) are not available." %(len(matches_not_found), len(matches_not_found)), verbose = verbose)
        logPrint(matches_not_found, verbose = verbose)
    TFTGame_stat_statistics_output_order: list[int] = [0, 19, 46, 47, 43, 5, 14, 15, 16, 6, 10, 18, 7, 13, 11, 12, 307, 305, 40, 55, 33, 34, 35, 38, 52, 53, 49, 36, 50, 42, 54, 41, 39, 44, 45, 23, 24, 25, 150, 148, 149, 203, 206, 209, 155, 153, 154, 212, 215, 218, 160, 158, 159, 221, 224, 227, 165, 163, 164, 230, 233, 236, 170, 168, 169, 239, 242, 245, 175, 173, 174, 248, 251, 254, 180, 178, 179, 257, 260, 263, 185, 183, 184, 266, 269, 272, 190, 188, 189, 275, 278, 281, 195, 193, 194, 284, 287, 290, 200, 198, 199, 293, 296, 299, 61, 57, 58, 59, 60, 68, 64, 65, 66, 67, 75, 71, 72, 73, 74, 82, 78, 79, 80, 81, 89, 85, 86, 87, 88, 96, 92, 93, 94, 95, 103, 99, 100, 101, 102, 110, 106, 107, 108, 109, 117, 113, 114, 115, 116, 124, 120, 121, 122, 123, 131, 127, 128, 129, 130, 138, 134, 135, 136, 137, 145, 141, 142, 143, 144]
    TFTGame_stat_data_organized: dict[str, list[Any]] = {}
    for i in TFTGame_stat_statistics_output_order:
        key: str = TFTGame_info_header_keys[i]
        TFTGame_stat_data_organized[key] = TFTGame_stat_data[key]
    TFTGame_stat_df: pandas.DataFrame = pandas.DataFrame(data = TFTGame_stat_data_organized)
    logPrint("正在优化逻辑值显示……\nOptimizing the display of boolean values ...", verbose = verbose)
    for column in TFTGame_stat_df:
        if TFTGame_stat_df[column].dtype == "bool":
            TFTGame_stat_df[column] = TFTGame_stat_df[column].astype(str)
            TFTGame_stat_df[column] = list(map(lambda x: "√" if x == "True" else "", TFTGame_stat_df[column].to_list()))
    logPrint("逻辑值显示优化完成！\nBoolean value display optimization finished!", verbose = verbose)
    TFTGame_stat_df = pandas.concat([pandas.DataFrame([TFTGame_info_header])[TFTGame_stat_df.columns], TFTGame_stat_df], ignore_index = True)
    return TFTGame_stat_df
