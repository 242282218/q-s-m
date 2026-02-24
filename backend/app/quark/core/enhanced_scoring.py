import re, math, unicodedata
from datetime import datetime, timezone
from typing import Optional, Dict, Any

VIDEO_NEG = [
    "解说文案","文案","讲解稿","台词","脚本","宣传文案","攻略","补丁","修改器",
    "安装","破解版","内购","加速器","网游","手游","客户端",
    ".apk",".exe",".torrent",".pdf",".doc",".docx",".ppt",".pptx",".xls",".xlsx",
    "课程","教程","小说","听书"
]
DOC_EXT = [".pdf",".epub",".mobi",".azw",".azw3",".txt",".doc",".docx",".ppt",".pptx",".xls",".xlsx"]
ARCHIVE_EXT = [".zip",".rar",".7z",".tar",".gz",".bz2"]

VIDEO_POS = [
    "电影","影视","剧集","电视剧","网盘","蓝光","原盘","remux","bdmv","webrip","web-dl",
    "1080p","2160p","4k","720p","x264","x265","hevc","hdr","dv","杜比","atmos","dtsx","中字","字幕"
]

def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\s+", "", s)
    return s

def has_any(s: str, lst) -> bool:
    return any(x in s for x in lst)

def parse_size_to_gb(size_str: str) -> Optional[float]:
    if not size_str: return None
    s = unicodedata.normalize("NFKC", size_str).lower()
    m = re.search(r"([\d.]+)\s*(tb|t|gb|g|mb|m|kb|k)", s)
    if not m: return None
    val, unit = float(m.group(1)), m.group(2)
    if unit in ("tb","t"): return val * 1024
    if unit in ("gb","g"): return val
    if unit in ("mb","m"): return val / 1024
    if unit in ("kb","k"): return val / (1024 * 1024)
    return None

def extract_tags(name: str):
    n = unicodedata.normalize("NFKC", name or "")
    nl = n.lower()
    tags = set()

    if re.search(r"\b2160p\b|4k|uhd", nl): tags.add("4k")
    if re.search(r"\b1080p\b", nl): tags.add("1080p")
    if re.search(r"\b720p\b", nl): tags.add("720p")

    if "hdr" in nl: tags.add("hdr")
    if "dolby vision" in nl or "杜比视界" in n or re.search(r"\bdv\b", nl): tags.add("dv")

    if "remux" in nl: tags.add("remux")
    if "bdmv" in nl: tags.add("bdmv")
    if "bluray" in nl or "蓝光" in n or "原盘" in n: tags.add("bluray")

    if "web-dl" in nl or "webdl" in nl: tags.add("webdl")
    if "webrip" in nl: tags.add("webrip")

    if "imax" in nl: tags.add("imax")

    if "x265" in nl or "h.265" in nl or "hevc" in nl: tags.add("x265")
    if "x264" in nl or "h.264" in nl: tags.add("x264")

    if "ddp" in nl or "eac3" in nl: tags.add("ddp")
    if "truehd" in nl: tags.add("truehd")
    if "dts-hd" in nl or "dtshd" in nl: tags.add("dtshd")
    if "atmos" in nl or "杜比全景声" in n: tags.add("atmos")
    if "dtsx" in nl: tags.add("dtsx")

    if "特效字幕" in n: tags.add("fx_sub")
    if "中字" in n or "字幕" in n: tags.add("cn_sub")
    if "国英" in n or "双语" in n or "双音" in n: tags.add("multi_audio")
    if "合集" in n or "系列" in n: tags.add("collection")
    if re.search(r"\b60fps\b|\b120fps\b|高帧", n, re.I): tags.add("hfr")

    return tags

def text_similarity(query: str, name: str) -> float:
    qn, nn = normalize_text(query), normalize_text(name)
    if not qn or not nn: return 0.0
    if qn in nn: return 1.0

    def bigrams(s):
        return {s[i:i+2] for i in range(len(s)-1)} if len(s) >= 2 else {s}

    qbg, nbg = bigrams(qn), bigrams(nn)
    inter, uni = len(qbg & nbg), len(qbg | nbg)
    j = inter / uni if uni else 0.0

    qtok = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", query).lower())
    ntok = set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", name).lower()))
    tok_hit = (sum(1 for t in qtok if t in ntok) / max(1, len(qtok))) if qtok else 0.0

    return max(j, tok_hit * 0.9)

def intent_score(name: str, size_gb, tags) -> float:
    n = unicodedata.normalize("NFKC", name or "")
    nl = n.lower()

    if has_any(n, VIDEO_NEG) or has_any(nl, [x.lower() for x in VIDEO_NEG]):
        if ".iso" in nl and ({"bluray","bdmv"} & tags or "原盘" in n):
            return 0.7
        return 0.0

    if any(ext in nl for ext in DOC_EXT):
        return 0.0

    if any(ext in nl for ext in ARCHIVE_EXT):
        if tags & {"remux","bdmv","bluray"}: return 0.6
        if size_gb is not None and size_gb >= 1.5: return 0.4
        return 0.0

    pos = 0.0
    if has_any(n, VIDEO_POS): pos += 0.7
    if tags: pos += 0.2
    if size_gb is not None and size_gb >= 0.7: pos += 0.1
    return min(1.0, pos)

