# CardputerZero 蓝牙时之笛演奏器

在 Switch 2 版《时之笛》的自由演奏模式中，把 MP3 主旋律转为经典蓝牙 Pro Controller 输入。USB 可供电脑通过 ADB 管理 Zero。手柄输入由 Zero 的内置蓝牙直接发往 Switch 2。

## 制作自己的演奏曲目

**从录音开始。** 选自己的录音或已获授权的音源，在音频编辑器里从目标乐句的弱起裁到最后一个音的尾部。保留句间休止，优先导出单声部主旋律。下面的 FFmpeg 命令从第 12 秒截取 16 秒，可按自己的录音修改。

```sh
ffmpeg -n -i recording.wav -ss 12 -t 16 -ac 1 -ar 44100 -c:a libmp3lame -b:a 128k take.mp3
python3 ocarina.py take.mp3 --listen check.wav --preview > preview.json
```

听一遍 `check.wav`，特别留意连续同音、休止和八度跳进。混音里若经常选中低音，可以在上一步加 `--lead-range 60 84`，并给试听文件换个新名字。把确认好的 MP3 放进 **Zero 当前用户的 `~/Music/`**，在 NS Pad 按 `M` 选曲。通过 USB 传输时，可以先运行 `adb push take.mp3 /tmp/take.mp3`，再用 Zero 当前用户在机身终端执行 `mkdir -p ~/Music && cp /tmp/take.mp3 ~/Music/`。

**从乐谱开始。** 在制谱软件中截取目标小节，只留下主旋律。将连音线两端合并为一个长音，重复起音保留为两个音符。把截取后的第一拍设为时间零，导出这一轨的单声部 MP3。再将每个音记成 `[起始毫秒, 结束毫秒, MIDI 音高]`（中央 C 为 60），按起始时间排序。定速曲目每拍毫秒数为 `60000 / BPM`，变速曲目按各段速度换算。时间和音高使用整数，每个音至少 26 毫秒，相邻音保持先后且不重叠。

**保存精确指法。** 如果只上传 MP3，Zero 会自动识谱。要固定手工校对过的音高和起止时刻，可以编辑第一步生成的 `preview.json`，再运行下面的命令，把这份谱绑定到最后导出的 MP3。也可以从制谱软件整理的三列数据开始，直接用它替换代码里的 `notes`。

```sh
python3 - <<'PYTHON'
from pathlib import Path
import hashlib
import json

track = Path("take.mp3")
events = json.loads(Path("preview.json").read_text())
notes = [[event["start_ms"], event["end_ms"], event["midi"]] for event in events]
score = {"sha256": hashlib.sha256(track.read_bytes()).hexdigest(), "notes": notes}
track.with_suffix(".ocarina.json").write_text(json.dumps(score))
PYTHON
```

把 `take.ocarina.json` 与 `take.mp3` 放在 Zero 的同一曲库目录下。机身应用用文件摘要匹配乐谱，重新导出 MP3 后需要重新生成配套文件。

## Zero 机身手柄

在 Zero 原厂应用菜单打开 **NS Pad**。已保存这台 NS2 的配对记录时，应用会尝试重连。首次配对时，在主机打开「手柄 → 更改握法／顺序」。Zero 显示「已连接」后，按 `1`，等主机出现手柄图标，再按 Zero 的回车（A）确认。保持此应用打开，用同一把手柄切回游戏、选择道具、进入演奏界面。

| Zero 的按键 | NS 手柄输入 |
|---|---|
| 1 / 回车 | L+R / A |
| WASD / TFGH | 左摇杆 / 十字键（依次为上、左、下、右） |
| J / I / U | B / X / Y |
| Q / E、Z / C | L / R、ZL / ZR |
| O / K / L / P | 右摇杆上 / 左 / 下 / 右 |
| 2 / 3 / 4 | − / + / HOME |
| 5 / 6 | 按下左 / 右摇杆 |

长按可持续移动，松开回中。进入游戏演奏界面后，在 Zero 按 `M` 可以选择 `~/Music` 里的 MP3。W/S 选曲，回车载入，看到「待演奏」后再按回车开始。Esc 从选曲或播放返回手柄，在手柄页按 Esc 退出应用。选曲和播放都沿用同一条蓝牙连接。

## 演奏画面

演奏页左侧显示当前 NS 按键及对应机身键，右侧预告后两个音的指法。十字箭头表示十字键，杆箭头表示左摇杆。组合键一同按下，休止时松键。底部显示经过时间、曲长、音符计数和进度条。按 Esc 停止并回到手柄。

## 命令行演奏

安装到 `/opt/cardputer-ocarina` 后，打开 Switch 2 的「手柄 → 更改握法／顺序」，在 Zero 的 CLI 运行：

```sh
/opt/cardputer-ocarina/ocarina-play "$HOME/Music/take.mp3"
```

输入 `lr` 再回车可登记，输入 `a` 再回车可确认。进入游戏的自由演奏模式后，按空回车演奏。Ctrl+C 可停止。把自己的 MP3 放进用户的 Music 目录，下次不带路径运行可按编号选曲。启动器需要 sudo 临时切换蓝牙服务，服务退出后恢复常规蓝牙。手动结束配对会话可用 `sudo systemctl stop ocarina-pad`。

通过本机 USB 管理时，将 MP3 发送到 Zero 可使用 `adb push song.mp3 /tmp/song.mp3`。用 `adb shell -t runuser -u egguncle -- /opt/cardputer-ocarina/ocarina-play /tmp/song.mp3` 在电脑终端操作。

## 软件与实测

真机为 Debian 13 ARM64。音频使用 python3-numpy 和 python3-soundfile。随包蓝牙后端来自 [pcble2gamepad](https://github.com/wozt/pcble2gamepad/tree/97084dbdc6f83d16663b32a0721ec6b713e2bbe6)，在这台 Zero 编译，许可证见 licenses。已在 Zero 与 Switch 2 上实测蓝牙重连、手柄登记、机身选曲和游戏内演奏。

## 曲目的处理

程序分块解码，跟踪每 20 ms 音频中的谐波和连续音高，保留休止、时值和可辨认的重复起音。最适合独奏、人声清唱或主旋律突出的录音。混音中可能选中伴奏，和弦只能演奏其中一音。默认识别候选音区为 A2–F6，游戏的书写音域为 B3–F5。自动移调优先减小越界幅度，同等条件下保留原调或八度，仍超出的音按八度折回。短于约 60 ms 的碎音会被过滤。

在本地目录中试听自己的编配效果：

```sh
python3 ocarina.py "$HOME/Music/song.mp3" --listen song-ocarina.wav
aplay song-ocarina.wav
```

默认会同时考虑多个声部。若低音盖过主旋律，可加 `--lead-range 60 84`，只跟踪 C4 到 C6 之间的音。试听和实际演奏使用相同的音符与松键时刻。试听使用合成音色，游戏中的音色由主机产生。

[指法依据](https://github.com/diacoviello/LoZ-Ocarina-Note-Charts) · [手柄后端 v7.1.0](https://github.com/Dycool/NS-PC-Control/tree/v7.1.0) · [Zero 原厂 USB 说明](https://docs.m5stack.com/zh_CN/compute/cardputerzero/usage)
