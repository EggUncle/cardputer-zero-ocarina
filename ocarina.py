#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

from music import arrange, transcribe, write_audition


def choose_song():
    folder = Path.home() / "Music"
    songs = sorted(p for p in folder.glob("*") if p.is_file() and p.suffix.lower() == ".mp3")
    if not songs:
        raise ValueError(f"请将 MP3 放入 {folder}，或在命令行指定文件")
    for index, path in enumerate(songs, 1):
        print(index, path.name)
    choice = int(input("输入曲目编号："))
    if not 1 <= choice <= len(songs):
        raise ValueError("编号不在曲目列表中")
    return songs[choice - 1]


def main():
    parser = argparse.ArgumentParser(description="MP3 → Switch 2《时之笛》自由演奏")
    parser.add_argument("song", nargs="?", type=Path)
    parser.add_argument("--preview", action="store_true", help="输出乐谱，不连接手柄")
    parser.add_argument("--scale", action="store_true", help="用五个自然音和变音校验游戏指法")
    parser.add_argument("--lead-range", type=int, nargs=2, default=(45, 89), metavar=("LOW", "HIGH"),
                        help="限定旋律的 MIDI 音区；例如 60 84 只跟踪 C4 到 C6")
    parser.add_argument("--listen", type=Path, metavar="FILE.wav",
                        help="保存移调后的旋律试听，不连接手柄")
    args = parser.parse_args()
    if not 24 <= args.lead_range[0] <= args.lead_range[1] <= 108:
        parser.error("音区应按从低到高填写，范围为 24 到 108")
    if args.listen and args.listen.suffix.lower() != ".wav":
        parser.error("试听文件应使用 .wav 扩展名")
    if args.scale:
        pitches = [62, 65, 69, 71, 74, 63, 64, 59, 77]
        notes = [(i*600, i*600+450, pitch) for i,pitch in enumerate(pitches)]
    else:
        notes = transcribe(args.song or choose_song(), args.lead_range)
    events, shift, folded = arrange(notes)
    print(f"{len(events)} 个音，全曲移调 {shift:+d} 半音，{folded} 个音调整八度。", file=sys.stderr)
    if args.listen:
        write_audition(args.listen, events)
    if args.preview:
        print(json.dumps([dict(start_ms=a, end_ms=b, midi=p, hold=mods, press=btn)
                          for a,b,p,mods,btn in events], ensure_ascii=False, indent=2))
    elif not args.listen:
        from controller import play
        play(events)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("演奏已停止")
    except (ValueError, RuntimeError, OSError, EOFError) as exc:
        sys.exit(str(exc))