def plausibility_score(name: str, size_gb, tags) -> float:
    if size_gb is None: return 0.4

    if size_gb < 0.5 and ({"4k","bdmv","remux","bluray","dv","hdr"} & tags):
        return 0.0

    is_series = bool(re.search(r"S\d|全\d+季|全集|全\d+集|季", name))

    if "bdmv" in tags or "bluray" in tags:
        mn, mx = (25, 120) if not is_series else (40, 800)
        if "4k" in tags: mn = 45 if not is_series else 80
    elif "remux" in tags:
        mn, mx = (20, 120) if not is_series else (40, 800)
        if "4k" in tags: mn = 35 if not is_series else 80
    elif "webdl" in tags or "webrip" in tags:
        mn, mx = (2.5, 25) if "4k" in tags else (1.0, 15)
        if is_series: mx = 200
    else:
        if "4k" in tags:
            mn, mx = (4.0, 35.0)
            if "dv" in tags or "hdr" in tags: mn = 4.5
        elif "1080p" in tags:
            mn, mx = (1.2, 18.0)
        elif "720p" in tags:
            mn, mx = (0.6, 8.0)
        else:
            mn, mx = (0.7, 200.0)

    if size_gb < mn: return max(0.0, size_gb / mn)
    if size_gb > mx: return max(0.0, mx / size_gb)
    mid = (mn + mx) / 2
    span = (mx - mn) / 2
    return 0.8 + 0.2 * (1 - abs(size_gb - mid) / span) if span > 0 else 1.0

def quality_score(tags, name: str, size_gb) -> float:
    pts = 0
    if "4k" in tags: pts += 25
    elif "1080p" in tags: pts += 15
    elif "720p" in tags: pts += 6

    if "bdmv" in tags: pts += 35
    elif "remux" in tags: pts += 30
    elif "bluray" in tags: pts += 24
    elif "webdl" in tags or "webrip" in tags: pts += 18

    if "dv" in tags: pts += 20
    if "hdr" in tags: pts += 10

    if "atmos" in tags: pts += 10
    if "dtsx" in tags: pts += 8
    if "truehd" in tags: pts += 6
    if "dtshd" in tags: pts += 5
    if "ddp" in tags: pts += 3

    if "x265" in tags: pts += 4
    if "x264" in tags: pts += 2

    if "fx_sub" in tags: pts += 6
    elif "cn_sub" in tags: pts += 3
    if "multi_audio" in tags: pts += 4

    if "imax" in tags: pts += 2
    if "hfr" in tags: pts += 2
    if "collection" in tags: pts += 2
    if "高码率" in name: pts += 4

    if "4k" in tags and "1080p" in tags: pts -= 12

    return max(0.0, min(1.0, pts / 110))

def alpha_from_conf(conf: float, zxd_high=False, plaus_low=False) -> float:
    if conf < 0.5: a = 0.7
    elif conf < 0.8: a = 0.55
    else: a = 0.4
    if zxd_high: a = max(0.3, a - 0.1)
    if plaus_low: a = min(0.8, a + 0.1)
    return a

def popularity_score(views) -> float:
    try: v = float(views)
    except: return 0.0
    return min(1.0, math.log1p(v) / math.log1p(200))

def freshness_score(updatetime: str) -> float:
    if not updatetime: return 0.5
    now = datetime(2026, 1, 8, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(updatetime.replace("Z", "+00:00"))
        days = (now - dt).total_seconds() / 86400
        return math.exp(-max(0, days) / 60)
    except:
        return 0.5

def score_item(query: str, item: dict) -> Optional[Dict[str, Any]]:
    name = item.get("name", "")
    size_gb = parse_size_to_gb(item.get("size", ""))
    tags = extract_tags(name)
    nl = unicodedata.normalize("NFKC", name).lower()

    if any(ext in nl for ext in DOC_EXT): return None
    if ".apk" in nl or ".exe" in nl or ".torrent" in nl: return None
    if any(ext in nl for ext in ARCHIVE_EXT) and (size_gb is None or size_gb < 0.7): return None
    if size_gb is not None and size_gb < 0.5 and ({"4k","bdmv","remux","bluray","dv","hdr"} & tags): return None

    c_text = text_similarity(query, name)
    c_int = intent_score(name, size_gb, tags)
    c_plaus = plausibility_score(name, size_gb, tags)

    conf = c_text * (0.7 + 0.3 * (0.5 * c_int + 0.5 * c_plaus))
    conf = max(0.0, min(1.0, conf))
    if c_text < 0.25 or c_int == 0.0:
        conf *= 0.15

    qual = quality_score(tags, name, size_gb)

    P = popularity_score(item.get("views", 0))
    R = freshness_score(item.get("updatetime"))

    zxd_high = (c_text >= 0.8 and c_int >= 0.8 and c_plaus >= 0.8)
    plaus_low = (c_plaus < 0.4)
    a = alpha_from_conf(conf, zxd_high=zxd_high, plaus_low=plaus_low)

    pr_gate = 1.0 if conf >= 0.6 else (0.3 if conf >= 0.4 else 0.0)

    score = a * conf + (1 - a) * qual + pr_gate * (0.10 * P + 0.05 * R)
    if conf < 0.08:
        score = conf

    return {
        "score": score,
        "Conf": conf,
        "Qual": qual,
        "alpha": a,
        "tags": sorted(tags),
        "size_gb": size_gb,
        "C_text": c_text,
        "C_intent": c_int,
        "C_plaus": c_plaus,
        "P": P,
        "R": R
    }
