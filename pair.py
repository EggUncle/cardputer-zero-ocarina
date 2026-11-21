#!/usr/bin/env python3
"""Keep a real pairing window open, e.g. while choosing a track on the Zero."""
import time
from controller import request

def main():
    start = time.monotonic()
    announced = False
    while time.monotonic()-start < 300:
        try:
            state = request("status")
        except (ConnectionRefusedError, FileNotFoundError):
            if time.monotonic()-start > 25:
                raise SystemExit("蓝牙后端未启动，请检查 journalctl -u ocarina-pad")
            time.sleep(.25)
            continue
        if state["initialized"] and not announced:
            print("已收到主机的蓝牙手柄初始化，等待演奏。", flush=True)
            announced = True
        time.sleep(.5)

if __name__ == "__main__":
    main()
