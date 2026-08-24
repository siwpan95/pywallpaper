"""
效果展示视频生成器
==================
遍历 pywallpaper effects/ 目录下的所有效果，
逐效果渲染帧并合成 MP4 展示视频。

用法：
    python video_generator.py                          # 默认参数生成
    python video_generator.py --duration 2.0 --fps 30  # 每效果 2 秒，30fps
    python video_generator.py --width 1920 --height 1080
    python video_generator.py --output showcase.mp4
    python video_generator.py --start 0 --end 50       # 只生成前 50 个效果
    python video_generator.py --no-text                # 不显示效果名称叠加
"""

import json
import os
import glob
import re
import sys
import time
import math
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── pywallpaper 项目路径 ──
PYWALLPAPER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PYWALLPAPER_DIR)

from systems.audio_system import AudioSimulator
from engine.effect_loader import create_effect
from utils.helpers import hsv_to_rgb, get_energy_color

# ── 背景主题 ──
from systems.render_system import BACKGROUND_THEMES as _BG_THEMES_RAW
from systems.render_system import load_background_themes as _load_bg_themes


class VideoGenerator:
    """效果展示视频生成器"""

    def __init__(
        self,
        effects_dir: str = None,
        output_path: str = "effect_showcase.mp4",
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        duration_per_effect: float = 1.5,
        start_index: int = 0,
        end_index: int = None,
        show_text: bool = True,
        show_progress: bool = True,
        category_filter: str = None,
    ):
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.duration_per_effect = duration_per_effect
        self.frames_per_effect = int(fps * duration_per_effect)
        self.show_text = show_text
        self.show_progress = show_progress
        self.category_filter = category_filter

        # 效果目录
        if effects_dir is None:
            effects_dir = os.path.join(PYWALLPAPER_DIR, "effects")
        self.effects_dir = effects_dir

        # 加载效果列表
        self.effect_files = self._load_effect_files()
        total = len(self.effect_files)
        si = max(0, start_index)
        ei = min(total, end_index) if end_index is not None else total
        self.effect_files = self.effect_files[si:ei]
        self.start_index = si

        # 音频模拟器（驱动所有可视化效果）
        self.audio = AudioSimulator()

        # 检查是否有 numba / asteval（CA 原语需要）
        self._has_numba = False
        try:
            import numba
            self._has_numba = True
        except ImportError:
            pass

        self._has_asteval = False
        try:
            import asteval
            self._has_asteval = True
        except ImportError:
            pass

        # 统计
        self.total_frames = len(self.effect_files) * self.frames_per_effect
        self.rendered_frames = 0
        self.skipped_effects = 0
        self.error_count = 0

        # 字体（用于叠加效果名称）
        self._font = None
        if show_text:
            self._font = self._load_font()

    def _load_effect_files(self) -> list:
        """加载排序后的效果 JSON 文件列表（支持按分类过滤）"""
        pattern = os.path.join(self.effects_dir, "*_*.json")
        all_files = sorted(
            glob.glob(pattern),
            key=lambda f: int(re.match(r"(\d+)_", os.path.basename(f)).group(1)),
        )

        if self.category_filter:
            filtered = []
            for f in all_files:
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    cat = data.get("category", "")
                    if self.category_filter.lower() in cat.lower():
                        filtered.append(f)
                except Exception:
                    pass
            print(f"[INFO] 发现 {len(all_files)} 个效果文件，按分类「{self.category_filter}」筛选后: {len(filtered)} 个")
            return filtered

        print(f"[INFO] 发现 {len(all_files)} 个效果文件")
        return all_files

    def _load_font(self):
        """加载用于文本叠加的字体"""
        font_paths = [
            "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
            "C:/Windows/Fonts/simsun.ttc",  # 宋体
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, 48)
                except Exception:
                    continue
        # fallback: 默认字体
        try:
            return ImageFont.truetype("arial.ttf", 48)
        except Exception:
            return ImageFont.load_default()

    def _render_frame(self, effect_config: dict, dt: float,
                      bg_theme_obj, bg_color: tuple) -> Image.Image:
        """渲染单帧 — 返回 PIL Image"""
        img = Image.new("RGB", (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)

        # 绘制背景主题
        if bg_theme_obj:
            bg_theme_obj.update(dt)
            bg_theme_obj.draw()
        else:
            # 无主题时的默认微光呼吸
            t = getattr(self, "_frame_time", 0.0)
            cx, cy = self.width / 2, self.height / 2
            max_r = min(self.width, self.height) * 0.4
            breath = 0.3 + 0.15 * math.sin(t * 0.6)
            for layer in range(10, 0, -1):
                r = max_r * layer / 10
                alpha = int(breath * 0.03 * (1.0 - layer / 12) * 255)
                hue = (0.6 + t * 0.01) % 1.0
                c = hsv_to_rgb(hue, 0.05, 1.0)
                draw.ellipse(
                    [cx - r, cy - r, cx + r, cy + r],
                    fill=(min(c[0], alpha), min(c[1], alpha), min(c[2], alpha)),
                )

        # 创建效果实例
        try:
            effect = create_effect(effect_config, draw, self.width, self.height, self.audio)
        except Exception as e:
            draw.rectangle([0, 0, self.width, self.height], fill=(30, 30, 40))
            raise e

        # 更新 -> 绘制
        self._frame_time = self._frame_time + dt if hasattr(self, "_frame_time") else dt
        effect.update(dt)
        effect.draw()

        return img

    def _add_text_overlay(self, img: Image.Image, text: str, frame_idx: int, total_effect_frames: int):
        """在帧上叠加效果名称和进度信息"""
        if not self._font:
            return

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 底部半透明背景条
        bar_height = 80
        draw.rectangle(
            [0, self.height - bar_height, self.width, self.height],
            fill=(0, 0, 0, 140),
        )

        # 效果名称（左对齐）
        draw.text((40, self.height - bar_height + 12), text, font=self._font, fill=(255, 255, 255, 255))

        # 右下角帧进度
        progress_text = f"{(frame_idx + 1)}/{total_effect_frames}"
        bbox = self._font.getbbox(progress_text) if hasattr(self._font, "getbbox") else (0, 0, 300, 48)
        tw = bbox[2] - bbox[0]
        draw.text(
            (self.width - tw - 40, self.height - bar_height + 12),
            progress_text,
            font=self._font,
            fill=(180, 180, 200, 255),
        )

        img.paste(overlay, (0, 0), overlay)

    def generate(self):
        """主生成流程"""
        import imageio

        print(f"\n{'=' * 60}")
        print(f"  效果展示视频生成器")
        print(f"{'=' * 60}")
        print(f"  效果数量:   {len(self.effect_files)}")
        print(f"  每效果帧数: {self.frames_per_effect} ({self.duration_per_effect}s @ {self.fps}fps)")
        print(f"  分辨率:     {self.width}×{self.height}")
        print(f"  输出文件:   {self.output_path}")
        print(f"  预计总帧:   {self.total_frames}")
        print(f"  预计时长:   {self.total_frames / self.fps:.1f}s ({self.total_frames / self.fps / 60:.1f}min)")
        print(f"{'=' * 60}\n")

        # 确保背景主题已加载
        effects_dir = os.path.join(PYWALLPAPER_DIR, "effects")
        _load_bg_themes(os.path.join(effects_dir, "themes.json"))
        self._bg_themes = dict(_BG_THEMES_RAW)

        writer = None
        try:
            writer = imageio.get_writer(
                self.output_path,
                fps=self.fps,
                codec="libx264",
                format="ffmpeg",
                quality=8,
                pixelformat="yuv420p",
                macro_block_size=1,
            )

            for eff_idx, json_path in enumerate(self.effect_files):
                global_idx = self.start_index + eff_idx + 1
                fname = os.path.basename(json_path)

                # 加载效果配置
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception as e:
                    print(f"  [SKIP] {fname}: 无法加载 JSON ({e})")
                    self.skipped_effects += 1
                    continue

                # 效果名称
                display_name = config.get("full_name", config.get("name", fname))
                category = config.get("category", "")
                label = f"{display_name}"
                if category:
                    label += f"  [{category}]"
                
                # 显示行号
                idx_label = f"{global_idx}/{len(self.effect_files) + self.start_index}"
                print(f"  [{idx_label}] {label}")

                # ── 背景主题 ──
                bg_name = config.get("background_theme", "").strip()
                bg_color = (0, 0, 0)
                bg_theme_cls = self._bg_themes.get(bg_name)
                bg_theme_obj = None
                if bg_theme_cls:
                    # 每个效果新建一个主题实例（继承 BackgroundTheme 基类）
                    try:
                        dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                        bg_theme_obj = bg_theme_cls(dummy_draw, self.width, self.height)
                    except Exception:
                        bg_theme_obj = None

                # 重置音频模拟器时间
                self.audio.time = 0.0
                self.audio.beat = 0.0
                self.audio.band_energy = [0.0] * self.audio.num_bands
                self.audio.freq_data = [0.0] * len(self.audio.freq_data)

                # 渲染帧
                rendered = 0
                self._frame_time = 0.0
                try:
                    for frame_i in range(self.frames_per_effect):
                        dt = 1.0 / self.fps
                        self.audio.update(dt)

                        img = self._render_frame(config, dt, bg_theme_obj, bg_color)

                        # 叠加效果名称
                        if self.show_text:
                            self._add_text_overlay(img, label, frame_i, self.frames_per_effect)

                        # 写入视频帧
                        frame_array = np.array(img)
                        writer.append_data(frame_array)
                        rendered += 1
                        self.rendered_frames += 1

                except Exception as e:
                    print(f"    ⚠ 渲染错误: {e}")
                    self.error_count += 1
                    placeholder = self._make_error_placeholder(display_name, str(e))
                    frame_array = np.array(placeholder)
                    for _ in range(self.frames_per_effect - rendered):
                        writer.append_data(frame_array)
                        self.rendered_frames += 1

                if self.show_progress:
                    pct = (eff_idx + 1) / len(self.effect_files) * 100
                    elapsed = time.time() - self._start_time
                    if eff_idx > 0:
                        eta = (elapsed / (eff_idx + 1)) * (len(self.effect_files) - eff_idx - 1)
                        print(f"    进度: {pct:.0f}% | 已用时: {elapsed:.0f}s | 预计剩余: {eta:.0f}s ({eta/60:.1f}min)")
                    sys.stdout.flush()

            writer.close()
            writer = None

            elapsed = time.time() - self._start_time
            print(f"\n{'=' * 60}")
            print(f"  生成完成！")
            print(f"  总帧数:   {self.rendered_frames}")
            print(f"  总时长:   {self.rendered_frames / self.fps:.1f}s")
            print(f"  耗时:     {elapsed:.0f}s ({elapsed / 60:.1f}min)")
            print(f"  跳过:     {self.skipped_effects} 个效果")
            print(f"  错误:     {self.error_count} 个效果")
            print(f"  输出:     {os.path.abspath(self.output_path)}")
            print(f"{'=' * 60}")

        except Exception as e:
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    pass
            print(f"\n[FATAL] 视频生成失败: {e}")
            raise

    def _make_error_placeholder(self, name: str, error_msg: str) -> Image.Image:
        """生成错误占位帧"""
        img = Image.new("RGB", (self.width, self.height), (40, 10, 10))
        draw = ImageDraw.Draw(img)
        # 红色边框
        draw.rectangle([20, 20, self.width - 20, self.height - 20], outline=(200, 50, 50), width=3)
        # 错误信息
        if self._font:
            draw.text((60, 100), f"渲染错误: {name}", font=self._font, fill=(255, 200, 200))
            # 截断错误信息到 80 字符
            short_err = error_msg[:80] + ("..." if len(error_msg) > 80 else "")
            draw.text((60, 170), short_err, font=ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 24), fill=(200, 150, 150))
        return img


