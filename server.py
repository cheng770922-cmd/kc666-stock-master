from __future__ import annotations

import datetime as dt
import concurrent.futures
import html
import http.cookiejar
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
UA = "Mozilla/5.0 KC666/2.0"
CACHE = {"time": 0, "data": None}


def get_bytes(url, data=None, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=35) as res:
        return res.read()


def get_json(url, data=None, headers=None):
    return json.loads(get_bytes(url, data, headers).decode("utf-8"))


def number(value):
    try:
        return float(str(value).replace(",", "").replace("--", ""))
    except (ValueError, TypeError):
        return 0.0


def latest_twse():
    day = dt.date.today()
    for _ in range(12):
        key = day.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={key}&type=ALLBUT0999"
        payload = get_json(url)
        if payload.get("tables"):
            return day, payload
        day -= dt.timedelta(days=1)
    raise RuntimeError("找不到最近交易日資料")


def parse_twse(day, payload):
    table = next(t for t in payload["tables"] if "證券代號" in t.get("fields", []) and "收盤價" in t.get("fields", []))
    fields = table["fields"]
    idx = {name: fields.index(name) for name in ["證券代號", "證券名稱", "成交股數", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"]}
    rows = []
    for r in table["data"]:
        code = r[idx["證券代號"]].strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        close = number(r[idx["收盤價"]])
        diff = number(r[idx["漲跌價差"]])
        sign_text = r[idx["漲跌(+/-)"]]
        if "green" in sign_text or "-" in re.sub("<[^>]+>", "", sign_text):
            diff = -diff
        prev = close - diff
        pct = diff / prev * 100 if prev else 0
        rows.append({
            "code": code, "name": r[idx["證券名稱"]].strip(), "market": "上市",
            "close": close, "change": diff, "pct": pct,
            "open": number(r[idx["開盤價"]]), "high": number(r[idx["最高價"]]), "low": number(r[idx["最低價"]]),
            "volume": int(number(r[idx["成交股數"]]) / 1000)
        })
    taiex_table = payload["tables"][0]
    taiex = next((x for x in taiex_table["data"] if x[0] == "發行量加權股價指數"), None)
    index = {"close": number(taiex[1]), "change": number(taiex[3]), "pct": number(taiex[4])} if taiex else {}
    return rows, index


def parse_tpex(day):
    payload = get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
    roc = f"{day.year - 1911:03d}{day:%m%d}"
    rows = []
    for r in payload:
        code = r.get("SecuritiesCompanyCode", "").strip()
        if r.get("Date") != roc or not re.fullmatch(r"\d{4}", code):
            continue
        close, diff = number(r.get("Close")), number(r.get("Change"))
        prev = close - diff
        rows.append({
            "code": code, "name": r.get("CompanyName", "").strip(), "market": "上櫃",
            "close": close, "change": diff, "pct": diff / prev * 100 if prev else 0,
            "open": number(r.get("Open")), "high": number(r.get("High")), "low": number(r.get("Low")),
            "volume": int(number(r.get("TradingShares")) / 1000)
        })
    return rows


def twse_institutions(day):
    key = day.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={key}&selectType=ALLBUT0999&response=json"
    p = get_json(url)
    f = p.get("fields", [])
    result = {}
    if not f:
        return result
    def ix(text): return next(i for i, name in enumerate(f) if text == name)
    ci, ni = ix("證券代號"), ix("證券名稱")
    fi = ix("外陸資買賣超股數(不含外資自營商)")
    ti = ix("投信買賣超股數")
    di = ix("自營商買賣超股數")
    for r in p["data"]:
        code = r[ci].strip()
        if re.fullmatch(r"\d{4}", code):
            result[code] = {"code": code, "name": r[ni].strip(), "foreign": int(number(r[fi]) / 1000), "trust": int(number(r[ti]) / 1000), "dealer": int(number(r[di]) / 1000)}
    return result


def tpex_institutions(day):
    payload = get_json("https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading")
    roc = f"{day.year - 1911:03d}{day:%m%d}"
    result = {}
    for r in payload:
        code = r.get("SecuritiesCompanyCode", "").strip()
        if r.get("Date") != roc or not re.fullmatch(r"\d{4}", code):
            continue
        result[code] = {
            "code": code, "name": r.get("CompanyName", "").strip(),
            "foreign": int(number(r.get("ForeignInvestorsInclude MainlandAreaInvestors-Difference")) / 1000),
            "trust": int(number(r.get("SecuritiesInvestmentTrustCompanies-Difference")) / 1000),
            "dealer": int(number(r.get("Dealers-Difference")) / 1000)
        }
    return result


def roc_date(day):
    return f"{day.year - 1911:03d}/{day:%m/%d}"


def etf_request(fund_code, day, specific):
    body = json.dumps({"fundCode": fund_code, "date": roc_date(day), "specificDate": specific}).encode()
    page = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    endpoint = "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.open(urllib.request.Request(page, headers={"User-Agent": UA}), timeout=35).read()
    headers = {"User-Agent": UA, "Content-Type": "application/json; charset=utf-8", "Referer": page, "Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"}
    request = urllib.request.Request(endpoint, body, headers, method="POST")
    try:
        raw = opener.open(request, timeout=35).read()
    except urllib.error.HTTPError as exc:
        if exc.code != 307 or not exc.headers.get("Location"):
            raise
        redirect = urllib.parse.urljoin(endpoint, exc.headers["Location"])
        raw = opener.open(urllib.request.Request(redirect, body, headers, method="POST"), timeout=35).read()
    return json.loads(raw.decode("utf-8"))


def holding_map(payload):
    stock = next((x for x in (payload.get("asset") or []) if x.get("AssetCode") == "ST"), {})
    return {x["DetailCode"].strip(): {"code": x["DetailCode"].strip(), "name": x["DetailName"].strip(), "shares": int(number(x["Share"])), "weight": number(x.get("NavRate")), "date": str(x.get("TranDate", ""))[:10]} for x in (stock.get("Details") or [])}


def etf_changes(fund_code, display_code, name, market_day):
    current = holding_map(etf_request(fund_code, dt.date.today(), False))
    previous = holding_map(etf_request(fund_code, market_day, True))
    changes = []
    for code, item in current.items():
        old = previous.get(code)
        delta = item["shares"] - (old["shares"] if old else 0)
        if not old:
            kind = "新增"
        elif delta > 0:
            kind = "加碼"
        elif delta < 0:
            kind = "減碼"
        else:
            continue
        changes.append({**item, "kind": kind, "delta": delta})
    for code, item in previous.items():
        if code not in current:
            changes.append({**item, "kind": "剔除", "delta": -item["shares"]})
    order = {"新增": 0, "剔除": 1, "加碼": 2, "減碼": 3}
    changes.sort(key=lambda x: (order[x["kind"]], -abs(x["delta"])))
    return {"code": display_code, "name": name, "asOf": max((x["date"] for x in current.values()), default=str(market_day)), "changes": changes,
            "counts": {k: sum(1 for x in changes if x["kind"] == k) for k in ["新增", "加碼", "減碼", "剔除"]}}


def market_data(force=False):
    if not force and CACHE["data"] and time.time() - CACHE["time"] < 300:
        return CACHE["data"]
    day, raw = latest_twse()
    listed, index = parse_twse(day, raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        otc_job = pool.submit(parse_tpex, day)
        twse_inst_job = pool.submit(twse_institutions, day)
        tpex_inst_job = pool.submit(tpex_institutions, day)
        etf1_job = pool.submit(etf_changes, "49YTW", "00981A", "主動統一台股增長", day)
        etf2_job = pool.submit(etf_changes, "63YTW", "00403A", "主動統一升級50", day)
        otc = otc_job.result()
        inst = twse_inst_job.result()
        inst.update(tpex_inst_job.result())
        etfs = [etf1_job.result(), etf2_job.result()]
    stocks = listed + otc
    consensus = []
    by_code = {x["code"]: x for x in stocks}
    for code, x in inst.items():
        if x["foreign"] > 0 and x["trust"] > 0 and x["dealer"] > 0 and code in by_code:
            consensus.append({**x, "market": by_code[code]["market"], "close": by_code[code]["close"], "pct": by_code[code]["pct"], "total": x["foreign"] + x["trust"] + x["dealer"]})
    consensus.sort(key=lambda x: x["total"], reverse=True)
    active = [x for x in stocks if x["volume"] > 0]
    data = {
        "asOf": day.isoformat(), "asOfLabel": f"{day.year} 年 {day.month} 月 {day.day} 日盤後",
        "index": index,
        "breadth": {"up": sum(x["change"] > 0 for x in active), "down": sum(x["change"] < 0 for x in active), "flat": sum(x["change"] == 0 for x in active), "total": len(active)},
        "strong": sorted(active, key=lambda x: (x["pct"], x["volume"]), reverse=True)[:50],
        "weak": sorted(active, key=lambda x: (x["pct"], -x["volume"]))[:50],
        "institutions": consensus, "stocks": stocks, "institutionMap": inst,
        "etfs": etfs,
        "sources": ["臺灣證券交易所 MI_INDEX / T86", "證券櫃檯買賣中心 OpenAPI", "統一投信 PCF"]
    }
    CACHE.update({"time": time.time(), "data": data})
    return data


def stock_detail(code):
    market = market_data()
    base = next((x for x in market["stocks"] if x["code"] == code), None)
    if not base:
        raise KeyError(code)
    suffix = ".TW" if base["market"] == "上市" else ".TWO"
    end = int(time.time()) + 86400
    start = end - 86400 * 280
    chart = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{suffix}?period1={start}&period2={end}&interval=1d&events=history")
    result = chart["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    candles = []
    for i, stamp in enumerate(result.get("timestamp", [])):
        vals = [quote[k][i] for k in ["open", "high", "low", "close", "volume"]]
        if all(v is not None for v in vals):
            candles.append({"date": dt.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d"), "open": vals[0], "high": vals[1], "low": vals[2], "close": vals[3], "volume": vals[4]})
    query = urllib.parse.quote(f'{code} {base["name"]} when:14d')
    rss = get_bytes(f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    news = []
    for item in ET.fromstring(rss).findall("./channel/item")[:10]:
        title = html.unescape(item.findtext("title", ""))
        news.append({"title": title, "link": item.findtext("link", "#"), "date": item.findtext("pubDate", ""), "source": title.rsplit(" - ", 1)[-1] if " - " in title else "Google 新聞"})
    return {"stock": base, "candles": candles[-120:], "chips": market["institutionMap"].get(code, {"foreign": 0, "trust": 0, "dealer": 0}), "news": news, "asOf": market["asOf"]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "https://cheng770922-cmd.github.io")
        self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "https://cheng770922-cmd.github.io")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/market":
                data = dict(market_data())
                data.pop("stocks", None); data.pop("institutionMap", None)
                return self.json_response(data)
            if parsed.path == "/api/search":
                q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip().lower()
                result = [x for x in market_data()["stocks"] if q and (q in x["code"].lower() or q in x["name"].lower())][:12]
                return self.json_response(result)
            if parsed.path == "/api/stock":
                code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0]
                return self.json_response(stock_detail(code))
        except Exception as exc:
            return self.json_response({"error": str(exc)}, 500)
        return super().do_GET()


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "4173"))
    print(f"KC 666 running at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
