import requests
import os
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk
import threading
import sys
import json
import re
import shutil
import time
import ctypes
import signal
import zipfile  # 用于解压 ffmpeg

# psutil 为可选依赖，用于更彻底地终止子进程。
# 如果未安装 psutil，不会影响程序其它功能，仅在“取消下载”时退化为普通 terminate。
try:
    import psutil  # type: ignore[reportMissingImports]
except ImportError:  # 在当前环境未安装时，后续逻辑会做兼容处理
    psutil = None  # type: ignore[assignment]
try:
    import winreg  # Windows 注册表操作，用于环境变量配置
except ImportError:
    winreg = None

###YTB 3.5 版本更新说明
#时间：2025-11-26
#作者：飞车羊
#B站：飞车的散装电音
#版本：3.5

CONFIG_DIR = os.path.join(os.getenv("APPDATA"), "YTBDownloader")  # 获取配置文件路径
os.makedirs(CONFIG_DIR, exist_ok=True)  # 创建配置文件夹
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")  # 获取配置文件路径

def resource_path(relative_path):  # 获取资源路径
    try:  # 如果资源路径存在
        base_path = sys._MEIPASS  # 获取资源路径
    except AttributeError:  # 如果资源路径不存在
        base_path = os.path.dirname(os.path.abspath(__file__))  # 获取资源路径
    return os.path.join(base_path, relative_path)  # 返回资源路径

def load_config():  # 加载配置
    if os.path.exists(CONFIG_PATH):  # 如果配置文件存在
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:  # 打开配置文件
            return json.load(f)  # 加载配置文件
    return {}  # 返回空字典

def save_config(data):  # 保存配置
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:  # 打开配置文件
        json.dump(data, f)  # 保存配置

# ==================== 自动配置模块（集成在主文件中） ====================

