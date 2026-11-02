"""
系统托盘模块 - 最小化到系统托盘，右键菜单控制
依赖: pystray, Pillow

[2026-11-02 接线改造：事件驱动]
菜单回调不再直接改渲染器状态，而是 emit 事件，由 core/assembly.py 装配的
订阅者执行 —— 托盘线程与渲染主线程通过 Context 通信，避免跨线程直改状态。
"""
import threading
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw
    _PYSTRAY_OK = True
except ImportError:
    _PYSTRAY_OK = False


def _create_icon_image(size: int = 64, hue: float = 0.6) -> Image.Image:
    """用 PIL 生成托盘图标：渐变圆形 + 音波纹"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 渐变圆形背景
    cx, cy = size // 2, size // 2
    for r in range(size // 2, 0, -1):
        t = r / (size // 2)
        # HSV → RGB 简化
        h = hue
        s = 0.8
        v = 0.5 + 0.5 * (1 - t)
        import colorsys
        rgb = colorsys.hsv_to_rgb(h, s, v)
        color = tuple(int(c * 255) for c in rgb) + (230,)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # 音波纹（3条弧线）
    for i, amp in enumerate([0.7, 0.5, 0.3]):
        wave_r = int(size * 0.2 * amp)
        y_offset = int((i - 1) * size * 0.12)
        alpha = int(200 * amp)
        draw.arc(
            [cx - wave_r, cy + y_offset - wave_r, cx + wave_r, cy + y_offset + wave_r],
            start=200, end=340,
            fill=(255, 255, 255, alpha),
            width=max(1, size // 20)
        )

    return img


class SystemTrayManager:
    """系统托盘管理器 — 右键菜单控制壁纸"""

    def __init__(self, renderer, ctx=None):
        """
        Args:
            renderer: WallpaperRenderer 实例，用于控制渲染/音乐/效果切换
            ctx: core.context.Context 实例。提供时菜单回调改为 emit 事件
                  （事件驱动、跨线程安全）；缺省时退化为直调 renderer（向后兼容）。
        """
        self.renderer = renderer
        self.ctx = ctx
        if not _PYSTRAY_OK:
            print("[TRAY] pystray 未安装，系统托盘功能不可用")
            print("[TRAY] 安装: pip install pystray")
            self._icon = None
            return

        self._icon: Optional[pystray.Icon] = None
        self._muted = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None

        # 构建菜单
        self._menu = pystray.Menu(
            pystray.MenuItem(
                lambda text: self._get_current_effect_text(),
                lambda: None,
                enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda text: '🔊 取消静音' if self._muted else '🔇 静音',
                self._toggle_mute),
            pystray.MenuItem(
                lambda text: '▶ 恢复渲染' if self._paused else '⏸ 暂停渲染',
                self._toggle_pause),
            pystray.MenuItem('⏭ 下一个效果', self._next_effect),
            pystray.MenuItem('🔄 重新加载效果', self._reload_effects),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('❌ 退出', self._quit),
        )

    # ---- 事件派发 ----

    def _emit(self, event: str, *args) -> bool:
        """emit 事件到 Context。返回是否成功派发（无 ctx 或无订阅者时为 False）。"""
        if self.ctx is None:
            return False
        try:
            self.ctx.emit(event, *args)
            return True
        except Exception as e:
            print(f"[TRAY] 派发事件 '{event}' 失败: {e}")
            return False

    # ---- 菜单回调 ----

    def _get_current_effect_text(self) -> str:
        """获取当前效果名"""
        try:
            name = self.renderer.effect_manager.get_current_effect_name()
            return f'♪ {name}'
        except Exception:
            return '♪ Blur 壁纸'

    def _toggle_mute(self, icon, item):
        """切换静音（事件驱动：emit tray:mute，由装配层订阅者执行）"""
        if self._emit("tray:mute"):
            self._muted = not self._muted
            print(f"[TRAY] {'已静音' if self._muted else '已取消静音'}")
        else:
            self._toggle_mute_direct()
        self._update_icon(icon)

    def _toggle_mute_direct(self):
        """无 Context 时的直调退化路径（向后兼容）。"""
        self._muted = not self._muted
        try:
            if self._muted:
                # 静音：暂停音乐
                import pygame
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.pause()
                print("[TRAY] 已静音")
            else:
                # 取消静音：恢复播放
                import pygame
                if pygame.mixer.get_init():
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.unpause()
                    elif self.renderer.music.music_path:
                        pygame.mixer.music.play(loops=-1)
                print("[TRAY] 已取消静音")
        except Exception as e:
            print(f"[TRAY] 切换静音失败: {e}")

    def _toggle_pause(self, icon, item):
        """切换暂停渲染（事件驱动：emit tray:pause）"""
        if self._emit("tray:pause"):
            self._paused = not self._paused
            print(f"[TRAY] {'暂停渲染' if self._paused else '恢复渲染'}")
        else:
            self._toggle_pause_direct()
        self._update_icon(icon)

    def _toggle_pause_direct(self):
        """无 Context 时的直调退化路径（向后兼容）。"""
        self._paused = not self._paused
        self.renderer.paused = self._paused
        print(f"[TRAY] {'暂停渲染' if self._paused else '恢复渲染'}")

    def _next_effect(self, icon, item):
        """切换到下一个效果（事件驱动：emit tray:next → effect:requested）"""
        if not self._emit("tray:next"):
            try:
                self.renderer.effect_manager._start_transition()
                print(f"[TRAY] 切换效果: {self.renderer.effect_manager.next_effect_name}")
            except Exception as e:
                print(f"[TRAY] 切换效果失败: {e}")

    def _reload_effects(self, icon, item):
        """手动全量重载效果（事件驱动：emit effect:reload_requested，由 HMR 插件消费）"""
        from core.assembly import EVENTS
        if not self._emit(EVENTS.EFFECT_RELOAD_REQUESTED):
            print("[TRAY] 无可用 Context，无法请求效果重载")
        else:
            print("[TRAY] 已请求重新加载效果")
        self._update_icon(icon)

    def _quit(self, icon, item):
        """退出程序（事件驱动：emit app:quit）"""
        print("[TRAY] 用户点击退出")
        if not self._emit("tray:quit"):
            if self._icon:
                self._icon.stop()
            self.renderer.running = False

    def _update_icon(self, icon):
        """刷新菜单显示（图标不可用时静默跳过）。"""
        if icon is None:
            return
        try:
            icon.update_menu()
        except Exception:
            pass

    # ---- 生命周期 ----

    def run(self):
        """在独立线程中运行托盘图标"""
        if not _PYSTRAY_OK:
            return

        icon_image = _create_icon_image()
        self._icon = pystray.Icon(
            name='Blur壁纸',
            icon=icon_image,
            title='Blur 动态壁纸',
            menu=self._menu,
        )

        def _run_in_thread():
            try:
                self._icon.run()
            except Exception as e:
                print(f"[TRAY] 托盘运行出错: {e}")

        self._thread = threading.Thread(target=_run_in_thread, daemon=True)
        self._thread.start()
        print("[TRAY] 系统托盘已启动")

    def stop(self):
        """停止托盘"""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def paused(self) -> bool:
        return self._paused
