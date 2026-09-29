# -*- coding: utf-8 -*-
"""merge.py — 把自动生成的 hmt.m3u(港台) 并入手动维护的 base.m3u(主列表)，输出 iptv.m3u
用法: python merge.py
规则:
  - base.m3u 由你手动维护（组播等固定频道），Actions 只读不写
  - hmt.m3u 由 Actions 每次自动生成（实测通过的港台源）
  - 合并结果写入 iptv.m3u，供播放器订阅；base 永远不被改写
  - 发布前校验：iptv.m3u 必须存在且频道数正常，否则不写入（避免发布残缺文件）
"""
import os, shutil, re

BASE = "base.m3u"   # 你的固定主列表（手动维护）
HMT  = "hmt.m3u"    # Actions 自动生成的港台源
OUT  = "iptv.m3u"   # 发布版（订阅这个）
MIN_CH = 50         # 发布版最少频道数阈值，低于此视为失败不发布

def count_ch(text):
    return sum(1 for l in text.splitlines()
               if l.startswith("#EXTINF") and not l.startswith("##"))

def main():
    if not os.path.exists(BASE):
        print(f"缺少 {BASE}，请把主列表放进来"); return
    base = open(BASE, encoding="utf-8-sig").read().rstrip("\n")

    if os.path.exists(HMT):
        hmt = open(HMT, encoding="utf-8").read().lstrip("\ufeff").rstrip("\n")
        if hmt.startswith("#EXTM3U"):
            hmt = hmt[len("#EXTM3U"):].lstrip("\n")
        total = base + "\n" + hmt
    else:
        total = base

    n = count_ch(total)
    if n < MIN_CH:
        print(f"❌ 校验失败：合并后频道数 {n} < 阈值 {MIN_CH}，不发布，保留上次版本")
        return 1
    if not total.strip():
        print("❌ 校验失败：合并结果为空，不发布")
        return 1

    # 备份上一版（仅保留 1 份 .bak）
    if os.path.exists(OUT):
        try:
            shutil.copy(OUT, OUT + ".bak")
        except Exception:
            pass

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(total.rstrip("\n") + "\n")
    print(f"✅ 已合并并校验通过 → {OUT}（{n} 个频道：主列表 {count_ch(base)} + 港台 {count_ch(hmt) if os.path.exists(HMT) else 0}）")
    return 0

if __name__ == "__main__":
    sys_exit = main()
    import sys; sys.exit(sys_exit if sys_exit is not None else 0)
