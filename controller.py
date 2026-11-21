"""Nintendo classic Bluetooth HID via pcble2gamepad's owner-only local socket."""
import json
import os
import select
import socket
import sys
import time


def request(method, **params):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(f"/run/pcble2gamepad/{os.getuid()}/pro.sock")
        sock.sendall((json.dumps(dict(version=1, method=method, **params))+"\n").encode())
        with sock.makefile("rb") as reader:
            reply = json.loads(reader.readline(131072))
    if not reply["ok"]:
        raise RuntimeError(reply.get("error", "Bluetooth backend error"))
    return reply["result"]


def frame(keys):
    buttons = [0, 0, 0]
    bits = {"Y": (0,1), "X": (0,2), "B": (0,4), "A": (0,8), "R": (0,64), "ZR": (0,128),
            "MINUS": (1,1), "PLUS": (1,2), "R3": (1,4), "L3": (1,8), "HOME": (1,16),
            "DPAD_LEFT": (2,8), "DPAD_RIGHT": (2,4), "ZL": (2,128),
            "L": (2,64), "DPAD_UP": (2,2), "DPAD_DOWN": (2,1)}
    for key in keys:
        if key in bits:
            byte, mask = bits[key]
            buttons[byte] |= mask
    def axis(center, positive, negative):
        delta = int(positive in keys) - int(negative in keys)
        return 4095 if delta > 0 else 0 if delta < 0 else center
    sticks = [axis(2159, "LSTICK_RIGHT", "LSTICK_LEFT"), axis(1916, "LSTICK_UP", "LSTICK_DOWN"),
              axis(2070, "RSTICK_RIGHT", "RSTICK_LEFT"), axis(2013, "RSTICK_UP", "RSTICK_DOWN")]
    return dict(buttons=buttons, sticks=sticks)


def hold(keys, until):
    while True:
        status = request("input", **frame(keys))
        if status["simulated"] or not status["initialized"]:
            raise ConnectionError("蓝牙手柄连接中断")
        left = until - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(.18, left))
        if time.monotonic() >= until:
            return


def play(events):
    print("请在 Switch 2 打开手柄的更改握法／顺序。", flush=True)
    while True:
        state = request("status")
        if state["simulated"]:
            raise RuntimeError("当前服务处于模拟测试模式")
        if state["initialized"]:
            break
        time.sleep(.3)
    print("蓝牙握手成功。输入 lr 登记，a 确认。进入自由演奏后空回车开始。", flush=True)
    try:
        while True:
            if not select.select([sys.stdin], [], [], .3)[0]:
                if not request("status")["initialized"]:
                    raise ConnectionError("蓝牙手柄已断开")
                continue
            command = sys.stdin.readline()
            if not command:
                raise ValueError("演奏需要交互终端")
            cmd = command.strip().lower()
            if not cmd:
                break
            if cmd in ("lr", "a"):
                hold(["L","R"] if cmd=="lr" else ["A"], time.monotonic()+.25)
                request("release")
        origin = time.monotonic()+.15
        for start, end, _, mods, button in events:
            onset = origin + start/1000
            hold([], onset-.020)
            hold(mods, onset)
            hold(mods+[button], origin+(end-25)/1000)
        request("release")
    finally:
        try:
            request("release")
        except OSError:
            pass
