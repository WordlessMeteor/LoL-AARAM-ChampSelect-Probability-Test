from lcu_driver.connection import Connection
import os
from urllib.parse import quote
from typing import Any, IO

#-----------------------------------------------------------------------------
# 获得召唤师数据（Get access to summoner data）
#-----------------------------------------------------------------------------
async def get_summoner_data(connection: Connection):
    summoner: dict[str, Any] = await (await connection.request("GET", "/lol-summoner/v1/current-summoner")).json()
    print("displayName:    %s" %(summoner["gameName"] + "#" + summoner["tagLine"]))
    print("summonerId:     %s" %(summoner["summonerId"]))
    print("puuid:          %s" %(summoner["puuid"]))
    print("-")

#-----------------------------------------------------------------------------
#  lockfile
#-----------------------------------------------------------------------------
async def update_lockfile(connection: Connection) -> None:
    path: str = os.path.join(connection.installation_path.encode("gb18030").decode("utf-8"), "lockfile")
    if os.path.isfile(path):
        file: IO[Any] = open(path, "w+")
        text: str = "LeagueClient:%d:%d:%s:%s" %(connection.pid, connection.port, connection.auth_key, connection.protocols[0])
        file.write(text)
        file.close()
    return None

async def get_lockfile(connection: Connection) -> str | None:
    path: str = os.path.join(connection.installation_path.encode("gb18030").decode("utf-8"), "lockfile")
    if os.path.isfile(path):
        file: IO[Any] = open(path, "r")
        text: str = file.readline().split(":")
        file.close()
        print(connection.address)
        print(f"riot    {text[3]}")
        return text[3]
    return None

