from flask import Flask, request, jsonify
import Config.ConfigServer as Cs
from OutPut.outPut import *
import logging
import threading
import os
import requests as req
import tempfile
import uuid
import json
from urllib.parse import urlparse

# 配置日志
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从配置文件读取API设置
config_data = Cs.returnConfigData()
API_CONFIG = config_data.get('apiConfig', {})
API_SECRET = API_CONFIG.get('apiKey', 'your_api_secret_here')
API_HOST = API_CONFIG.get('host', '127.0.0.1')
API_PORT = API_CONFIG.get('port', 8000)

# 创建Flask应用
app = Flask(__name__)

# 添加一个请求前处理函数，处理不同的Content-Type
@app.before_request
def handle_content_type():
    if request.method == 'POST':
        content_type = request.headers.get('Content-Type', '')
        if 'text/plain' in content_type and request.data:
            try:
                # 尝试将text/plain内容解析为JSON
                data = json.loads(request.data)
                # 将解析后的数据存储在request.json_data中
                request.json_data = data
            except json.JSONDecodeError as e:
                logger.error(f"无法解析JSON数据: {str(e)}")
                return jsonify({"error": "无效的JSON数据"}), 400

# 获取请求数据的辅助函数
def get_request_json():
    if hasattr(request, 'json_data'):
        return request.json_data
    return request.get_json()

class ExternalApiServer:
    def __init__(self, wcf):
        self.wcf = wcf
        self.api_key = API_SECRET
        
    def verify_api_key(self, request_api_key):
        """验证API密钥"""
        return request_api_key == self.api_key
        
    def run_server(self, host=API_HOST, port=API_PORT):
        """启动API服务器"""
        try:
            op(f'[*]: 启动外部API服务器 {host}:{port}')
            app.run(host=host, port=port, debug=False, threaded=True)
        except Exception as e:
            op(f'[-]: 启动外部API服务器失败: {str(e)}')

# 创建全局变量存储wcf实例
wcf_instance = None

@app.route('/send_text', methods=['POST'])
def send_text():
    """
    发送文本消息
    :param receiver: room_id 或 wxid
    :param content: 消息内容
    :param at_list: 可选，@的用户wxid列表
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    content = data.get('content')
    at_list = data.get('at_list', [])
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not content:
        return jsonify({"error": "缺少 receiver 或 content 参数"}), 400

    try:
        logger.info(f"尝试发送文本: 接收者={receiver}, 内容长度={len(content)}")
        if at_list:
            at_users = []
            for user in at_list:
                at_users.append({"nickname": "", "wxid": user})
            logger.info(f"发送@消息，@用户: {at_list}")
            wcf_instance.send_room_at_msg(content, receiver, at_users)
        else:
            wcf_instance.send_text(content, receiver)
        logger.info(f"文本发送请求已处理")
        return jsonify({"status": "成功", "message": "文本消息发送请求已处理"}), 200
    except Exception as e:
        logger.error(f"发送文本消息失败: {str(e)}")
        return jsonify({"error": f"发送文本消息失败: {str(e)}"}), 500

@app.route('/send_image', methods=['POST'])
def send_image():
    """
    发送图片消息
    :param receiver: room_id 或 wxid
    :param path: 图片路径或URL
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    path = data.get('path')
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not path:
        return jsonify({"error": "缺少 receiver 或 path 参数"}), 400

    try:
        # 添加调试信息
        logger.info(f"尝试发送图片: 接收者={receiver}, 路径={path}")
        
        # 检查是否是URL
        is_url = path.startswith(('http://', 'https://'))
        local_path = path
        temp_file = None
        
        if is_url:
            try:
                # 下载图片到临时文件
                logger.info(f"检测到URL，正在下载图片: {path}")
                response = req.get(path, stream=True, timeout=30)
                response.raise_for_status()
                
                # 从URL中提取文件名
                url_path = urlparse(path).path
                file_ext = os.path.splitext(url_path)[1]
                if not file_ext:
                    file_ext = '.png'  # 默认扩展名
                
                # 创建临时文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
                temp_file.close()
                local_path = temp_file.name
                
                # 保存图片到临时文件
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"图片已下载到临时文件: {local_path}")
            except Exception as e:
                logger.error(f"下载图片失败: {str(e)}")
                return jsonify({"error": f"下载图片失败: {str(e)}"}), 400
        
        # 检查文件是否存在
        if not os.path.exists(local_path):
            logger.error(f"图片文件不存在: {local_path}")
            return jsonify({"error": f"图片文件不存在: {local_path}"}), 400
            
        # 检查文件是否可读
        if not os.access(local_path, os.R_OK):
            logger.error(f"图片文件无法读取(权限问题): {local_path}")
            return jsonify({"error": f"图片文件无法读取(权限问题): {local_path}"}), 400
            
        # 检查文件大小
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            logger.error(f"图片文件大小为0: {local_path}")
            return jsonify({"error": f"图片文件大小为0: {local_path}"}), 400
            
        logger.info(f"图片文件检查通过: 存在={os.path.exists(local_path)}, 大小={file_size}字节")
        
        # 尝试发送图片
        wcf_instance.send_image(local_path, receiver)
        
        # 忽略返回值，只要没有抛出异常就认为成功
        logger.info(f"图片发送请求已处理: {path}")
        
        # 如果是临时文件，在发送后删除
        if is_url and temp_file:
            try:
                os.unlink(local_path)
                logger.info(f"临时文件已删除: {local_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {str(e)}")
        
        return jsonify({"status": "成功", "message": "图片消息发送请求已处理"}), 200
    except Exception as e:
        # 如果是临时文件，确保在出错时也删除
        if 'is_url' in locals() and is_url and 'local_path' in locals() and os.path.exists(local_path):
            try:
                os.unlink(local_path)
            except:
                pass
        
        logger.error(f"发送图片消息失败: {str(e)}")
        return jsonify({"error": f"发送图片消息失败: {str(e)}"}), 500

