"""
音频系统 - 音乐生成 + 音频模拟器（支持真实音乐驱动）
从 data/audio.json 读取音乐理论数据，纯逻辑驱动
"""
import math
import random
import wave
import struct
import time
import os
from datetime import datetime
from typing import Optional

from ecs import System
from data_loader import get_audio_data as _load_audio_data, get_config as _load_config

# 尝试导入 pygame
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
    _PYGAME_OK = True
except Exception:
    pygame = None
    _PYGAME_OK = False

# 懒加载音频理论数据
_audio_data = None

def get_audio_data():
    global _audio_data
    if _audio_data is None:
        _audio_data = _load_audio_data()
    return _audio_data

# ==================== 波形合成 ====================
def sine_wave(freq: float, t: float, phase: float = 0.0) -> float:
    return math.sin(2 * math.pi * freq * t + phase)

def square_wave(freq: float, t: float, duty: float = 0.5) -> float:
    phase = (freq * t) % 1.0
    return 1.0 if phase < duty else -1.0

def sawtooth_wave(freq: float, t: float) -> float:
    return 2.0 * ((freq * t) % 1.0) - 1.0

def triangle_wave(freq: float, t: float) -> float:
    p = (freq * t) % 1.0
    return 4.0 * p - 1.0 if p < 0.5 else 3.0 - 4.0 * p

def organ_wave(freq: float, t: float) -> float:
    return (
        sine_wave(freq, t) * 0.5
        + sine_wave(freq * 2, t) * 0.3
        + sine_wave(freq * 3, t) * 0.15
        + sine_wave(freq * 4, t) * 0.05
    )

def piano_wave(freq: float, t: float, duration: float, note_t: float) -> float:
    harmonics_sum = (
        sine_wave(freq, t) * 1.0
        + sine_wave(freq * 2, t) * 0.5
        + sine_wave(freq * 3, t) * 0.25
        + sine_wave(freq * 4, t) * 0.1
        + sine_wave(freq * 5, t) * 0.05
    )
    decay = math.exp(-note_t * 4.0 / max(duration, 0.01))
    return harmonics_sum * decay


def note_freq(name: str, octave: int) -> float:
    """根据音名和八度计算频率 A4=440Hz"""
    ad = get_audio_data()
    semitone = ad['note_names'].index(name)
    midi = (octave + 1) * 12 + semitone
    return ad['reference_note']['frequency'] * (2 ** ((midi - ad['reference_note']['midi_number']) / 12))


def adsr_envelope(note_t: float, duration: float) -> float:
    """ADSR 包络"""
    ad = get_audio_data()['adsr_envelope']
    a, d, s, r = ad['attack'], ad['decay'], ad['sustain'], ad['release']
    if note_t < a:
        return note_t / a
    elif note_t < a + d:
        return 1.0 - (1.0 - s) * (note_t - a) / d
    elif note_t < duration - r:
        return s
    elif note_t < duration:
        return s * (1.0 - (note_t - (duration - r)) / r)
    return 0.0


def render_note(freq: float, duration: float, sample_rate: int, timbre: str, volume: float = 0.8) -> list:
    """渲染单个音符"""
    n_samples = int(duration * sample_rate)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        note_t = i / sample_rate
        if freq <= 0:
            samples.append(0.0)
            continue
        if timbre == "钢琴":
            raw = piano_wave(freq, t, duration, note_t)
        elif timbre == "管风琴":
            raw = organ_wave(freq, t)
        elif timbre == "方波":
            raw = square_wave(freq, t, duty=random.uniform(0.4, 0.6))
        elif timbre == "三角波":
            raw = triangle_wave(freq, t)
        elif timbre == "锯齿波":
            raw = sawtooth_wave(freq, t)
        else:
            raw = sine_wave(freq, t)
        samples.append(raw * adsr_envelope(note_t, duration) * volume)
    return samples