#-----------------------------------------------------------------------------
#  查询召唤师信息（Search for summoner information）
#-----------------------------------------------------------------------------
async def get_info(connection: Connection, name: str, searchType: str | int = "riotId") -> dict[str, Any]:
    #searchTypes = {0: "selfCheck", 1: "riotId", 2: "puuid", 3: "summonerId"}
    current_info: dict[str, Any] = await (await connection.request("GET", "/lol-summoner/v1/current-summoner")).json()
    result: dict[str, Any] = {"searchType": "riotId", "endpoint": "/lol-summoner/v2/summoners/puuid/{puuid}", "info_got": False, "network_error": False, "body": {}, "message": "", "selfInfo": False}
    if "errorCode" in current_info:
        result["searchType"] = "puuid"
        result["endpoint"] = "/lol-summoner/v1/current-summoner"
        result["network_error"] = True
        result["body"] = current_info
        if current_info["httpStatus"] == 404 and current_info["message"] == "You are not logged in.":
            result["message"] = "您还未登录。\nYou're not logged in."
        else:
            result["message"] = "网络异常。\nNetwork Error."
        result["selfInfo"] = True
    else:
        try:
            summonerId: int = int(name)
        except ValueError:
            if name == "current-summoner":
                result = {"searchType": "selfCheck", "endpoint": "/lol-summoner/v1/current-summoner", "info_got": True, "network_error": False, "body": current_info, "message": "", "selfInfo": True}
            elif name.count("-") == 4 and len(name.replace(" ", "")) > 22: #拳头规定的玩家昵称不超过16个字符，昵称编号不超过5个字符（Riot game name can't exceed 16 characters. The tagline can't exceed 5 characters）
                result["searchType"] = "puuid"
                result["endpoint"] = "/lol-summoner/v2/summoners/puuid/{puuid}"
                info: dict[str, Any] = await (await connection.request("GET", f"/lol-summoner/v2/summoners/puuid/{name}")).json()
                result["body"] = info
                if "errorCode" in info:
                    if info["httpStatus"] == 400:
                        if "in UUID format" in info["message"]:
                            result["message"] = "您输入的玩家通用唯一识别码格式有误！请重新输入！\nPUUID wasn't in UUID format! Please try again!"
                        elif "Error response for POST /player-account/lookup/v1/namesets-for-puuids: Failed to connect to 127.0.0.1 port" in info["message"]:
                            result["message"] = "连接超时！请检查您的登录状态。\nConnection timed out! Please check your login status."
                    elif info["httpStatus"] == 404:
                        result["message"] = "未找到玩家通用唯一识别码为%s的玩家；请核对识别码并稍后再试。\nA player with puuid %s was not found; verify the puuid and try again." %(name, name)
                    else:
                        result["network_error"] = True
                        result["message"] = "网络异常。\nNetwork Error."
                else:
                    result["info_got"] = True
                    result["selfInfo"] = info["puuid"] == current_info["puuid"]
            else:
                result["searchType"] = "riotId"
                result["endpoint"] = "/lol-summoner/v1/summoners?name={name}"
                if name.count("#") == 0:
                    result["message"] = '召唤师名称已变更为拳头ID。请以“{玩家昵称}#{昵称编号}”的格式输入。\nSummoner name has been replaced with Riot ID. Please input the name in this format: "{gameName}#{tagLine}", e.g. "%s#%s".' %(current_info["gameName"], current_info["tagLine"])
                elif name.count("#") > 1:
                    result["message"] = "该玩家名字包含了无效字符。\nThis player name contains invalid characters."
                else:
                    gameName, tagLine = name.split("#")
                    if len(gameName) == 0:
                        result["message"] = "缺少玩家昵称。\nGame name is missing."
                    elif len(tagLine) == 0:
                        result["message"] = "缺少昵称编号。\nTagline is missing."
                    elif len(gameName) < 3:
                        result["message"] = "召唤师昵称过短。\nRiot ID is too short."
                    elif len(gameName.replace(" ", "")) > 16:
                        result["message"] = "召唤师昵称过长。\nRiot ID is too long."
                    else:
                        info = await (await connection.request("GET", "/lol-summoner/v1/summoners?name=" + quote(name))).json()
                        result["body"] = info
                        if "errorCode" in info:
                            if info["httpStatus"] == 404:
                                result["message"] = "未找到%s；请核对下名字并稍后再试。\n%s was not found; verify the name and try again." %(name, name)
                            else:
                                result["network_error"] = True
                                result["message"] = "网络异常。\nNetwork Error."
                        else:
                            result["info_got"] = True
                            result["selfInfo"] = info["puuid"] == current_info["puuid"]
        else:
            result["searchType"] = "summonerId"
            result["endpoint"] = "/lol-summoner/v1/summoners/{id}"
            info: dict[str, Any] = await (await connection.request("GET", f"/lol-summoner/v1/summoners/{summonerId}")).json()
            result["body"] = info
            if "errorCode" in info:
                if info["httpStatus"] == 400:
                    if info["message"] == "Value %d for 'id' of type uint64 is out of range":
                        result["message"] = "您输入的召唤师序号格式有误！请重新输入！\nValue for 'id' of type uint64 is out of range! Please try again!"
                    else:
                        result["message"] = "未找到召唤师序号为%s的玩家；请核对召唤师序号并稍后再试。\nA player with summonerId %s was not found; verify the summonerId and try again." %(name, name)
                elif info["httpStatus"] == 404:
                    result["message"] = "未找到召唤师序号为%s的玩家；请核对召唤师序号并稍后再试。\nA player with summonerId %s was not found; verify the summonerId and try again." %(name, name)
                else:
                    result["network_error"] = True
                    result["message"] = "网络异常。\nNetwork Error."
            else:
                result["info_got"] = True
                result["selfInfo"] = info["puuid"] == current_info["puuid"]
    return result