@app.route('/send_file', methods=['POST'])
def send_file():
    """
    发送文件消息
    :param receiver: room_id 或 wxid
    :param path: 文件路径或URL
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    path = data.get('path')
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not path:
        return jsonify({"error": "缺少 receiver 或 path 参数"}), 400

    try:
        # 添加调试信息
        logger.info(f"尝试发送文件: 接收者={receiver}, 路径={path}")
        
        # 检查是否是URL
        is_url = path.startswith(('http://', 'https://'))
        local_path = path
        temp_file = None
        
        if is_url:
            try:
                # 下载文件到临时文件
                logger.info(f"检测到URL，正在下载文件: {path}")
                response = req.get(path, stream=True, timeout=30)
                response.raise_for_status()
                
                # 从URL中提取文件名
                url_path = urlparse(path).path
                file_name = os.path.basename(url_path)
                if not file_name:
                    file_name = f"file_{uuid.uuid4().hex}"
                
                # 创建临时文件
                temp_dir = tempfile.gettempdir()
                local_path = os.path.join(temp_dir, file_name)
                
                # 保存文件到临时文件
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"文件已下载到临时文件: {local_path}")
            except Exception as e:
                logger.error(f"下载文件失败: {str(e)}")
                return jsonify({"error": f"下载文件失败: {str(e)}"}), 400
        
        # 检查文件是否存在
        if not os.path.exists(local_path):
            logger.error(f"文件不存在: {local_path}")
            return jsonify({"error": f"文件不存在: {local_path}"}), 400
            
        # 检查文件是否可读
        if not os.access(local_path, os.R_OK):
            logger.error(f"文件无法读取(权限问题): {local_path}")
            return jsonify({"error": f"文件无法读取(权限问题): {local_path}"}), 400
            
        # 检查文件大小
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            logger.error(f"文件大小为0: {local_path}")
            return jsonify({"error": f"文件大小为0: {local_path}"}), 400
            
        logger.info(f"文件检查通过: 存在={os.path.exists(local_path)}, 大小={file_size}字节")
        
        # 尝试发送文件
        wcf_instance.send_file(local_path, receiver)
        
        # 忽略返回值，只要没有抛出异常就认为成功
        logger.info(f"文件发送请求已处理: {path}")
        
        # 如果是临时文件，在发送后删除
        if is_url and os.path.exists(local_path):
            try:
                os.unlink(local_path)
                logger.info(f"临时文件已删除: {local_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {str(e)}")
        
        return jsonify({"status": "成功", "message": "文件消息发送请求已处理"}), 200
    except Exception as e:
        # 如果是临时文件，确保在出错时也删除
        if 'is_url' in locals() and is_url and 'local_path' in locals() and os.path.exists(local_path):
            try:
                os.unlink(local_path)
            except:
                pass
        
        logger.error(f"发送文件消息失败: {str(e)}")
        return jsonify({"error": f"发送文件消息失败: {str(e)}"}), 500

@app.route('/send_video', methods=['POST'])
def send_video():
    """
    发送视频消息
    :param receiver: room_id 或 wxid
    :param path: 视频文件路径或URL
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    path = data.get('path')
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not path:
        return jsonify({"error": "缺少 receiver 或 path 参数"}), 400

    try:
        # 添加调试信息
        logger.info(f"尝试发送视频: 接收者={receiver}, 路径={path}")
        
        # 检查是否是URL
        is_url = path.startswith(('http://', 'https://'))
        local_path = path
        temp_file = None
        
        if is_url:
            try:
                # 下载视频到临时文件
                logger.info(f"检测到URL，正在下载视频: {path}")
                response = req.get(path, stream=True, timeout=60)  # 视频可能较大，增加超时时间
                response.raise_for_status()
                
                # 从URL中提取文件名
                url_path = urlparse(path).path
                file_ext = os.path.splitext(url_path)[1]
                if not file_ext:
                    file_ext = '.mp4'  # 默认扩展名
                
                # 创建临时文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
                temp_file.close()
                local_path = temp_file.name
                
                # 保存视频到临时文件
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"视频已下载到临时文件: {local_path}")
            except Exception as e:
                logger.error(f"下载视频失败: {str(e)}")
                return jsonify({"error": f"下载视频失败: {str(e)}"}), 400
        
        # 检查文件是否存在
        if not os.path.exists(local_path):
            logger.error(f"视频文件不存在: {local_path}")
            return jsonify({"error": f"视频文件不存在: {local_path}"}), 400
            
        # 检查文件是否可读
        if not os.access(local_path, os.R_OK):
            logger.error(f"视频文件无法读取(权限问题): {local_path}")
            return jsonify({"error": f"视频文件无法读取(权限问题): {local_path}"}), 400
            
        # 检查文件大小
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            logger.error(f"视频文件大小为0: {local_path}")
            return jsonify({"error": f"视频文件大小为0: {local_path}"}), 400
            
        logger.info(f"视频文件检查通过: 存在={os.path.exists(local_path)}, 大小={file_size}字节")
        
        # 尝试发送视频
        wcf_instance.send_video(local_path, receiver)
        
        # 忽略返回值，只要没有抛出异常就认为成功
        logger.info(f"视频发送请求已处理: {path}")
        
        # 如果是临时文件，在发送后删除
        if is_url and temp_file:
            try:
                os.unlink(local_path)
                logger.info(f"临时文件已删除: {local_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {str(e)}")
        
        return jsonify({"status": "成功", "message": "视频消息发送请求已处理"}), 200
    except Exception as e:
        # 如果是临时文件，确保在出错时也删除
        if 'is_url' in locals() and is_url and 'local_path' in locals() and os.path.exists(local_path):
            try:
                os.unlink(local_path)
            except:
                pass
        
        logger.error(f"发送视频消息失败: {str(e)}")
        return jsonify({"error": f"发送视频消息失败: {str(e)}"}), 500