def apply_reverb(samples: list, sample_rate: int) -> list:
    """混响效果"""
    rv = get_audio_data()['reverb']
    delay_ms = random.uniform(rv['delay_ms_range'][0], rv['delay_ms_range'][1])
    decay = random.uniform(rv['decay_range'][0], rv['decay_range'][1])
    mix = rv['mix']
    delay_samples = int(delay_ms * sample_rate / 1000)
    out = list(samples)
    for i in range(delay_samples, len(out)):
        out[i] += out[i - delay_samples] * decay * mix
    return out


def low_pass_filter(samples: list) -> list:
    """低通滤波"""
    cutoff = get_audio_data()['low_pass_filter']['cutoff_ratio']
    alpha = 1.0 - math.exp(-2 * math.pi * cutoff)
    out = []
    prev = 0.0
    for s in samples:
        prev = prev + alpha * (s - prev)
        out.append(prev)
    return out


def build_scale_notes(root_name: str, root_octave: int, scale_intervals: list) -> list:
    """构建音阶频率列表"""
    ad = get_audio_data()
    root_semitone = ad['note_names'].index(root_name) + (root_octave + 1) * 12
    notes = []
    for octave_offset in [0, 12]:
        for interval in scale_intervals:
            midi = root_semitone + interval + octave_offset
            freq = ad['reference_note']['frequency'] * (2 ** ((midi - ad['reference_note']['midi_number']) / 12))
            notes.append(freq)
    return notes


def generate_melody(scale_notes: list, n_bars: int, bpm: int, time_sig: int = 4) -> list:
    """生成旋律序列 [(freq, duration_sec), ...]"""
    mg = get_audio_data()['melody_generation']
    beat_dur = 60.0 / bpm
    rhythms = mg['rhythms']
    step_weights = mg['step_weights']
    melody = []
    prev_idx = len(scale_notes) // 2
    for _ in range(n_bars):
        rhythm = random.choice(rhythms)
        total = sum(rhythm)
        rhythm = [r * time_sig / total for r in rhythm]
        for dur_beats in rhythm:
            dur_sec = dur_beats * beat_dur
            rnd = random.random()
            cumulative = 0
            chosen_deltas = step_weights['stepwise']['deltas']
            for key in ['stepwise', 'skip', 'leap']:
                cumulative += step_weights[key]['probability']
                if rnd < cumulative:
                    chosen_deltas = step_weights[key]['deltas']
                    break
            delta = random.choice(chosen_deltas)
            prev_idx = max(0, min(len(scale_notes) - 1, prev_idx + delta))
            if random.random() < mg['rest_probability']:
                melody.append((0, dur_sec))
            else:
                melody.append((scale_notes[prev_idx], dur_sec))
    return melody


