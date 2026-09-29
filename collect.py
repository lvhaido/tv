# -*- coding: utf-8 -*-
"""collect.py — 从多个已知源仓库拉取列表，筛出港台频道，生成 candidates.json
用法: python collect.py  (输出 candidates.json)
"""
import json, re, urllib.request, concurrent.futures

# 已知持续更新的源聚合文件（可自行增删）
SOURCES = [
    "https://raw.githubusercontent.com/jn950/live/main/tv/pllive.txt",
    "https://raw.githubusercontent.com/FRANKASEE/TV/refs/heads/master/result.txt",
    "https://live.fanmingming.com/tv/m3u/v6.txt",
    "https://vip.iptv365.org/live2025.txt",
]

# 目标频道关键词（正则，命中任一即保留）
PAT = re.compile(
    # 香港 · TVB系
    r"(凤凰中文|凤凰资讯|凤凰香港|凤凰|翡翠台|明珠台|翡翠|明珠|J2|星河频道|星河|"
    r"无线新闻|無線新聞|无线财经|無線財經|无线体育|無線體育|互动新闻|互動新聞|香港台|"
    # 香港 · 港台电视 / 有线 / now
    r"港台电视|港台電視|RTHK|香港电台|香港電台|有线新闻|有線新聞|有线财经|有線財經|"
    r"有线娱乐|有線娛樂|有线电影|有線電影|有线体育|有線體育|Cable|"
    r"Now.?新闻|Now.?財經|Now.?爆谷|Now.?TV|nownews|nowtv|ViuTV|VIUTV|Viu|VIU|"
    r"开电视|開電視|HOY|亚洲电视|亞洲電視|亚视|亞視|ATV|"
    # 台湾 · 无线台
    r"台视|台視|中视|中視|华视|華視|民视|民視|公视|公視|大爱|大愛|"
    # 台湾 · 有线
    r"东森|東森|ETTV|中天|TVBS|三立|非凡|壹电视|壹電視|年代|寰宇|八大|纬来|緯來|"
    # 澳门 / 其它
    r"澳门|澳門|莲花卫视|蓮花衛視|星空|国际台)",
    re.IGNORECASE,
)

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception:
        return ""

def parse(text):
    """解析 m3u / txt 混合文本，返回 [(name,url), ...]"""
    out, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF") or (not line.startswith("#") and "," in line and "http" in line):
            # m3u: #EXTINF...,url  或  txt: 频道名,url
            if "http" in line:
                parts = line.rsplit(",", 1)
                nm = parts[0].split(",", 1)[-1] if "," in parts[0] else parts[0]
                out.append((nm.strip(), parts[-1].strip()))
        elif line.startswith("http") and cur:
            out.append((cur, line.strip())); cur = None
        elif "," in line and line.split(",")[-1].strip().startswith("http"):
            nm, url = line.split(",", 1)
            out.append((nm.strip(), url.strip()))
    return out

def main():
    text = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for t in ex.map(fetch, SOURCES):
            text += "\n" + t

    seen, cands = set(), []
    for name, url in parse(text):
        # 只留目标频道
        if PAT.search(name):
            # 去重（URL唯一），跳过带时效 token 的
            if url in seen:
                continue
            if re.search(r"\?(.*txSecret|.*txTime|.*mac=|.*auth|.*token|.*key=.*&)", url, re.I):
                continue
            seen.add(url)
            cands.append({"name": name, "url": url})

    # 每台最多保留 N 条候选，压缩实测规模（避免几百条全部 ffprobe 拖慢）
    N = 5
    by_name = {}
    for c in cands:
        key = re.sub(r"[\s\[\]\-（）()]", "", c["name"]).lower()
        key = re.sub(r"(高清|超清|标清|HD|SD|HDR|4K|TV|频道|台)$", "", key, flags=re.I)
        by_name.setdefault(key, []).append(c)
    limited = []
    for k, v in by_name.items():
        limited.extend(v[:N])
    cands = limited

    with open("candidates.json", "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=2)
    print(f"共筛出候选 {len(cands)} 条（去重后每台限 {N} 条）")

if __name__ == "__main__":
    main()
