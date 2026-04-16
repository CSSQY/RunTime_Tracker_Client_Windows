import sys
import os
import time
import requests
import json
import logging
import winreg
from threading import Thread
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, SubtitleLabel, 
    ComboBox, PrimaryPushButton, SwitchButton, 
    Theme, setTheme, isDarkTheme, InfoBar, InfoBarPosition, FluentIcon
)
from qfluentwidgets.components.navigation.navigation_interface import NavigationInterface

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，区分开发环境和打包环境"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))

def get_user_data_path(relative_path):
    """获取用户数据文件的绝对路径（配置、日志等需要修改的文件）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        base_path = exe_dir
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))

# 配置日志
import datetime

# 创建logs目录
log_dir = get_user_data_path('logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 生成日志文件名
log_filename = os.path.join(log_dir, f"runtime_tracker_{datetime.datetime.now().strftime('%Y-%m-%d')}.log")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置参数
API_URL = "https://api.example.com"
SECRET_KEY = "your_secret_key"
DEVICE_ID = "your_device_id"

# 配置文件路径
CONFIG_FILE = get_user_data_path('config.json')

# 默认配置
DEFAULT_CONFIG = {
    "api_url": API_URL,
    "secret_key": SECRET_KEY,
    "device_id": DEVICE_ID,
    "report_enabled": True,
    "monitor_interval": 1,
    "theme": 0  # 0: 跟随系统, 1: 浅色, 2: 深色
}

# 全局配置
config = {}

def load_config():
    """加载配置"""
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info("配置加载成功")
        else:
            config = DEFAULT_CONFIG.copy()
            save_config()
            logger.info("使用默认配置")
    except Exception as e:
        logger.error(f"加载配置失败: {str(e)}")
        config = DEFAULT_CONFIG.copy()

def save_config():
    """保存配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("配置保存成功")
    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")

def is_report_enabled():
    """检查是否启用了上报功能"""
    return config.get("report_enabled", False)

# 上一次记录的应用程序名称
last_app = None
# 记录系统是否处于休眠状态
system_suspended = False
# 记录屏幕是否关闭的状态
screen_off = False

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒

# 电池状态获取
import ctypes
from ctypes import wintypes

class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ('ACLineStatus', ctypes.c_byte),
        ('BatteryFlag', ctypes.c_byte),
        ('BatteryLifePercent', ctypes.c_byte),
        ('Reserved1', ctypes.c_byte),
        ('BatteryLifeTime', ctypes.c_ulong),
        ('BatteryFullLifeTime', ctypes.c_ulong)
    ]

def get_battery_status():
    """获取电池状态"""
    status = SYSTEM_POWER_STATUS()
    if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        # 检查是否无电池 (BatteryFlag 为 255)
        if status.BatteryFlag == 255:
            return -1, False
        # ACLineStatus: 0 = 电池供电, 1 = 交流供电
        is_charging = status.ACLineStatus == 1
        # BatteryLifePercent: 0-100
        battery_level = status.BatteryLifePercent
        return battery_level, is_charging
    return None, None

