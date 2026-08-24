"""
壁纸系统 - Windows 壁纸 API + WallpaperRenderer
从 data/config.json 读取配置，管理渲染循环和壁纸设置
"""
import ctypes
import os
import time
import random
import math
import atexit
from collections import deque
from typing import Optional

from PIL import Image, ImageDraw

from data_loader import get_config
from systems.audio_system import AudioSimulator, MusicPlaybackSystem
from systems.render_system import EFFECT_REGISTRY, BACKGROUND_THEMES, BackgroundTheme
from systems.effect_manager import _make_effect


# ==================== Windows 壁纸 API ====================
def set_wallpaper(image_path: str) -> bool:
    """使用 Windows API 设置桌面壁纸"""
    try:
        abs_path = os.path.abspath(image_path).replace('/', '\\')
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        user32 = ctypes.windll.user32
        result = user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, abs_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return result != 0
    except Exception as e:
        print(f"设置壁纸失败: {e}")
        return False


# ==================== 性能监控 ====================
class PerformanceMonitor:
    """性能监控器"""
    def __init__(self):
        self.frame_times = deque(maxlen=60)
        self.start_time = time.time()
        self.frame_count = 0
        self.fps = 0.0

    def start_frame(self):
        self._frame_start = time.time()

    def end_frame(self):
        if not hasattr(self, '_frame_start'):
            return
        self.frame_count += 1
        frame_time = time.time() - self._frame_start
        self.frame_times.append(frame_time)
        if time.time() - self.start_time >= 1.0:
            self.fps = self.frame_count / (time.time() - self.start_time)
            self.start_time = time.time()
            self.frame_count = 0

    def get_fps(self) -> float:
        return self.fps

    def get_avg_frame_time(self) -> float:
        return sum(self.frame_times) / len(self.frame_times) if self.frame_times else 0


