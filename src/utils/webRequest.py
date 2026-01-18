from lcu_driver.connection import Connection
import requests
from src.utils.logging import LogManager
from typing import Any
from urllib.parse import urljoin

def requestUrl(method: str, url: str, session: requests.sessions.Session | None = None, log: LogManager | None = None, verbose: bool = True, **kwargs: Any) -> tuple[requests.models.Response, int, requests.sessions.Session]:
    if session == None:
        session = requests.Session()
        # session.trust_env = False
    if log == None:
        log = LogManager()
    logPrint = log.logPrint
    retry: int = 0
    while True:
        retry += 1
        try:
            source: requests.Response = session.request(method, url, **kwargs)
        except Exception as e:
            session = requests.Session()
            if retry > 5:
                source = requests.Response() #这只是为了保持代码类型检查的一致性（This is meant to keep consistency for code type checking）
                source.status_code = -1
                # session.trust_env = False
                break
            if isinstance(e, requests.exceptions.SSLError):
                if "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol" in str(e):
                    logPrint(f"违反协议导致读取中断！正在尝试第{retry}次重新获取数据！\nEOF occurred in violation of protocol! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
                elif "certificate verify failed" in str(e):
                    logPrint(f"SSL证书验证失败！正在尝试第{retry}次重新获取数据！\nSSL certificate verify failed! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
                elif "Max retries exceeded with url" in str(e):
                    logPrint(f"请求数量超过限制！正在尝试第{retry}次重新获取数据！\nMax retries exceed with url! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            elif isinstance(e, requests.exceptions.ProxyError):
                logPrint(f"无法连接到代理！正在尝试第{retry}次重新获取数据！\nCannot connect to proxy! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            elif isinstance(e, requests.exceptions.ChunkedEncodingError):
                logPrint(f"接收数据块长度不正确导致连接中断！正在尝试第{retry}次重新获取数据！\nConnection broken: InvalidChunkLength. Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            elif isinstance(e, requests.exceptions.ConnectionError):
                if "Failed to establish a new connection: [Errno 11001] getaddrinfo failed" in str(e):
                    logPrint(f"无法获取网址信息，因此无法建立连接！正在尝试第{retry}次重新获取数据！\nCannot get address information, so connection can't be established! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
                else:
                    logPrint(f"由于远程服务器端无响应，连接已关闭！正在尝试第{retry}次重新获取数据！\nRemote end closed connection without response. Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            elif isinstance(e, requests.exceptions.ReadTimeout):
                logPrint(f"读取超时！正在尝试第{retry}次重新获取数据！\nRead time out! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            else:
                logPrint(e)
                logPrint(f"请求失败！正在尝试第{retry}次重新获取数据！\nRequest failed! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
        else:
            try:
                source.raise_for_status()
            except Exception as e:
                session = requests.Session()
                # session.trust_env = False
                if retry > 5:
                    break
                if isinstance(e, requests.exceptions.HTTPError):
                    if e.response.status_code in {403, 404}:
                        return (source, e.response.status_code, session)
                else:
                    logPrint(e)
                    logPrint(f"请求失败！正在尝试第{retry}次重新获取数据！\nRequest failed! Trying to recapture the data with url: {url}. Time(s) tried: {retry}", write_time = False)
            else:
                return (source, source.status_code, session)
    return (source, source.status_code, session)

class SGPSession:
    def __init__(self, token: str | None = None, client_settings: dict[str, Any] | None = None, log: LogManager | None = None, verbose: bool = True) -> None:
        self.userInfoToken: str = "" if token == None else token
        self._headers: dict[str, str] = {"Authorization": f"Bearer {token}", "Content-type": "application/json"}
        self.session: requests.Session = requests.Session()
        # self.session.trust_env = False #忽略系统代理设置（Bypass system proxy）
        self.log: LogManager = log or LogManager()
        self.verbose: bool = verbose
        if isinstance(client_settings, dict) and "lol.client_settings.league_edge.url" in client_settings:
            self.client_settings: dict[str, Any] = client_settings
    
    def __repr__(self) -> str:
        return (f'SGPSession("{self.userInfoToken}")')
    
    def setLog(self, log: LogManager):
        self.log = log
    
    async def update_userInfo_token(self, connection: Connection) -> None:
        token: str = await (await connection.request("GET", "/lol-league-session/v1/league-session-token")).json()
        if isinstance(token, str):
            self.userInfoToken = token
            self._headers["Authorization"] = f"Bearer {token}"
        else:
            self.log.logPrint(token, verbose = self.verbose)
            if token["httpStatus"] == 404 and token["message"] == "NOT_FOUND":
                self.log.logPrint("未找到用户信息令牌。请检查您的登录状态。\nUser info token not found. Please check your login status.")
            else:
                self.log.logPrint("令牌更新失败！\nToken update failed!", verbose = self.verbose)
    
    async def init(self, connection: Connection) -> None:
        await self.update_userInfo_token(connection)
        self.client_settings = await (await connection.request("GET", "/client-config/v2/namespace/lol.client_settings")).json()
        self.session = requests.Session()
        # self.session.headers.update({"X-Riot-Spectator-Key": "YOUR_SPECTATOR_KEY_HERE"})
        # self.session.trust_env = False #忽略系统代理设置（Bypass system proxy）
    
    async def request(self, connection: Connection, method: str, endpoint: str, headers: dict[str, str] | None = None, verbose: bool = True, **kwargs: Any) -> requests.models.Response: #参考了lcu_driver的代码（Referred to code in `lcu_driver`）
        #参数预处理（Parameter preparation）
        if not hasattr(self, "client_settings"):
            self.client_settings = await (await connection.request("GET", "/client-config/v2/namespace/lol.client_settings")).json()
        if endpoint.startswith("https://"):
            url: str = endpoint
        elif endpoint.startswith(("/login-queue", "/session-external", "/services", "/match-history-query")):
            url = urljoin(self.client_settings.get("lol.client_settings.account_verification_edge.url", self.client_settings["lol.client_settings.league_edge.url"]), endpoint)
        else:
            url = urljoin(self.client_settings["lol.client_settings.league_edge.url"], endpoint)
        if headers == None:
            headers = {}
        response, status, self.session = requestUrl(method, url, session = self.session, headers = self._headers | headers, log = self.log, verbose = True, **kwargs)
        try:
            body: dict[str, Any] = response.json()
        except requests.exceptions.JSONDecodeError:
            self.log.logPrint("在转换为json对象时发生了错误。\nAn error occurred when converting the response body into a json object.", verbose = self.verbose)
        except AttributeError: #AttributeError: 'NoneType' object has no attribute 'json'
            pass
        else:
            if body == {"httpStatus": 400, "message": "A newer more recent session has been processed for this player", "errorCode": "INVALID_PLAYER_SESSION"} or body == {"status": {"message": "Unauthorized", "status_code": 401}}:
                self.log.logPrint("令牌已过期。正在更新令牌……\nToken has expired. Updating the token ...", verbose = self.verbose)
                await self.update_userInfo_token(connection)
                response = self.session.request(method = method, url = url, headers = self._headers | headers, **kwargs)
        return response

def sgpConnect(method: str, url: str, token: str, extra_headers: dict[str, str] | None = None, session: requests.Session | None = None, **kwargs: Any) -> tuple[dict[str, Any], requests.Session]: #一个单独用来调试SGP API的函数（A function specially designed to debug SGP API）
    if session == None:
        session = requests.Session()
        # session.trust_env = False #忽略系统代理设置（Bypass system proxy）
    if extra_headers == None:
        extra_headers = {}
    result: dict[str, Any] = {"status_code": 0, "json": None, "error": None}
    headers = {"Authorization": f"Bearer {token}", "Content-type": "application/json"}
    try:
        response = session.request(method, url, headers = headers | extra_headers, **kwargs)
    except requests.exceptions.SSLError as ssl_error:
        result["status_code"] = -1
        result["error"] = str(ssl_error)
    else:
        result["status_code"] = response.status_code
        result["json"] = response.json()
    return (result, session)
