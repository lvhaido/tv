# -*- coding: utf-8 -*-
"""collect.py v3 — 融合 iptv-org 国别源 + Guovin 测活源 + 国内IPv4/IPv6源 + 全球聚合源
繁简归一化 + 白名单子串严选，生成 candidates.json（含分组信息）
用法: python collect.py  (输出 candidates.json)
"""
import json, re, urllib.request, concurrent.futures, sys

# ============================================================
# 1. 源列表（分层：可信度从高到低）
# ============================================================
# A. 国别官方源：只有港澳台，纯净、从根上杜绝混入韩台/杂台
COUNTRY_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/countries/tw.m3u",
    "https://iptv-org.github.io/iptv/countries/mo.m3u",
]
# B. 测活精选源：已被别人自动测活，命中率高、间接加快我们实测
LIVE_SOURCES = [
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-database/master/result.m3u",
]
# C. 国内聚合源（含 IPv6，对国内直连更友好）
CN_AGG_SOURCES = [
    "https://live.fanmingming.com/tv/m3u/ipv6.m3u",
    "https://live.zbds.top/tv/iptv4.m3u",
    "https://live.zbds.top/tv/iptv6.m3u",
]
# D. 全球聚合源
GLOBAL_SOURCES = [
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://raw.githubusercontent.com/Meroser/IPTV/main/IPTV.m3u",
    "https://raw.githubusercontent.com/joevess/IPTV/main/iptv.m3u8",
]
# E. 原有用源（保留）
ORIG_SOURCES = [
    "https://raw.githubusercontent.com/jn950/live/main/tv/pllive.txt",
    "https://raw.githubusercontent.com/FRANKASEE/TV/refs/heads/master/result.txt",
    "https://live.fanmingming.com/tv/m3u/v6.txt",
    "https://vip.iptv365.org/live2025.txt",
]
SOURCES = COUNTRY_SOURCES + LIVE_SOURCES + CN_AGG_SOURCES + GLOBAL_SOURCES + ORIG_SOURCES

# ============================================================
# 2. 繁简归一化（修掉"白名单是简体、源是繁体"的误杀）
# ============================================================
_SIMPLIFY = str.maketrans({
    "東": "东", "緯": "纬", "愛": "爱", "爾": "尔", "達": "达", "視": "视",
    "頻": "频", "聞": "闻", "財": "财", "經": "经", "體": "体", "劇": "剧",
    "綜": "综", "樂": "乐", "電": "电", "訊": "讯", "網": "网", "蓮": "莲",
    "鳳": "凤", "臺": "台", "戲": "戏", "韓": "韩", "龍": "龙", "時": "时",
    "紀": "纪", "實": "实", "欄": "栏", "創": "创", "際": "际", "銀": "银",
    "節": "节", "縣": "县", "廣": "广", "匯": "汇", "寧": "宁", "麗": "丽",
    "點": "点", "濟": "济", "陽": "阳", "華": "华", "動": "动", "麥": "麦",
    "衞": "卫", "衛": "卫", "專": "专", "導": "导", "數": "数", "義": "义",
})

def to_simplified(s):
    return s.translate(_SIMPLIFY)

# ============================================================
# 3. 白名单（用户可维护：想看的好台主词，子串匹配）
# ============================================================
WHITE_LIST = [
    # 香港 · TVB / 凤凰
    "翡翠", "明珠", "tvb", "j2", "无线新闻", "星河", "凤凰", "香港卫视",
    # 香港 · 有线 / now / Viu / 开电视
    "now新闻", "now财经", "now爆谷", "now剧集", "now电影",
    "有线新闻", "有线财经", "有线综合", "有线剧集", "有线电影",
    "viutv", "viutvsix", "hoy", "开电视", "香港电台31", "香港电台32",
    # 台湾 · 无线
    "台视", "中视", "华视", "民视", "公视", "客家",
    # 台湾 · 有线新闻/综合/戏剧
    "tvbs", "东森", "中天", "三立", "八大", "纬来", "非凡", "年代", "寰宇", "爱尔达", "momo",
    # 澳门
    "澳视", "澳门资讯", "澳门莲花", "莲花卫视",
]

