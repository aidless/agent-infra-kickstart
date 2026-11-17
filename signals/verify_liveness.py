#!/usr/bin/env python3
"""verify_liveness.py — 核验一条招聘链接背后岗位是否仍在招。

背景（实测教训，2026-11-16）：
  招聘聚合站（freehire / wellfound / 猎聘镜像）会把**已下线**岗位继续留在索引里，
  而且详情页一律返回 HTTP 200 —— 用 `curl -o /dev/null -w %{http_code}` 判活是**装饰**。
  实测：飞书招聘门户对**任意** position id（含 9999999999999999999）都返回 200 + 200KB HTML，
  HTML 里连岗位标题都没有（标题只有公司名）。唯一可靠的判据是**ATS 自己的 JSON 接口**。

本脚本按 ATS 家族分派，每家给出一条真判据：
  feishu      GET  /api/v1/job/posts/{id}      -> data.job_post_detail 非空 且 channel_online_status==1
  moka        GET  /api/outer/... 不可用，退回页面内嵌 JSON（找不到即 UNKNOWN，不下"在招"结论）
  greenhouse  GET  job-boards.greenhouse.io/{board}/jobs/{id}/json（有则 200，无则 404）
  wellfound   页面 ld+json 的 JobPosting + "Apply now" 存在性（弱判据，见 --note）
  workable / lever / ashby 同理按各自 API

三态输出，禁止二态：
  ONLINE      ATS 明确说这条岗位在线
  GONE        ATS 明确说查不到（例如 detail 为空 / 404）
  UNKNOWN     ATS 接口不可达或该家族没有真判据（此时**不得**在报告里写"仍在招"）

自检（--selftest）：对每个家族喂一个**已知存在**的样本和一个**构造的假 id**，
  必须得到 ONLINE / GONE 两个不同答案。只对假 id 判 GONE 不算过（那不是判活，是判"id 格式对不对"）。
反证（--prove-red）：把 probe 换成"永远返回 ONLINE"的桩，selftest 必须红。

用法：
  python3 signals/verify_liveness.py --selftest
  python3 signals/verify_liveness.py --prove-red
  python3 signals/verify_liveness.py --url <URL> [--url <URL> ...]
  python3 signals/verify_liveness.py --file signals/candidates.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30


@dataclass
class Verdict:
    url: str
    family: str
    state: str          # ONLINE | GONE | UNKNOWN
    evidence: str       # 判据本身，必须能贴进报告
    title: Optional[str] = None
    published: Optional[str] = None
    online_flag: Optional[int] = None
    company: Optional[str] = None


def _get(url: str, headers: Optional[Dict[str, str]] = None,
         attempts: int = 3) -> Tuple[Optional[int], str]:
    """网络层偶发抖动（实测 greenhouse 假 id 第一轮返回 HTTP None，单独重跑就是 404）
    必须重试，否则「偶发失败」会被写成 UNKNOWN，等于把网络抖动记成产品结论。
    HTTPError 不重试——那是服务端明确表态。"""
    req = urllib.request.Request(url, headers={**{"User-Agent": UA}, **(headers or {})})
    last: Optional[int] = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception:
                return e.code, ""
        except Exception:
            last = None
            if i + 1 < attempts:
                import time as _t
                _t.sleep(1.5 * (i + 1))
    return last, ""


def _family(url: str) -> str:
    u = url.lower()
    if ".jobs.feishu.cn" in u:
        return "feishu"
    if "mokahr.com" in u:
        return "moka"
    if "greenhouse.io" in u:
        return "greenhouse"
    if "wellfound.com" in u or "angel.co" in u:
        return "wellfound"
    if "ashbyhq.com" in u:
        return "ashby"
    if "workable.com" in u:
        return "workable"
    if "lever.co" in u:
        return "lever"
    return "unknown"


# ---------------------------------------------------------------- feishu
FEISHU_ID = re.compile(r"/position/(\d+)/detail")


def probe_feishu(url: str) -> Verdict:
    m = FEISHU_ID.search(url)
    host_m = re.match(r"https://([^.]+)\.jobs\.feishu\.cn", url)
    if not (m and host_m):
        return Verdict(url, "feishu", "UNKNOWN", "URL 形态不符 /position/<id>/detail")
    host, job = host_m.group(1), m.group(1)
    st, body = _get(
        f"https://{host}.jobs.feishu.cn/api/v1/job/posts/{job}",
        {"Accept": "application/json", "portal-platform": "pc", "x-cs-locale": "zh-CN",
         "Referer": f"https://{host}.jobs.feishu.cn/index/position/{job}/detail"},
    )
    if st != 200:
        return Verdict(url, "feishu", "UNKNOWN", f"detail API HTTP {st}")
    try:
        d = json.loads(body)
    except Exception:
        return Verdict(url, "feishu", "UNKNOWN", "detail API 非 JSON")
    det = (d.get("data") or {}).get("job_post_detail") or {}
    if not det:
        return Verdict(url, "feishu", "GONE",
                       f"detail API code={d.get('code')} 但 job_post_detail 为空（该 id 查无此岗）")
    flag = det.get("channel_online_status")
    pub = _epoch_ms_to_date(det.get("publish_time"))
    # 公司名必须从 tenant/info 取，不能从聚合站的 company 字段（实测聚合站会张冠李戴：
    # 同一个 host 下的岗位被 freehire 标成了 Alibaba/ByteDance，而 tenant_name 说它是 MiniMax）
    comp = _feishu_tenant_name(host)
    if flag != 1:
        return Verdict(url, "feishu", "GONE",
                       f"channel_online_status={flag}", det.get("title"), pub, flag, comp)
    return Verdict(url, "feishu", "ONLINE",
                   "job_post_detail 非空 且 channel_online_status=1",
                   det.get("title"), pub, flag, comp)


_TENANT_CACHE: Dict[str, Optional[str]] = {}


def _feishu_tenant_name(host: str) -> Optional[str]:
    if host in _TENANT_CACHE:
        return _TENANT_CACHE[host]
    st, body = _get(f"https://{host}.jobs.feishu.cn/api/v1/tenant/info",
                    {"Accept": "application/json", "portal-platform": "pc", "x-cs-locale": "zh-CN"})
    if st != 200:
        return None
    try:
        v = ((json.loads(body).get("data") or {}).get("tenant_info") or {}).get("tenant_name")
    except Exception:
        v = None
    _TENANT_CACHE[host] = v
    return v


def _epoch_ms_to_date(v) -> Optional[str]:
    """publish_time 是毫秒 epoch（实测 1713337388481 -> 2024-04-17）。"""
    try:
        import datetime as _dt
        return _dt.datetime.fromtimestamp(int(v) / 1000, _dt.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


# ---------------------------------------------------------------- moka
MOKA_JOB = re.compile(r"#/job/([0-9a-f-]{36})")


def probe_moka(url: str) -> Verdict:
    """moka 的公开 API 路径未找到（2026-11-16 实测 /api/outer/jobs/* 全 404）。
    因此**没有真判据** —— 明确返回 UNKNOWN，禁止凭 HTTP 200 写"在招"。"""
    m = MOKA_JOB.search(url)
    if not m:
        return Verdict(url, "moka", "UNKNOWN", "URL 里找不到 #/job/<uuid>")
    st, body = _get(re.sub(r"#/job/.*$", "", url), {"Accept": "text/html"})
    if st is None:
        return Verdict(url, "moka", "UNKNOWN", "moka 站点不可达")
    jid = m.group(1)
    in_page = jid in body
    return Verdict(url, "moka", "UNKNOWN",
                   f"moka 无公开 detail API（/api/outer/jobs/* 实测 404）；"
                   f"页面 {'含' if in_page else '不含'}该 uuid，两者都不能判活")


# ---------------------------------------------------------------- greenhouse
GH = re.compile(r"greenhouse\.io/(?P<board>[^/]+)/jobs/(?P<id>\d+)")


def probe_greenhouse(url: str) -> Verdict:
    m = GH.search(url)
    if not m:
        return Verdict(url, "greenhouse", "UNKNOWN", "URL 形态不符")
    st, body = _get(f"https://boards-api.greenhouse.io/v1/boards/{m.group('board')}/jobs/{m.group('id')}")
    if st == 404:
        return Verdict(url, "greenhouse", "GONE", "boards-api 返回 404")
    if st != 200:
        return Verdict(url, "greenhouse", "UNKNOWN", f"boards-api HTTP {st}")
    try:
        d = json.loads(body)
    except Exception:
        return Verdict(url, "greenhouse", "UNKNOWN", "boards-api 非 JSON")
    t = d.get("title")
    return Verdict(url, "greenhouse", "ONLINE" if t else "GONE",
                   "boards-api 返回职位对象" if t else "boards-api 200 但无 title", t)


# ---------------------------------------------------------------- wellfound
LDJSON = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
WELLFOUND_ID = re.compile(r"/jobs/(\d+)")


SOFT_404_BYTES = 100_000     # wellfound 的"URL 形态不对"页比真页还大（实测 166KB vs 61KB）


def probe_wellfound(url: str) -> Verdict:
    """wellfound 的判活必须用**带 slug 的完整 URL**。

    实测（2026-11-16，三条对照）：
      /jobs/5079523                                  -> 404 + 166,395 B，无 JobPosting（**软 404**）
      /jobs/5079523-software-engineer-ai-agent-...   -> 200 +  61,358 B，JobPosting + Apply now  ← 真址
      /jobs/9999999-nonexistent-role-for-selftest    -> 404 +  34,922 B，无 JobPosting（**硬 404**）
    所以：id-only URL 的 404 **不是**"岗位下线"，只是"你少给了 slug"。
    判据顺位：200 且含 JobPosting -> ONLINE；404/410 且无 JobPosting 且体积 < SOFT_404_BYTES -> GONE；
    其余（含大体积软 404）-> UNKNOWN，并明确写出"需带 slug"。"""
    has_slug = re.search(r"/jobs/\d+-[a-z0-9-]+", url) is not None
    if not has_slug:
        return Verdict(url, "wellfound", "UNKNOWN",
                       "URL 只有 job id 没有 slug —— wellfound 对 id-only URL 返回软 404（实测 166KB），"
                       "这不是下线信号，必须用 /jobs/<id>-<slug> 完整形态")
    st, body = _get(url, {"Accept": "text/html"})
    if st != 200:
        hard404 = st in (404, 410) and "JobPosting" not in body and len(body) < SOFT_404_BYTES
        if hard404:
            return Verdict(url, "wellfound", "GONE", f"页面 HTTP {st}，无 JobPosting，{len(body)} B")
        return Verdict(url, "wellfound", "UNKNOWN", f"页面 HTTP {st}，{len(body)} B（疑似软 404）")
    for blk in LDJSON.findall(body):
        try:
            d = json.loads(blk)
        except Exception:
            continue
        stack = [d]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if o.get("@type") == "JobPosting" and o.get("title"):
                    has_apply = body.count("Apply now") > 0
                    return Verdict(url, "wellfound", "ONLINE" if has_apply else "UNKNOWN",
                                   f"ld+json JobPosting title={o['title']!r}, "
                                   f"datePosted={o.get('datePosted')}, "
                                   f"'Apply now' {'在' if has_apply else '不在'}页面",
                                   o["title"])
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return Verdict(url, "wellfound", "UNKNOWN", "页面无 JobPosting ld+json")


# ---------------------------------------------------------------- ashby / workable / lever
ASHBY = re.compile(r"ashbyhq\.com/([^/]+)/([0-9a-f-]{36})")
WORKABLE = re.compile(r"apply\.workable\.com/([^/]+)/j/([A-Z0-9]+)")
LEVER = re.compile(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})")


def probe_ashby(url: str) -> Verdict:
    m = ASHBY.search(url)
    if not m:
        return Verdict(url, "ashby", "UNKNOWN", "URL 形态不符")
    st, body = _get(
        f"https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}?includeCompensation=true")
    if st != 200:
        return Verdict(url, "ashby", "UNKNOWN", f"posting-api HTTP {st}")
    try:
        d = json.loads(body)
    except Exception:
        return Verdict(url, "ashby", "UNKNOWN", "posting-api 非 JSON")
    hit = [j for j in (d.get("jobs") or []) if (j.get("id") or "") == m.group(2)]
    if not hit:
        return Verdict(url, "ashby", "GONE", "posting-api 列表里没有该 job id")
    return Verdict(url, "ashby", "ONLINE", "posting-api 列表命中该 job id", hit[0].get("title"))


def probe_workable(url: str) -> Verdict:
    m = WORKABLE.search(url)
    if not m:
        return Verdict(url, "workable", "UNKNOWN", "URL 形态不符")
    st, body = _get(f"https://apply.workable.com/api/v1/widget/accounts/{m.group(1)}?details=true")
    if st != 200:
        return Verdict(url, "workable", "UNKNOWN", f"widget API HTTP {st}")
    return Verdict(url, "workable", "UNKNOWN",
                   "widget API 返回账户级数据，不足以按 job 判活（需 /api/v3/accounts/{}/jobs/{}）")


def probe_lever(url: str) -> Verdict:
    m = LEVER.search(url)
    if not m:
        return Verdict(url, "lever", "UNKNOWN", "URL 形态不符")
    st, body = _get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}")
    if st == 404:
        return Verdict(url, "lever", "GONE", "lever postings API 404")
    if st != 200:
        return Verdict(url, "lever", "UNKNOWN", f"lever postings API HTTP {st}")
    try:
        d = json.loads(body)
    except Exception:
        return Verdict(url, "lever", "UNKNOWN", "lever API 非 JSON")
    return Verdict(url, "lever", "ONLINE" if d.get("text") else "GONE",
                   "postings API 返回职位对象" if d.get("text") else "200 但无 text", d.get("text"))


PROBES = {
    "feishu": probe_feishu, "moka": probe_moka, "greenhouse": probe_greenhouse,
    "wellfound": probe_wellfound, "ashby": probe_ashby, "workable": probe_workable,
    "lever": probe_lever,
}


def probe(url: str) -> Verdict:
    fam = _family(url)
    fn = PROBES.get(fam)
    if fn is None:
        return Verdict(url, fam, "UNKNOWN", "无该 ATS 家族的判据")
    return fn(url)


# ---------------------------------------------------------------- selftest
SELFTEST = [
    # (label, 已知存在的 URL, 同站点的构造假 URL)
    ("feishu", "https://jm196x6sv7.jobs.feishu.cn/index/position/7358727908871801127/detail",
               "https://jm196x6sv7.jobs.feishu.cn/index/position/9999999999999999999/detail"),
    ("ashby", "https://jobs.ashbyhq.com/adaption/23ae2f19-4917-4e6a-8e0d-0e928c531019",
              "https://jobs.ashbyhq.com/adaption/00000000-0000-0000-0000-000000000000"),
    ("greenhouse", "https://job-boards.greenhouse.io/ogroup/jobs/7767882003",
                   "https://job-boards.greenhouse.io/ogroup/jobs/9999999999"),
    # wellfound 必须用带 slug 的完整 URL：id-only 形态返回软 404（166KB），那是"少给 slug"而非下线
    ("wellfound", "https://wellfound.com/jobs/5079523-software-engineer-ai-agent-qa-observability",
                  "https://wellfound.com/jobs/9999999-nonexistent-role-for-selftest"),
]


def selftest(probe_fn=probe) -> bool:
    ok = True
    for fam, live_url, fake_url in SELFTEST:
        a = probe_fn(live_url)
        b = probe_fn(fake_url)
        good = a.state == "ONLINE" and b.state == "GONE"
        print(f"  [{fam}] live={a.state} fake={b.state} -> {'OK' if good else 'FAIL'}")
        if not good:
            print(f"        live evidence: {a.evidence}")
            print(f"        fake evidence: {b.evidence}")
            ok = False
    return ok


def _always_online(url: str) -> Verdict:            # 反证用桩：只会在 --prove-red 里出现
    return Verdict(url, _family(url), "ONLINE", "stub: always online")


def prove_red() -> int:
    print("inject: probe -> always ONLINE")
    if selftest(probe_fn=_always_online):
        print("FAIL: selftest 没有红 —— 说明它判的不是'岗位在不在'")
        return 1
    print("OK: selftest goes red under injected always-ONLINE probe")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--prove-red", action="store_true")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--file", help="JSON 文件，元素含 url 字段或就是 URL 字符串")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    if a.prove_red:
        return prove_red()
    if a.selftest:
        ok = selftest()
        print("selftest: " + ("OK" if ok else "FAIL"))
        return 0 if ok else 1

    urls = list(a.url)
    if a.file:
        raw = json.load(open(a.file))
        for row in raw:
            urls.append(row if isinstance(row, str) else row.get("url"))
    urls = [u for u in urls if u]
    if not urls:
        ap.print_help()
        return 2

    out: List[Dict[str, Any]] = []
    for u in urls:
        v = probe(u)
        out.append(asdict(v))
        print(f"{v.state:8s} {v.family:11s} {(v.company or '-')[:16]:18s} "
              f"{(v.title or '-')[:34]:36s} {v.published or '-':12s} {v.evidence}")
    if a.out:
        json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
        print(f"\nwritten: {a.out} ({len(out)} rows)")
    bad = [r for r in out if r["state"] == "UNKNOWN"]
    if bad:
        print(f"\n{len(bad)} 条 UNKNOWN —— 报告里不许写成「仍在招」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