# ==================== 壁纸渲染器 ====================
class WallpaperRenderer:
    """壁纸渲染器 - 主控制器，组装各系统"""

    def __init__(self, width: int = 1920, height: int = 1080):
        self.config = get_config()
        self.width = width
        self.height = height

        # 音频系统
        print("[INIT] 创建 AudioSimulator...", flush=True)
        self.audio = AudioSimulator()

        # 性能监控
        self.perf = PerformanceMonitor()

        # 效果管理
        print("[INIT] 创建 EffectManager...", flush=True)
        from systems.effect_manager import EffectManager
        self.effect_manager = EffectManager(EFFECT_REGISTRY, self.config)

        # 背景主题
        self.bg_theme: Optional[BackgroundTheme] = None
        self.current_bg_name = self.effect_manager.current_bg_name

        # 音乐播放
        self.music: Optional[MusicPlaybackSystem] = None
        self.music_params = {}

        # 壁纸设置
        self.temp_wallpaper_path = os.path.join(
            os.environ.get('TEMP', '.'), self.config['wallpaper']['temp_filename'])
        self.running = True
        self.paused = False  # 托盘可暂停渲染

        # 帧率控制
        self.last_frame_time = time.time()
        self.target_fps = self.config['wallpaper']['target_fps']
        self.min_frame_time = 1.0 / self.target_fps

        # 分辨率缩放
        perf_cfg = self.config['performance']
        self.resolution_scale = self.config['wallpaper']['resolution_scale']
        self.render_width = int(self.width * self.resolution_scale)
        self.render_height = int(self.height * self.resolution_scale)
        self.low_performance_mode = False

        print(f"[INIT] 壁纸尺寸: {self.width}x{self.height}")
        print(f"[INIT] 渲染尺寸: {self.render_width}x{self.render_height}")
        print("[INIT] 初始化完成!", flush=True)

        # 生成并播放音乐
        self._init_music()

        # 系统托盘
        from systems.tray_system import SystemTrayManager
        self.tray = SystemTrayManager(self)

        # 注册退出清理钩子
        atexit.register(self.shutdown)

    def _init_music(self):
        """生成并播放音乐"""
        self.music = MusicPlaybackSystem(self.audio)
        self.music.generate_and_play()

    def get_screen_resolution(self) -> tuple:
        """获取屏幕分辨率"""
        try:
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except:
            return 1920, 1080

    def render_frame(self) -> Image.Image:
        """渲染一帧"""
        current_time = time.time()
        dt = current_time - self.last_frame_time
        self.last_frame_time = current_time

        # 更新音频
        self.audio.update(dt)

        # 更新效果切换
        self.effect_manager.update()

        # 创建渲染图像
        img = Image.new('RGB', (self.render_width, self.render_height),
                        self.effect_manager.bg_default_color)
        draw = ImageDraw.Draw(img)

        # 绘制背景主题
        bg_name = self.effect_manager.current_bg_name
        bg_cls = BACKGROUND_THEMES.get(bg_name)
        if bg_cls:
            if self.bg_theme is None or self.current_bg_name != bg_name:
                self.bg_theme = bg_cls(draw, self.render_width, self.render_height)
                self.current_bg_name = bg_name
            self.bg_theme.update(dt)
            self.bg_theme.draw()
        else:
            # 默认渐变背景
            bg_hue = (current_time * 0.02) % 1.0
            from utils.helpers import hsv_to_rgb
            bg_color = hsv_to_rgb(bg_hue, 0.3, 0.05)
            draw.rectangle([0, 0, self.render_width, self.render_height], fill=bg_color)

        # 渲染当前效果（携带 params）
        current_entry = self.effect_manager.get_current_effect_entry()
        if current_entry:
            effect = _make_effect(current_entry, draw, self.render_width, self.render_height, self.audio)
            effect.update(dt)
            effect.draw()

        # 处理过渡
        if self.effect_manager.is_transitioning:
            overlay = self.effect_manager.render_with_transition(
                draw, self.render_width, self.render_height, self.audio, dt)
            if overlay:
                alpha = self.effect_manager.transition_progress
                mask = Image.new('L', (self.render_width, self.render_height), int(alpha * 255))
                img = Image.composite(img, overlay, mask)

        # 缩放回原始分辨率
        if self.resolution_scale != 1.0:
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

        return img

    def update_wallpaper(self):
        """更新壁纸"""
        img = self.render_frame()
        img.save(self.temp_wallpaper_path)
        set_wallpaper(self.temp_wallpaper_path)
        self.perf.end_frame()

    def run(self):
        """运行渲染循环"""
        print("=" * 50)
        print("Windows 动态壁纸已启动 (ECS 架构)")
        print("=" * 50)
        print(f"可用效果: {len(self.effect_manager.effect_names)} 种")
        print(f"可用背景主题: {', '.join(self.effect_manager.bg_theme_names)}")
        print("已最小化到系统托盘，右键图标可控制")
        print("=" * 50)

        # 启动系统托盘（独立线程）
        self.tray.run()

        frame_count = 0
        start_time = time.time()
        last_perf_check = start_time
        frame_count_per_sec = 0
        frame_times_sum = 0.0
        perf_cfg = self.config['performance']

        try:
            while self.running:
                # 暂停时空转等待
                if self.paused:
                    time.sleep(0.1)
                    continue

                frame_start = time.time()

                self.perf.start_frame()
                self.update_wallpaper()
                frame_count += 1
                frame_count_per_sec += 1

                frame_time = time.time() - frame_start
                frame_times_sum += frame_time

                # 每秒性能检查
                if time.time() - last_perf_check >= 1.0:
                    actual_fps = frame_count_per_sec

                    # 低性能自适应
                    if actual_fps < self.target_fps * perf_cfg['low_perf_fps_threshold_ratio'] and not self.low_performance_mode:
                        self.low_performance_mode = True
                        if self.resolution_scale > perf_cfg['min_resolution_scale']:
                            self.resolution_scale *= perf_cfg['resolution_scale_down_factor']
                            self.render_width = int(self.width * self.resolution_scale)
                            self.render_height = int(self.height * self.resolution_scale)
                            self.bg_theme = None
                            print(f"[性能] 降低分辨率至 {self.render_width}x{self.render_height}")
                    elif actual_fps > self.target_fps * perf_cfg['recovery_fps_threshold_ratio'] and self.low_performance_mode:
                        if self.resolution_scale < 1.0:
                            self.resolution_scale = min(
                                self.resolution_scale * perf_cfg['resolution_scale_up_factor'], 1.0)
                            self.render_width = int(self.width * self.resolution_scale)
                            self.render_height = int(self.height * self.resolution_scale)
                            self.bg_theme = None
                            print(f"[性能] 提高分辨率至 {self.render_width}x{self.render_height}")

                    print(f"[{self.effect_manager.current_name}] FPS: {actual_fps:.1f} | 渲染: {self.render_width}x{self.render_height}")

                    last_perf_check = time.time()
                    frame_count_per_sec = 0
                    frame_times_sum = 0

                # 帧率控制
                sleep_time = self.min_frame_time - frame_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n正在退出...")
            self.shutdown()

    def shutdown(self):
        """完整关闭渲染器：停止托盘、停止音乐、释放资源"""
        print("[EXIT] 正在关闭...", flush=True)
        self.running = False
        self.paused = False  # 解除暂停，让主循环退出
        if hasattr(self, 'tray'):
            self.tray.stop()
        if self.music:
            try:
                self.music.shutdown()
            except Exception as e:
                print(f"[EXIT] 关闭音乐系统时出错: {e}")
        print("[EXIT] 已退出。")


# ==================== 注册表工具 ====================
def toggle_auto_start(enable: bool):
    """切换开机自启动"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DynamicWallpaper"
    import sys
    script_path = os.path.abspath(sys.argv[0])
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{script_path}"')
            print("已开启开机自启动")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                print("已关闭开机自启动")
            except FileNotFoundError:
                print("开机自启动未设置")
        winreg.CloseKey(key)
    except Exception as e:
        print(f"设置开机自启动失败: {e}")


def is_auto_start_enabled() -> bool:
    """检查是否已开启开机自启动"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DynamicWallpaper"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