# 明显非目标 / 不可直连的拦截词
BLACK_WORDS = ["vpn", "直播源", "预告", "测试", "试播", "演示", "演示台"]

def is_whitelisted(name):
    n = to_simplified(name).lower()
    n = re.sub(r"\s+", "", n)          # 去空格，避免 "TVB 翡翠台" 匹配失败
    n = re.sub(r"[\[\]（）()\-_]", "", n)  # 去括号/连接符
    if any(b in n for b in BLACK_WORDS):
        return False
    return any(w in n for w in WHITE_LIST)

# ============================================================
# 4. 分组（供后续 merge 归类）
# ============================================================
def group_of(name):
    n = to_simplified(name).lower()
    if "凤凰" in n: return "凤凰"
    if "翡翠" in n or "明珠" in n: return "翡翠明珠"
    if "tvb" in n or "无线" in n or "星河" in n: return "无线TVB"
    if "有线" in n or "cable" in n or "now" in n: return "有线/now"
    if "viu" in n or "开电视" in n or "hoy" in n or "亚视" in n or "atv" in n: return "其他香港"
    if ("台视" in n or "中视" in n or "华视" in n or "民视" in n or "公视" in n
            or "东森" in n or "中天" in n or "tvbs" in n or "三立" in n
            or "非凡" in n or "年代" in n or "寰宇" in n or "八大" in n
            or "纬来" in n or "爱尔达" in n or "momo" in n): return "台湾台"
    if "澳" in n or "莲花" in n: return "澳门"
    return "其他港台"

# ============================================================
# 5. 网络与解析
# ============================================================
def fetch(url):
    try:
        print(f"[INFO] 拉取源: {url}")
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        data = urllib.request.urlopen(req, timeout=15).read()
        return data.decode("utf-8", "ignore")
    except Exception as e:
        print(f"[WARN] 拉取失败: {url} | {e}", file=sys.stderr)
        return ""

def parse(text):
    """兼容解析 m3u 与 txt，返回 [(name,url), ...]"""
    out, cur = [], ""
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("#EXTINF"):
            m = re.search(r',(.+)$', line)
            if m: cur = m.group(1).strip()
        elif line.startswith("http"):
            if cur:
                out.append((cur, line)); cur = ""
            elif "," in line:
                nm, u = line.split(",", 1)
                if u.strip().startswith("http"): out.append((nm.strip(), u.strip()))
        elif "," in line:
            nm, u = line.split(",", 1)
            if u.strip().startswith("http"): out.append((nm.strip(), u.strip()))
    return out

# ============================================================
# 6. 主流程
# ============================================================
def main():
    raw = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for res in ex.map(fetch, SOURCES):
            raw += "\n" + res

    channels = parse(raw)
    print(f"解析出原始条目 {len(channels)} 条")

    # 筛选 + 去重
    seen_urls, result = set(), []
    for name, url in channels:
        if not is_whitelisted(name):
            continue
        if re.search(r"\(vpn\)", name, re.I):
            continue
        if re.search(r"(\?|&)(txSecret|txTime|mac=|auth=|token=|key=)", url, re.I):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        result.append({"name": name.strip(), "url": url.strip(), "group": group_of(name)})

    # 每台最多保留 N 条候选（保留备源，但压缩实测规模）
    N = 5
    by_name = {}
    for c in result:
        k = re.sub(r"[\s\[\]\-（）()]", "", to_simplified(c["name"])).lower()
        k = re.sub(r"(高清|超清|标清|hd|sd|hdr|4k|tv|频道|台)$", "", k, flags=re.I)
        by_name.setdefault(k, []).append(c)
    limited = []
    for k, v in by_name.items():
        limited.extend(v[:N])
    result = limited

    with open("candidates.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 统计
    from collections import Counter
    gcount = Counter(c["group"] for c in result)
    print(f"[SUCCESS] 严选候选 {len(result)} 条（每台限 {N}）")
    print("分组:", dict(gcount))

if __name__ == "__main__":
    main()
