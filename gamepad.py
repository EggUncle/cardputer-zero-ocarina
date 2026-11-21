#!/usr/bin/python3
"""CardputerZero local keyboard and 320x170 LCD, classic Bluetooth Pro Controller."""
import concurrent.futures
from functools import lru_cache
import hashlib
import json
import fcntl
import mmap
import os
from pathlib import Path
import select
import struct
import time

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from controller import frame, request
from music import transcribe, arrange

# Linux KEY_* codes from the tca8418c input device.
KEYS = {
    2: ("L","R"), 28: ("A",), 36: ("B",), 23: ("X",), 22: ("Y",),
    16: ("L",), 18: ("R",), 44: ("ZL",), 46: ("ZR",),
    17: ("LSTICK_UP",), 30: ("LSTICK_LEFT",), 31: ("LSTICK_DOWN",), 32: ("LSTICK_RIGHT",),
    20: ("DPAD_UP",), 33: ("DPAD_LEFT",), 34: ("DPAD_DOWN",), 35: ("DPAD_RIGHT",),
    103: ("DPAD_UP",), 105: ("DPAD_LEFT",), 108: ("DPAD_DOWN",), 106: ("DPAD_RIGHT",),
    24: ("RSTICK_UP",), 37: ("RSTICK_LEFT",), 38: ("RSTICK_DOWN",), 25: ("RSTICK_RIGHT",),
    3: ("MINUS",), 4: ("PLUS",), 5: ("HOME",), 6: ("L3",), 7: ("R3",)
}
EV = struct.Struct("@llHHi")
GRAB = 0x40044590
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def keyboard():
    for dev in Path("/sys/class/input").glob("event*"):
        if (dev/"device/name").read_text().strip() == "tca8418c":
            return os.open("/dev/input/"+dev.name, os.O_RDONLY | os.O_NONBLOCK)
    raise RuntimeError("找不到机身键盘")


