#!/usr/bin/env python3
"""
service_value_probe.py — 给一批 “IP:端口 + 服务类型” 打价值分

解决的问题
    扫描输出只有「开了什么端口」，看不出「里面有没有东西」。
    判定一个端点值不值得跟进，最省事的三个指标是：
      Redis      → DBSIZE（有多少键）
      ES         → _cat/indices 的文档总数（有多少条数据）
      Memcached  → stats items（有多少 slab 里有 item）
      Docker     → /containers/json（有多少容器、什么镜像）

用法
    python3 service_value_probe.py hits.jsonl -o valuable.jsonl

    输入每行：{"ip": "...", "port": 6379, "svc": "REDIS"}
    输出每行：原字段 + {"score": N, "detail": "..."}
              score = -1 表示连接失败/超时；>0 表示可量化的数据规模

注意
    - 只做只读探测（DBSIZE / _cat / stats），不写、不删除
    - 并发 60，单点超时 4~8 秒，避免把对方打挂
"""

import argparse
import json
import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

lock = threading.Lock()


# ---------------------------------------------------------------- 各服务探测

def _sock(ip, port, timeout=4):
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((ip, port))
    return s


def probe_redis(ip, port):
    s = _sock(ip, port)
    def cmd(*args):
        buf = ("*%d\r\n" % len(args)).encode()
        for a in args:
            buf += ("$%d\r\n%s\r\n" % (len(a), a)).encode()
        s.sendall(buf)
        time.sleep(0.25)
        try:
            return s.recv(65535).decode("utf8", "ignore")
        except Exception:
            return ""
    info = cmd("INFO", "keyspace")
    keys = None
    if "db0" in info:
        import re
        m = re.search(r"db\d+:keys=(\d+)", info)
        if m:
            keys = int(m.group(1))
    if keys is None:
        d = cmd("DBSIZE")
        for line in d.split("\r\n"):
            if line.strip().isdigit():
                keys = int(line)
                break
    cfg = cmd("CONFIG", "GET", "dir")
    s.close()
    return keys, cfg[:120].replace("\r\n", " ")


def probe_es(ip, port):
    try:
        info = json.loads(urllib.request.urlopen("http://%s:%d/" % (ip, port), timeout=5).read(4096))
        ver = info.get("version", {}).get("number", "?")
        cluster = info.get("cluster_name", "")
        try:
            idx = json.loads(urllib.request.urlopen(
                "http://%s:%d/_cat/indices?h=index,docs.count&format=json" % (ip, port), timeout=7).read(400000))
            docs = sum(int(i.get("docs.count") or 0) for i in idx
                       if str(i.get("docs.count", "")).isdigit())
            return docs, "v%s cluster=%s indices=%d" % (ver, cluster, len(idx))
        except Exception:
            return 0, "v%s cluster=%s (indices 无权限)" % (ver, cluster)
    except Exception as e:
        return -1, "err %s" % e


def probe_memcached(ip, port):
    s = _sock(ip, port)
    s.sendall(b"stats items\r\n")
    time.sleep(0.3)
    try:
        d = s.recv(20000).decode("utf8", "ignore")
    except Exception:
        d = ""
    s.close()
    return d.count("STAT items:"), d[:100].replace("\r\n", " ")


def probe_docker(ip, port):
    try:
        c = json.loads(urllib.request.urlopen(
            "http://%s:%d/containers/json?all=1" % (ip, port), timeout=6).read(400000))
        return len(c), "containers=%d" % len(c)
    except Exception as e:
        return -1, "err %s" % e


PROBES = {"REDIS": probe_redis, "ES": probe_es, "MEMCACHED": probe_memcached, "DOCKER": probe_docker}


def work(row, out_path):
    svc = (row.get("svc") or "").upper()
    fn = PROBES.get(svc)
    if not fn:
        return None
    ip, port = row["ip"], int(row["port"])
    try:
        score, detail = fn(ip, port)
    except Exception as e:
        return None
    rec = dict(row)
    rec["score"] = score
    rec["detail"] = detail
    with lock:
        with open(out_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="valuable.jsonl")
    ap.add_argument("--workers", type=int, default=60)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.input) if l.strip()]
    targets = [r for r in rows if (r.get("svc") or "").upper() in PROBES]
    print("input rows %d, probe targets %d" % (len(rows), len(targets)))
    open(args.out, "w").close()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(lambda r: work(r, args.out), targets))

    res = [json.loads(l) for l in open(args.out)]
    pos = [r for r in res if isinstance(r.get("score"), int) and r["score"] > 0]
    print("responded %d, with data %d" % (len(res), len(pos)))
    for r in sorted(pos, key=lambda x: -x["score"])[:10]:
        print("  %-16s %-6d %-10s score=%-10d %s"
              % (r["ip"], r["port"], r["svc"], r["score"], (r.get("detail") or "")[:60]))


if __name__ == "__main__":
    main()