async def get_infos(connection: Connection, puuids: list[str] | None = None, batch_size: int = 1500, retry: int = 5) -> dict[str, dict[str, Any]]: #下面的接口非常容易报错。非—常—难—受！（The following endpoint is likely to return an error. Very frustrating）
    '''
    通过POST /lol-summoner/v2/summoners/puuid接口批量获取多名召唤师的信息。对于天梯等内部数据的信息呈现非常有帮助。<br>Get multiple summoners' information through `POST /lol-summoner/v2/summoners/puuid` endpoint in batches. Especially helpful for internal data transformation like ranked ladders.
    
    :type connection: lcu_driver.connection.Connection
    :param puuids: 由玩家通用唯一识别码组成的列表。<br>A list of player universally unique identifiers (PUUIDs).
    :type puuids: list[str]
    :param batch_size: 每批召唤师的数量。默认为1500个。这个数量不能过多，否则上述接口会返回错误信息。<br>The number of each batch of summoners to query. 1500 by default. This number shouldn't be set too high, or the above endpoint will return an error message.
    :type batch_size: int
    :param retry: 每批召唤师在获取失败后的重新尝试次数。默认为5次。<br>The times of retries after an error occurs in the first fetch of each batch of summoners' information. 5 by default.
    :type retry: int
    :return: 召唤师信息索引字典。键是玩家通用唯一识别码，值是对应的召唤师信息。<br>A summoner information index dictionary, whose keys are puuids and values are corresponding summoner information.
    :rtype: dict[str, dict[str, Any]]
    '''
    if puuids == None:
        puuids = []
    puuid_search_batches: list[list[str]] = []
    for i in range(len(puuids) // 1500):
        puuid_search_batches.append(puuids[batch_size * i:batch_size * (i + 1)])
    puuid_search_batches.append(puuids[len(puuids) // 1500 * 1500:])
    summoners: dict[str, dict[str, Any]] = {}
    for i in range(len(puuid_search_batches)):
        batch: list[str] = puuid_search_batches[i]
        print("正在查询第%d/%d批共%d名召唤师的信息……\nSearching for information of %d summoners in Batch %d / %d ..." %(i + 1, len(puuid_search_batches), len(batch), len(batch), i + 1, len(puuid_search_batches)))
        summoner_infos_recapture: int = 0
        while True:
            summoner_info_bodies: list[dict[str, Any]] | dict[str, Any] = await (await connection.request("POST", "/lol-summoner/v2/summoners/puuid", data = batch)).json()
            if summoner_infos_recapture > retry:
                break
            if isinstance(summoner_info_bodies, dict) and "errorCode" in summoner_info_bodies and summoner_info_bodies["httpStatus"] == 400 and summoner_info_bodies["message"] == "Error response for POST /player-account/lookup/v1/namesets-for-puuids: ":
                print("召唤师信息获取失败。正在第%d次尝试重新获取这些玩家的信息。\nSummoner info capture failure! Recapturing these players' information ... Times tried: %d" %(summoner_infos_recapture, summoner_infos_recapture))
            else:
                break
            summoner_infos_recapture += 1
        if isinstance(summoner_info_bodies, dict) and "errorCode" in summoner_info_bodies:
            print(summoner_info_bodies)
            if summoner_info_bodies["errorCode"] == "BAD_REQUEST_HEADERS" and summoner_info_bodies["httpStatus"] == 413 and summoner_info_bodies["message"] == "Content length is too large":
                print("请求内容过长。请尝试每批查询召唤师的数量。\nRequest content too long. Please try reducing the number of summoners of each batch.")
            elif summoner_info_bodies["httpStatus"] == 400 and summoner_info_bodies["message"] == '{"httpStatus":400,"errorCode":"BAD_REQUEST","message":"PUUID was not in UUID format","implementationDetails":"filtered"}':
                print("您输入的玩家通用唯一识别码格式有误！请重新输入！\nPUUID wasn't in UUID format! Please try again!")
            elif summoner_info_bodies["httpStatus"] == 400 and summoner_info_bodies["message"] == "Error response for POST /player-account/lookup/v1/namesets-for-puuids: ":
                print("查询对应的账号信息时出现了一个问题。\nAn error occurred while looking up a player's account.")
        else:
            for info_body in summoner_info_bodies:
                summoners[info_body["puuid"]] = info_body
    return summoners

def get_info_name(info: dict[str, Any], mode: int = 1) -> str:
    if isinstance(info, dict) and all(i in info for i in ["displayName", "gameName", "tagLine"]):
        if info["displayName"] or info["gameName"]:
            if info["gameName"] and info["tagLine"]:
                name: str = info["gameName"] + "#" + info["tagLine"]
            elif not info["tagLine"] and info["gameName"]:
                name = info["gameName"]
            else:
                name = info["displayName"]
        else: #新玩家属于这种类型（This case matches new players）
            if mode == 2: #仅用于设置召唤师数据保存路径（Designed to set the summoner name directory）
                name = "0. 新玩家\\" + str(info["puuid"])
            elif mode == 3: #仅用于设置召唤师数据保存路径（Designed to set the summoner name directory）
                name = "0. New Player\\" + str(info["puuid"])
            else:
                name = info["puuid"]
    else:
        print("您的召唤师信息格式有误！\nERROR format of summoner information!")
        name = ""
    return name