def generate_bass(scale_notes: list, chord_prog: list, n_bars: int, bpm: int, time_sig: int = 4) -> list:
    """生成低音序列"""
    bg = get_audio_data()['bass_generation']
    beat_dur = 60.0 / bpm
    bass_notes = scale_notes[:len(scale_notes) // 2]
    bass = []
    bars_per_chord = max(1, n_bars // len(chord_prog))
    for chord_idx in chord_prog:
        root_idx = min(chord_idx - 1, len(bass_notes) - 1)
        fifth_idx = min(root_idx + 4, len(bass_notes) - 1)
        for _ in range(bars_per_chord):
            pattern = [
                (bass_notes[root_idx], beat_dur),
                (bass_notes[fifth_idx], beat_dur * 0.5),
                (bass_notes[root_idx], beat_dur * 0.5),
                (bass_notes[fifth_idx], beat_dur),
                (bass_notes[root_idx], beat_dur),
            ]
            total_beats = sum(p[1] for p in pattern) / beat_dur
            for freq, dur in pattern:
                bass.append((freq, dur * time_sig / total_beats))
    while len(bass) < n_bars * time_sig:
        bass.append((bass_notes[0], beat_dur))
    return bass


def mix_tracks(tracks: list) -> list:
    """混合多音轨"""
    max_len = max(len(t) for t in tracks)
    mixed = [0.0] * max_len
    for track in tracks:
        for i, s in enumerate(track):
            mixed[i] += s
    peak = max(abs(s) for s in mixed) or 1.0
    if peak > 0.9:
        factor = 0.9 / peak
        mixed = [s * factor for s in mixed]
    return mixed


def samples_to_wav(samples: list, sample_rate: int, filepath: str, bit_depth: int = 16):
    """将采样数据写入 WAV 文件"""
    max_val = (2 ** (bit_depth - 1)) - 1
    fmt = "<h" if bit_depth == 16 else "<i"
    with wave.open(filepath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack(fmt, int(clamped * max_val)))


def generate_music_to_file(output_path: str = None,
                           bpm: int = None,
                           scale_name: str = None,
                           root_note: str = None,
                           root_octave: int = None,
                           timbre: str = None,
                           n_bars: int = None,
                           add_bass: bool = None,
                           add_reverb: bool = None,
                           sample_rate: int = 44100) -> tuple:
    """生成音乐并保存 WAV，返回 (文件路径, 参数字典, 旋律序列, 低音序列, 采样率, 时长)"""
    ad = get_audio_data()
    mg = ad['melody_generation']

    bpm = bpm or random.randint(mg['bpm_range'][0], mg['bpm_range'][1])
    scale_name = scale_name or random.choice(list(ad['scales'].keys()))
    root_note = root_note or random.choice(mg['root_notes'])
    root_octave = root_octave if root_octave is not None else random.choice(mg['root_octaves'])
    timbre = timbre or random.choice(ad['timbres'])
    n_bars = n_bars or random.randint(mg['n_bars_range'][0], mg['n_bars_range'][1])
    add_bass = add_bass if add_bass is not None else random.choice([True, False])
    add_reverb = add_reverb if add_reverb is not None else random.choice([True, False])
    chord_prog = random.choice(ad['chord_progressions'])['degrees']
    time_sig = mg['time_signature']

    params = {
        "bpm": bpm,
        "调式": scale_name,
        "主音": f"{root_note}{root_octave}",
        "音色": timbre,
        "小节数": n_bars,
        "低音声部": add_bass,
        "混响": add_reverb,
        "和弦进行": chord_prog,
    }

    print("\n🎵 生成音乐中...")
    print("=" * 40)
    for k, v in params.items():
        print(f"  {k}: {v}")
    print("=" * 40)

    scale_intervals = ad['scales'][scale_name]
    scale_notes = build_scale_notes(root_note, root_octave, scale_intervals)

    print("  生成旋律…")
    melody_seq = generate_melody(scale_notes, n_bars, bpm, time_sig)
    melody_track = []
    for freq, dur in melody_seq:
        melody_track.extend(render_note(freq, dur, sample_rate, timbre, volume=mg['volume']))
    tracks = [melody_track]

    bass_seq = None
    if add_bass:
        print("  生成低音…")
        bass_seq = generate_bass(scale_notes, chord_prog, n_bars, bpm, time_sig)
        bass_timbre = ad['bass_generation']['timbre']
        bass_track = []
        for freq, dur in bass_seq:
            bass_track.extend(render_note(freq / 2, dur, sample_rate, bass_timbre, volume=ad['bass_generation']['volume']))
        tracks.append(bass_track)

    print("  混合音轨…")
    mixed = mix_tracks(tracks)

    if add_reverb:
        print("  应用混响…")
        mixed = apply_reverb(mixed, sample_rate)

    lpf_timbres = ad['low_pass_filter']['applicable_timbres']
    if timbre in lpf_timbres:
        mixed = low_pass_filter(mixed)

    target = ad['mastering']['peak_target']
    peak = max(abs(s) for s in mixed) or 1.0
    mixed = [s * target / peak for s in mixed]

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.environ.get('TEMP', '.'), f"wallpaper_music_{ts}.wav")

    samples_to_wav(mixed, sample_rate, output_path)
    duration_sec = len(mixed) / sample_rate
    print(f"\n🎼 完成！时长约 {duration_sec:.1f} 秒")

    return output_path, params, melody_seq, bass_seq, sample_rate, duration_sec


# ==================== AudioSimulator ====================
class AudioSimulator:
    """音频模拟器 - 模拟/真实音频数据，驱动可视化"""

    def __init__(self):
        cfg = _load_config()['audio']
        self.num_bands = cfg['num_bands']
        self.sample_rate = cfg['sample_rate']
        self.smoothing = cfg['smoothing_factor']

        self.freq_data = [random.random() for _ in range(cfg['freq_data_length'])]
        self.band_energy = [0.0] * self.num_bands
        self.time = 0.0
        self.beat = 0.0
        self.beat_counter = 0

        # 真实音乐驱动
        self.melody_notes = []
        self.bass_notes = []
        self.music_start_time = 0.0
        self.music_duration = 0.0
        self.bpm = 120
        self.use_real_music = False

    def load_music_score(self, melody_seq, bass_seq, bpm, duration_sec):
        """载入音乐乐谱驱动可视化"""
        self.melody_notes = []
        self.bass_notes = []
        t = 0.0
        for freq, dur in melody_seq:
            self.melody_notes.append((t, freq, dur))
            t += dur
        t = 0.0
        if bass_seq:
            for freq, dur in bass_seq:
                self.bass_notes.append((t, freq, dur))
                t += dur
        self.bpm = bpm
        self.music_duration = duration_sec
        self.use_real_music = True
        print(f"[Audio] 已载入乐谱: 旋律{len(self.melody_notes)}音符, 低音{len(self.bass_notes)}音符, 时长{duration_sec:.1f}s")

    def _freq_to_band(self, freq: float) -> int:
        """频率 → 频谱带索引"""
        from utils.helpers import map_freq_to_band
        return map_freq_to_band(freq, self.num_bands)

    def update(self, dt: float = 0.0, world=None):
        now = time.time()
        if self.use_real_music and self.music_duration > 0:
            elapsed = (now - self.music_start_time) % self.music_duration
            self.time = elapsed
            self._update_from_score(elapsed)
        else:
            self._simulated_update()

    def _simulated_update(self):
        """随机模拟音频数据"""
        self.time += 0.1
        self.beat_counter += 1
        if self.beat_counter >= random.randint(10, 30):
            self.beat = 1.0
            self.beat_counter = 0
        else:
            self.beat = max(0, self.beat - 0.1)
        for i in range(len(self.freq_data)):
            base = math.sin(self.time + i * 0.01) * 0.5 + 0.5
            harmonic = math.sin(self.time * 2 + i * 0.02) * 0.3
            noise = random.uniform(-0.1, 0.1)
            lfo = math.sin(self.time * 0.5) * 0.2
            new_value = base * 0.4 + harmonic * 0.3 + noise * 0.1 + lfo + 0.1
            self.freq_data[i] = self.freq_data[i] * 0.8 + new_value * 0.2
        bands_per = 1024 // self.num_bands
        for band in range(self.num_bands):
            start = band * bands_per
            end = min(start + bands_per, 1024)
            band_energy = sum(self.freq_data[start:end]) / (end - start)
            self.band_energy[band] = (self.band_energy[band] * self.smoothing + band_energy * (1 - self.smoothing))

    def _update_from_score(self, elapsed: float):
        """根据乐谱更新频谱"""
        new_energy = [0.0] * self.num_bands
        for note_start, freq, dur in self.melody_notes:
            note_end = note_start + dur
            if note_start <= elapsed <= note_end + 0.2:
                band = self._freq_to_band(freq)
                if band < 0:
                    continue
                note_elapsed = elapsed - note_start
                if note_elapsed < 0.02:
                    env = note_elapsed / 0.02
                elif note_elapsed < 0.07:
                    env = 1.0 - (1.0 - 0.7) * (note_elapsed - 0.02) / 0.05
                elif note_elapsed < dur:
                    env = 0.7
                else:
                    env = max(0, 0.7 * (1 - (note_elapsed - dur) / 0.2))
                new_energy[band] = max(new_energy[band], env)
                for h in range(2, 6):
                    b = self._freq_to_band(freq * h)
                    if b >= 0:
                        new_energy[b] = max(new_energy[b], env * (0.6 / h))
                idx = band * (1024 // self.num_bands)
                spread = 4
                for offset in range(-spread, spread + 1):
                    fi = idx + offset * 2
                    if 0 <= fi < 1024:
                        self.freq_data[fi] = max(self.freq_data[fi], 0.4 * env)

        for note_start, freq, dur in self.bass_notes:
            note_end = note_start + dur
            if note_start <= elapsed <= note_end + 0.3:
                band = self._freq_to_band(freq / 2)
                if band >= 0:
                    note_elapsed = elapsed - note_start
                    env = max(0, 1.0 - note_elapsed / (dur + 0.3))
                    new_energy[band] = max(new_energy[band], env * 1.2)

        beat_interval = 60.0 / self.bpm
        beat_phase = (elapsed % beat_interval) / beat_interval
        self.beat = max(0, 1.0 - beat_phase / 0.15) if beat_phase < 0.15 else 0.0

        for b in range(self.num_bands):
            self.band_energy[b] = self.band_energy[b] * self.smoothing + new_energy[b] * (1 - self.smoothing)

        bands_per = 1024 // self.num_bands
        for b in range(self.num_bands):
            if new_energy[b] < 0.01:
                continue
            start = b * bands_per
            end = min(start + bands_per, 1024)
            for fi in range(start, end):
                target = new_energy[b] * (0.7 + 0.3 * random.random())
                self.freq_data[fi] = self.freq_data[fi] * 0.8 + target * 0.2

    def get_band_energy(self, band_idx: int) -> float:
        return self.band_energy[band_idx] if 0 <= band_idx < len(self.band_energy) else 0.0

    def get_full_spectrum(self) -> list:
        return self.freq_data

    def get_beat(self) -> float:
        return self.beat


class MusicPlaybackSystem(System):
    """音乐播放系统（ECS 系统）"""

    def __init__(self, audio_sim: AudioSimulator):
        self.audio_sim = audio_sim
        self.music_path: Optional[str] = None
        self.params: Optional[dict] = None

    def generate_and_play(self, world=None):
        """生成音乐、加载到模拟器、开始播放"""
        print("[MUSIC] 正在生成音乐...", flush=True)
        try:
            result = generate_music_to_file()
            music_path, params, melody_seq, bass_seq, sr, dur = result
            self.music_path = music_path
            self.params = params

            print(f"[MUSIC] 音乐已生成: {os.path.basename(music_path)}")
            print(f"[MUSIC] 参数: {params}")

            if dur > 0:
                self.audio_sim.load_music_score(melody_seq, bass_seq, params["bpm"], dur)
                self.audio_sim.music_start_time = time.time()
                print(f"[MUSIC] 乐谱已载入 AudioSimulator，时长 {dur:.1f}s")

            if _PYGAME_OK:
                try:
                    pygame.mixer.music.load(music_path)
                    pygame.mixer.music.play(loops=-1)
                    print("[MUSIC] 正在播放音乐（循环）")
                except Exception as e:
                    print(f"[WARN] 音乐播放失败: {e}")

            return True
        except Exception as e:
            print(f"[WARN] 音乐生成失败，使用模拟音频: {e}")
            self.audio_sim.use_real_music = False
            return False

    def update(self, dt: float, world=None):
        """播放系统不需要逐帧更新（已循环播放）"""
        pass

    def stop(self):
        """停止音乐播放并释放资源"""
        if not _PYGAME_OK:
            return
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            print("[MUSIC] 音乐已停止")
        except Exception as e:
            print(f"[MUSIC] 停止音乐时出错: {e}")

    def shutdown(self):
        """完整关闭音频系统"""
        self.stop()
        if _PYGAME_OK:
            try:
                pygame.mixer.quit()
                print("[MUSIC] pygame.mixer 已关闭")
            except Exception as e:
                print(f"[MUSIC] 关闭 mixer 时出错: {e}")