def send_api_request(payload, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY):
    """发送API请求，带重试机制和响应验证"""
    for attempt in range(max_retries):
        try:
            api_url = config.get("api_url", API_URL)
            response = requests.post(api_url, json=payload, timeout=5)
            
            # 验证响应状态码
            if response.status_code == 200:
                # 验证响应格式
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and response_data.get('success') is True:
                        logger.info(f"API请求成功: {payload.get('app_name', '未知应用')}")
                        return True, response_data
                    else:
                        logger.warning(f"API响应格式不正确: {response_data}")
                        return False, response_data
                except json.JSONDecodeError:
                    logger.error(f"API响应不是有效的JSON: {response.text}")
                    return False, None
            else:
                logger.warning(f"API请求失败，状态码: {response.status_code}, 响应: {response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求异常 (尝试 {attempt+1}/{max_retries}): {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    
    logger.error(f"API请求失败，已达到最大重试次数")
    return False, None

def report_system_status(app_name, running):
    """上报系统状态"""
    # 检查是否启用上报
    if not config.get("report_enabled", True):
        logger.info(f"上报已禁用: {app_name}, running: {running}")
        return False
    
    try:
        # 获取电池状态
        battery_level, is_charging = get_battery_status()
        
        payload = {
            "secret": config.get("secret_key", SECRET_KEY),
            "device": config.get("device_id", DEVICE_ID),
            "app_name": app_name,
            "running": running
        }
        
        # 只有在获取到电池状态且不是无电池时才添加到 payload
        if battery_level is not None and battery_level != -1:
            payload["batteryLevel"] = battery_level
            payload["isCharging"] = is_charging
        
        success, response_data = send_api_request(payload)
        if success:
            logger.info(f"状态上报成功: {app_name}, running: {running}")
            return True
        else:
            logger.warning(f"状态上报失败: {app_name}")
            return False
    except Exception as e:
        logger.error(f"状态上报异常: {app_name}, 错误: {str(e)}")
        return False

def report_app_change(current_app):
    """上报应用程序变化"""
    # 检查是否启用上报
    if not config.get("report_enabled", True):
        logger.info(f"上报已禁用: {current_app}")
        return
    
    global last_app

    if current_app != last_app:
        # 根据应用名称判断 running 状态
        # 如果是待机、关机、屏幕关闭等状态，running 为 False，否则为 True
        running_status = True
        if current_app in ["设备待机", "设备关机", "系统休眠", "屏幕关闭"]:
            running_status = False
        
        try:
            # 获取电池状态
            battery_level, is_charging = get_battery_status()
            
            payload = {
                "secret": config.get("secret_key", SECRET_KEY),
                "device": config.get("device_id", DEVICE_ID),
                "app_name": current_app,
                "running": running_status
            }
            
            # 只有在获取到电池状态时才添加到 payload
            if battery_level is not None:
                payload["batteryLevel"] = battery_level
                payload["isCharging"] = is_charging

            success, response_data = send_api_request(payload)

            if success:
                logger.info(f"成功上报: {current_app}, running: {running_status}")
                last_app = current_app
            else:
                logger.warning(f"上报失败: {current_app}")

        except Exception as e:
            logger.error(f"发生错误: {str(e)}")

# 应用映射
apps_json_path = None
original_mapping = {}
app_mapping = {}

try:
    apps_json_path = get_resource_path('apps.json')
    
    with open(apps_json_path, 'r', encoding='utf-8') as f:
        original_mapping = json.load(f)
        app_mapping = {k.lower(): v for k, v in original_mapping.items()}
    logger.info("应用映射加载成功")
except FileNotFoundError:
    logger.error(f"错误：文件未找到: {apps_json_path}")
    app_mapping = {}
except json.JSONDecodeError:
    logger.error("错误：JSON格式不正确")
    app_mapping = {}
except Exception as e:
    logger.error(f"未知错误：{str(e)}")
    app_mapping = {}

def get_mapped_app_name(exe_name):
    """根据对照表获取映射的应用名称"""
    exe_name_lower = exe_name.lower()
    return app_mapping.get(exe_name_lower, exe_name)

# 应用监控线程
class AppMonitorThread(QThread):
    app_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.last_logged_interval = None
    
    def run(self):
        while True:
            try:
                current_app = self.get_foreground_app()
                self.app_changed.emit(current_app)
                report_app_change(current_app)
                # 使用配置中的监控间隔
                monitor_interval = config.get("monitor_interval", 1)
                # 验证监控间隔是否为有效数值
                if not isinstance(monitor_interval, (int, float)) or monitor_interval <= 0:
                    monitor_interval = 1
                    logger.warning(f"监控间隔配置无效，使用默认值: {monitor_interval}秒")
                # 当日志间隔变化时记录日志
                if self.last_logged_interval != monitor_interval:
                    logger.info(f"当前监控间隔: {monitor_interval}秒")
                    self.last_logged_interval = monitor_interval
                time.sleep(monitor_interval)  # 根据配置的间隔检查
            except Exception as e:
                logger.error(f"监控线程错误: {str(e)}")
                # 发生错误时使用默认间隔
                time.sleep(1)
    
    def get_foreground_app(self):
        """使用win32api获取前台应用窗口"""
        global system_suspended, screen_off

        # 如果系统处于休眠状态，直接返回待机状态
        if system_suspended:
            return "设备待机"

        # 如果屏幕关闭，返回屏幕关闭
        if screen_off:
            return "屏幕关闭"

        try:
            # 尝试使用psutil获取前台进程
            import psutil
            import win32gui
            import win32process
            
            # 获取前台窗口句柄
            window = win32gui.GetForegroundWindow()
            if not window:
                return "桌面"

            # 获取窗口标题
            window_title = win32gui.GetWindowText(window)
            # 获取进程ID
            _, pid = win32process.GetWindowThreadProcessId(window)

            if not pid:
                return "桌面"

            try:
                process = psutil.Process(pid)
                exe_filename = process.name()
                
                # 使用映射名称
                mapped_name = get_mapped_app_name(exe_filename)
                # 如果映射后还是原文件名，尝试使用窗口标题进一步识别
                if mapped_name == exe_filename and window_title:
                    # 对于常见系统窗口的特殊处理
                    title_lower = window_title.lower()
                    if "任务管理器" in window_title or "task manager" in title_lower:
                        return "任务管理器"
                    elif "设置" in window_title or "settings" in title_lower:
                        return "系统设置"
                    elif "控制面板" in window_title or "control panel" in title_lower:
                        return "控制面板"
                    elif "设备管理器" in window_title or "device manager" in title_lower:
                        return "设备管理器"
                    elif "磁盘管理" in window_title or "disk management" in title_lower:
                        return "磁盘管理"
                    elif "服务" in window_title or "services" in title_lower:
                        return "服务"
                    elif "事件查看器" in window_title or "event viewer" in title_lower:
                        return "事件查看器"
                    elif "任务计划程序" in window_title or "task scheduler" in title_lower:
                        return "任务计划程序"
                    elif "计算机管理" in window_title or "computer management" in title_lower:
                        return "计算机管理"
                    elif "本地组策略编辑器" in window_title or "group policy" in title_lower:
                        return "本地组策略编辑器"
                    elif "注册表编辑器" in window_title or "registry editor" in title_lower:
                        return "注册表编辑器"
                    elif "系统配置" in window_title or "system configuration" in title_lower:
                        return "系统配置"
                    elif "命令提示符" in window_title or "command prompt" in title_lower:
                        return "命令提示符"
                    elif "powershell" in title_lower:
                        return "PowerShell"
                    elif "windows terminal" in title_lower:
                        return "Windows Terminal"
                    elif "文件资源管理器" in window_title or "file explorer" in title_lower:
                        return "文件资源管理器"
                    elif "记事本" in window_title or "notepad" in title_lower:
                        return "记事本"
                    elif "写字板" in window_title or "wordpad" in title_lower:
                        return "写字板"
                    elif "画图" in window_title or "paint" in title_lower:
                        return "画图"
                    elif "计算器" in window_title or "calculator" in title_lower:
                        return "计算器"
                    elif "截图工具" in window_title or "snipping tool" in title_lower:
                        return "截图工具"
                    elif "便笺" in window_title or "sticky notes" in title_lower:
                        return "便笺"
                    elif "OneNote" in window_title:
                        return "OneNote"
                    elif "Outlook" in window_title:
                        return "Outlook"
                    elif "Word" in window_title:
                        return "Word"
                    elif "Excel" in window_title:
                        return "Excel"
                    elif "PowerPoint" in window_title:
                        return "PowerPoint"
                    elif "Edge" in window_title:
                        return "Edge浏览器"
                    elif "Chrome" in window_title:
                        return "Chrome浏览器"
                    elif "Firefox" in window_title:
                        return "Firefox浏览器"
                    elif "Opera" in window_title:
                        return "Opera浏览器"
                    elif "Brave" in window_title:
                        return "Brave浏览器"
                    elif "Vivaldi" in window_title:
                        return "Vivaldi浏览器"
                    elif "Safari" in window_title:
                        return "Safari浏览器"
                return mapped_name

            except Exception as e:
                logger.error(f"获取进程信息失败: {str(e)}")
                # 权限不足时，尝试使用窗口标题作为备用
                if window_title:
                    # 对于已知的系统程序，返回友好名称
                    title_lower = window_title.lower()
                    if "任务管理器" in window_title or "task manager" in title_lower:
                        return "任务管理器"
                    elif "设置" in window_title or "settings" in title_lower:
                        return "系统设置"
                    elif "控制面板" in window_title or "control panel" in title_lower:
                        return "控制面板"
                    elif "设备管理器" in window_title or "device manager" in title_lower:
                        return "设备管理器"
                    elif "磁盘管理" in window_title or "disk management" in title_lower:
                        return "磁盘管理"
                    elif "服务" in window_title or "services" in title_lower:
                        return "服务"
                    elif "事件查看器" in window_title or "event viewer" in title_lower:
                        return "事件查看器"
                    elif "任务计划程序" in window_title or "task scheduler" in title_lower:
                        return "任务计划程序"
                    elif "计算机管理" in window_title or "computer management" in title_lower:
                        return "计算机管理"
                    elif "本地组策略编辑器" in window_title or "group policy" in title_lower:
                        return "本地组策略编辑器"
                    elif "注册表编辑器" in window_title or "registry editor" in title_lower:
                        return "注册表编辑器"
                    elif "系统配置" in window_title or "system configuration" in title_lower:
                        return "系统配置"
                    elif "命令提示符" in window_title or "command prompt" in title_lower:
                        return "命令提示符"
                    elif "powershell" in title_lower:
                        return "PowerShell"
                    elif "windows terminal" in title_lower:
                        return "Windows Terminal"
                    elif "文件资源管理器" in window_title or "file explorer" in title_lower:
                        return "文件资源管理器"
                    elif "记事本" in window_title or "notepad" in title_lower:
                        return "记事本"
                    elif "写字板" in window_title or "wordpad" in title_lower:
                        return "写字板"
                    elif "画图" in window_title or "paint" in title_lower:
                        return "画图"
                    elif "计算器" in window_title or "calculator" in title_lower:
                        return "计算器"
                    elif "截图工具" in window_title or "snipping tool" in title_lower:
                        return "截图工具"
                    elif "便笺" in window_title or "sticky notes" in title_lower:
                        return "便笺"
                    elif "OneNote" in window_title:
                        return "OneNote"
                    elif "Outlook" in window_title:
                        return "Outlook"
                    elif "Word" in window_title:
                        return "Word"
                    elif "Excel" in window_title:
                        return "Excel"
                    elif "PowerPoint" in window_title:
                        return "PowerPoint"
                    elif "Edge" in window_title:
                        return "Edge浏览器"
                    elif "Chrome" in window_title:
                        return "Chrome浏览器"
                    elif "Firefox" in window_title:
                        return "Firefox浏览器"
                    elif "Opera" in window_title:
                        return "Opera浏览器"
                    elif "Brave" in window_title:
                        return "Brave浏览器"
                    elif "Vivaldi" in window_title:
                        return "Vivaldi浏览器"
                    elif "Safari" in window_title:
                        return "Safari浏览器"
                    # 返回窗口标题
                    return window_title

            return "系统进程"

        except Exception as e:
            logger.error(f"获取前台应用错误: {str(e)}")
            return "未知"

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()
        self.start_monitor()
        self.init_system_tray()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("运行时间跟踪器")
        self.resize(800, 600)
        
        # 创建主页面
        self.home_page = QWidget()
        self.home_page.setObjectName("homePage")
        self.app_mapping_page = QWidget()
        self.app_mapping_page.setObjectName("appMappingPage")
        self.config_page = QWidget()
        self.config_page.setObjectName("configPage")
        self.log_page = QWidget()
        self.log_page.setObjectName("logPage")
        self.about_page = QWidget()
        self.about_page.setObjectName("aboutPage")
        
        # 添加导航项
        self.addSubInterface(self.home_page, FluentIcon.HOME, "主页面")
        self.addSubInterface(self.app_mapping_page, FluentIcon.EDIT, "应用映射")
        self.addSubInterface(self.log_page, FluentIcon.DOCUMENT, "日志")
        self.addSubInterface(self.config_page, FluentIcon.SETTING, "配置", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.about_page, FluentIcon.INFO, "关于", NavigationItemPosition.BOTTOM)
        
        # 初始化页面
        self.init_home_page()
        self.init_app_mapping_page()
        self.init_log_page()
        self.init_config_page()
        self.init_about_page()
        
        # 设置默认页面
        self.navigationInterface.setCurrentItem("homePage")
        
    def init_home_page(self):
        """初始化主页面"""
        from qfluentwidgets import CardWidget, BodyLabel, TitleLabel
        
        layout = QVBoxLayout(self.home_page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # 添加标题
        title = TitleLabel("设备使用情况")
        layout.addWidget(title)
        
        # 添加状态卡片
        status_card = CardWidget(self.home_page)
        status_layout = QVBoxLayout(status_card)
        
        # 当前应用
        app_label = BodyLabel("当前应用: 初始化中...")
        status_layout.addWidget(app_label)
        
        # 电池状态
        battery_label = BodyLabel("电池状态: 初始化中...")
        status_layout.addWidget(battery_label)
        
        # 设备信息
        device_label = BodyLabel(f"设备ID: {config.get('device_id', DEVICE_ID)}")
        status_layout.addWidget(device_label)
        # 保存设备标签引用
        self.device_label = device_label
        
        layout.addWidget(status_card)
        layout.addStretch(1)
        
        # 保存标签引用
        self.app_label = app_label
        self.battery_label = battery_label
        
    def init_log_page(self):
        """初始化日志页面"""
        from qfluentwidgets import (CardWidget, BodyLabel, PrimaryPushButton, ComboBox)
        from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QTextEdit, QFileDialog
        
        layout = QVBoxLayout(self.log_page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # 添加标题
        title = BodyLabel("日志查看")
        layout.addWidget(title)
        
        # 日志文件选择卡片
        log_file_card = CardWidget(self.log_page)
        log_file_layout = QHBoxLayout(log_file_card)
        log_file_label = BodyLabel("选择日志文件:")
        self.log_file_combo = ComboBox()
        self.log_file_combo.currentIndexChanged.connect(self.on_log_file_changed)
        log_file_layout.addWidget(log_file_label)
        log_file_layout.addWidget(self.log_file_combo)
        layout.addWidget(log_file_card)
        
        # 日志内容显示卡片
        log_content_card = CardWidget(self.log_page)
        log_content_layout = QVBoxLayout(log_content_card)
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(QTextEdit.NoWrap)
        
        # 设置日志文本编辑器的颜色以适应主题
        # 根据当前主题设置日志查看器颜色
        if isDarkTheme():
            # 深色主题
            self.log_text_edit.setStyleSheet("background-color: #1e1e1e; color: #f0f0f0;")
        else:
            # 浅色主题
            self.log_text_edit.setStyleSheet("background-color: #ffffff; color: #000000;")
        
        log_content_layout.addWidget(self.log_text_edit)
        layout.addWidget(log_content_card, 1)
        
        # 操作按钮布局
        button_layout = QHBoxLayout()
        self.refresh_button = PrimaryPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_log_files)
        self.export_button = PrimaryPushButton("导出")
        self.export_button.clicked.connect(self.export_log)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.export_button)
        layout.addLayout(button_layout)
        
        # 加载日志文件列表
        self.refresh_log_files()
        
        # 初始化日志刷新定时器
        self.log_refresh_timer = QTimer(self)
        self.log_refresh_timer.timeout.connect(self.refresh_log_content)
        self.log_refresh_timer.start(2000)  # 每2秒刷新一次
    
    def init_config_page(self):
        """初始化配置页面"""
        from qfluentwidgets import (LineEdit, ComboBox, SwitchButton, CardWidget, PrimaryPushButton, BodyLabel, TitleLabel)
        from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
        
        layout = QVBoxLayout(self.config_page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # 主题设置卡片
        theme_card = CardWidget(self.config_page)
        theme_layout = QVBoxLayout(theme_card)
        theme_label = BodyLabel("主题设置")
        self.theme_combo = ComboBox()
        self.theme_combo.addItems(["跟随系统", "浅色主题", "深色主题"])
        self.theme_combo.setCurrentIndex(config.get("theme", 0))
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)
        
        # API设置卡片
        api_card = CardWidget(self.config_page)
        api_layout = QVBoxLayout(api_card)
        api_label = BodyLabel("API设置")
        
        # API地址
        api_url_layout = QHBoxLayout()
        api_url_label = BodyLabel("API地址:")
        self.api_url_edit = LineEdit()
        self.api_url_edit.setText(config.get("api_url", API_URL))
        api_url_layout.addWidget(api_url_label)
        api_url_layout.addWidget(self.api_url_edit)
        
        # 密钥
        secret_key_layout = QHBoxLayout()
        secret_key_label = BodyLabel("密钥:")
        self.secret_key_edit = LineEdit()
        self.secret_key_edit.setText(config.get("secret_key", SECRET_KEY))
        secret_key_layout.addWidget(secret_key_label)
        secret_key_layout.addWidget(self.secret_key_edit)
        
        # 设备ID
        device_id_layout = QHBoxLayout()
        device_id_label = BodyLabel("设备ID:")
        self.device_id_edit = LineEdit()
        self.device_id_edit.setText(config.get("device_id", DEVICE_ID))
        device_id_layout.addWidget(device_id_label)
        device_id_layout.addWidget(self.device_id_edit)
        
        api_layout.addWidget(api_label)
        api_layout.addLayout(api_url_layout)
        api_layout.addLayout(secret_key_layout)
        api_layout.addLayout(device_id_layout)
        
        # 监控设置卡片
        monitor_card = CardWidget(self.config_page)
        monitor_layout = QVBoxLayout(monitor_card)
        monitor_label = BodyLabel("监控设置")
        
        # 监控间隔
        monitor_interval_layout = QHBoxLayout()
        monitor_interval_label = BodyLabel("监控间隔(秒):")
        self.monitor_interval_edit = LineEdit()
        self.monitor_interval_edit.setText(str(config.get("monitor_interval", 1)))
        monitor_interval_layout.addWidget(monitor_interval_label)
        monitor_interval_layout.addWidget(self.monitor_interval_edit)
        
        # 上报功能开关
        report_layout = QHBoxLayout()
        report_label = BodyLabel("上报功能:")
        self.report_switch = SwitchButton()
        self.report_switch.setChecked(config.get("report_enabled", True))
        self.report_switch.checkedChanged.connect(self.on_report_toggled)
        report_layout.addWidget(report_label)
        report_layout.addWidget(self.report_switch)
        
        monitor_layout.addWidget(monitor_label)
        monitor_layout.addLayout(monitor_interval_layout)
        monitor_layout.addLayout(report_layout)
        
        # 保存按钮
        save_button = PrimaryPushButton("保存配置")
        save_button.clicked.connect(self.save_config)
        
        # 添加到布局
        layout.addWidget(theme_card)
        layout.addWidget(api_card)
        layout.addWidget(monitor_card)
        layout.addSpacing(20)  # 添加间距
        layout.addWidget(save_button)
        layout.addStretch(1)
    
    def init_app_mapping_page(self):
        """初始化应用映射管理页面"""
        from qfluentwidgets import (CardWidget, BodyLabel, TitleLabel, TableWidget, PushButton, 
                                       PrimaryPushButton, LineEdit, Dialog)
        from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QHeaderView, QAbstractItemView
        
        layout = QVBoxLayout(self.app_mapping_page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # 添加标题
        title = TitleLabel("应用映射管理")
        layout.addWidget(title)
        layout.addSpacing(20)
        
        # 表格卡片
        table_card = CardWidget(self.app_mapping_page)
        table_layout = QVBoxLayout(table_card)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        self.add_button = PrimaryPushButton("新增")
        self.add_button.clicked.connect(self.add_mapping)
        self.edit_button = PushButton("编辑")
        self.edit_button.clicked.connect(self.edit_mapping)
        self.delete_button = PushButton("删除")
        self.delete_button.clicked.connect(self.delete_mapping)
        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self.save_app_mappings)
        
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.save_button)
        
        table_layout.addLayout(button_layout)
        
        # 创建表格
        self.mapping_table = TableWidget()
        self.mapping_table.setColumnCount(2)
        self.mapping_table.setHorizontalHeaderLabels(["可执行文件名", "映射名称"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.mapping_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.load_mappings_to_table()
        
        table_layout.addWidget(self.mapping_table)
        
        layout.addWidget(table_card, 1)
    
    def load_mappings_to_table(self):
        """加载应用映射到表格"""
        global original_mapping
        self.mapping_table.setRowCount(0)
        
        for exe_name, display_name in original_mapping.items():
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            from PyQt5.QtWidgets import QTableWidgetItem
            self.mapping_table.setItem(row, 0, QTableWidgetItem(exe_name))
            self.mapping_table.setItem(row, 1, QTableWidgetItem(display_name))
    
    def add_mapping(self):
        """新增映射"""
        from qfluentwidgets import Dialog, LineEdit, BodyLabel
        from PyQt5.QtWidgets import QVBoxLayout, QFormLayout
        
        dialog = Dialog("新增应用映射", self.app_mapping_page)
        dialog_layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        exe_edit = LineEdit()
        name_edit = LineEdit()
        form_layout.addRow(BodyLabel("可执行文件名:"), exe_edit)
        form_layout.addRow(BodyLabel("映射名称:"), name_edit)
        
        dialog_layout.addLayout(form_layout)
        dialog.textLayout.addLayout(dialog_layout)
        
        if dialog.exec():
            exe_name = exe_edit.text().strip()
            display_name = name_edit.text().strip()
            
            if exe_name and display_name:
                global original_mapping
                original_mapping[exe_name] = display_name
                self.load_mappings_to_table()
                InfoBar.success(
                    title="新增成功",
                    content=f"已添加映射: {exe_name} → {display_name}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.error(
                    title="新增失败",
                    content="可执行文件名和映射名称不能为空",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
    
    def edit_mapping(self):
        """编辑映射"""
        selected_items = self.mapping_table.selectedItems()
        if not selected_items:
            InfoBar.warning(
                title="提示",
                content="请先选择要编辑的映射",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
            return
        
        row = selected_items[0].row()
        old_exe = self.mapping_table.item(row, 0).text()
        old_name = self.mapping_table.item(row, 1).text()
        
        from qfluentwidgets import Dialog, LineEdit, BodyLabel
        from PyQt5.QtWidgets import QVBoxLayout, QFormLayout
        
        dialog = Dialog("编辑应用映射", self.app_mapping_page)
        dialog_layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        exe_edit = LineEdit()
        exe_edit.setText(old_exe)
        name_edit = LineEdit()
        name_edit.setText(old_name)
        form_layout.addRow(BodyLabel("可执行文件名:"), exe_edit)
        form_layout.addRow(BodyLabel("映射名称:"), name_edit)
        
        dialog_layout.addLayout(form_layout)
        dialog.textLayout.addLayout(dialog_layout)
        
        if dialog.exec():
            new_exe = exe_edit.text().strip()
            new_name = name_edit.text().strip()
            
            if new_exe and new_name:
                global original_mapping
                if old_exe != new_exe:
                    del original_mapping[old_exe]
                original_mapping[new_exe] = new_name
                self.load_mappings_to_table()
                InfoBar.success(
                    title="编辑成功",
                    content=f"已更新映射: {new_exe} → {new_name}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.error(
                    title="编辑失败",
                    content="可执行文件名和映射名称不能为空",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
    
    def delete_mapping(self):
        """删除映射"""
        selected_items = self.mapping_table.selectedItems()
        if not selected_items:
            InfoBar.warning(
                title="提示",
                content="请先选择要删除的映射",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
            return
        
        row = selected_items[0].row()
        exe_name = self.mapping_table.item(row, 0).text()
        display_name = self.mapping_table.item(row, 1).text()
        
        from qfluentwidgets import Dialog
        dialog = Dialog("确认删除", f"确定要删除映射: {exe_name} → {display_name} 吗?", self.app_mapping_page)
        
        if dialog.exec():
            global original_mapping
            del original_mapping[exe_name]
            self.load_mappings_to_table()
            InfoBar.success(
                title="删除成功",
                content=f"已删除映射: {exe_name} → {display_name}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
    
    def save_app_mappings(self):
        """保存应用映射到 apps.json 并更新内存中的 app_mapping"""
        global original_mapping, app_mapping, apps_json_path
        
        try:
            with open(apps_json_path, 'w', encoding='utf-8') as f:
                json.dump(original_mapping, f, indent=2, ensure_ascii=False)
            
            app_mapping = {k.lower(): v for k, v in original_mapping.items()}
            logger.info("应用映射保存成功")
            
            InfoBar.success(
                title="保存成功",
                content="应用映射已保存到 apps.json 并更新到内存",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
        except Exception as e:
            logger.error(f"保存应用映射失败: {str(e)}")
            InfoBar.error(
                title="保存失败",
                content=f"保存应用映射失败: {str(e)}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
    
    def init_about_page(self):
        """初始化关于页面"""
        from qfluentwidgets import (CardWidget, BodyLabel, TitleLabel, HyperlinkButton)

        layout = QVBoxLayout(self.about_page)
        layout.setContentsMargins(40, 40, 40, 40)

        # 添加标题
        title = TitleLabel("关于")
        layout.addWidget(title)
        layout.addSpacing(20)

        # 应用信息卡片
        app_info_card = CardWidget(self.about_page)
        app_info_layout = QVBoxLayout(app_info_card)

        app_name_label = TitleLabel("运行时间跟踪器")
        app_info_layout.addWidget(app_name_label)

        version_label = BodyLabel("版本: 1.0.0")
        app_info_layout.addWidget(version_label)

        developer_label = BodyLabel("开发者: CSSQY")
        app_info_layout.addWidget(developer_label)

        app_info_layout.addSpacing(10)

        desc_label = BodyLabel("一个设备使用情况监控工具，可以实时跟踪设备上运行的应用程序，并将数据上报到服务器进行分析。")
        desc_label.setWordWrap(True)
        app_info_layout.addWidget(desc_label)

        layout.addWidget(app_info_card)
        layout.addSpacing(20)

        # 项目链接卡片
        project_card = CardWidget(self.about_page)
        project_layout = QVBoxLayout(project_card)

        project_title = TitleLabel("项目链接")
        project_layout.addWidget(project_title)

        project_link = HyperlinkButton("https://github.com/CSSQY/RunTime_Tracker_Client_Windows", "GitHub - RunTime_Tracker_Client_Windows")
        project_layout.addWidget(project_link)

        layout.addWidget(project_card)
        layout.addSpacing(20)

        # 关联项目卡片
        related_card = CardWidget(self.about_page)
        related_layout = QVBoxLayout(related_card)

        related_title = TitleLabel("相关项目")
        related_layout.addWidget(related_title)

        related_link1 = HyperlinkButton("https://github.com/1812z/RunTime_Tracker", "GitHub - RunTime_Tracker (服务端)")
        related_layout.addWidget(related_link1)

        related_link2 = HyperlinkButton("https://github.com/1812z/Tracker_Client", "GitHub - Tracker_Client (Android客户端)")
        related_layout.addWidget(related_link2)

        related_link3 = HyperlinkButton("https://github.com/zhiyiYo/PyQt-Fluent-Widgets", "GitHub - PyQt-Fluent-Widgets (UI框架)")
        related_layout.addWidget(related_link3)

        layout.addWidget(related_card)
        layout.addSpacing(20)

        # 开源许可卡片
        license_card = CardWidget(self.about_page)
        license_layout = QVBoxLayout(license_card)

        license_title = TitleLabel("开源许可")
        license_layout.addWidget(license_title)

        license_label = BodyLabel("本项目采用 MIT 许可证。")
        license_layout.addWidget(license_label)

        layout.addWidget(license_card)
        layout.addStretch(1)
        
    def on_theme_changed(self, index):
        """主题切换处理"""
        if index == 0:
            setTheme(Theme.AUTO)
        elif index == 1:
            setTheme(Theme.LIGHT)
        elif index == 2:
            setTheme(Theme.DARK)
        
        # 更新配置
        config["theme"] = index
        save_config()
        
        # 更新日志查看器背景颜色
        if hasattr(self, 'log_text_edit'):
            # 根据选择的主题设置日志查看器颜色
            if isDarkTheme():
                # 深色主题
                self.log_text_edit.setStyleSheet("background-color: #1e1e1e; color: #f0f0f0;")
            else:
                # 浅色主题
                self.log_text_edit.setStyleSheet("background-color: #ffffff; color: #000000;")
        
        # 显示提示信息
        InfoBar.success(
            title="主题已更改",
            content=f"当前主题: {'跟随系统' if index == 0 else '浅色主题' if index == 1 else '深色主题'}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )
    
    def on_report_toggled(self, state):
        """上报功能开关处理"""
        config["report_enabled"] = bool(state)
        save_config()
        
        # 显示提示信息
        InfoBar.success(
            title="上报功能已更改",
            content=f"当前状态: {'已启用' if state else '已禁用'}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )
    
    def save_config(self):
        """保存配置"""
        try:
            # 更新配置
            config["api_url"] = self.api_url_edit.text()
            config["secret_key"] = self.secret_key_edit.text()
            config["device_id"] = self.device_id_edit.text()
            # 解析并验证监控间隔
            try:
                new_interval = int(self.monitor_interval_edit.text())
                if new_interval <= 0:
                    new_interval = 1
                    logger.warning("监控间隔必须为正数，已设置为1秒")
                config["monitor_interval"] = new_interval
                logger.info(f"监控间隔已更新为: {new_interval}秒")
            except ValueError:
                logger.error("监控间隔必须为整数，使用默认值1秒")
                config["monitor_interval"] = 1
            config["report_enabled"] = self.report_switch.isChecked()
            
            # 保存到文件
            save_config()
            
            # 更新主页面设备ID显示
            if hasattr(self, 'device_label'):
                self.device_label.setText(f"设备ID: {config.get('device_id', DEVICE_ID)}")
            
            # 显示提示信息
            InfoBar.success(
                title="配置已保存",
                content="所有配置已保存到本地",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            InfoBar.error(
                title="保存失败",
                content=f"保存配置失败: {str(e)}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
    
    def init_data(self):
        """初始化数据"""
        # 上报程序启动状态
        report_system_status("程序启动", True)
        
        # 更新电池状态
        self.update_battery_status()
        
        # 定时更新电池状态
        self.battery_timer = QTimer(self)
        self.battery_timer.timeout.connect(self.update_battery_status)
        self.battery_timer.start(60000)  # 每分钟更新一次
        
        # 监听系统主题变化
        # 在当前版本的qfluentwidgets中，主题变化通过QApplication的paletteChanged信号实现
        QApplication.instance().paletteChanged.connect(self.on_system_theme_changed)
    
    def start_monitor(self):
        """启动应用监控线程"""
        self.monitor_thread = AppMonitorThread()
        self.monitor_thread.app_changed.connect(self.on_app_changed)
        self.monitor_thread.start()
    
    def on_app_changed(self, app_name):
        """应用切换处理"""
        if hasattr(self, 'app_label'):
            self.app_label.setText(f"当前应用: {app_name}")
    
    def update_battery_status(self):
        """更新电池状态"""
        battery_level, is_charging = get_battery_status()
        if battery_level is not None:
            if battery_level == -1:
                status_text = "电池状态: 无电池"
            else:
                status_text = f"电池状态: {battery_level}% {'(充电中)' if is_charging else ''}"
            if hasattr(self, 'battery_label'):
                self.battery_label.setText(status_text)
    
    def refresh_log_files(self):
        """刷新日志文件列表"""
        # 清空下拉框
        self.log_file_combo.clear()
        
        # 获取logs目录
        log_dir = get_user_data_path('logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 列出所有日志文件
        log_files = []
        for file in os.listdir(log_dir):
            if file.startswith('runtime_tracker_') and file.endswith('.log'):
                log_files.append(file)
        
        # 按日期降序排序
        log_files.sort(reverse=True)
        
        # 添加到下拉框
        for log_file in log_files:
            self.log_file_combo.addItem(log_file)
        
        # 如果有日志文件，默认选中第一个
        if log_files:
            self.on_log_file_changed(0)
    
    def on_log_file_changed(self, index):
        """当选择的日志文件变化时，读取并显示日志内容"""
        if index < 0:
            return
        
        # 获取选中的日志文件名
        log_file_name = self.log_file_combo.currentText()
        if not log_file_name:
            return
        
        # 构建日志文件路径
        log_dir = get_user_data_path('logs')
        log_file_path = os.path.join(log_dir, log_file_name)
        
        # 读取日志文件内容
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            self.log_text_edit.setText(log_content)
        except Exception as e:
            self.log_text_edit.setText(f"读取日志文件失败: {str(e)}")
    
    def refresh_log_content(self):
        """刷新当前日志文件内容并滚动到底部"""
        index = self.log_file_combo.currentIndex()
        if index < 0:
            return
        
        # 获取选中的日志文件名
        log_file_name = self.log_file_combo.currentText()
        if not log_file_name:
            return
        
        # 构建日志文件路径
        log_dir = get_user_data_path('logs')
        log_file_path = os.path.join(log_dir, log_file_name)
        
        # 读取日志文件内容
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            self.log_text_edit.setText(log_content)
            
            # 移动光标到文本末尾并滚动到底部
            from PyQt5.QtGui import QTextCursor
            cursor = self.log_text_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text_edit.setTextCursor(cursor)
            self.log_text_edit.ensureCursorVisible()
        except Exception as e:
            self.log_text_edit.setText(f"读取日志文件失败: {str(e)}")
    
    def export_log(self):
        """导出日志文件"""
        # 获取当前选中的日志文件名
        log_file_name = self.log_file_combo.currentText()
        if not log_file_name:
            from qfluentwidgets import InfoBar
            InfoBar.error(
                title="导出失败",
                content="请先选择一个日志文件",
                parent=self
            )
            return
        
        # 构建日志文件路径
        log_dir = get_user_data_path('logs')
        log_file_path = os.path.join(log_dir, log_file_name)
        
        # 选择导出路径
        from PyQt5.QtWidgets import QFileDialog
        export_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志文件", log_file_name, "日志文件 (*.log);;所有文件 (*.*)"
        )
        
        if export_path:
            try:
                # 复制文件
                import shutil
                shutil.copy2(log_file_path, export_path)
                from qfluentwidgets import InfoBar
                InfoBar.success(
                    title="导出成功",
                    content=f"日志文件已导出到: {export_path}",
                    parent=self
                )
            except Exception as e:
                from qfluentwidgets import InfoBar
                InfoBar.error(
                    title="导出失败",
                    content=f"导出日志文件失败: {str(e)}",
                    parent=self
                )
    
    def on_system_theme_changed(self, palette):
        """系统主题变化处理"""
        # 系统主题变化时，QfluentWidgets会自动更新应用主题
        # 更新日志查看器背景颜色
        if hasattr(self, 'log_text_edit'):
            if isDarkTheme():
                # 深色主题
                self.log_text_edit.setStyleSheet("background-color: #1e1e1e; color: #f0f0f0;")
            else:
                # 浅色主题
                self.log_text_edit.setStyleSheet("background-color: #ffffff; color: #000000;")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 当关闭窗口时，只隐藏到托盘，不退出程序
        event.ignore()
        self.hide()
        self.tray_icon.showMessage("运行时间跟踪器", "应用已最小化到系统托盘", QSystemTrayIcon.Information, 2000)
    
    def init_system_tray(self):
        """初始化系统托盘"""
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置图标，优先使用.ico格式
        icon_path = get_resource_path('图标.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            icon_path = get_resource_path('图标.png')
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
        
        # 设置托盘提示
        self.tray_icon.setToolTip("运行时间跟踪器")
        
        # 创建托盘菜单
        tray_menu = QMenu(self)
        
        # 显示窗口动作
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        # 退出动作
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        # 设置托盘菜单
        self.tray_icon.setContextMenu(tray_menu)
        
        # 显示托盘图标
        self.tray_icon.show()
        
        # 连接托盘图标激活信号
        self.tray_icon.activated.connect(self.on_tray_activated)
    
    def on_tray_activated(self, reason):
        """托盘图标激活回调"""
        if reason == QSystemTrayIcon.Trigger:
            # 单击托盘图标时显示/隐藏窗口
            if self.isVisible():
                self.hide()
            else:
                self.show()
    
    def nativeEvent(self, eventType, message):
        """重写nativeEvent监听系统消息"""
        import ctypes
        msg = ctypes.wintypes.MSG.from_address(message.__int__())
        if msg.message == 0x0011:  # WM_QUERYENDSESSION
            # 系统即将关机/重启/注销，上报设备关机状态
            logger.info("检测到系统关机/重启/注销，正在上报设备关机状态")
            try:
                # 直接调用report_app_change上报设备关机
                report_app_change("设备关机")
                # 同时使用report_system_status确保上报成功
                report_system_status("设备关机", False)
                # 等待一段时间确保上报完成
                time.sleep(1)
                logger.info("设备关机状态上报完成")
            except Exception as e:
                logger.error(f"上报设备关机状态失败: {str(e)}")
        # 返回False表示继续处理该消息
        return False, 0

    def quit_application(self):
        """退出应用程序"""
        # 上报退出状态
        report_system_status("程序退出", False)
        # 停止监控线程
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.terminate()
        # 停止定时器
        if hasattr(self, 'battery_timer'):
            self.battery_timer.stop()
        # 隐藏托盘图标
        self.tray_icon.hide()
        # 退出应用
        QApplication.instance().quit()

if __name__ == "__main__":
    # 单实例检查 - 使用 Windows 互斥量
    import win32event
    import win32api
    import winerror
    import win32gui
    import win32con
    
    # 定义互斥量名称
    MUTEX_NAME = "RunTimeTracker_Application_Mutex"
    WINDOW_TITLE = "运行时间跟踪器"
    
    # 创建互斥量
    try:
        mutex = win32event.CreateMutex(None, True, MUTEX_NAME)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            # 互斥量已存在，说明已有实例运行
            # 尝试查找并激活已有窗口
            def enum_windows_callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title == WINDOW_TITLE:
                        # 找到窗口，将其置于前台
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        return False
                return True
            
            win32gui.EnumWindows(enum_windows_callback, None)
            # 退出新实例
            sys.exit(0)
    except Exception as e:
        print(f"单实例检查失败: {str(e)}")
        # 如果单实例检查失败，仍然允许继续运行
    
    # 加载配置
    load_config()
    
    # 设置应用程序属性
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    
    # 设置应用程序图标，优先使用.ico格式
    icon_path = get_resource_path('图标.ico')
    if not os.path.exists(icon_path):
        icon_path = get_resource_path('图标.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 根据配置设置主题
    theme = config.get("theme", 0)
    if theme == 0:
        setTheme(Theme.AUTO)
    elif theme == 1:
        setTheme(Theme.LIGHT)
    elif theme == 2:
        setTheme(Theme.DARK)
    
    # 创建主窗口
    window = MainWindow()
    # 设置主窗口图标
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()
    
    sys.exit(app.exec_())