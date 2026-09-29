# -*- coding: utf-8 -*-
"""test_merge.py — 用 ffprobe 实测候选源，通过的分组生成 hmt.m3u（港台列表）
用法: python test_merge.py  (读 candidates.json, 输出 hmt.m3u)
判据: ffprobe 能解出 video/audio 流 => 通过；404/超时/无流 => 淘汰
"""
import json, subprocess, re, concurrent.futures, os, time, shutil, urllib.request

FFPROBE = shutil.which("ffprobe")  # GitHub Actions 里存在；本机没有则走 HTTP 兜底

def is_ts(data):
    """判断字节里是否含 TS(0x47) 同步流"""
    if not data: return False
    idx = data.find(b"\x47")
    if idx < 0: return False
    cnt = 0
    for i in range(idx, min(len(data), idx + 188 * 12), 188):
        if data[i:i+1] == b"\x47": cnt += 1
        else: break
    return cnt >= 4

def http_probe(url, timeout=12):
    """HTTP 兜底判据：直链测 TS 同步字节；m3u8 取首个分片再测"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read(65536)
        head = data[:2000]
        if b"#EXTM3U" in head or b"#EXT-X" in head:
            text = data.decode("utf-8", "ignore")
            seg = next((l.strip() for l in text.splitlines()
                        if l.strip() and not l.startswith("#")
                        and l.strip().endswith((".ts", ".m4s", ".aac", ".m3u8"))), None)
            if seg:
                seg_url = seg if seg.startswith("http") else url.rsplit("/", 1)[0] + "/" + seg
                r2 = urllib.request.urlopen(
                    urllib.request.Request(seg_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout)
                return is_ts(r2.read(262144))
            return None
        return is_ts(data)
    except Exception:
        return None

def probe(url, timeout=10):
    """返回 True=有节目, False=无信号, None=不确定/失败"""
    if FFPROBE:
        try:
            r = subprocess.run(
                [FFPROBE, "-v", "error",
                 "-show_entries", "stream=codec_type",
                 "-of", "csv=p=0",
                 "-rw_timeout", "12000000", url],
                capture_output=True, text=True, timeout=timeout,
            )
            out = (r.stdout or "") + (r.stderr or "")
            if "video" in out or "audio" in out:
                return True
            if "Connection" in out or "404" in out or "403" in out or "Invalid" in out or "unable" in out:
                return False
            return None  # 连上但没解出 → 存疑
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return None
    return http_probe(url, timeout)

def group_of(name):
    n = name.lower()
    if "凤凰" in n: return "凤凰"
    if "翡翠" in n or "明珠" in n: return "翡翠明珠"
    if "无线" in n or "無線" in n or "tvb" in n or "互动新闻" in n or "星河" in n: return "无线TVB"
    if "有线" in n or "有線" in n or "cable" in n or "now" in n: return "有线/now"
    if "viu" in n or "开电视" in n or "開電視" in n or "hoy" in n or "亚视" in n or "亞視" in n or "atv" in n: return "其他香港"
    if ("台视" in n or "中视" in n or "华视" in n or "民视" in n or "公视" in n or "大爱" in n
            or "东森" in n or "中天" in n or "tvbs" in n or "三立" in n or "非凡" in n
            or "壹电视" in n or "年代" in n or "寰宇" in n or "八大" in n or "纬来" in n or "緯來" in n): return "台湾台"
    if "澳门" in n or "澳門" in n or "莲花" in n or "蓮花" in n: return "澳门"
    return "其他港台"

def norm_key(name):
    """归一化台名，用于同台去重"""
    n = re.sub(r"\[[^\]]*\]", "", name)
    n = re.sub(r"[\s\-_（）()]", "", n)
    n = re.sub(r"(高清|超清|标清|HD|SD|HDR|4K|TV|频道|频道|台)$", "", n, flags=re.I)
    return n.lower()

def main():
    if not os.path.exists("candidates.json"):
        print("无 candidates.json"); return
    cands = json.load(open("candidates.json", encoding="utf-8"))
    print(f"候选 {len(cands)} 条，开始实测...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for (name, url), ok in zip(
            [(c["name"], c["url"]) for c in cands],
            ex.map(lambda c: probe(c["url"]), cands),
        ):
            results.append({"name": name, "url": url, "ok": ok})

    passed = [r for r in results if r["ok"] is True]
    unsure = [r for r in results if r["ok"] is None]
    dead = [r for r in results if r["ok"] is False]
    print(f"通过 {len(passed)} 条，存疑 {len(unsure)}，失效 {len(dead)}")

    # 分组 + 同名去重（每台保留 1 主 1 备，共 2 条）
    groups = {}
    for r in passed:
        groups.setdefault(group_of(r["name"]), []).append(r)
    for g in groups:
        seen, keep = {}, []
        for r in groups[g]:
            k = norm_key(r["name"])
            seen[k] = seen.get(k, 0)
            if seen[k] < 2:
                seen[k] += 1
                keep.append(r)
        groups[g] = keep

    # 生成 hmt.m3u
    lines = ["#EXTM3U", "", "# 港台频道（自动收集+实测，仅保留能播源）", ""]
    for g in sorted(groups):
        items = groups[g]
        lines.append(f"# ---------- {g} ----------")
        for r in items:
            lines.append(f"#EXTINF:-1 group-title=\"{g}\",{r['name']}")
            lines.append(r["url"])
        lines.append("")
    with open("hmt.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    total_kept = sum(len(v) for v in groups.values())
    print(f"已生成 hmt.m3u：{len(passed)} 条通过 → 去重后保留 {total_kept} 条")
    print("分组明细:", {g: len(v) for g, v in groups.items()})

if __name__ == "__main__":
    main()