@app.route('/send_card', methods=['POST'])
def send_card():
    """
    发送名片消息
    :param receiver: room_id 或 wxid
    :param wxid: 被分享的名片wxid
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    wxid = data.get('wxid')
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not wxid:
        return jsonify({"error": "缺少 receiver 或 wxid 参数"}), 400

    try:
        logger.info(f"尝试发送名片: 接收者={receiver}, 名片wxid={wxid}")
        wcf_instance.send_card(wxid, receiver)
        logger.info(f"名片发送请求已处理: wxid={wxid}")
        return jsonify({"status": "成功", "message": "名片消息发送请求已处理"}), 200
    except Exception as e:
        logger.error(f"发送名片消息失败: {str(e)}")
        return jsonify({"error": f"发送名片消息失败: {str(e)}"}), 500

@app.route('/send_link', methods=['POST'])
def send_link():
    """
    发送链接消息
    :param receiver: room_id 或 wxid
    :param url: 链接URL
    :param title: 链接标题
    :param desc: 链接描述(可选)
    :param api_key: API密钥
    """
    data = get_request_json()
    receiver = data.get('receiver')
    url = data.get('url')
    title = data.get('title')
    desc = data.get('desc', '')
    api_key = data.get('api_key')

    if not api_key or not ExternalApiServer(wcf_instance).verify_api_key(api_key):
        return jsonify({"error": "无效的API密钥"}), 401

    if not receiver or not url or not title:
        return jsonify({"error": "缺少 receiver、url 或 title 参数"}), 400

    try:
        logger.info(f"尝试发送链接: 接收者={receiver}, 链接={url}")
        xml_content = f'''<?xml version="1.0"?>
        <msg>
            <appmsg appid="" sdkver="0">
                <title>{title}</title>
                <des>{desc}</des>
                <url>{url}</url>
                <type>5</type>
            </appmsg>
        </msg>'''
        wcf_instance.send_xml(xml_content, receiver)
        logger.info(f"链接发送请求已处理: url={url}")
        return jsonify({"status": "成功", "message": "链接消息发送请求已处理"}), 200
    except Exception as e:
        logger.error(f"发送链接消息失败: {str(e)}")
        return jsonify({"error": f"发送链接消息失败: {str(e)}"}), 500

def start_api_server(wcf):
    """启动外部API服务器"""
    global wcf_instance
    wcf_instance = wcf
    
    api_server = ExternalApiServer(wcf)
    server_thread = threading.Thread(target=api_server.run_server)
    server_thread.daemon = True
    server_thread.start()
    op(f'[+]: 外部API服务器线程已启动')
    return server_thread 