class Display:
    def __init__(self):
        self.font = ImageFont.truetype(FONT, 14)
        self.title = ImageFont.truetype(FONT, 18)
        fd = os.open("/dev/fb_lcd", os.O_RDWR)
        try:
            self.fb = mmap.mmap(fd, 320*170*2)
        finally:
            os.close(fd)
        self.last = None

    @lru_cache(maxsize=320)
    def label(self, text, size, color, width):
        font = self.face(size)
        while len(text) > 1 and font.getlength(text) > width:
            text = text[:-2] + "…" if text.endswith("…") else text[:-1] + "…"
        left, top, right, bottom = font.getbbox(text)
        tile = Image.new("RGBA", (max(1, right-left), max(1, bottom-top)))
        ImageDraw.Draw(tile).text((-left,-top), text, font=font, fill=color)
        return tile

    @lru_cache(maxsize=8)
    def face(self, size):
        return ImageFont.truetype(FONT, size)

    def draw(self, header, lines, footer):
        content = (header, tuple(lines), footer)
        if content == self.last:
            return
        self.last = content
        image = Image.new("RGB", (320,170), "#101924")
        pen = ImageDraw.Draw(image)
        pen.text((6,0), header, font=self.title, fill="#75e0c1")
        for n,line in enumerate(lines[:6]):
            pen.text((6,27+19*n),line,font=self.font,fill="#edf3f5")
        pen.rectangle((0,147,320,170),fill="#243447")
        pen.text((6,148),footer,font=self.font,fill="#ffda8b")
        self.present(image)

    def performance(self, title, events, cursor, keys, elapsed, armed):
        # Each note has three controller reports: prepare, press and release.
        count = min(len(events), (cursor + 1) // 3)
        duration = events[-1][1]
        elapsed = min(duration, max(0, int(elapsed)))
        progress = round(304 * elapsed / duration)
        state = (title, count, tuple(keys), progress, elapsed // 1000, armed)
        if state == self.last:
            return
        self.last = state
        image = Image.new("RGB", (320,170), "#101924")
        pen = ImageDraw.Draw(image)
        def put(x, y, text, size, color, width):
            tile = self.label(text, size, color, width)
            image.paste(tile, (x,y), tile)
        put(8, 6, title, 16, "#edf3f5", 230)
        put(250, 8, "待演奏" if armed else "演奏中", 13, "#75e0c1", 62)
        pen.line((8,29,312,29), fill="#304354")
        put(8, 37, "当前输入", 13, "#a5b9c9", 100)
        current = "准备" if armed else combo(keys, PAD_LABELS) or "休止"
        put(8, 62, current, 20, "#75e0c1", 188)
        put(8, 96, "机身  " + (combo(keys, ZERO_LABELS) or "—"), 14, "#edf3f5", 186)
        pen.line((200,36,200,119), fill="#304354")
        put(211, 37, "接下来", 13, "#a5b9c9", 100)
        for row, event in enumerate(events[count:count+2]):
            put(211, 63+23*row, combo([*event[3],event[4]], PAD_LABELS),
                14, "#e8c788" if row == 0 else "#a5b9c9", 101)
        if count == len(events):
            put(211, 63, "收尾", 14, "#a5b9c9", 100)
        def clock(ms):
            seconds = int(ms) // 1000
            return f"{seconds//60}:{seconds%60:02d}"
        put(8, 125, f"{clock(elapsed)} / {clock(duration)}", 13, "#edf3f5", 132)
        put(207, 125, f"{count} / {len(events)} 音", 13, "#a5b9c9", 105)
        pen.rectangle((8,145,311,148), fill="#304354")
        if progress:
            pen.rectangle((8,145,7+progress,148), fill="#75e0c1")
        put(8, 154, "回车 开始     Esc 返回" if armed else "Esc 停止", 12, "#e8c788", 220)
        self.present(image)

    def present(self, image):
        rgb = np.asarray(image).astype(np.uint16)
        pixels = ((rgb[:,:,0]>>3)<<11) | ((rgb[:,:,1]>>2)<<5) | (rgb[:,:,2]>>3)
        self.fb[:] = pixels.astype("<u2").tobytes()


PAD_LABELS = {"DPAD_UP":"十字↑", "DPAD_DOWN":"十字↓", "LSTICK_UP":"杆↑", "LSTICK_DOWN":"杆↓"}
ZERO_LABELS = {"DPAD_UP":"T", "DPAD_DOWN":"G", "LSTICK_UP":"W", "LSTICK_DOWN":"S",
               "L":"Q", "R":"E", "A":"回车", "Y":"U", "X":"I"}


def combo(keys, labels):
    return "+".join(labels.get(key, key) for key in keys)


def timeline(events):
    steps = []
    for start,end,_,mods,button in events:
        steps.extend([(start-20, mods), (start, [*mods,button]), (end-25, [])])
    return steps


def read_song(path):
    # Only use a companion score if it belongs to this exact MP3.
    score = path.with_suffix(".ocarina.json")
    notes = None
    if score.is_file():
        try:
            if score.stat().st_size <= 1_000_000:
                data = json.loads(score.read_bytes())
                with path.open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
                candidate = data["notes"]
                if (digest == data["sha256"] and isinstance(candidate, list) and candidate
                        and all(isinstance(row, list) and len(row) == 3
                                and all(type(x) is int for x in row)
                                and 0 <= row[0] < row[1] - 25 and 0 <= row[2] <= 127
                                for row in candidate)
                        and all(a[1] <= b[0] for a,b in zip(candidate, candidate[1:]))):
                    notes = candidate
        except (OSError, ValueError, TypeError, KeyError):
            pass
    events = arrange(notes if notes is not None else transcribe(path))[0]
    return events, timeline(events)


def application():
    screen = Display()
    fd = keyboard()
    worker = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    painter = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    painting = None
    last_draw = -1.
    held = set()
    min_hold = {}
    dropped = False
    tracks = []
    index = 0
    mode = "pad"
    ready = False
    last_send = last_poll = last_start = -100.
    last_keys = None
    message = "打开 NS2 的「更改握法／顺序」"
    steps = []
    pending = None
    cursor = 0
    state = {}
    try:
        fcntl.ioctl(fd, GRAB, 1)
        while True:
            now = time.monotonic()
            if select.select([fd], [], [], .008)[0]:
                for _,_,kind,code,value in EV.iter_unpack(os.read(fd, EV.size*32)):
                    if kind == 0 and code == 3:  # kernel dropped buffered events
                        dropped = True
                        held.clear()
                        min_hold.clear()
                    if dropped:
                        if kind == 0 and code == 0:
                            dropped = False
                        continue
                    if kind != 1 or value == 2:
                        continue
                    if not value:
                        held.discard(code)
                        continue
                    if code == 1:  # ESC
                        if mode == "pad":
                            return
                        mode, pending = "pad", None
                        held.clear()
                        min_hold.clear()
                        continue
                    if mode == "pad" and code == 50 and ready:  # M
                        tracks = sorted((Path.home()/"Music").glob("*"))
                        tracks = [p for p in tracks if p.is_file() and p.suffix.lower()==".mp3"]
                        if tracks:
                            mode, index = "songs", 0
                        else:
                            message = "曲库为空，请把 MP3 放入 ~/Music"
                        held.clear()
                        min_hold.clear()
                    elif mode == "songs" and code in (17,103,31,108):
                        index = (index + (-1 if code in (17,103) else 1)) % len(tracks)
                    elif mode == "songs" and code == 28:
                        pending = worker.submit(read_song, tracks[index])
                        mode = "loading"
                    elif mode == "armed" and code == 28:
                        origin, cursor, mode = now+.12, 0, "playing"
                    elif mode == "pad" and ready and code in KEYS:
                        held.add(code)
                        min_hold[code] = now + .12

            if mode == "loading" and pending.done():
                try:
                    events, steps = pending.result()
                    mode = "armed"
                except (ValueError, OSError, RuntimeError) as exc:
                    message, mode = str(exc), "pad"
            if now-last_poll >= .5:
                last_poll = now
                try:
                    state = request("status")
                    connected = state["initialized"] and not state["simulated"]
                    if connected and not ready:
                        message = "1 登记 L+R，然后回车确认 A"
                    if not connected and ready:
                        mode, message = "pad", "连接已断开，请重新配对"
                        held.clear()
                        min_hold.clear()
                    ready = connected
                except (OSError, ValueError, RuntimeError):
                    ready, mode = False, "pad"
                    held.clear()
                    min_hold.clear()
                    if now-last_start > 12:
                        watch = Path.home()/".local/state/ocarina-radio.request"
                        watch.parent.mkdir(parents=True,exist_ok=True)
                        watch.touch()
                        last_start = now
            min_hold = {code: until for code, until in min_hold.items() if until > now}
            keys = sorted({key for code in held.union(min_hold) for key in KEYS[code]}) if mode=="pad" else []
            if mode=="playing":
                elapsed=(now-origin)*1000
                while cursor<len(steps) and steps[cursor][0]<=elapsed:
                    cursor+=1
                keys = steps[cursor-1][1] if cursor else []
                if cursor==len(steps):
                    mode, message = "pad", "演奏结束，已回到手柄"
            if ready and (keys!=last_keys or now-last_send>=.15):
                try:
                    request("input", **frame(keys))
                except (OSError, ValueError, RuntimeError):
                    ready, mode = False, "pad"
                    held.clear()
                    min_hold.clear()
                last_keys, last_send = keys, now
            if painting and (painting.done() or mode not in ("armed", "playing")):
                painting.result()
                painting = None
            if mode=="pad":
                screen.draw("NS 手柄   "+("已连接" if ready else "配对中"),[
                    "1  L+R 登记       回车  A 确认",
                    "WASD 左摇杆     TFGH 十字键",
                    "J  B     I  X     U  Y     Q/E  L/R",
                    "Z/C  ZL/ZR      2/3  −/+     4  HOME",
                    "OKLP 右摇杆     5/6  左/右摇杆键",
                    "M  选曲            Esc  退出"], " + ".join(keys) or message)
            elif mode=="songs":
                screen.draw("选择曲目", [f"{index+1}/{len(tracks)}", tracks[index].name],
                            "W/S 选择  回车载入  Esc 返回")
            elif mode in ("armed", "playing"):
                armed = mode == "armed"
                if painting is None and now - last_draw >= .045:
                    painting = painter.submit(screen.performance, tracks[index].stem, events,
                                              0 if armed else cursor, [] if armed else keys,
                                              0 if armed else elapsed, armed)
                    last_draw = now
            else:
                screen.draw("分析旋律", [tracks[index].stem], "Esc 返回手柄")
    finally:
        try:
            request("release")
        except (OSError, ValueError, RuntimeError):
            pass
        os.close(fd)
        painter.shutdown(wait=True)
        screen.fb.close()
        worker.shutdown(wait=False, cancel_futures=True)


if __name__=="__main__":
    application()
