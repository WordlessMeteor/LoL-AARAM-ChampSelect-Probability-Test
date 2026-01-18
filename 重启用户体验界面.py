from lcu_driver import Connector
from lcu_driver.connection import Connection
from typing import Any

#=============================================================================
# * 声明（Declaration）
#=============================================================================
# 作者（Author）：          WordlessMeteor
# 主页（Home page）：       https://github.com/WordlessMeteor/LoL-DIY-Programs/
# 鸣谢（Acknowledgement）： XHXIAIEIN
# 更新（Last update）：     2026/01/07
#=============================================================================

#-----------------------------------------------------------------------------
# 工具库（Tool library）
#-----------------------------------------------------------------------------
#  - lcu-driver 
#    https://github.com/sousa-andre/lcu-driver
#-----------------------------------------------------------------------------

connector: Connector = Connector()

#-----------------------------------------------------------------------------
# 重启用户体验界面（Restart ux）
#-----------------------------------------------------------------------------
async def kill_and_restart_ux(connection: Connection):
    response: dict[str, Any] | None = await (await connection.request("POST", "/riotclient/kill-and-restart-ux")).json()
    if response == None:
        print("已重启英雄联盟用户体验界面。\nRestarted the League Client ux.")

#-----------------------------------------------------------------------------
# websocket
#-----------------------------------------------------------------------------
@connector.ready
async def connect(connection: Connection):
    await kill_and_restart_ux(connection)


#-----------------------------------------------------------------------------
# Main
#-----------------------------------------------------------------------------

connector.start()