class AutoSetup:
    """自动配置类，负责下载依赖和配置环境变量"""
    
    def __init__(self, log_callback=None):
        """
        初始化自动配置
        :param log_callback: 日志回调函数，用于在GUI中显示日志
        """
        self.log_callback = log_callback
        self.setup_complete = False
        self.setup_status_file = os.path.join(os.getenv("APPDATA"), "YTBDownloader", "setup_status.json")
        
    def log(self, message):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def check_setup_status(self):
        """检查是否已经完成过初始化"""
        if os.path.exists(self.setup_status_file):
            try:
                with open(self.setup_status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                    return status.get('setup_complete', False)
            except:
                return False
        return False
    
    def mark_setup_complete(self):
        """标记初始化完成"""
        status = {
            'setup_complete': True,
            'setup_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        os.makedirs(os.path.dirname(self.setup_status_file), exist_ok=True)
        with open(self.setup_status_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    
    def check_python_package(self, package_name):
        """检查 Python 包是否已安装"""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False
    
    def install_python_package(self, package_name):
        """使用 pip 安装 Python 包"""
        try:
            self.log(f"📦 正在安装 {package_name}...")
            # 使用 python -m pip 确保使用正确的 pip
            python_exe = sys.executable
            cmd = [python_exe, "-m", "pip", "install", package_name, "--quiet", "--upgrade"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                self.log(f"✅ {package_name} 安装成功")
                return True
            else:
                self.log(f"❌ {package_name} 安装失败: {result.stderr}")
                return False
        except Exception as e:
            self.log(f"❌ 安装 {package_name} 时出错: {e}")
            return False
    
    def check_and_install_python_dependencies(self):
        """检查并安装所有 Python 依赖"""
        self.log("🔍 检查 Python 依赖...")
        dependencies = ['requests', 'psutil']
        all_installed = True
        
        for dep in dependencies:
            if not self.check_python_package(dep):
                self.log(f"⚠️ 未找到 {dep}，开始安装...")
                if not self.install_python_package(dep):
                    all_installed = False
            else:
                self.log(f"✅ {dep} 已安装")
        
        return all_installed
    
    def download_yt_dlp(self):
        """下载 yt-dlp.exe"""
        try:
            save_dir = os.path.join(os.getenv("APPDATA"), "YTBDownloader")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, "yt-dlp.exe")
            
            # 检查是否已存在
            if os.path.exists(save_path):
                try:
                    # 检查版本
                    result = subprocess.run(
                        [save_path, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip().split('\n')[0]
                        self.log(f"✅ yt-dlp 已存在: {version}")
                        return True
                except:
                    pass
            
            self.log("📥 正在下载 yt-dlp.exe...")
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            if percent % 10 == 0:  # 每10%显示一次
                                self.log(f"📥 下载进度: {percent}%")
            
            self.log(f"✅ yt-dlp.exe 下载完成: {save_path}")
            
            # 添加到 PATH
            self.add_to_user_path(save_dir)
            
            return True
        except Exception as e:
            self.log(f"❌ 下载 yt-dlp.exe 失败: {e}")
            return False
    
    def check_ffmpeg(self):
        """检查 ffmpeg 是否在 PATH 中"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                self.log(f"✅ ffmpeg 已安装: {version_line}")
                return True
        except:
            pass
        
        # 检查常见安装位置
        common_paths = [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            os.path.join(os.getenv("PROGRAMFILES", ""), "ffmpeg", "bin"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "ffmpeg", "bin"),
        ]
        
        for path in common_paths:
            if not path:
                continue
            ffmpeg_exe = os.path.join(path, "ffmpeg.exe")
            if os.path.exists(ffmpeg_exe):
                self.log(f"✅ 在 {path} 找到 ffmpeg")
                self.add_to_user_path(path)
                return True
        
        return False
    
    def download_ffmpeg(self):
        """自动下载并安装 ffmpeg"""
        try:
            self.log("📥 正在下载 ffmpeg...")
            
            # 使用 Gyan.dev 的构建版本（稳定可靠）
            # 下载 essentials 版本（包含必要文件）
            download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            
            # 安装目录
            install_dir = r"C:\ffmpeg"
            bin_dir = os.path.join(install_dir, "bin")
            temp_zip = os.path.join(os.getenv("TEMP"), "ffmpeg.zip")
            temp_extract = os.path.join(os.getenv("TEMP"), "ffmpeg_extract")
            
            try:
                # 下载 zip 文件
                response = requests.get(download_url, stream=True, timeout=60)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                
                with open(temp_zip, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int(downloaded * 100 / total_size)
                                if percent % 10 == 0:  # 每10%显示一次
                                    self.log(f"📥 下载进度: {percent}%")
                
                self.log("📦 正在解压 ffmpeg...")
                
                # 解压 zip 文件
                with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract)
                
                # 查找解压后的 ffmpeg 文件夹（通常是 ffmpeg-x.x.x-essentials_build）
                extracted_dirs = [d for d in os.listdir(temp_extract) if os.path.isdir(os.path.join(temp_extract, d)) and d.startswith("ffmpeg")]
                if not extracted_dirs:
                    self.log("❌ 解压后未找到 ffmpeg 文件夹")
                    return False
                
                source_dir = os.path.join(temp_extract, extracted_dirs[0])
                
                # 如果安装目录已存在，先删除
                if os.path.exists(install_dir):
                    self.log(f"⚠️ 检测到已存在的 {install_dir}，正在删除...")
                    try:
                        shutil.rmtree(install_dir)
                    except Exception as e:
                        self.log(f"⚠️ 删除旧目录失败: {e}，尝试继续...")
                
                # 复制到安装目录
                self.log(f"📁 正在安装到 {install_dir}...")
                shutil.copytree(source_dir, install_dir)
                
                # 验证安装
                ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")
                if not os.path.exists(ffmpeg_exe):
                    self.log("❌ 安装后未找到 ffmpeg.exe")
                    return False
                
                # 添加到 PATH
                self.add_to_user_path(bin_dir)
                
                self.log(f"✅ ffmpeg 安装完成: {install_dir}")
                self.log("   ⚠️ 需要重启程序或重新打开命令行才能使用 ffmpeg")
                
                return True
                
            except Exception as e:
                self.log(f"❌ 下载或安装 ffmpeg 失败: {e}")
                return False
            finally:
                # 清理临时文件
                try:
                    if os.path.exists(temp_zip):
                        os.remove(temp_zip)
                    if os.path.exists(temp_extract):
                        shutil.rmtree(temp_extract)
                except:
                    pass
                    
        except Exception as e:
            self.log(f"❌ 下载 ffmpeg 时出错: {e}")
            return False
    
    def add_to_user_path(self, new_path):
        """添加路径到用户 PATH 环境变量"""
        if not winreg:
            self.log("⚠️ 无法配置环境变量（winreg 不可用）")
            return False
            
        try:
            # 规范化路径
            new_path = os.path.normpath(new_path)
            
            # 打开注册表
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Environment',
                0,
                winreg.KEY_ALL_ACCESS
            )
            
            try:
                current_path, _ = winreg.QueryValueEx(reg_key, 'PATH')
            except FileNotFoundError:
                current_path = ''
            
            # 检查是否已存在
            path_dirs = [os.path.normpath(p) for p in current_path.split(';') if p]
            if new_path not in path_dirs:
                new_path_value = current_path + (';' if current_path else '') + new_path
                winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path_value)
                self.log(f"✅ 已将 {new_path} 添加到用户 PATH 环境变量")
                self.log("   ⚠️ 需要重启程序或重新打开命令行才能生效")
            else:
                self.log(f"ℹ️ {new_path} 已在 PATH 环境变量中")
            
            winreg.CloseKey(reg_key)
            return True
        except Exception as e:
            self.log(f"⚠️ 添加 PATH 变量失败: {e}")
            self.log("   请手动将路径添加到系统环境变量")
            return False
    
    def check_biliup(self):
        """检查 biliup 是否存在（可选）"""
        # 获取程序所在目录
        if getattr(sys, 'frozen', False):
            program_dir = os.path.dirname(sys.executable)
        else:
            program_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 检查程序目录
        biliup_exe = os.path.join(program_dir, "biliup.exe")
        if os.path.exists(biliup_exe):
            self.log(f"✅ 找到 biliup: {biliup_exe}")
            return True
        
        # 检查 biliup 文件夹
        biliup_dir = os.path.join(program_dir, "biliup")
        if os.path.exists(os.path.join(biliup_dir, "biliup.exe")):
            self.log(f"✅ 找到 biliup: {biliup_dir}")
            return True
        
        self.log("ℹ️ 未找到 biliup（可选，用于B站上传）")
        return False
    
    def run_setup(self, force=False):
        """运行完整的自动配置"""
        if not force and self.check_setup_status():
            # 已检测到完成过初始化，静默跳过，不显示提示信息
            return True
        
        self.log("=" * 50)
        self.log("🚀 开始自动配置环境...")
        self.log("=" * 50)
        
        success = True
        
        # 1. 检查并安装 Python 依赖
        self.log("\n📦 步骤 1/4: 检查 Python 依赖")
        if not self.check_and_install_python_dependencies():
            self.log("⚠️ Python 依赖安装不完整，但可以继续")
        
        # 2. 下载 yt-dlp
        self.log("\n📥 步骤 2/4: 检查 yt-dlp")
        if not self.download_yt_dlp():
            self.log("❌ yt-dlp 下载失败，请检查网络连接")
            success = False
        
        # 3. 检查 ffmpeg
        self.log("\n🎬 步骤 3/4: 检查 ffmpeg")
        if not self.check_ffmpeg():
            self.log("⚠️ 未找到 ffmpeg，开始自动下载...")
            if self.download_ffmpeg():
                self.log("✅ ffmpeg 下载并安装成功")
                # 再次检查确认
                if self.check_ffmpeg():
                    self.log("✅ ffmpeg 配置完成")
                else:
                    self.log("⚠️ ffmpeg 已安装但可能需要重启程序才能使用")
            else:
                self.log("❌ ffmpeg 自动下载失败，部分功能可能无法使用")
                self.log("   可以手动下载: https://www.gyan.dev/ffmpeg/builds/")
                # ffmpeg 不是必须的，不标记为失败
        
        # 4. 检查 biliup（可选）
        self.log("\n📺 步骤 4/4: 检查 biliup（可选）")
        self.check_biliup()
        
        # 标记完成
        if success:
            self.mark_setup_complete()
            self.log("\n" + "=" * 50)
            self.log("✅ 自动配置完成！")
            self.log("=" * 50)
        else:
            self.log("\n" + "=" * 50)
            self.log("⚠️ 自动配置部分完成，请检查上述错误信息")
            self.log("=" * 50)
        
        self.setup_complete = True
        return success


def run_auto_setup(log_callback=None, force=False):
    """
    运行自动配置（在后台线程中）
    :param log_callback: 日志回调函数
    :param force: 是否强制重新配置
    :return: AutoSetup 实例
    """
    setup = AutoSetup(log_callback)
    
    def run_in_thread():
        time.sleep(0.5)  # 等待 GUI 初始化
        setup.run_setup(force=force)
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    
    return setup

# ==================== 自动配置模块结束 ====================

class SimpleDownloader:  # 创建下载器类
    def __init__(self, root):
        self.root = root
        self.root.geometry("1500x800")
        self.root.configure(bg="white")

        # 获取屏幕宽度和高度
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # 窗口宽度和高度
        window_width = 1500
        window_height = 800

        # 计算窗口左上角坐标
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        # 设置窗口几何形状
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        config = load_config()
        # 统一规范为 Windows 风格路径显示（使用反斜杠）
        self.save_path = os.path.normpath(config.get("save_path", os.getcwd()))
        self.cookies_path = os.path.normpath(config.get("cookies_path", "")) if config.get("cookies_path") else ""
        # 检查是否以管理员身份运行
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except:
            is_admin = False

        # 更新窗口标题
        admin_status = "以管理员身份运行" if is_admin else "非管理员身份运行"
        self.root.title(f"YTB视频下载器-3.5版本-{admin_status}")

        self.create_menu()
        self.create_widgets()
        self.cookies_valid = False
        self.current_process = None
        # 当前正在下载的任务在队列中的名称（用于“取消下载”识别，避免依赖文本里的“下载中”关键字）
        self.current_downloading_name = None
        self.download_info = {}  # 用于存储下载信息
        # 下载队列控制：确保一次只下载一个任务
        self.download_task_queue = []  # [(url, format_id), ...]
        self.is_downloading = False    # 当前是否有任务正在下载
        # 下载取消标记：用于在“准备下载/获取标题/封面”阶段安全中止当前任务
        self.download_cancelled = False
        # 标题缓存：url -> (原始标题, 已清洗标题)
        self.title_cache = {}
        self.log_lock = threading.Lock()  # 添加日志锁
        self.yt_dlp_path = os.path.join(os.getenv("APPDATA"), "YTBDownloader", "yt-dlp.exe")

        # 启动自动配置（首次运行）
        self.root.after(50, self.run_auto_setup_on_startup)  # 最先运行自动配置
        
        self.root.after(100, self.check_and_update_yt_dlp)  # 启动后延迟检测 yt-dlp
        self.root.after(200, self._check_biliup_status)  # 启动后延迟检测 biliup
        self.show_home()  # 启动时直接显示主页
        
        self.download_status_label = tk.Label(self.root, text="", bg="white", font=(None, 10))
        self.download_status_label.pack(pady=5)
        
        # 初始化biliup路径
        self.biliup_path = None
        self.biliup_exe_path = None
        self.biliup_cookies_path = None
        
        # 初始化上传进程跟踪
        self.bili_upload_process = None
        self.bili_terminal_process = None
        self.bili_upload_thread = None
        self.bili_upload_cancelled = False  # 标记是否被用户取消

    def center_window(self):  # 居中窗口
        self.root.update_idletasks()  # 更新窗口信息
        width = self.root.winfo_width()  # 获取窗口宽度
        height = self.root.winfo_height()  # 获取窗口高度
        screen_width = self.root.winfo_screenwidth()  # 获取屏幕宽度
        screen_height = self.root.winfo_screenheight()  # 获取屏幕高度
        x = (screen_width // 2) - (width // 2)  # 计算窗口居中位置的X坐标
        y = (screen_height // 2) - (height // 2)  # 计算窗口居中位置的Y坐标
        self.root.geometry(f'{width}x{height}+{x}+{y}')  # 设置窗口位置


    def create_menu(self):  # 创建菜单
        menubar = tk.Menu(self.root)  # 创建菜单栏
        self.root.config(menu=menubar)  # 设置菜单栏

        menubar.add_command(label=" 🏠 主页  ", command=self.show_home) # 添加主页菜单项
        menubar.add_command(label=" 📝 日志 ", command=self.show_log) # 添加日志菜单项
        menubar.add_command(label=" ⚙️ 设置 ", command=self.show_settings) # 添加设置菜单项


    def check_cookies_valid(self):
        if not self.cookies_path or not os.path.exists(self.cookies_path):
            return False
        try:
            test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            cmd = [self.yt_dlp_path, "--cookies", self.cookies_path, "--dump-json", test_url]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, creationflags=creationflags, env=env)
            return result.returncode == 0 and "LOGIN_REQUIRED" not in result.stderr
        except Exception:
            return False

    def create_widgets(self):
        self.settings_frame = tk.Frame(self.root, bg="white")
        self.main_frame = tk.Frame(self.root, bg="white")
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        frame = tk.Frame(self.main_frame, bg="white")
        frame.pack(pady=0)  # Reduced padding here

        # 添加下载和下载列表选项卡
        self.main_tabs = ttk.Notebook(self.main_frame)

        self.custom_tab = tk.Frame(self.main_tabs, bg="white", height=10)
        self.main_tabs.add(self.custom_tab, text="📥 下载页")

        custom_frame = tk.Frame(self.custom_tab, bg="white")
        custom_frame.pack(pady=10, padx=10, anchor="center")

        icon_button_frame = tk.Frame(custom_frame, bg="white")
        icon_button_frame.grid(row=0, column=2, rowspan=2, padx=(10, 0), pady=(0, 10))

        search_icon_path = resource_path(os.path.join("icons", "搜索1.png"))
        search_icon = tk.PhotoImage(file=search_icon_path).subsample(12, 12)
        self.search_icon = search_icon

        download2_icon_path = resource_path(os.path.join("icons", "下载2.png"))
        download2_icon = tk.PhotoImage(file=download2_icon_path).subsample(12, 12)
        self.download2_icon = download2_icon

        tk.Label(custom_frame, text="视频链接：", bg="white", font=(None, 10)).grid(row=0, column=0, sticky="e")
        self.custom_url_entry = tk.Entry(custom_frame, width=60, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.custom_url_entry.grid(row=0, column=1, padx=5)

        tk.Label(custom_frame, text="格式编号：", bg="white", font=(None, 10)).grid(row=1, column=0, sticky="e")
        self.custom_format_entry = tk.Entry(custom_frame, width=60, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.custom_format_entry.grid(row=1, column=1, padx=5, sticky="w")

        tk.Button(icon_button_frame, image=search_icon, command=self.query_formats, relief="flat", bg="white", activebackground="white", highlightthickness=0, bd=0).pack(pady=(0, 10))
        tk.Button(icon_button_frame, image=download2_icon, command=self.download_selected_format, relief="flat", bg="white", activebackground="white", highlightthickness=0, bd=0).pack()

        self.format_listbox = tk.Listbox(self.custom_tab, font=(None, 10), bg="white", bd=1, relief="solid")
        self.format_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 添加下载队列选项卡
        self.queue_tab = tk.Frame(self.main_tabs, bg="white")
        self.main_tabs.add(self.queue_tab, text="📋 下载队列")

        self.download_queue_listbox = tk.Listbox(self.queue_tab, font=(None, 10), bg="white", bd=1, relief="solid", highlightthickness=1, highlightbackground="#CCCCCC")
        self.download_queue_listbox.pack(fill="both", expand=True, padx=10, pady=10)

        self.queue_menu = tk.Menu(self.root, tearoff=0)
        self.queue_menu.add_command(label="重新下载", command=self.retry_download)
        self.queue_menu.add_command(label="取消下载", command=self.cancel_download)

        self.download_queue_listbox.bind("<Button-3>", self.show_queue_menu)

        self.log_frame = tk.Frame(self.root, bg="white")


        self.log_notebook = ttk.Notebook(self.log_frame)
        self.log_notebook.pack(fill="both", expand=True, padx=10, pady=0)

        self.download_log_text_frame = tk.Frame(self.log_notebook, bg="white")
        self.download_log_text_frame.pack(fill="both", expand=True)

        self.download_log_text = tk.Text(self.download_log_text_frame, height=15, wrap="word", bg="white", font=(None, 10))
        self.download_log_text.pack(side="left", fill="both", expand=True)
        self.download_log_text.bind("<Control-c>", lambda e: self.copy_selected(self.download_log_text))
        # 防止用户编辑日志内容 - 使用更强的方法
        def prevent_edit(event):
            if self.download_log_text.cget("state") == "disabled":
                return "break"
            return None
        self.download_log_text.bind("<Key>", prevent_edit)
        self.download_log_text.bind("<KeyPress>", prevent_edit)
        self.download_log_text.bind("<KeyRelease>", prevent_edit)

        download_scroll = tk.Scrollbar(self.download_log_text_frame, command=self.download_log_text.yview)
        download_scroll.pack(side="right", fill="y")
        self.download_log_text.configure(yscrollcommand=download_scroll.set)

        # 均衡器调整选项卡
        self.eq_tab = tk.Frame(self.main_tabs, bg="white", height=10)
        self.main_tabs.add(self.eq_tab, text="🎶 均衡器调节")
        self.build_eq_tab(self.eq_tab)

        # B站上传选项卡
        self.bili_tab = tk.Frame(self.main_tabs, bg="white", height=10)
        self.main_tabs.add(self.bili_tab, text="📺 B站上传")
        self.build_bili_tab(self.bili_tab)

        self.download_log_text.config(state="disabled")
        self.log_notebook.add(self.download_log_text_frame, text=" 📥 运行日志 ")

        self.cookies_log_text = tk.Text(self.log_notebook, height=15, wrap="word", bg="white", font=(None, 10))
        self.cookies_log_text.bind("<Control-c>", lambda e: self.copy_selected(self.cookies_log_text))
        # 防止用户编辑日志内容 - 使用更强的方法
        def prevent_edit_cookies(event):
            if self.cookies_log_text.cget("state") == "disabled":
                return "break"
            return None
        self.cookies_log_text.bind("<Key>", prevent_edit_cookies)
        self.cookies_log_text.bind("<KeyPress>", prevent_edit_cookies)
        self.cookies_log_text.bind("<KeyRelease>", prevent_edit_cookies)
        cookies_scroll = tk.Scrollbar(self.cookies_log_text, command=self.cookies_log_text.yview)
        self.cookies_log_text.configure(yscrollcommand=cookies_scroll.set)
        cookies_scroll.pack(side="right", fill="y")
        self.cookies_log_text.config(state="disabled")
        
        self.log_notebook.add(self.cookies_log_text, text=" 🍪 Cookies日志 ")

        clear_frame = tk.Frame(self.log_frame, bg="white")
        clear_frame.pack(pady=5)
        tk.Button(clear_frame, text="🧹 清空运行日志", command=self.clear_download_log).pack(side="left", padx=10)
        tk.Button(clear_frame, text="🧹 清空Cookies日志", command=self.clear_cookies_log).pack(side="left", padx=10)

    def update_task(self, filename, status):
        # 更新下载队列中的任务状态（基于前缀匹配）
        for i in range(self.download_queue_listbox.size()):
            if self.download_queue_listbox.get(i).startswith(filename + ":"):
                self.download_queue_listbox.delete(i)
                self.download_queue_listbox.insert(i, f"{filename}: {status}")
                return

    def show_log(self):
        self.clear_frames()
        self.log_frame.pack(fill="both", expand=True)

    def show_home(self):
        self.clear_frames()
        self.main_frame.pack(fill="both", expand=True)
        self.main_tabs.pack(fill="both", expand=True)  # 确保选项卡被添加到主界面
        self.main_tabs.select(self.custom_tab)  # 默认选择下载页选项卡

    def show_settings(self):
        self.clear_frames()
        self.settings_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 先销毁旧的标签，避免路径叠加显示
        if hasattr(self, 'save_label'):
            try:
                self.save_label.destroy()
            except:
                pass
        if hasattr(self, 'cookies_label'):
            try:
                self.cookies_label.destroy()
            except:
                pass
        if hasattr(self, 'yt_dlp_install_label'):
            try:
                self.yt_dlp_install_label.destroy()
            except:
                pass
        if hasattr(self, 'cookies_check_button'):
            try:
                self.cookies_check_button.destroy()
            except:
                pass

        tk.Label(self.settings_frame, text="📂 保存路径：", font=(None, 10)).grid(row=0, column=0, sticky="w")
        self.save_label = tk.Label(self.settings_frame, text=self.save_path, font=(None, 10))
        self.save_label.grid(row=0, column=1, sticky="w")
        tk.Button(self.settings_frame, text="📂 选择保存路径", command=self.choose_save_path).grid(row=0, column=2, padx=10)

        tk.Label(self.settings_frame, text="🍪 Cookies路径：", font=(None, 10)).grid(row=1, column=0, sticky="w")
        self.cookies_label = tk.Label(self.settings_frame, text=self.cookies_path, font=(None, 10))
        self.cookies_label.grid(row=1, column=1, sticky="w")
        tk.Button(self.settings_frame, text="🍪 选择Cookies文件", command=self.choose_cookies_path).grid(row=1, column=2, padx=10)
        # 创建检测按钮，默认显示"点击检测"（蓝色）
        self.cookies_check_button = tk.Button(
            self.settings_frame, 
            text="🔍 点击检测", 
            font=(None, 10), 
            command=self.refresh_cookies_status,
            bg="#2196F3",  # 蓝色
            fg="white",
            relief="flat",
            padx=15,
            pady=5
        )
        self.cookies_check_button.grid(row=1, column=3, padx=10)

        tk.Label(self.settings_frame, text="📦 yt-dlp安装路径：", font=(None, 10)).grid(row=2, column=0, sticky="w")
        self.yt_dlp_install_label = tk.Label(self.settings_frame, text=self.yt_dlp_path, font=(None, 10))
        self.yt_dlp_install_label.grid(row=2, column=1, sticky="w")

        # 添加重新检测环境按钮
        tk.Label(self.settings_frame, text="🔧 环境配置：", font=(None, 10)).grid(row=3, column=0, sticky="w", pady=(20, 0))
        tk.Button(self.settings_frame, text="🔄 重新检测环境", command=self.force_rerun_setup, font=(None, 10), bg="#4CAF50", fg="white", relief="flat", padx=15, pady=5).grid(row=3, column=1, sticky="w", pady=(20, 0))

    def choose_save_path(self):
        path = filedialog.askdirectory()
        if path:
            threading.Thread(target=lambda: self.update_save_path(path)).start()

    def update_save_path(self, path):
        # 统一规范为 Windows 风格路径（反斜杠）
        path = os.path.normpath(path)
        self.save_path = path
        # 确保save_label存在且有效后再更新
        if hasattr(self, 'save_label') and self.save_label.winfo_exists():
            self.root.after(0, lambda: self.save_label.config(text=path))
        config = load_config()
        config["save_path"] = path
        save_config(config)


    def copy_selected(self, widget):
        try:
            selected_text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError:
            pass

    def clear_download_log(self):
        self.download_log_text.config(state="normal")
        self.download_log_text.delete("1.0", tk.END)
        self.download_log_text.config(state="disabled")

    def clear_cookies_log(self):
        self.cookies_log_text.config(state="normal")
        self.cookies_log_text.delete("1.0", tk.END)
        self.cookies_log_text.config(state="disabled")

    def choose_cookies_path(self):
        # 设置初始目录为当前cookies路径的目录（如果存在），否则使用用户主目录
        initialdir = None
        if self.cookies_path and os.path.exists(self.cookies_path):
            initialdir = os.path.dirname(self.cookies_path)
        elif self.cookies_path:
            # 如果路径存在但文件不存在，使用路径的目录部分
            initialdir = os.path.dirname(self.cookies_path) if os.path.dirname(self.cookies_path) else None
        
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=initialdir
        )
        if path:
            # 确保路径是绝对路径并规范化
            path = os.path.abspath(path)
            threading.Thread(target=lambda: self.update_cookies_path(path)).start()

    def update_cookies_path(self, path):
        # 确保路径是绝对路径并规范化为 Windows 风格（反斜杠）
        path = os.path.normpath(os.path.abspath(path))
        self.cookies_path = path
        # 确保cookies_label存在且有效后再更新
        if hasattr(self, 'cookies_label') and self.cookies_label.winfo_exists():
            self.root.after(0, lambda: self.cookies_label.config(text=path))
        config = load_config()
        config["cookies_path"] = path
        save_config(config)
        self.refresh_cookies_status()

    def check_cookies_on_startup(self):
        def check():
            # 等待一小段时间确保 yt-dlp 完全准备好
            time.sleep(1)
            self.log("🕒 启动时检测 Cookies 可用性...", category="Cookies")
            valid = self.check_cookies_valid()
            self.cookies_valid = valid
            # 启动时的检测不更新按钮状态，保持默认的"点击检测"状态
            
            if valid:
                self.log(f"🍪 Cookies 🔍启动检测结果：✅ 可用", category="Cookies")
                self.log("ℹ️ Cookies 可用，启用 cookies 功能", category="Cookies")
                self.log("", category="Cookies")  # 空行分隔
            else:
                self.log(f"🍪 Cookies 🔍启动检测结果：❌ 不可用", category="Cookies")
                self.log("ℹ️ Cookies 不可用，临时禁用 cookies 功能", category="Cookies")
                self.log("", category="Cookies")  # 空行分隔
        threading.Thread(target=check).start()

    def refresh_cookies_status(self):
        # 点击时先重置为蓝色（正常状态）
        if hasattr(self, 'cookies_check_button'):
            self.root.after(0, lambda: self.cookies_check_button.config(
                bg="#2196F3",  # 蓝色
                text="🔍 点击检测",
                state="disabled"  # 暂时禁用，防止重复点击
            ))
        
        # 短暂延迟后设置为黄色（检测中）
        def set_checking():
            time.sleep(0.2)  # 短暂延迟，让用户看到蓝色状态
            if hasattr(self, 'cookies_check_button'):
                self.root.after(0, lambda: self.cookies_check_button.config(
                    bg="#FFC107",  # 黄色
                    text="🕒 检测中..."
                ))
        
        threading.Thread(target=set_checking, daemon=True).start()
        
        def check():
            self.log("🕒 开始检测 🍪Cookies 可用性...", category="Cookies")
            valid = self.check_cookies_valid()
            self.cookies_valid = valid
            
            # 使用self.root.after确保在检测完成后更新UI
            # 更新按钮颜色：可用=绿色，不可用=红色，并重新启用按钮
            # 按钮将保持检测后的状态，直到用户再次点击进行检测
            if hasattr(self, 'cookies_check_button'):
                if valid:
                    self.root.after(0, lambda: self.cookies_check_button.config(
                        bg="#4CAF50",  # 绿色
                        text="✅ 可用",
                        state="normal"  # 重新启用按钮
                    ))
                else:
                    self.root.after(0, lambda: self.cookies_check_button.config(
                        bg="#F44336",  # 红色
                        text="❌ 不可用",
                        state="normal"  # 重新启用按钮
                    ))
            
            if valid:
                self.log(f"🍪 Cookies 🔍 检测完成：✅ 可用", category="Cookies")
                self.log("ℹ️ Cookies 可用，启用 cookies 功能", category="Cookies")
                self.log("", category="Cookies")  # 空行分隔
            else:
                self.log(f"🍪 Cookies 🔍 检测完成：❌ 不可用", category="Cookies")
                self.log("ℹ️ Cookies 不可用，临时禁用 cookies 功能", category="Cookies")
                self.log("", category="Cookies")  # 空行分隔
        
        threading.Thread(target=check).start()

    def run_auto_setup_on_startup(self):
        """在启动时运行自动配置"""
        def setup_log_callback(message):
            """自动配置的日志回调"""
            self.log(message, category="下载")
        
        # 运行自动配置（在后台线程中）
        self.auto_setup = run_auto_setup(log_callback=setup_log_callback, force=False)
    
    def force_rerun_setup(self):
        """强制重新运行自动配置"""
        def setup_log_callback(message):
            """自动配置的日志回调"""
            self.log(message, category="下载")
        
        self.log("🔄 用户手动触发重新检测环境...", category="下载")
        # 运行自动配置（强制模式，在后台线程中）
        self.auto_setup = run_auto_setup(log_callback=setup_log_callback, force=True)

    def log(self, message, category="General"):
        """
        线程安全的日志接口：
        - 如果在主线程中调用，直接更新 Tk 组件
        - 如果在子线程中调用，通过 root.after 把更新委托给主线程
        """
        if threading.current_thread() is threading.main_thread():
            self._log_to_ui(message, category)
        else:
            # 把实际 UI 更新调度到主线程执行，避免跨线程直接操作 Tk 导致卡死
            self.root.after(0, lambda m=message, c=category: self._log_to_ui(m, c))

    def _log_to_ui(self, message, category="General"):
        """仅在主线程中执行的实际 UI 日志更新逻辑"""
        with self.log_lock:  # 使用锁来确保同一时间只有一个线程在记录日志
            if category == "Cookies":
                self.cookies_log_text.config(state="normal")
                self.cookies_log_text.insert(tk.END, f"{message}\n")
                self.cookies_log_text.config(state="disabled")
                self.cookies_log_text.see(tk.END)  # 自动滚动到底部
            else:  # 将所有非Cookies日志信息显示在运行日志中
                self.download_log_text.config(state="normal")
                self.download_log_text.insert(tk.END, f"{message}\n")  # 去掉类别标签
                self.download_log_text.see(tk.END)  # 自动滚动到底部
                self.download_log_text.config(state="disabled")  # 确保在最后设置为禁用状态

    def clear_frames(self):
        for widget in self.root.winfo_children():
            widget.pack_forget()

    def update_new_download_label(self, content):
        self.new_download_label.config(text=content)

    def check_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def update_progress(self, line):
        if "%" in line:
            progress = line.split("%")[0].strip()
            self.download_log_text.config(state="normal")
            self.download_log_text.insert(tk.END, f"下载进度: {progress}%\n")
            self.download_log_text.config(state="disabled")

    def query_formats(self):
        url = self.custom_url_entry.get().strip()
        if not url:
            self.log("请输入视频链接用于格式查询", category="下载")
            return

        def run():
            self.log(f"\n🔍 正在获取格式列表：{url}", category="下载")
            cmd = [self.yt_dlp_path, "-F", url]
            # 只有在cookies路径存在且cookies有效时才使用cookies
            if self.cookies_path and self.cookies_valid:
                cmd += ["--cookies", self.cookies_path]
                self.log("🍪 使用cookies进行格式查询", category="下载")
            else:
                self.log("ℹ️ 未使用cookies进行格式查询", category="下载")
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags, env=env)
                self.format_listbox.delete(0, tk.END)
                if result.returncode == 0:
                    formats = result.stdout.splitlines()
                    for line in formats:
                        self.format_listbox.insert(tk.END, line)
                    self.log("✅ 格式列表获取完成", category="下载")
                else:
                    self.log("❌ 获取格式失败，请检查链接是否正确", category="下载")
            except Exception as e:
                self.log(f"❌ 异常：{e}", category="下载")
        threading.Thread(target=run).start()

    def download_selected_format(self):
        url = self.custom_url_entry.get().strip()
        format_id = self.custom_format_entry.get().strip()
        if not url or not format_id:
            self.log("请输入链接和格式编号", category="下载")
            return

        # 在下载队列中添加初始任务（仅标记为“待下载...”，真正下载由队列调度）
        filename = url.split("?")[0].split("/")[-1]
        # 记录本次下载的链接和格式编号，供“重新下载”功能使用
        self.download_info[filename] = (url, format_id)
        self.download_queue_listbox.insert(tk.END, f"{filename}: 待下载...")

        # 压入内部任务队列
        self.download_task_queue.append((url, format_id))

        # 后台预先获取标题，并立即更新队列显示为“视频标题: 待下载...”
        threading.Thread(
            target=self._prepare_title_for_queue,
            args=(url, filename),
            daemon=True
        ).start()

        # 若当前没有任务在下载，则立即启动队列中的下一个任务
        if not self.is_downloading:
            self.start_next_download()

    def _prepare_title_for_queue(self, url, filename):
        """
        在点击下载按钮后，提前获取视频标题，并把下载队列中的 URL 名称替换为“视频标题”。
        仅更新队列显示和映射，不启动下载。
        """
        try:
            title = self.get_video_title(url, filename)
            if not title:
                return

            sanitized_title = self.sanitize_path(title)

            # 缓存标题，供后续真正下载时复用，避免再次调用 yt-dlp 获取标题
            self.title_cache[url] = (title, sanitized_title)

            # 更新下载信息映射键：filename -> sanitized_title
            if filename in self.download_info:
                self.download_info[sanitized_title] = self.download_info.pop(filename)

            # 更新队列显示：URL 文件名 -> 视频标题
            # 注意：如果此时下载已经开始（状态可能已变为“⬇️ 下载中...”），则只改名称，不改状态
            def _update_queue_title():
                for i in range(self.download_queue_listbox.size()):
                    item_text = self.download_queue_listbox.get(i)
                    name, *rest = item_text.split(":", 1)
                    if name == filename:
                        status_text = rest[0] if rest else ""
                        # 保留原有状态，只替换前缀为标题
                        self.download_queue_listbox.delete(i)
                        self.download_queue_listbox.insert(i, f"{sanitized_title}:{status_text}")
                        break

            self.root.after(0, _update_queue_title)
        except Exception as e:
            # 获取标题失败时不影响主流程，仅记录日志
            self.log(f"⚠️ 预获取标题失败: {e}", category="下载")

    def start_next_download(self):
        """
        从队列中取出下一个任务并启动下载。
        确保任意时刻只会有一个下载任务在进行。
        """
        # 队列为空，则标记为空闲
        if not self.download_task_queue:
            self.is_downloading = False
            self.current_process = None
            return

        # 取出下一个任务
        url, format_id = self.download_task_queue.pop(0)
        self.is_downloading = True
        # 每次开始新任务时重置下载取消标记
        self.download_cancelled = False

        # 记录当前正在下载的队列名称（可能是原始文件名，也可能是已经替换为视频标题）
        cached = self.title_cache.get(url)
        if cached:
            _, sanitized_title = cached
            self.current_downloading_name = sanitized_title
        else:
            self.current_downloading_name = url.split("?")[0].split("/")[-1]

        # 启动实际下载线程
        threading.Thread(target=self._download_task, args=(url, format_id)).start()

    def _download_task(self, url, format_id):
        """
        实际执行单个视频下载的逻辑。
        该方法会在独立线程中运行，结束后自动触发下一个队列任务。
        """
        # 根据 URL 生成初始文件名，用于与列表中的“排队中”项对应
        filename = url.split("?")[0].split("/")[-1]

        try:
            # 优先使用预先缓存的标题（在点击下载按钮时已获取）
            cached = self.title_cache.get(url)
            if cached:
                title, sanitized_title = cached
            else:
                # 如果没有缓存，再调用 yt-dlp 获取标题，并写入缓存
                title = self.get_video_title(url, filename)
                sanitized_title = self.sanitize_path(title)
                self.title_cache[url] = (title, sanitized_title)

            # 如果在“获取标题阶段”用户已经点击取消，则直接中止本任务
            if self.download_cancelled:
                self.log(f"⏹️ 已在准备阶段取消当前任务: {filename}", category="下载")
                return

            # 一旦获取到标题，就立刻把队列中对应的 URL 文件名替换为“视频标题”
            # 此时状态也更新为“⬇️ 下载中...”
            self.root.after(0, lambda: self.replace_task(filename, sanitized_title, "⬇️ 下载中..."))
            # 迁移下载信息键：从临时 filename (由URL截取) 改为 sanitized_title，确保后续操作一致
            if filename in self.download_info:
                self.download_info[sanitized_title] = self.download_info.pop(filename)

            # 日志：显示本次下载使用的格式、视频标题和 URL（直接使用用户输入的原始 URL）
            self.log(f"\n⬇️ 开始使用格式 {format_id} 下载视频：{title}", category="下载")
            self.log(f"\nURL：{url}\n", category="下载")

            # 创建以替换后的标题命名的文件夹
            title_folder = os.path.join(self.save_path, sanitized_title)
            os.makedirs(title_folder, exist_ok=True)

            # 下载封面并保存为 JPG
            try:
                self.download_thumbnail_jpg(url, title_folder, title)
            except Exception as e:
                self.log(f"⚠️ 封面下载失败: {e}", category="下载")

            # 如果在“下载封面阶段”用户已经点击取消，则直接中止本任务
            if self.download_cancelled:
                self.log(f"⏹️ 封面阶段被取消，未开始实际下载: {sanitized_title}", category="下载")
                return

            # 直接合并下载（yt-dlp 自动合并 bestvideo+bestaudio）
            # 下载前先清理上一次可能残留的中间文件（原视频.*），避免 --no-post-overwrites 导致 100% 后仍报错
            try:
                for f in os.listdir(title_folder):
                    if f.startswith("原视频"):
                        try:
                            os.remove(os.path.join(title_folder, f))
                        except Exception:
                            pass
            except Exception:
                pass

            # 合并后的中间文件命名为 "原视频.扩展名"
            merged_output_tmpl = os.path.join(title_folder, "原视频.%(ext)s")
            dl_cmd = [
                self.yt_dlp_path,
                "-f", format_id,                   # 可传 "137+140" 或单一整合格式
                "--remux-video", "mp4",           # 强制封装为 MP4（尽可能不转码）
                "--output", merged_output_tmpl,
                url,
                "--no-post-overwrites",
                "--retries", "5",                 # 适中的重试次数
                "--fragment-retries", "5",        # 片段重试次数
                "--socket-timeout", "30",         # 设置socket超时
                "--http-chunk-size", "5242880",   # 5MB块大小，更稳定
                "--buffer-size", "32768",         # 适中的缓冲区
                "--concurrent-fragments", "1",    # 单线程下载，最稳定
                "--sleep-interval", "1",          # 请求间隔1秒
                "--max-sleep-interval", "3",      # 最大间隔5秒
            ]
            if self.cookies_path and self.cookies_valid:
                dl_cmd += ["--cookies", self.cookies_path]
                self.log("🍪 使用cookies进行下载", category="下载")
            else:
                self.log("ℹ️ 未使用cookies进行下载", category="下载")

            self.log("", category="下载")
            self.log("⬇️ yt-dlp 下载开始\n\n", category="下载")

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            dl_process = subprocess.Popen(
                dl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='ignore',
                creationflags=creationflags
            )
            self.current_process = dl_process

            def log_output(process):
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            self.log(line.strip(), category="下载")
                            self.root.after(0, lambda l=line: self.update_download_status(l.strip()))
                except ValueError:
                    self.log("日志读取过程中发生错误，文件描述符已关闭。", category="下载")

            dl_thread = threading.Thread(target=log_output, args=(dl_process,))
            dl_thread.start()
            dl_process.wait()
            dl_thread.join()
            dl_process.stdout.close()

            if dl_process.returncode != 0:
                self.log("❌ 下载失败\n", category="下载")
                # 此时队列前缀已经被替换为标题（sanitized_title），这里用标题来更新状态
                self.root.after(0, lambda: self.replace_task(sanitized_title, sanitized_title, "❌ 下载失败"))
                return

            self.log("\n✅ 下载完成\n", category="下载")
            self.root.after(0, lambda: self.replace_task(sanitized_title, sanitized_title, "✅ 下载完成\n"))

            # 检测合并后文件的实际扩展名（mp4/mkv/webm）
            merged_path = None
            for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                candidate = os.path.join(title_folder, f"原视频{ext}")
                if os.path.exists(candidate):
                    merged_path = candidate
                    break
            if not merged_path:
                self.log("❌ 未找到下载后的视频文件", category="下载")
                # 队列里显示的也是标题，保持一致更新
                self.root.after(0, lambda: self.replace_task(sanitized_title, sanitized_title, "❌ 下载文件缺失"))
                return

            # 按批处理方式生成 hi-res MKV：复制视频流，音频转 PCM 32bit/48kHz/2ch，+genpts
            mkv_output_path = os.path.join(title_folder, f"{sanitized_title}.mkv")
            self.log("🔄 开始生成PCM音视频流\n", category="下载")
            ffmpeg_cmd = [
                "ffmpeg",
                "-loglevel", "info",
                "-i", merged_path,
                "-c:v", "copy",
                "-c:a", "pcm_s32le",
                "-ar", "48000",
                "-ac", "2",
                "-fflags", "+genpts",
                "-y",
                mkv_output_path
            ]
            subprocess.run(ffmpeg_cmd, shell=True)
            self.log(f"✅ PCM音视频流生成完成: {mkv_output_path}\n", category="下载")
            self.root.after(0, lambda: self.replace_task(sanitized_title, sanitized_title, "✅ PCM音视频流生成完成"))

            # 重命名为标题名（与你原逻辑一致）
            try:
                sanitized_title = self.sanitize_path(title)
                new_name = os.path.join(self.save_path, sanitized_title, f"{sanitized_title}.mkv")
                os.rename(mkv_output_path, new_name)
                self.log(f"✅ 文件已重命名为: {new_name}\n", category="下载")
                # 下载成功后额外空三行，方便在日志中分隔不同任务
                self.log("✅ 下载成功\n\n\n", category="下载")
                self.root.after(0, lambda: self.replace_task(sanitized_title, sanitized_title, "✅ 下载成功"))
            except Exception as e:
                self.log(f"⚠️ 重命名失败，但已生成 PCM音视频流: {mkv_output_path}，错误：{e}", category="下载")
        finally:
            # 标记当前下载结束，并自动拉起下一个任务
            self.is_downloading = False
            self.current_process = None
            self.current_downloading_name = None
            # 在主线程调度下一个任务，避免线程直接操作 Tk
            self.root.after(0, self.start_next_download)

    def retry_download(self):
        selected = self.download_queue_listbox.curselection()
        if selected:
            task = self.download_queue_listbox.get(selected[0])
            filename = task.split(":")[0]
            self.log(f"重新下载：{filename}", category="下载")
            url, format_code = self.get_download_info(filename)
            if url is None:
                self.log("无法获取下载信息，URL 为空", category="下载")
                return
            # 检查是否已经存在相同文件名称的项
            for i in range(self.download_queue_listbox.size()):
                if self.download_queue_listbox.get(i).startswith(filename + ":"):
                    self.download_queue_listbox.delete(i)
                    break
            # 调用下载方法
            self.custom_url_entry.delete(0, tk.END)
            self.custom_url_entry.insert(0, url)
            self.custom_format_entry.delete(0, tk.END)
            self.custom_format_entry.insert(0, format_code)
            self.download_selected_format()

    def cancel_download(self):
        """
        右键“取消下载”的逻辑，恢复为 3.4 版本的简单行为：
        - 如果选中的是“当前正在下载”的那一条：终止当前下载进程
        - 如果选中的是“已完成/排队中”的那一条：只删队列记录，不影响正在下载的任务
        """
        selected = self.download_queue_listbox.curselection()
        if selected:
            task = self.download_queue_listbox.get(selected[0])
            filename = task.split(":")[0]

            # 只有当选中的这一条，正好是当前正在下载的任务时，才去终止下载进程
            if filename == self.current_downloading_name and self.current_process:
                # 标记取消，供“获取标题/获取封面”阶段使用
                self.download_cancelled = True
                try:
                    if psutil is not None:
                        parent = psutil.Process(self.current_process.pid)
                        for child in parent.children(recursive=True):
                            child.kill()
                        parent.kill()
                    else:
                        # 未安装 psutil 时，直接终止当前进程
                        self.current_process.terminate()
                    self.log(f"⛔ 已经取消下载任务 {filename}", category="下载")
                except Exception as e:
                    self.log(f"❌ 无法取消下载任务: {e}", category="下载")
                self.current_process = None

            # 尝试从内部队列中也移除对应任务（3.4 中没有这部分，这里做个兼容清理即可）
            url, _ = self.get_download_info(filename)
            if url:
                # 从内部任务队列中移除对应的任务
                for i, item in enumerate(self.download_task_queue):
                    if isinstance(item, (list, tuple)) and len(item) >= 1 and item[0] == url:
                        self.download_task_queue.pop(i)
                        break
                # 清理标题缓存和映射
                if url in self.title_cache:
                    self.title_cache.pop(url, None)
                if filename in self.download_info:
                    self.download_info.pop(filename, None)

            # 删除队列中的这条记录
            self.download_queue_listbox.delete(selected[0])
            self.log(f"下载任务已从队列中移除: {filename}", category="下载")

    def update_download_status(self, line):
        if self.current_process:
            self.root.after(0, lambda: self.download_log_text.config(state="normal"))
            self.download_log_text.insert(tk.END, line + "\n")
            self.download_log_text.config(state="disabled")

    def get_video_title(self, url, filename):
        try:
            cmd = [self.yt_dlp_path, "--get-title", url]
            # 只有在cookies路径存在且cookies有效时才使用cookies
            if self.cookies_path and self.cookies_valid:
                cmd += ["--cookies", self.cookies_path]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags, env=env)
            if result.returncode == 0:
                title = result.stdout.strip()
                return title
            else:
                self.log(f"获取视频标题失败: {result.stderr}", category="下载")
                return filename # 如果获取失败，则使用文件名作为标题
        except Exception as e:
            self.log(f"获取视频标题失败: {e}", category="下载")
            return filename

    def download_thumbnail_jpg(self, url, title_folder, expected_title):
        # 使用 yt-dlp 写缩略图并转换为 jpg，然后重命名为 cover.jpg
        # 输出模板到标题文件夹，避免污染其它位置
        self.log("🖼️ 正在获取封面...", category="下载")  # 新增：开始日志
        out_tmpl = os.path.join(title_folder, "%(title)s.%(ext)s")
        cmd = [
            self.yt_dlp_path,
            "--skip-download",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", out_tmpl,
            url
        ]
        # 只有在cookies路径存在且cookies有效时才使用cookies
        if self.cookies_path and self.cookies_valid:
            cmd += ["--cookies", self.cookies_path]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags, env=env)

        if result.returncode != 0:
            self.log(f"❌ 封面下载失败：{result.stderr.strip() or 'yt-dlp 缩略图提取失败'}", category="下载")  # 新增：失败日志
            raise RuntimeError(result.stderr.strip() or "yt-dlp 缩略图提取失败")

        # 在标题文件夹里寻找 jpg 缩略图（优先匹配标题名）
        jpg_candidates = [f for f in os.listdir(title_folder) if f.lower().endswith(".jpg")]
        if not jpg_candidates:
            self.log("❌ 未找到已转换的 JPG 封面", category="下载")  # 新增：失败日志
            raise FileNotFoundError("未找到已转换的 JPG 封面")
        # 优先找到与标题最相关的文件，否则取第一个
        expected_prefix = expected_title
        best = None
        for f in jpg_candidates:
            if f.startswith(expected_prefix):
                best = f
                break
        if not best:
            best = jpg_candidates[0]

        src = os.path.join(title_folder, best)
        dst = os.path.join(title_folder, "封面.jpg")

        # 若已有旧封面则覆盖
        try:
            if os.path.exists(dst):
                os.remove(dst)
        except Exception:
            pass

        os.rename(src, dst)
        self.log(f"🖼️ 已保存封面: {dst}", category="下载")  # 成功日志（保留）
        # 与后续下载日志之间空一行
        self.log("", category="下载")

    def get_download_info(self, filename):  # 获取下载信息
        if filename in self.download_info:  # 如果文件名在下载信息中，则返回下载信息
            return self.download_info[filename]     
        return None, None  # 如果文件名不在下载信息中，则返回None

    def replace_task(self, title, new_title, status):  # 修改为使用title
        for i in range(self.download_queue_listbox.size()):
            item_text = self.download_queue_listbox.get(i)
            name = item_text.split(":", 1)[0]
            # 兼容两种情况：
            # 1. 还没替换标题时，使用原始 filename 作为前缀
            # 2. 已经被预处理为视频标题时，前缀是 new_title
            if name == title or name == new_title:
                self.download_queue_listbox.delete(i)  # 删除旧任务
                self.download_queue_listbox.insert(i, f"{new_title}: {status}")  # 插入新任务
                break  # 跳出循环

    def merge_audio_video_to_mkv(self, video_path, audio_path, mkv_output_path, audio_path_for_ffmpeg, title, filename,output_audio_path):  # 合并音频和视频
        try:
            # 使用 ffmpeg 合并音频和视频
            self.log(f"🔄 开始合并音频和视频:\n{video_path}\n{audio_path}\n", category="下载")
            self.root.after(0, lambda: self.replace_task(title, title, "⬇️ 合并音频和视频中..."))
            ffmpeg_cmd = [
                "ffmpeg",
                "-loglevel", "info",
                "-i", video_path,
                "-i", audio_path_for_ffmpeg,
                "-c", "copy",
                "-y",
                mkv_output_path
            ]
            subprocess.run(ffmpeg_cmd, shell=True)
            self.log(f"✅ 音频和视频已合并为: {mkv_output_path}\n", category="下载")
            self.root.after(0, lambda: self.replace_task(title, title, "✅ 合并音频和视频完成"))

            # 更改合并后的文件名称
            sanitized_title = self.sanitize_path(title)  # 确保标题名称合法
            new_name = os.path.join(self.save_path, sanitized_title, f"{sanitized_title}.mkv")
            os.rename(mkv_output_path, new_name)
            self.log(f"✅ 文件已重命名为: {new_name}\n", category="下载")
            # 下载成功后额外空三行，方便在日志中分隔不同任务
            self.log("✅ 下载成功\n\n\n", category="下载")
            self.root.after(0, lambda: self.replace_task(title, title, "✅ 下载成功"))
        except Exception as e:
            self.log(f"❌ 合并音频和视频失败: {e}\n", category="下载")
            self.root.after(0, lambda: self.replace_task(title, title, "❌ 合并音频和视频失败"))

    def show_queue_menu(self, event):  # 显示队列菜单
        # 获取鼠标点击位置的列表项索引
        index = self.download_queue_listbox.nearest(event.y)
        # 设置选中状态
        self.download_queue_listbox.selection_clear(0, tk.END)
        self.download_queue_listbox.selection_set(index)
        self.download_queue_listbox.activate(index)
        # 显示菜单
        self.queue_menu.post(event.x_root, event.y_root)

    def sanitize_path(self, path):  # 清理路径
        return re.sub(r'[<>:"/\\|?*]', '-', path)

    def check_and_update_yt_dlp(self):
        def run_check():
            try:
                self.log("🔍 检测 yt-dlp 版本中...", category="下载")
                # 检查 APPDATA/YTBDownloader 下是否有 yt-dlp.exe
                if os.path.exists(self.yt_dlp_path):
                    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    env = os.environ.copy()
                    env['PYTHONIOENCODING'] = 'utf-8'
                    result = subprocess.run([self.yt_dlp_path, "--version"], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags, env=env)
                    current_version_line = result.stdout.splitlines()[0] if result.returncode == 0 else ""
                else:
                    current_version_line = ""
                current_version_match = re.search(r'\d+\.\d+\.\d+', current_version_line)
                current_version = current_version_match.group(0) if current_version_match else "未知版本"

                # 获取 PyPI 上最新版本
                response = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=5)
                if response.status_code == 200:
                    latest_version = response.json()["info"]["version"]
                else:
                    latest_version = "未知版本"

                def normalize_version(ver):
                    return ".".join(str(int(x)) for x in ver.split(".")) if ver and ver != "未知版本" else ver

                if (not os.path.exists(self.yt_dlp_path)) or (normalize_version(current_version) != normalize_version(latest_version)):
                    # 不是最新版本或没有
                    self.root.after(0, lambda: self.log(f"❌ yt-dlp 不存在或不是最新版本 (当前: {current_version}, 最新: {latest_version})，正在下载...", category="下载"))
                    self.download_yt_dlp_exe()
                else:
                    self.root.after(0, lambda: self.log(f"✅ yt-dlp 已是最新版本 (本机: {current_version}, 最新: {latest_version})", category="下载"))
                    # 只有最新版本时才检测 cookies
                    self.root.after(0, self.check_cookies_on_startup)
            except Exception as e:
                self.root.after(0, lambda e=e: self.log(f"❌ 检测 yt-dlp 版本失败: {e}", category="下载"))
                self.root.after(0, self.check_cookies_on_startup)  # 即使失败也继续检测 cookies
        threading.Thread(target=run_check).start()

    def add_to_user_path(self, new_path):
        import winreg
        try:
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment', 0, winreg.KEY_ALL_ACCESS)
            try:
                current_path, _ = winreg.QueryValueEx(reg_key, 'PATH')
            except FileNotFoundError:
                current_path = ''
            if new_path not in current_path:
                new_path_value = current_path + (';' if current_path else '') + new_path
                winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path_value)
                self.root.after(0, lambda: self.download_log_text.insert(
                    tk.END, f"✅ 已将 {new_path} 添加到用户 PATH 环境变量，重启命令行后可全局使用 yt-dlp\n"))
            else:
                self.root.after(0, lambda: self.download_log_text.insert(
                    tk.END, f"ℹ️ {new_path} 已在 PATH 环境变量中，无需重复添加\n"))
            winreg.CloseKey(reg_key)
        except Exception as e:
            self.root.after(0, lambda: self.download_log_text.insert(
                tk.END, f"⚠️ 添加 PATH 变量失败: {e}\n"))

    def download_yt_dlp_exe(self, system32=False):
        def run_download():
            try:
                # 下载前先检测并添加 PATH
                save_dir = os.path.join(os.getenv("APPDATA"), "YTBDownloader")
                path_env = os.environ.get("PATH", "")
                path_dirs = [os.path.normcase(os.path.normpath(p)) for p in path_env.split(";") if p]
                save_dir_norm = os.path.normcase(os.path.normpath(save_dir))
                if save_dir_norm not in path_dirs:
                    self.add_to_user_path(save_dir)

                save_path = os.path.join(save_dir, "yt-dlp.exe")
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except Exception as e:
                        self.root.after(0, lambda: self.download_log_text.config(state="normal"))
                        self.root.after(0, lambda: self.download_log_text.insert(
                            tk.END, f"❌ 无法删除旧的 yt-dlp.exe: {e}\n请手动关闭所有 yt-dlp 相关程序并删除该文件后重试。\n"))
                        self.root.after(0, lambda: self.download_log_text.config(state="disabled"))
                        return

                self.root.after(0, lambda: self.download_log_text.config(state="normal"))
                self.root.after(0, lambda: self.download_log_text.insert(tk.END, f"🔄 正在下载最新的 yt-dlp.exe...\n"))
                self.root.after(0, lambda: self.download_log_text.config(state="disabled"))

                url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                response = requests.get(url, stream=True)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                start_time = time.time()

                # 创建进度条
                self.root.after(0, lambda: self.create_download_progressbar())

                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            percent = int(downloaded * 100 / total_size) if total_size else 0
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            remain = (total_size - downloaded) / speed if speed > 0 else 0
                            # 更新进度条和剩余时间
                            self.root.after(0, lambda p=percent, r=remain: self.update_download_progressbar(p, r))

                # 下载完成后移除进度条
                self.root.after(0, self.remove_download_progressbar)

                install_path = save_path
                self.root.after(0, lambda: self.download_log_text.config(state="normal"))
                self.root.after(0, lambda: self.download_log_text.insert(tk.END, f"✅ yt-dlp.exe 已成功下载并安装到：{install_path} 路径\n"))
                self.root.after(0, lambda: self.download_log_text.config(state="disabled"))
                # 下载完成后再次检测是否为最新版本
                self.root.after(0, self.check_and_update_yt_dlp)
            except Exception as e:
                self.root.after(0, lambda: self.download_log_text.config(state="normal"))
                self.root.after(0, lambda: self.download_log_text.insert(tk.END, f"❌ 下载 yt-dlp.exe 过程中出现错误: {e}\n"))
                self.root.after(0, lambda: self.download_log_text.insert(tk.END, f"❌ 请检查你的网络连接是否正常，或手动将 yt-dlp.exe 放入 PATH 目录\n"))
                self.root.after(0, lambda: self.download_log_text.config(state="disabled"))

        threading.Thread(target=run_download).start()

    def create_download_progressbar(self):
        if hasattr(self, 'download_progressbar'):
            self.download_progressbar.destroy()
        self.download_progressbar = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.download_progressbar.pack(pady=10)
        self.download_progress_label = tk.Label(self.root, text="下载进度：0%")
        self.download_progress_label.pack()

    def update_download_progressbar(self, percent, remain):
        if hasattr(self, 'download_progressbar'):
            self.download_progressbar['value'] = percent
            mins, secs = divmod(int(remain), 60)
            self.download_progress_label.config(text=f"下载进度：{percent}%  剩余时间：{mins:02d}:{secs:02d}")

    def remove_download_progressbar(self):
        if hasattr(self, 'download_progressbar'):
            self.download_progressbar.destroy()
            self.download_progress_label.destroy()

    def build_eq_tab(self, tab):
        container = tk.Frame(tab, bg="white")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # 文件选择
        file_frame = tk.Frame(container, bg="white")
        file_frame.pack(fill="x", pady=(0, 8))
        tk.Label(file_frame, text="目标视频/音频文件：", bg="white", font=(None, 10)).pack(side="left")
        self.eq_file_entry = tk.Entry(file_frame, width=50, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.eq_file_entry.pack(side="left", padx=6)
        tk.Button(file_frame, text="选择文件", command=self._choose_eq_file).pack(side="left")

        # 9 段 EQ 输入（低3/中3/高3），输入 +3 / -3
        grp = tk.LabelFrame(container, text="均衡器（单位 dB）", bg="white", font=(None, 10))
        grp.pack(fill="x", pady=(8, 6))

        tk.Label(grp, text="低频", bg="white", font=(None, 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(grp, text="中频", bg="white", font=(None, 10, "bold")).grid(row=0, column=3, columnspan=3, sticky="w", padx=(10,0))
        tk.Label(grp, text="高频", bg="white", font=(None, 10, "bold")).grid(row=0, column=6, columnspan=3, sticky="w", padx=(10,0))

        self._eq_freqs = {
            "L1": 60, "L2": 120, "L3": 250,
            "M1": 500, "M2": 1000, "M3": 2000,
            "H1": 4000, "H2": 8000, "H3": 16000
        }
        labels = [("L1","60Hz"),("L2","120Hz"),("L3","250Hz"),
                  ("M1","500Hz"),("M2","1kHz"),("M3","2kHz"),
                  ("H1","4kHz"),("H2","8kHz"),("H3","16kHz")]

        self.eq_inputs = {}
        for idx, (key, text) in enumerate(labels):
            tk.Label(grp, text=text, bg="white", font=(None, 9)).grid(row=1, column=idx, padx=(0,6), sticky="w")
            ent = tk.Entry(grp, width=6, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
            ent.grid(row=2, column=idx, padx=(0,6), pady=(0,6))
            self.eq_inputs[key] = ent

        # 右侧：总体音量（与高中低同一行风格）
        tk.Label(grp, text="总音量", bg="white", font=(None, 10, "bold")).grid(row=0, column=9, columnspan=1, sticky="w", padx=(10,0))
        tk.Label(grp, text="总音量", bg="white", font=(None, 9)).grid(row=1, column=9, padx=(0,6), sticky="w")
        self.eq_volume_entry = tk.Entry(grp, width=8, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.eq_volume_entry.grid(row=2, column=9, padx=(0,6), pady=(0,6))

        # 操作按钮
        btns = tk.Frame(container, bg="white")
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="应用EQ", command=self.apply_eq_to_path).pack(side="left")
        tk.Button(btns, text="重置为0dB", command=self._reset_eq_inputs).pack(side="left", padx=8)

        # 提示
        tk.Label(container, text="在各框输入+3或-3，留空表示不调节。视频将复制视频流并替换为EQ后的音频。", bg="white", fg="#666", font=(None, 9)).pack(anchor="w", pady=(6, 0))

        # 均衡器日志区域
        log_frame = tk.Frame(container, bg="white")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(log_frame, text="均衡器日志", bg="white", font=(None, 10, "bold")).pack(anchor="w", pady=(0, 6))
        inner = tk.Frame(log_frame, bg="white")
        inner.pack(fill="both", expand=True)
        self.eq_log_text = tk.Text(inner, height=10, wrap="word", bg="white", font=(None, 10), state="disabled")
        self.eq_log_text.pack(side="left", fill="both", expand=True)
        # 防止用户编辑日志内容 - 使用更强的方法
        def prevent_edit_eq(event):
            if self.eq_log_text.cget("state") == "disabled":
                return "break"
            return None
        self.eq_log_text.bind("<Key>", prevent_edit_eq)
        self.eq_log_text.bind("<KeyPress>", prevent_edit_eq)
        self.eq_log_text.bind("<KeyRelease>", prevent_edit_eq)
        eq_scroll = tk.Scrollbar(inner, command=self.eq_log_text.yview)
        eq_scroll.pack(side="right", fill="y")
        self.eq_log_text.configure(yscrollcommand=eq_scroll.set)

    def _choose_eq_file(self):
        path = filedialog.askopenfilename(filetypes=[("Media files", "*.mp3;*.wav;*.flac;*.m4a;*.mp4;*.mkv;*.mov"), ("All files", "*.*")])
        if path:
            self.eq_file_entry.delete(0, tk.END)
            self.eq_file_entry.insert(0, path)

    def _reset_eq_inputs(self):
        for ent in self.eq_inputs.values():
            ent.delete(0, tk.END)
        if hasattr(self, 'eq_volume_entry'):
            self.eq_volume_entry.delete(0, tk.END)

    def _parse_gain(self, s, clamp=True):
        try:
            s = (s or "").strip()
            if not s:
                return 0.0
            # 兼容：全角空格、全角正负号、中文逗号小数、dB/db 后缀
            s = s.replace('\u3000', ' ').replace('，', ',')
            s = s.replace('＋', '+').replace('－', '-').replace('—', '-')
            s = s.replace('Db', 'dB')
            # 去掉 dB/db 后缀
            if s.lower().endswith('db'):
                s = s[:-2]
            s = s.strip()
            # 将逗号作为小数点
            if s.count(',') == 1 and '.' not in s:
                s = s.replace(',', '.')
            # 去掉开头的+
            if s.startswith('+'):
                s = s[1:]
            val = float(s)
            if clamp:
                if val > 12:
                    val = 12
                if val < -12:
                    val = -12
            return val
        except Exception:
            return 0.0

    def _nudge_volume(self, delta):
        try:
            current = self._parse_gain(self.eq_volume_entry.get() if hasattr(self, 'eq_volume_entry') else "")
            new_val = current + float(delta)
            if new_val > 12:
                new_val = 12
            if new_val < -12:
                new_val = -12
            # 显示为不带多余零的小数，尽量贴近其他输入风格
            text = f"{new_val:.2f}".rstrip('0').rstrip('.')
            if not text.startswith('-') and not text.startswith('0') and not text.startswith('.'):
                text = "+" + text  # 与频段常用“+3/-3”风格一致
            self.eq_volume_entry.delete(0, tk.END)
            self.eq_volume_entry.insert(0, text)
        except Exception:
            pass

    def _build_9band_filter(self):
        # 根据 9 个输入构造 ffmpeg equalizer 滤镜链（仅包含非 0dB 的频段）
        filters = []
        for key, f in self._eq_freqs.items():
            g = self._parse_gain(self.eq_inputs[key].get(), clamp=True)
            if g != 0.0:
                filters.append(f"equalizer=f={float(f)}:t=o:w=1:g={g}")
        # 追加总体音量调节（若有输入）
        vol_db = self._parse_gain(self.eq_volume_entry.get() if hasattr(self, 'eq_volume_entry') else "", clamp=False)
        if vol_db != 0.0:
            filters.append(f"volume={vol_db}dB")
        if not filters:
            return None
        return ",".join(filters)

    def apply_eq_to_path(self):
        path = (self.eq_file_entry.get() or "").strip()
        if not path or not os.path.exists(path):
            self.eq_log("❌ 请选择有效的文件路径")
            return

        eq_filter = self._build_9band_filter()
        if not eq_filter:
            self.eq_log("ℹ️ 未设置任何增益（均为 0dB），不进行处理")
            return

        def run():
            base, ext = os.path.splitext(path)
            ext_lower = ext.lower()
            try:
                if ext_lower in [".mp3", ".wav", ".flac", ".m4a"]:
                    out_path = f"{base}_EQ.wav"
                    self.eq_log(f"🔄 处理音频文件: {path}")
                    self.eq_log(f"🔧 使用滤镜: -af {eq_filter}")
                    cmd = [
                        "ffmpeg", "-loglevel", "info",
                        "-i", path,
                        "-af", eq_filter,
                        "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s32le",
                        "-y", out_path
                    ]
                    subprocess.run(cmd, shell=False)
                    self.eq_log(f"✅ 完成，已输出: {out_path}\n")
                elif ext_lower in [".mp4", ".mkv", ".mov"]:
                    out_path = f"{base}_EQ.mkv"
                    self.eq_log(f"🔄 处理视频文件: {path}")
                    self.eq_log(f"🔧 使用滤镜: -af {eq_filter}")
                    cmd = [
                        "ffmpeg", "-loglevel", "info",
                        "-i", path,
                        "-c:v", "copy",
                        "-af", eq_filter,
                        "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s32le",
                        "-y", out_path
                    ]
                    subprocess.run(cmd, shell=False)
                    self.eq_log(f"✅ 完成，已输出: {out_path}\n")
                else:
                    self.eq_log("❌ 不支持的文件类型（支持音频：mp3/wav/flac/m4a；视频：mp4/mkv/mov）")
            except Exception as e:
                self.eq_log(f"❌ EQ 处理失败: {e}")

        threading.Thread(target=run).start()

    def eq_log(self, message):
        # 在主线程安全写入"均衡器日志"
        def _write():
            if not hasattr(self, "eq_log_text"):
                return
            self.eq_log_text.config(state="normal")
            self.eq_log_text.insert(tk.END, f"{message}\n")
            self.eq_log_text.config(state="disabled")
            self.eq_log_text.see(tk.END)
        try:
            self.root.after(0, _write)
        except Exception:
            pass

    def build_bili_tab(self, tab):
        container = tk.Frame(tab, bg="white")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # 文件选择区域
        file_frame = tk.Frame(container, bg="white")
        file_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(file_frame, text="选择视频文件：", bg="white", font=(None, 10)).pack(side="left")
        self.bili_file_entry = tk.Entry(file_frame, width=60, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.bili_file_entry.pack(side="left", padx=6)
        tk.Button(file_frame, text="选择文件", command=self._choose_bili_file).pack(side="left")

        # biliup状态显示
        biliup_frame = tk.Frame(container, bg="white")
        biliup_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(biliup_frame, text="biliup状态：", bg="white", font=(None, 10)).pack(side="left")
        self.biliup_status_label = tk.Label(biliup_frame, text="检测中...", bg="white", font=(None, 10), fg="orange")
        self.biliup_status_label.pack(side="left", padx=6)
        tk.Button(biliup_frame, text="重新检测", command=self._check_biliup_status).pack(side="left")

        # 视频标题输入
        title_frame = tk.Frame(container, bg="white")
        title_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(title_frame, text="视频标题：", bg="white", font=(None, 10)).pack(side="left")
        self.bili_title_entry = tk.Entry(title_frame, width=60, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.bili_title_entry.pack(side="left", padx=6)

        # 封面图片选择
        cover_frame = tk.Frame(container, bg="white")
        cover_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(cover_frame, text="封面图片：", bg="white", font=(None, 10)).pack(side="left")
        self.bili_cover_entry = tk.Entry(cover_frame, width=50, bd=1, relief="solid", bg="white", highlightthickness=1, highlightbackground="#CCCCCC", fg="black", font=(None, 10))
        self.bili_cover_entry.pack(side="left", padx=6)
        tk.Button(cover_frame, text="选择封面", command=self._choose_bili_cover).pack(side="left")

        # 上传按钮
        upload_frame = tk.Frame(container, bg="white")
        upload_frame.pack(fill="x", pady=(0, 10))
        
        # 上传和取消按钮
        button_frame = tk.Frame(upload_frame, bg="white")
        button_frame.pack()
        
        self.bili_upload_button = tk.Button(button_frame, text="🚀 开始上传到B站", command=self.start_bili_upload, bg="#FF6B6B", fg="white", font=(None, 12, "bold"), relief="flat", padx=20, pady=8)
        self.bili_upload_button.pack(side="left", padx=(0, 10))
        
        self.bili_cancel_button = tk.Button(button_frame, text="⏹️ 取消上传", command=self.cancel_bili_upload, bg="#6C757D", fg="white", font=(None, 12, "bold"), relief="flat", padx=20, pady=8, state="disabled")
        self.bili_cancel_button.pack(side="left")

        # 上传状态显示
        self.bili_status_label = tk.Label(container, text="", bg="white", font=(None, 10))
        self.bili_status_label.pack(pady=5)
        

        # B站上传日志区域
        log_frame = tk.Frame(container, bg="white")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        # 日志标题和清空按钮
        log_header = tk.Frame(log_frame, bg="white")
        log_header.pack(fill="x", pady=(0, 6))
        tk.Label(log_header, text="B站上传日志", bg="white", font=(None, 10, "bold")).pack(side="left")
        tk.Button(log_header, text="🧹 清空日志", command=self.clear_bili_log).pack(side="right")
        
        inner = tk.Frame(log_frame, bg="white")
        inner.pack(fill="both", expand=True)
        self.bili_log_text = tk.Text(inner, height=10, wrap="word", bg="white", font=(None, 10), state="disabled")#B站上传日志区域
        self.bili_log_text.pack(side="left", fill="both", expand=True)
        self.bili_log_text.bind("<Control-c>", lambda e: self.copy_selected(self.bili_log_text))#允许使用 Ctrl+C 复制选中文本
        def prevent_edit_bili(event):#防止用户编辑日志内容 - 使用更强的方法
            if self.bili_log_text.cget("state") == "disabled":
                return "break"
            return None
        self.bili_log_text.bind("<Key>", prevent_edit_bili)
        self.bili_log_text.bind("<KeyPress>", prevent_edit_bili)
        self.bili_log_text.bind("<KeyRelease>", prevent_edit_bili)
        bili_scroll = tk.Scrollbar(inner, command=self.bili_log_text.yview)#B站上传日志区域滚动条
        bili_scroll.pack(side="right", fill="y")#B站上传日志区域滚动条
        self.bili_log_text.configure(yscrollcommand=bili_scroll.set)

    def _choose_bili_file(self):#选择视频文件
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4;*.mkv;*.mov;*.avi"), ("All files", "*.*")]
        )
        if path:
            self.bili_file_entry.delete(0, tk.END)
            self.bili_file_entry.insert(0, path)
            # 自动设置标题为文件名
            filename = os.path.splitext(os.path.basename(path))[0]
            self.bili_title_entry.delete(0, tk.END)
            self.bili_title_entry.insert(0, filename)
            # 自动查找封面
            self._auto_find_cover()

    def _find_biliup(self):
        """自动寻找biliup相关文件"""
        # 获取程序所在目录
        if getattr(sys, 'frozen', False):
            # 如果是打包的exe文件
            program_dir = os.path.dirname(sys.executable)
        else:
            # 如果是Python脚本
            program_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 首先检查程序同目录下是否有biliup.exe和cookies.json
        biliup_exe = os.path.join(program_dir, "biliup.exe")
        cookies_file = os.path.join(program_dir, "cookies.json")
        
        if os.path.exists(biliup_exe) and os.path.exists(cookies_file):
            self.biliup_path = program_dir
            self.biliup_exe_path = biliup_exe
            self.biliup_cookies_path = cookies_file
            return True
        
        # 检查程序安装目录（动态检测）
        if getattr(sys, 'frozen', False):
            # 如果是打包的exe文件，使用exe文件所在目录
            install_dir = os.path.dirname(sys.executable)
        else:
            # 如果是Python脚本，使用脚本所在目录
            install_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 检查程序安装目录
        if os.path.exists(install_dir):
            biliup_exe = os.path.join(install_dir, "biliup.exe")
            cookies_file = os.path.join(install_dir, "cookies.json")
            
            if os.path.exists(biliup_exe) and os.path.exists(cookies_file):
                self.biliup_path = install_dir
                self.biliup_exe_path = biliup_exe
                self.biliup_cookies_path = cookies_file
                return True
        
        # 如果程序同目录下没有，再寻找biliup文件夹
        biliup_dirs = [
            os.path.join(program_dir, "biliup"),
            os.path.join(program_dir, "..", "biliup"),  # 上级目录
            os.path.join(program_dir, "..", "..", "biliup"),  # 上上级目录
            os.path.join(install_dir, "biliup"),  # 程序安装目录下的biliup文件夹
        ]
        
        for biliup_dir in biliup_dirs:
            biliup_dir = os.path.abspath(biliup_dir)
            if os.path.exists(biliup_dir):
                biliup_exe = os.path.join(biliup_dir, "biliup.exe")
                cookies_file = os.path.join(biliup_dir, "cookies.json")
                
                if os.path.exists(biliup_exe) and os.path.exists(cookies_file):
                    self.biliup_path = biliup_dir
                    self.biliup_exe_path = biliup_exe
                    self.biliup_cookies_path = cookies_file
                    return True
        
        return False
    
    def _check_biliup_status(self):
        """检查biliup状态"""
        def check():
            if self._find_biliup():
                self.root.after(0, lambda: self.biliup_status_label.config(
                    text="✅ 已找到biliup", fg="green"
                ))
                self.bili_log(f"✅ 找到biliup: {self.biliup_path}")
                # 通过 biliup 的 cookies.json 尝试解析 B站用户名 和空间URL
                username, space_url = self.get_bili_user_info_from_cookies()
                self.bili_log(f"B站用户名：{username}")
                self.bili_log(f"URL：{space_url}")
                self.bili_log("")  # 添加空行
            else:
                self.root.after(0, lambda: self.biliup_status_label.config(
                    text="❌ 未找到biliup", fg="red"
                ))
                self.bili_log("❌ 未找到biliup相关文件")
                self.bili_log("请将biliup.exe和cookies.json文件放在以下位置之一：")
                
                # 显示实际检测到的程序路径
                if getattr(sys, 'frozen', False):
                    actual_path = os.path.dirname(sys.executable)
                else:
                    actual_path = os.path.dirname(os.path.abspath(__file__))
                
                self.bili_log(f"1. 程序目录下: {actual_path}")
                self.bili_log(f"2. 程序目录下的biliup文件夹: {os.path.join(actual_path, 'biliup')}")
                self.bili_log("3. 程序上级目录的biliup文件夹")
                self.bili_log("")  # 添加空行
        
        threading.Thread(target=check).start()

    def _choose_bili_cover(self):
        path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.bmp"), ("All files", "*.*")]
        )
        if path:
            self.bili_cover_entry.delete(0, tk.END)
            self.bili_cover_entry.insert(0, path)

    def _auto_find_cover(self):
        video_path = self.bili_file_entry.get().strip()
        if not video_path:
            self.bili_log("❌ 请先选择视频文件")
            self.bili_log("")  # 添加空行
            return
            
        video_dir = os.path.dirname(video_path)
        
        # 查找JPG格式
        for ext in ['*.jpg', '*.jpeg']:
            for file in os.listdir(video_dir):
                if file.lower().endswith(ext[1:]):
                    cover_path = os.path.join(video_dir, file)
                    self.bili_cover_entry.delete(0, tk.END)
                    self.bili_cover_entry.insert(0, cover_path)
                    return
        
        # 查找PNG格式
        for file in os.listdir(video_dir):
            if file.lower().endswith('.png'):
                cover_path = os.path.join(video_dir, file)
                self.bili_cover_entry.delete(0, tk.END)
                self.bili_cover_entry.insert(0, cover_path)
                return
                
        self.bili_log("❌ 未在视频目录找到JPG/PNG图片")

    def get_bili_user_info_from_cookies(self):
        """
        参考 biliup-app-new 的做法：
        - 从 biliup 使用的 cookies.json 中还原出 Cookie
        - 调用 B站开放接口获取当前登录账号信息
        - 返回 用户名 和 空间 URL
        任意一步失败则返回“未知”占位，避免影响主流程。
        """
        username = "未知"
        space_url = "未知"

        try:
            if not self.biliup_cookies_path or not os.path.exists(self.biliup_cookies_path):
                return username, space_url

            with open(self.biliup_cookies_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 先还原成 requests 可用的 cookies 字典
            cookies = {}

            # 情况 1：cookies.json 是一个 cookie 列表（常见）
            if isinstance(data, list):
                for c in data:
                    if not isinstance(c, dict):
                        continue
                    name = c.get("name")
                    value = c.get("value")
                    if name and value:
                        cookies[name] = value

            # 情况 2：cookies.json 是一个 dict（你的示例就是这种）
            elif isinstance(data, dict):
                # 2.1 biliup-app/biliup-rs 风格：{"cookie_info":{"cookies":[...]}, "token_info":{"mid":...}, ...}
                if "cookie_info" in data and isinstance(data["cookie_info"], dict):
                    ci = data["cookie_info"]
                    if "cookies" in ci and isinstance(ci["cookies"], list):
                        for c in ci["cookies"]:
                            if not isinstance(c, dict):
                                continue
                            name = c.get("name")
                            value = c.get("value")
                            if name and value:
                                cookies[name] = value
                # 2.2 通用结构：{"cookies":[...]}
                if not cookies and "cookies" in data and isinstance(data["cookies"], list):
                    for c in data["cookies"]:
                        if not isinstance(c, dict):
                            continue
                        name = c.get("name")
                        value = c.get("value")
                        if name and value:
                            cookies[name] = value
                # 2.3 顶层键值对形式
                if not cookies:
                    for k, v in data.items():
                        if isinstance(v, str):
                            cookies[k] = v

            # 如果没解析出任何 cookie，就直接返回“未知”
            if not cookies:
                return username, space_url

            # 先尝试直接从 token_info.mid 推出空间 URL（biliup-app 风格）
            if isinstance(data, dict) and "token_info" in data and isinstance(data["token_info"], dict):
                mid = data["token_info"].get("mid")
                if mid:
                    space_url = f"https://space.bilibili.com/{mid}"

            # 参考 biliup-app-new，使用 cookies 调用 B站 nav 接口获取当前登录用户信息
            # 如果本地网络或环境不通，这一步可能失败，不影响整体功能
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://www.bilibili.com/",
                }
                resp = requests.get(
                    "https://api.bilibili.com/x/web-interface/nav",
                    headers=headers,
                    cookies=cookies,
                    timeout=5,
                )

                if resp.status_code == 200:
                    j = resp.json()
                    if j.get("code") == 0 and "data" in j:
                        d = j["data"]
                        # data.uname 是当前登录账号昵称
                        uname = d.get("uname") or d.get("username")
                        if uname:
                            username = uname
                        mid2 = d.get("mid") or d.get("uid")
                        if mid2:
                            space_url = f"https://space.bilibili.com/{mid2}"
            except Exception:
                # 网络请求失败则忽略，保留前面从 token_info / cookies 推出来的信息
                pass

            # 如果 API 和 token_info 都没拿到 UID，再退一步从 cookies 里找 DedeUserID
            if space_url == "未知":
                uid = None
                # 从 cookies 字典里找
                for key, val in cookies.items():
                    if key.lower() == "dedeuserid" and val:
                        uid = val
                        break
                if uid:
                    space_url = f"https://space.bilibili.com/{uid}"

        except Exception:
            # 解析或网络请求失败时静默回退为“未知”
            pass

        return username, space_url

    def start_bili_upload(self):
        video_path = self.bili_file_entry.get().strip()
        title = self.bili_title_entry.get().strip()
        cover_path = self.bili_cover_entry.get().strip()
        
        if not video_path:
            self.bili_log("❌ 请选择要上传的视频文件")
            return
            
        if not os.path.exists(video_path):
            self.bili_log("❌ 视频文件不存在")
            return
            
        # 检查biliup是否已找到
        if not self.biliup_path or not self.biliup_exe_path or not self.biliup_cookies_path:
            self.bili_log("❌ 未找到biliup，请点击'重新检测'按钮")
            return
            
        if not title:
            title = os.path.splitext(os.path.basename(video_path))[0]
            self.bili_log(f"ℹ️ 使用视频文件名作为标题: {title}")

        def run_upload():
            try:
                self.bili_log("")  # 添加空行
                self.bili_log(f"🚀 开始上传视频到B站: {os.path.basename(video_path)}")
                self.bili_log(f"📝 标题: {title}")
                self.bili_log(f"🔧 使用biliup: {self.biliup_exe_path}")
                self.bili_log("")  # 添加空行
                self.bili_status_label.config(text="上传中...", fg="orange")
                
                # 添加上传前延迟，避免频率限制
                self.bili_log("⏳ 等待1秒后开始上传，避免频率限制...")
                time.sleep(1)
                
                # 更新按钮状态
                self.bili_upload_button.config(state="disabled")
                self.bili_cancel_button.config(state="normal")
                
                # 构建biliup命令
                cmd = [
                    self.biliup_exe_path, "upload",
                    "--title", title,
                    "--tag", "电音节,LIVE,DJ,电子音乐,电音",
                    "--tid", "29",
                    "--copyright", "2",
                    "--source", "yt",
                    "--hires", "1"
                ]
                
                # 添加封面参数
                if cover_path and os.path.exists(cover_path):
                    cmd.extend(["--cover", cover_path])
                    self.bili_log(f"🖼️ 使用封面: {os.path.basename(cover_path)}")
                    self.bili_log("")  # 添加空行
                else:
                    self.bili_log("ℹ️ 未设置封面，将使用默认封面")
                    self.bili_log("")  # 添加空行
                
                # 添加视频文件路径
                cmd.append(video_path)
                
                self.bili_log(f"🔧 执行命令: {' '.join(cmd)}")
                self.bili_log("")  # 添加空行
                
                # 检查cookies文件是否存在
                if not os.path.exists(self.biliup_cookies_path):
                    self.bili_log(f"❌ cookies文件不存在: {self.biliup_cookies_path}")
                    return
                
                # 切换到biliup目录，这样biliup就能找到cookies.json文件
                original_cwd = os.getcwd()
                os.chdir(self.biliup_path)
                
                try:
                    # 使用终端运行biliup，同时静默监控输出
                    if shutil.which("wt.exe"):
                        # 使用Windows Terminal
                        cmd_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
                        terminal_cmd = ["wt.exe", "cmd", "/c", f"cd /d \"{self.biliup_path}\" && {cmd_str}"]
                    elif shutil.which("powershell.exe"):
                        # 使用PowerShell
                        cmd_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
                        terminal_cmd = ["powershell.exe", "-Command", f"Set-Location '{self.biliup_path}'; & {cmd_str}"]
                    else:
                        # 使用传统CMD
                        cmd_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
                        terminal_cmd = ["cmd.exe", "/c", f"cd /d \"{self.biliup_path}\" && {cmd_str}"]
                    
                    # 启动终端窗口显示biliup输出，使用进程组
                    terminal_process = subprocess.Popen(
                        terminal_cmd,
                        stdout=None,  # 不重定向，让终端显示
                        stderr=None,
                        text=True, 
                        encoding='utf-8',
                        errors='replace',
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,  # 创建新的进程组
                        cwd=self.biliup_path
                    )
                    
                    # 同时启动静默监控进程
                    monitor_process = subprocess.Popen(
                        cmd,  # 直接使用biliup命令
                        stdout=subprocess.PIPE,  # 重定向输出以便检测完成
                        stderr=subprocess.STDOUT,
                        text=True, 
                        encoding='utf-8',
                        errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW,  # 不显示窗口
                        cwd=self.biliup_path  # 设置工作目录
                    )
                    
                    process = monitor_process  # 使用监控进程
                    
                    # 保存进程引用以便取消
                    self.bili_upload_process = process
                    self.bili_terminal_process = terminal_process
                    
                    # 显示上传开始信息
                    if shutil.which("wt.exe"):
                        self.bili_log("🚀 开始上传，请查看Windows Terminal窗口了解详细进度...")
                        self.bili_log("")  # 添加空行
                    elif shutil.which("powershell.exe"):
                        self.bili_log("🚀 开始上传，请查看PowerShell窗口了解详细进度...")
                        self.bili_log("")  # 添加空行
                    else:
                        self.bili_log("🚀 开始上传，请查看CMD窗口了解详细进度...")
                        self.bili_log("")  # 添加空行
                    
                    # 实时监控输出并等待投稿成功
                    self.bili_log("⏳ 等待上传完成...")
                    self.bili_log("")  # 添加空行
                    
                    upload_success = False
                    upload_failed = False
                    
                    # 静默监控输出，不显示详细日志
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if line:
                                line_stripped = line.strip()
                                # 不显示详细输出，只检测关键信息
                                
                                # 检查是否包含成功信息
                                if "投稿成功" in line_stripped or "APP接口投稿成功" in line_stripped:
                                    upload_success = True
                                    self.bili_log("✅ 检测到投稿成功！")
                                    break
                                elif "Error:" in line_stripped or "error" in line_stripped.lower() or "failed" in line_stripped.lower():
                                    upload_failed = True
                                    self.bili_log(f"❌ 检测到上传错误: {line_stripped}")
                                    break
                    except Exception as e:
                        self.bili_log(f"❌ 监控输出时出错: {e}")
                    
                    # 等待进程完成
                    return_code = process.wait()
                    
                    if upload_success or return_code == 0:
                        self.bili_log("✅ 上传成功！去B站创作中心查看~")
                        self.bili_log("")  # 添加空行
                        self.bili_status_label.config(text="上传成功！", fg="green")
                    elif self.bili_upload_cancelled:
                        # 用户主动取消，不显示失败信息
                        pass  # 取消信息已经在cancel_bili_upload中显示
                    elif upload_failed:
                        self.bili_log("❌ 上传失败！检测到错误信息")
                        self.bili_log("")  # 添加空行
                        self.bili_status_label.config(text="上传失败！", fg="red")
                    else:
                        self.bili_log(f"❌ 上传失败！返回码: {return_code}")
                        self.bili_log("")  # 添加空行
                        self.bili_status_label.config(text="上传失败！", fg="red")
                        
                finally:
                    # 恢复原始工作目录
                    os.chdir(original_cwd)
                    # 恢复按钮状态
                    self.bili_upload_button.config(state="normal")
                    self.bili_cancel_button.config(state="disabled")
                    # 清除进程引用
                    self.bili_upload_process = None
                    self.bili_terminal_process = None
                    self.bili_upload_cancelled = False  # 重置取消标志
                    
            except Exception as e:
                self.bili_log(f"❌ 上传过程中出现错误: {e}")
                self.bili_status_label.config(text="上传出错！", fg="red")
                # 恢复按钮状态
                self.bili_upload_button.config(state="normal")
                self.bili_cancel_button.config(state="disabled")
                # 清除进程引用
                self.bili_upload_process = None

        self.bili_upload_thread = threading.Thread(target=run_upload)
        self.bili_upload_thread.start()

    def cancel_bili_upload(self):
        """取消B站上传"""
        if self.bili_upload_process:
            try:
                self.bili_log("⏹️ 正在取消上传...")
                self.bili_upload_cancelled = True  # 设置取消标志
                
                # 终止监控进程（这会同时终止biliup）
                self.bili_upload_process.terminate()
                try:
                    self.bili_upload_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.bili_upload_process.kill()
                    self.bili_upload_process.wait()
                
                # 额外强制终止biliup进程
                try:
                    if os.name == 'nt':
                        # 使用taskkill强制终止所有biliup进程
                        subprocess.run([
                            "taskkill", "/F", "/IM", "biliup.exe"
                        ], capture_output=True, timeout=3)
                except Exception:
                    pass
                
                # 强制关闭CMD窗口
                try:
                    if os.name == 'nt':
                        # 使用taskkill强制终止CMD相关进程
                        subprocess.run([
                            "taskkill", "/F", "/T", "/PID", str(self.bili_terminal_process.pid)
                        ], capture_output=True, timeout=3)
                        
                        # 额外尝试终止所有cmd.exe进程（如果上面的方法失败）
                        try:
                            subprocess.run([
                                "taskkill", "/F", "/IM", "cmd.exe"
                            ], capture_output=True, timeout=2)
                        except Exception:
                            pass
                            
                        # 尝试终止Windows Terminal进程
                        try:
                            subprocess.run([
                                "taskkill", "/F", "/IM", "WindowsTerminal.exe"
                            ], capture_output=True, timeout=2)
                        except Exception:
                            pass
                            
                        # 尝试终止PowerShell进程
                        try:
                            subprocess.run([
                                "taskkill", "/F", "/IM", "powershell.exe"
                            ], capture_output=True, timeout=2)
                        except Exception:
                            pass
                except Exception as e:
                    self.bili_log(f"⚠️ 强制关闭终端时出错: {e}")
                
                self.bili_log("✅ 上传已取消")
                self.bili_status_label.config(text="上传已取消", fg="orange")
                
            except Exception as e:
                self.bili_log(f"❌ 取消上传时出现错误: {e}")
                self.bili_status_label.config(text="取消失败", fg="red")
            finally:
                # 恢复按钮状态
                self.bili_upload_button.config(state="normal")
                self.bili_cancel_button.config(state="disabled")
                # 清除进程引用
                self.bili_upload_process = None
                self.bili_terminal_process = None
        else:
            self.bili_log("ℹ️ 没有正在进行的上传任务")

    

    def clear_bili_log(self):
        """清空B站上传日志"""
        if hasattr(self, "bili_log_text"):
            self.bili_log_text.config(state="normal")
            self.bili_log_text.delete("1.0", tk.END)
            self.bili_log_text.config(state="disabled")

    def bili_log(self, message):
        # 在主线程安全写入"B站上传日志"
        def _write():
            if not hasattr(self, "bili_log_text"):
                return
            self.bili_log_text.config(state="normal")
            self.bili_log_text.insert(tk.END, f"{message}\n")
            self.bili_log_text.config(state="disabled")
            self.bili_log_text.see(tk.END)
        try:
            self.root.after(0, _write)
        except Exception:
            pass

if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass

    root = tk.Tk()
    icon_path = resource_path("icons/文2.ico")
    root.iconbitmap(default=icon_path)
    app = SimpleDownloader(root)
    root.mainloop()
