from BotServer.MainServer import MainServer
from ApiServer.ExternalApi import start_api_server
import Config.ConfigServer as Cs
from OutPut.outPut import *
from cprint import cprint
from PushServer.PushMainServer import PushMainServer

Bot_Logo = """
███▄▄▄▄      ▄██████▄   ▄████████ ▀█████████▄   ▄██████▄      ███     
███▀▀▀██▄   ███    ███ ███    ███   ███    ███ ███    ███ ▀█████████▄ 
███   ███   ███    █▀  ███    █▀    ███    ███ ███    ███    ▀███▀▀██ 
███   ███  ▄███        ███         ▄███▄▄▄██▀  ███    ███     ███   ▀ 
███   ███ ▀▀███ ████▄  ███        ▀▀███▀▀▀██▄  ███    ███     ███     
███   ███   ███    ███ ███    █▄    ███    ██▄ ███    ███     ███     
███   ███   ███    ███ ███    ███   ███    ███ ███    ███     ███     
 ▀█   █▀    ████████▀  ████████▀  ▄█████████▀   ▀██████▀     ▄████▀   
     Version: V2.3
     Author: NGC660安全实验室(eXM/云山) 
"""

def main():
    # 打印Logo
    cprint.info(Bot_Logo.strip())
    
    # 初始化机器人服务
    bot = MainServer()
    
    # 启动外部API服务
    config_data = Cs.returnConfigData()
    API_CONFIG = config_data.get('apiConfig', {})
    if API_CONFIG:
        op(f'[*]: 正在启动外部API服务...')
        start_api_server(bot.wcf)
        op(f'[+]: 外部API服务启动成功！')
    else:
        op(f'[!]: 未配置外部API服务，如需使用请在Config.yaml中添加apiConfig配置')
    
    try:
        # 启动机器人消息处理
        bot.processMsg()
    except KeyboardInterrupt:
        bot.Pms.stopPushServer()
        op(f'[*]: 检测到键盘中断，正在停止服务...')

if __name__ == '__main__':
    main()