def main():
    parser = argparse.ArgumentParser(description="效果展示视频生成器")
    parser.add_argument("--duration", type=float, default=2.0, help="每个效果的展示时长（秒），默认 2.0")
    parser.add_argument("--fps", type=float, default=30.0, help="视频帧率，默认 30")
    parser.add_argument("--width", type=int, default=1920, help="视频宽度，默认 1920")
    parser.add_argument("--height", type=int, default=1080, help="视频高度，默认 1080")
    parser.add_argument("--output", type=str, default="effect_showcase.mp4", help="输出文件路径")
    parser.add_argument("--effects-dir", type=str, default=None, help="效果 JSON 目录（默认 pywallpaper/effects）")
    parser.add_argument("--start", type=int, default=0, help="起始效果索引（0-based）")
    parser.add_argument("--end", type=int, default=None, help="结束效果索引（不包含）")
    parser.add_argument("--category", type=str, default=None, help="按分类过滤（如 频谱、纹理、粒子、CA、流）")
    parser.add_argument("--no-text", action="store_true", help="不显示效果名称叠加")
    parser.add_argument("--no-progress", action="store_true", help="不显示进度信息")
    parser.add_argument("--list-categories", action="store_true", help="列出所有效果分类")

    args = parser.parse_args()

    # ── 列出分类 ──
    if args.list_categories:
        effects_dir = args.effects_dir or os.path.join(PYWALLPAPER_DIR, "effects")
        pattern = os.path.join(effects_dir, "*_*.json")
        files = glob.glob(pattern)
        from collections import Counter
        cats = Counter()
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                cat = data.get("category", "(无分类)")
                cats[cat] += 1
            except Exception:
                cats["(加载失败)"] += 1
        print("\n  效果分类统计:\n")
        print(f"  {'分类':<16} {'数量':>6}")
        print(f"  {'-'*16} {'-'*6}")
        for cat, count in cats.most_common():
            print(f"  {cat:<16} {count:>6}")
        print(f"\n  共 {sum(cats.values())} 个效果\n")
        return

    print("[CHECK] 检查依赖...")
    try:
        import imageio
        print("  imageio: OK")
    except ImportError:
        print("  imageio: 未安装，请运行: pip install imageio[ffmpeg]")
        sys.exit(1)

    # 检查 ffmpeg 插件
    try:
        imageio.plugins.ffmpeg.download()
    except Exception:
        pass

    generator = VideoGenerator(
        effects_dir=args.effects_dir,
        output_path=args.output,
        width=args.width,
        height=args.height,
        fps=args.fps,
        duration_per_effect=args.duration,
        start_index=args.start,
        end_index=args.end,
        show_text=not args.no_text,
        show_progress=not args.no_progress,
        category_filter=args.category,
    )
    generator._start_time = time.time()
    generator.generate()


if __name__ == "__main__":
    main()
