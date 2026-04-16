#!/usr/bin/env python3
"""Collect frontier AI intelligence for Hermes daily digest (v3).

Core rules:
- One-main-many-aux sources (X primary + multi-source auxiliary).
- Strict timestamp extraction + ISO normalization.
- Reverse verification to find earliest public/source date.
- Hard filter by the earliest verified date within last 48 hours.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import math
import tempfile
import os
import re
import subprocess
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode, urlparse

STATUS_RE = re.compile(r"https?://x\.com/([^/]+)/status/(\d+)")
SNOWFLAKE_EPOCH_MS = 1288834974657
BJT = dt.timezone(dt.timedelta(hours=8))
UTC = dt.timezone.utc
MAX_AGE_HOURS = 48.0
MAX_REVERSE_CHECK = 32
LEARNING_HISTORY_MAX = 40
LEARNING_STATE_PATH = Path.home() / ".hermes" / "cron" / "state" / "x_ai_digest_learning.json"

TRUSTED_TIME_DOMAINS = {
    "arxiv.org",
    "github.com",
    "api.github.com",
    "openai.com",
    "anthropic.com",
    "blog.google",
    "deepmind.google",
    "aws.amazon.com",
    "cloud.google.com",
    "microsoft.com",
    "nvidia.com",
    "techcrunch.com",
    "venturebeat.com",
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "theverge.com",
    "technologyreview.com",
    "sifted.eu",
    "ycombinator.com",
    "huggingface.co",
    "paperswithcode.com",
}

TRUSTED_TIME_LABEL_PREFIXES = (
    "github:",
    "paper:",
    "hn:",
    "reddit:",
    "rss:",
    "ddgs:news:",
    "twikit:",
    "twscrape:",
)

AI_RELEVANCE_KEYS = [
    "ai",
    "artificial intelligence",
    "llm",
    "language model",
    "gpt",
    "claude",
    "gemini",
    "agent",
    "multimodal",
    "inference",
    "fine-tuning",
    "finetuning",
    "reasoning",
    "openai",
    "anthropic",
    "deepmind",
    "xai",
    "mistral",
    "nvidia",
    "huggingface",
    "arxiv",
    "transformer",
    "diffusion",
    "prompt",
    "foundation model",
]

X_ACCOUNT_QUERIES = [
    ("OpenAI", "site:x.com/OpenAI/status OpenAI GPT ChatGPT agent"),
    ("Anthropic", "site:x.com/AnthropicAI/status Claude Anthropic"),
    ("GoogleDeepMind", "site:x.com/GoogleDeepMind/status Gemini DeepMind AI"),
    ("xAI", "site:x.com/xai/status Grok xAI"),
    ("Mistral", "site:x.com/MistralAI/status Mistral AI model"),
    ("MetaAI", "site:x.com/AIatMeta/status Meta AI"),
    ("NVIDIA", "site:x.com/nvidia/status AI model agent"),
    ("AndrewNg", "site:x.com/AndrewYNg/status AI"),
]

FALLBACK_HANDLES = [
    ("OpenAI", "OpenAI"),
    ("Anthropic", "AnthropicAI"),
    ("GoogleDeepMind", "GoogleDeepMind"),
    ("xAI", "xai"),
    ("Mistral", "MistralAI"),
    ("MetaAI", "AIatMeta"),
]

AUX_TAVILY_QUERIES = [
    (
        "论文热点",
        "breakthrough AI paper in last 2 days site:arxiv.org OR site:huggingface.co/papers OR site:paperswithcode.com",
    ),
    (
        "大佬发言",
        "AI founder investor said on X today site:x.com/status OpenAI Anthropic xAI",
    ),
    (
        "创业融资",
        "AI startup funding raised seed Series A announced in last 2 days site:techcrunch.com OR site:venturebeat.com OR site:theinformation.com",
    ),
    (
        "爆火产品",
        "new viral AI product launched in last 2 days site:futuretools.io OR site:theresanaiforthat.com OR site:producthunt.com",
    ),
    (
        "开源趋势",
        "new trending open-source AI agent project in last 2 days site:github.com",
    ),
    (
        "前沿公司",
        "frontier AI company announcement in last 2 days OpenAI Anthropic DeepMind xAI Mistral",
    ),
    (
        "大佬推文",
        "site:x.com/sama/status OR site:x.com/karpathy/status OR site:x.com/ilyasut/status OR site:x.com/gdb/status AI",
    ),
    (
        "创业并购",
        "AI startup acquired OR partnership announced in last 2 days site:reuters.com OR site:bloomberg.com OR site:ft.com",
    ),
    (
        "海外监管与市场",
        "AI regulation policy antitrust export control announced in last 2 days US EU UK site:reuters.com OR site:ft.com OR site:wsj.com",
    ),
    (
        "云厂商与芯片",
        "NVIDIA AMD Microsoft Google Amazon AI infrastructure announcement in last 2 days site:nvidia.com OR site:microsoft.com OR site:cloud.google.com OR site:aws.amazon.com",
    ),
    (
        "前沿创业生态",
        "YC AI startup launch demo day in last 2 days site:ycombinator.com OR site:techcrunch.com OR site:sifted.eu",
    ),
    (
        "科研与产业结合",
        "AI research breakthrough industry deployment announced in last 2 days site:nature.com OR site:science.org OR site:arxiv.org",
    ),
    (
        "海外开发者生态",
        "new AI developer tool release in last 2 days site:github.com OR site:huggingface.co OR site:vercel.com/blog",
    ),
]

DDGS_NEWS_QUERIES = [
    "OpenAI Anthropic Google DeepMind xAI Mistral announcement",
    "AI startup raised seed series A funding today",
    "NVIDIA Microsoft Google Amazon AI infrastructure release",
    "AI regulation EU US UK policy update",
    "AI founder CTO chief scientist interview statement",
]

DDGS_TEXT_QUERIES = [
    "site:arxiv.org cs.AI OR cs.LG new paper",
    "site:github.com AI agent framework trending",
    "AI startup launch YC demo day",
    "enterprise AI product launch OpenAI Anthropic",
]


def _build_queries() -> list[tuple[str, str]]:
    return list(X_ACCOUNT_QUERIES[:7]) + list(AUX_TAVILY_QUERIES)


def _load_tavily_key() -> str:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if key:
        return key
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if line.startswith("TAVILY_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _load_env_value(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if val:
        return val
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return ""


def _safe_curl(cmd: list[str], timeout_flag: str = "20") -> subprocess.CompletedProcess[str]:
    clean_env = os.environ.copy()
    for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        clean_env.pop(k, None)
    full = ["curl", "-sS", "-L", "--retry", "2", "--retry-delay", "1", "--max-time", timeout_flag, *cmd]
    return subprocess.run(full, capture_output=True, text=True, check=False, env=clean_env)


def _format_bj(ts: dt.datetime) -> tuple[str, str]:
    bj = ts.astimezone(BJT)
    return bj.isoformat(timespec="seconds"), bj.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_item_time(item: dict[str, Any], event_dt: dt.datetime | None) -> bool:
    if not event_dt:
        return False
    iso_s, human_s = _format_bj(event_dt)
    item["event_time_iso"] = iso_s
    item["beijing_time"] = human_s
    return True


def _parse_any_datetime(raw: Any) -> dt.datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    fixed = s.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(fixed)
        return d if d.tzinfo else d.replace(tzinfo=BJT)
    except Exception:
        pass

    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for p in patterns:
        try:
            d = dt.datetime.strptime(s, p)
            if "H" in p:
                return d.replace(tzinfo=BJT)
            return d.replace(hour=0, minute=0, second=0, tzinfo=BJT)
        except Exception:
            continue

    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=BJT)
    except Exception:
        return None


def _extract_time_from_text(*texts: str) -> dt.datetime | None:
    full_patterns = [
        r"(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?)",
        r"(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?)",
        r"(20\d{2}/\d{2}/\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)",
    ]
    for text in texts:
        if not text:
            continue
        for pat in full_patterns:
            m = re.search(pat, text)
            if m:
                d = _parse_any_datetime(m.group(1))
                if d:
                    return d

    date_only = r"(20\d{2}[-/]\d{2}[-/]\d{2})"
    for text in texts:
        if not text:
            continue
        m = re.search(date_only, text)
        if m:
            d = _parse_any_datetime(m.group(1))
            if d:
                return d
    return None


def _snowflake_to_dt(status_id: str) -> dt.datetime | None:
    try:
        ts_ms = (int(status_id) >> 22) + SNOWFLAKE_EPOCH_MS
        return dt.datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
    except Exception:
        return None


def _call_tavily(api_key: str, query: str, max_results: int = 6, days: int = 2) -> dict[str, Any]:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
        "days": days,
    }
    proc = _safe_curl(
        [
            "-X",
            "POST",
            "https://api.tavily.com/search",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload, ensure_ascii=False),
        ],
        timeout_flag="18",
    )
    if proc.returncode != 0:
        return {"error": f"curl_exit_{proc.returncode}", "stderr": proc.stderr.strip()}
    try:
        return json.loads(proc.stdout or "{}")
    except Exception:
        return {"error": "invalid_json", "raw": (proc.stdout or "")[:400]}


def _call_ddgs_free_search() -> tuple[list[dict[str, Any]], list[dict[str, str]], bool]:
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    ddgs_path = subprocess.run(["bash", "-lc", "command -v ddgs"], capture_output=True, text=True, check=False).stdout.strip()
    if not ddgs_path:
        return out, [{"query_label": "ddgs", "error": "ddgs_cli_missing"}], False

    def _run_ddgs(mode: str, query: str, max_results: int, timelimit: str = "d") -> list[dict[str, Any]]:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="ddgs_", suffix=".json")
        os.close(tmp_fd)
        try:
            cmd = [
                ddgs_path,
                mode,
                "-q",
                query,
                "-m",
                str(max_results),
                "-t",
                timelimit,
                "-o",
                tmp_path,
                "-nc",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=20)
            if proc.returncode != 0:
                errors.append({"query_label": f"ddgs:{mode}:{query[:40]}", "error": f"exit_{proc.returncode}"})
                return []
            try:
                rows = json.loads(Path(tmp_path).read_text(encoding="utf-8", errors="ignore") or "[]")
                if not isinstance(rows, list):
                    return []
                return rows
            except Exception:
                errors.append({"query_label": f"ddgs:{mode}:{query[:40]}", "error": "invalid_json"})
                return []
        except subprocess.TimeoutExpired:
            errors.append({"query_label": f"ddgs:{mode}:{query[:40]}", "error": "timeout"})
            return []
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    for q in DDGS_NEWS_QUERIES:
        rows = _run_ddgs("news", q, max_results=8, timelimit="d")
        for row in rows:
            title = re.sub(r"\s+", " ", str(row.get("title") or "").strip())
            url = str(row.get("url") or row.get("href") or "").strip()
            if not title or not url:
                continue
            item = {
                "url": url,
                "source": str(row.get("source") or "ddgs-news"),
                "source_type": "web",
                "source_layer": "aux",
                "title": title,
                "content": re.sub(r"\s+", " ", str(row.get("body") or "").strip())[:600],
                "score": 0.61,
                "query_label": f"ddgs:news:{q}",
            }
            event_dt = _parse_any_datetime(row.get("date")) or _extract_time_from_text(title, str(row.get("body") or ""), url)
            if _normalize_item_time(item, event_dt):
                item["category"] = _infer_category(item)
                out.append(item)

    for q in DDGS_TEXT_QUERIES:
        rows = _run_ddgs("text", q, max_results=8, timelimit="d")
        for row in rows:
            title = re.sub(r"\s+", " ", str(row.get("title") or "").strip())
            url = str(row.get("url") or row.get("href") or "").strip()
            if not title or not url:
                continue
            item = {
                "url": url,
                "source": "ddgs-text",
                "source_type": "web",
                "source_layer": "aux",
                "title": title,
                "content": re.sub(r"\s+", " ", str(row.get("body") or "").strip())[:600],
                "score": 0.56,
                "query_label": f"ddgs:text:{q}",
            }
            event_dt = _extract_time_from_text(title, str(row.get("body") or ""), url)
            if _normalize_item_time(item, event_dt):
                item["category"] = _infer_category(item)
                out.append(item)

    return out, errors, True


def _obj_get(obj: Any, *names: str, default: Any = "") -> Any:
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj.get(n)
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def _infer_category(item: dict[str, Any]) -> str:
    src_type = str(item.get("source_type") or "")
    ql = str(item.get("query_label") or "").lower()
    txt = f"{item.get('title', '')} {item.get('content', '')}".lower()

    if src_type == "paper" or "arxiv" in txt or "paper" in ql or "论文" in ql:
        return "论文"
    if src_type == "github" or "open-source" in ql or "开源" in ql or "github" in txt:
        return "开源项目"
    if (
        "融资" in ql
        or "startup" in txt
        or "series a" in txt
        or "series b" in txt
        or "series c" in txt
        or "seed" in txt
        or "raised" in txt
        or "funding" in txt
        or "valuation" in txt
        or "acquire" in txt
    ):
        return "创业融资"
    if src_type == "x" or "发言" in ql or "said" in txt:
        return "大佬发言"
    if "tool" in txt or "product" in txt or "工具" in ql:
        return "AI产品"
    return "行业动态"


def _pick_items(resp: dict[str, Any], label: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in resp.get("results", []) or []:
        url = str(row.get("url") or "").strip()
        title = re.sub(r"\s+", " ", str(row.get("title") or "").strip())
        content = re.sub(r"\s+", " ", str(row.get("content") or "").strip())

        item: dict[str, Any] = {
            "url": url,
            "title": title,
            "content": content,
            "score": float(row.get("score") or 0),
            "query_label": label,
            "source_type": "web",
            "source": str(row.get("source") or "web"),
            "source_layer": "aux",
        }

        m = STATUS_RE.match(url)
        if m:
            user, sid = m.group(1), m.group(2)
            item["source"] = user
            item["status_id"] = sid
            item["source_type"] = "x"
            item["source_layer"] = "main"
            event_dt = _snowflake_to_dt(sid)
        else:
            event_dt = _parse_any_datetime(
                row.get("published_date")
                or row.get("published")
                or row.get("date")
                or row.get("updated_at")
                or row.get("created_at")
            )
            if not event_dt:
                event_dt = _extract_time_from_text(title, content, url)

        if not _normalize_item_time(item, event_dt):
            continue

        item["category"] = _infer_category(item)
        out.append(item)
    return out


async def _primary_from_twikit() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        import twikit  # type: ignore
    except Exception as e:
        return [], [{"query_label": "twikit", "error": f"import_failed:{type(e).__name__}"}]

    username = _load_env_value("TWIKIT_USERNAME")
    email = _load_env_value("TWIKIT_EMAIL")
    password = _load_env_value("TWIKIT_PASSWORD")
    totp_secret = _load_env_value("TWIKIT_TOTP_SECRET") or None
    cookies_path = _load_env_value("TWIKIT_COOKIES_PATH") or str(Path.home() / ".hermes" / "cache" / "twikit_cookies.json")
    Path(cookies_path).parent.mkdir(parents=True, exist_ok=True)

    twikit_proxy = _load_env_value("TWIKIT_PROXY") or _load_env_value("TWSC_PROXY") or None
    client = twikit.Client(language="en-US", proxy=twikit_proxy)
    try:
        if Path(cookies_path).exists():
            client.load_cookies(cookies_path)
        elif username and password:
            auth1 = username or email
            auth2 = email if email and email != auth1 else None
            await client.login(auth_info_1=auth1, auth_info_2=auth2, password=password, totp_secret=totp_secret)
            client.save_cookies(cookies_path)
        else:
            return [], [{"query_label": "twikit", "error": "not_configured"}]
    except Exception as e:
        return [], [{"query_label": "twikit", "error": f"auth_failed:{type(e).__name__}"}]

    for label, handle in FALLBACK_HANDLES:
        try:
            user = await client.get_user_by_screen_name(handle)
            uid = str(_obj_get(user, "id", "rest_id", default="")).strip()
            if not uid:
                errors.append({"query_label": f"twikit:{label}", "error": "missing_user_id"})
                continue
            tweets = await client.get_user_tweets(uid, "Tweets", count=9)
            for tw in list(tweets)[:7]:
                sid = str(_obj_get(tw, "id", "rest_id", "id_str", default="")).strip()
                if not sid:
                    continue
                text = re.sub(r"\s+", " ", str(_obj_get(tw, "full_text", "text", default="")).strip())
                event_dt = _snowflake_to_dt(sid)
                item = {
                    "url": f"https://x.com/{handle}/status/{sid}",
                    "source": handle,
                    "source_type": "x",
                    "source_layer": "main",
                    "status_id": sid,
                    "title": text[:160],
                    "content": text,
                    "score": 0.74,
                    "query_label": f"twikit:{label}",
                }
                if _normalize_item_time(item, event_dt):
                    item["category"] = _infer_category(item)
                    items.append(item)
        except Exception as e:
            errors.append({"query_label": f"twikit:{label}", "error": type(e).__name__})
    return items, errors


async def _primary_from_twscrape() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        from twscrape import API, AccountsPool, gather  # type: ignore
    except Exception as e:
        return [], [{"query_label": "twscrape", "error": f"import_failed:{type(e).__name__}"}]

    db_path = _load_env_value("TWSC_DB_PATH") or str(Path.home() / ".hermes" / "cache" / "twscrape_accounts.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    pool = AccountsPool(db_path)

    sc_user = _load_env_value("TWSC_USERNAME")
    sc_pass = _load_env_value("TWSC_PASSWORD")
    sc_email = _load_env_value("TWSC_EMAIL")
    sc_email_pass = _load_env_value("TWSC_EMAIL_PASSWORD")
    sc_mfa = _load_env_value("TWSC_MFA_CODE") or None
    sc_proxy = _load_env_value("TWSC_PROXY") or _load_env_value("TWIKIT_PROXY") or None

    try:
        if sc_user and sc_pass and sc_email and sc_email_pass:
            existing = await pool.get_account(sc_user)
            if not existing:
                await pool.add_account(sc_user, sc_pass, sc_email, sc_email_pass, proxy=sc_proxy, mfa_code=sc_mfa)
            await pool.login_all([sc_user])
    except Exception as e:
        errors.append({"query_label": "twscrape", "error": f"account_setup_failed:{type(e).__name__}"})

    try:
        infos = await pool.accounts_info()
        if not infos:
            return [], errors + [{"query_label": "twscrape", "error": "not_configured"}]
    except Exception:
        return [], errors + [{"query_label": "twscrape", "error": "pool_unavailable"}]

    api = API(pool=pool, proxy=sc_proxy)
    for label, handle in FALLBACK_HANDLES:
        try:
            u = await api.user_by_login(handle)
            uid = int(_obj_get(u, "id", "user_id", default=0) or 0)
            if not uid:
                errors.append({"query_label": f"twscrape:{label}", "error": "missing_user_id"})
                continue
            tweets = await gather(api.user_tweets(uid, limit=9))
            for tw in tweets[:7]:
                sid = str(_obj_get(tw, "id", "id_str", default="")).strip()
                if not sid:
                    continue
                text = re.sub(r"\s+", " ", str(_obj_get(tw, "rawContent", "content", "text", default="")).strip())
                src = str(_obj_get(_obj_get(tw, "user", default={}), "username", "login", default=handle)).strip() or handle
                event_dt = _snowflake_to_dt(sid)
                item = {
                    "url": f"https://x.com/{src}/status/{sid}",
                    "source": src,
                    "source_type": "x",
                    "source_layer": "main",
                    "status_id": sid,
                    "title": text[:160],
                    "content": text,
                    "score": 0.70,
                    "query_label": f"twscrape:{label}",
                }
                if _normalize_item_time(item, event_dt):
                    item["category"] = _infer_category(item)
                    items.append(item)
        except Exception as e:
            errors.append({"query_label": f"twscrape:{label}", "error": type(e).__name__})
    return items, errors


def _call_github_search() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    since = (dt.datetime.now(tz=UTC) - dt.timedelta(days=4)).date().isoformat()
    q = f"(topic:ai OR topic:llm OR topic:agent OR topic:multimodal) pushed:>={since} stars:>10"
    qs = urlencode({"q": q, "sort": "updated", "order": "desc", "per_page": 40})
    url = f"https://api.github.com/search/repositories?{qs}"

    headers = [
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
        "-H",
        "User-Agent: hermes-x-ai-digest",
    ]
    token = _load_env_value("GITHUB_TOKEN")
    if token:
        headers.extend(["-H", f"Authorization: Bearer {token}"])

    proc = _safe_curl([*headers, url], timeout_flag="22")
    if proc.returncode != 0:
        return [], [{"query_label": "github", "error": f"curl_exit_{proc.returncode}"}]

    try:
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return [], [{"query_label": "github", "error": "invalid_json"}]

    if isinstance(data, dict) and data.get("message"):
        return [], [{"query_label": "github", "error": str(data.get("message"))[:120]}]

    out: list[dict[str, Any]] = []
    for repo in (data.get("items") or [])[:24]:
        pushed = _parse_any_datetime(repo.get("pushed_at"))
        created = _parse_any_datetime(repo.get("created_at"))
        event_dt = pushed or created
        item = {
            "url": str(repo.get("html_url") or "").strip(),
            "source": str(repo.get("full_name") or "github"),
            "source_type": "github",
            "source_layer": "aux",
            "title": str(repo.get("full_name") or "").strip(),
            "content": re.sub(r"\s+", " ", str(repo.get("description") or "").strip()),
            "score": min(1.0, math.log1p(float(repo.get("stargazers_count") or 0)) / 8.0),
            "query_label": "github:hot_new",
            "stars": int(repo.get("stargazers_count") or 0),
            "forks": int(repo.get("forks_count") or 0),
            "language": str(repo.get("language") or ""),
        }
        if _normalize_item_time(item, event_dt):
            item["category"] = _infer_category(item)
            out.append(item)
    return out, []


def _strip_xml_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _domain_of(url: str) -> str:
    try:
        netloc = (urlparse(url or "").netloc or "").lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _is_trusted_time_domain(domain: str) -> bool:
    d = (domain or "").lower().strip()
    if not d:
        return False
    if d in TRUSTED_TIME_DOMAINS:
        return True
    return any(d.endswith("." + t) for t in TRUSTED_TIME_DOMAINS)


def _safe_round(v: float) -> float:
    return round(float(v), 3)


def _load_learning_state() -> dict[str, Any]:
    if not LEARNING_STATE_PATH.exists():
        return {"history": []}
    try:
        data = json.loads(LEARNING_STATE_PATH.read_text(encoding="utf-8", errors="ignore") or "{}")
        if isinstance(data, dict) and isinstance(data.get("history"), list):
            return data
    except Exception:
        pass
    return {"history": []}


def _save_learning_state(state: dict[str, Any]) -> None:
    LEARNING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_learning_report(
    generated_iso: str,
    filter_stats: dict[str, Any],
    top: list[dict[str, Any]],
    modules: dict[str, list[dict[str, Any]]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    state = _load_learning_state()
    history = list(state.get("history") or [])

    module_coverage = sum(1 for _, v in modules.items() if isinstance(v, list) and len(v) > 0)
    returned = len(top)
    raw = int(filter_stats.get("raw_collected", 0) or 0)
    err_count = len(errors)
    dropped_old = int(filter_stats.get("dropped_outside_48h", 0) or 0)
    dropped_irrelevant = int(filter_stats.get("dropped_irrelevant", 0) or 0)
    after_filter = int(filter_stats.get("after_filter", returned) or returned)

    efficiency = (returned / raw) if raw else 0.0
    freshness_keep = (after_filter / raw) if raw else 0.0

    current = {
        "ts": generated_iso,
        "raw_collected": raw,
        "after_filter": after_filter,
        "returned": returned,
        "module_coverage": module_coverage,
        "errors": err_count,
        "dropped_outside_48h": dropped_old,
        "dropped_irrelevant": dropped_irrelevant,
        "efficiency": _safe_round(efficiency),
        "freshness_keep_ratio": _safe_round(freshness_keep),
    }

    recent = [h for h in history if isinstance(h, dict)][-7:]
    def _avg(key: str) -> float:
        vals = [float(h.get(key) or 0.0) for h in recent]
        return (sum(vals) / len(vals)) if vals else 0.0

    baseline = {
        "returned_avg_7": _safe_round(_avg("returned")),
        "module_coverage_avg_7": _safe_round(_avg("module_coverage")),
        "errors_avg_7": _safe_round(_avg("errors")),
        "efficiency_avg_7": _safe_round(_avg("efficiency")),
    }

    delta = {
        "returned_vs_avg7": _safe_round(current["returned"] - baseline["returned_avg_7"]),
        "coverage_vs_avg7": _safe_round(current["module_coverage"] - baseline["module_coverage_avg_7"]),
        "errors_vs_avg7": _safe_round(current["errors"] - baseline["errors_avg_7"]),
        "efficiency_vs_avg7": _safe_round(current["efficiency"] - baseline["efficiency_avg_7"]),
    }

    progress_signals: list[str] = []
    if delta["returned_vs_avg7"] > 0:
        progress_signals.append("有效条目数高于近7次均值")
    if delta["coverage_vs_avg7"] > 0:
        progress_signals.append("模块覆盖度高于近7次均值")
    if delta["errors_vs_avg7"] < 0:
        progress_signals.append("错误数量低于近7次均值")
    if delta["efficiency_vs_avg7"] > 0:
        progress_signals.append("筛选效率高于近7次均值")

    next_actions: list[str] = []
    if module_coverage < 4:
        next_actions.append("提高人物/创业信号召回（扩充高管与创业查询词）")
    if dropped_old > max(20, raw * 0.3):
        next_actions.append("增加更高时效源权重（优先news/rss/github pushed）")
    if err_count > 0:
        next_actions.append("优先修复前3类错误源并重试抓取")
    if not next_actions:
        next_actions.append("保持当前配置，继续观察7日趋势并微调查询词")

    history.append(current)
    history = history[-LEARNING_HISTORY_MAX:]
    state["history"] = history
    _save_learning_state(state)

    return {
        "enabled": True,
        "history_window": min(7, len(history)),
        "current": current,
        "baseline_avg7": baseline,
        "delta_vs_avg7": delta,
        "progress_signals": progress_signals[:4],
        "next_actions": next_actions[:4],
    }


def _is_trusted_time_item(item: dict[str, Any]) -> bool:
    label = str(item.get("query_label") or "").lower()
    if label.startswith(TRUSTED_TIME_LABEL_PREFIXES):
        return True
    if str(item.get("source_type") or "") in {"x", "paper", "github"}:
        return True
    d = _domain_of(str(item.get("url") or ""))
    return _is_trusted_time_domain(d)


def _is_ai_relevant(item: dict[str, Any]) -> bool:
    src_type = str(item.get("source_type") or "")
    if src_type in {"x", "paper", "github"}:
        return True
    txt = f"{item.get('title', '')} {item.get('content', '')} {item.get('query_label', '')}".lower()
    return any(k in txt for k in AI_RELEVANCE_KEYS)


def _call_arxiv_recent() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    query = quote_plus("cat:cs.AI OR cat:cs.LG OR cat:cs.CL")
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={query}&start=0&max_results=30&sortBy=submittedDate&sortOrder=descending"
    )
    proc = _safe_curl([url], timeout_flag="20")
    if proc.returncode != 0:
        return [], [{"query_label": "arxiv", "error": f"curl_exit_{proc.returncode}"}]

    xml = proc.stdout or ""
    entries = re.findall(r"<entry>(.*?)</entry>", xml, flags=re.S)
    out: list[dict[str, Any]] = []
    for block in entries[:20]:
        title_m = re.search(r"<title>(.*?)</title>", block, flags=re.S)
        sum_m = re.search(r"<summary>(.*?)</summary>", block, flags=re.S)
        link_m = re.search(r"<id>(.*?)</id>", block, flags=re.S)
        pub_m = re.search(r"<published>(.*?)</published>", block, flags=re.S)
        up_m = re.search(r"<updated>(.*?)</updated>", block, flags=re.S)

        title = _strip_xml_text(title_m.group(1) if title_m else "")
        summary = _strip_xml_text(sum_m.group(1) if sum_m else "")
        link = _strip_xml_text(link_m.group(1) if link_m else "")
        event_dt = _parse_any_datetime((up_m.group(1) if up_m else "") or (pub_m.group(1) if pub_m else ""))

        if not title or not link:
            continue

        item = {
            "url": link,
            "source": "arxiv",
            "source_type": "paper",
            "source_layer": "aux",
            "title": title,
            "content": summary[:500],
            "score": 0.76,
            "query_label": "paper:arxiv_recent",
        }
        if _normalize_item_time(item, event_dt):
            item["category"] = _infer_category(item)
            out.append(item)

    return out, []


def _call_hn_recent() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    queries = [
        "OpenAI OR Anthropic OR Gemini",
        "AI startup funding",
        "open-source AI agent",
        "LLM release",
        "AI paper",
    ]
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for q in queries:
        qs = urlencode({"query": q, "tags": "story", "hitsPerPage": 20})
        url = f"https://hn.algolia.com/api/v1/search_by_date?{qs}"
        proc = _safe_curl([url], timeout_flag="16")
        if proc.returncode != 0:
            errors.append({"query_label": f"hn:{q}", "error": f"curl_exit_{proc.returncode}"})
            continue
        try:
            data = json.loads(proc.stdout or "{}")
        except Exception:
            errors.append({"query_label": f"hn:{q}", "error": "invalid_json"})
            continue

        for hit in (data.get("hits") or [])[:10]:
            created = _parse_any_datetime(hit.get("created_at"))
            title = str(hit.get("title") or hit.get("story_title") or "").strip()
            if not created or not title:
                continue
            link = str(hit.get("url") or hit.get("story_url") or "").strip()
            if not link:
                hn_id = str(hit.get("objectID") or "").strip()
                link = f"https://news.ycombinator.com/item?id={hn_id}" if hn_id else "https://news.ycombinator.com/"
            item = {
                "url": link,
                "source": "hackernews",
                "source_type": "web",
                "source_layer": "aux",
                "title": title,
                "content": re.sub(r"\s+", " ", str(hit.get("story_text") or "").strip()),
                "score": min(1.0, math.log1p(float(hit.get("points") or 0)) / 8.0),
                "query_label": f"hn:{q}",
            }
            if _normalize_item_time(item, created):
                item["category"] = _infer_category(item)
                out.append(item)
    return out, errors


def _call_reddit_ai_recent() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    subreddits = [
        "MachineLearning",
        "LocalLLaMA",
        "singularity",
        "artificial",
    ]
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    headers = [
        "-H",
        "User-Agent: hermes-ai-digest/1.0",
        "-H",
        "Accept: application/json",
    ]

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=30"
        proc = _safe_curl([*headers, url], timeout_flag="16")
        if proc.returncode != 0:
            errors.append({"query_label": f"reddit:{sub}", "error": f"curl_exit_{proc.returncode}"})
            continue
        try:
            data = json.loads(proc.stdout or "{}")
        except Exception:
            errors.append({"query_label": f"reddit:{sub}", "error": "invalid_json"})
            continue

        for row in (((data.get("data") or {}).get("children")) or [])[:15]:
            node = row.get("data") or {}
            ts_utc = node.get("created_utc")
            try:
                d = dt.datetime.fromtimestamp(float(ts_utc), tz=UTC)
            except Exception:
                d = None

            title = re.sub(r"\s+", " ", str(node.get("title") or "").strip())
            if not title:
                continue
            link = str(node.get("url") or "").strip()
            permalink = str(node.get("permalink") or "").strip()
            if not link and permalink:
                link = f"https://www.reddit.com{permalink}"
            elif permalink and "reddit.com" not in link:
                link = f"https://www.reddit.com{permalink}"

            item = {
                "url": link or "https://www.reddit.com/",
                "source": f"reddit:r/{sub}",
                "source_type": "web",
                "source_layer": "aux",
                "title": title,
                "content": re.sub(r"\s+", " ", str(node.get("selftext") or "").strip())[:500],
                "score": min(1.0, math.log1p(float(node.get("score") or 0)) / 8.0),
                "query_label": f"reddit:{sub}",
            }
            if _normalize_item_time(item, d):
                item["category"] = _infer_category(item)
                out.append(item)
    return out, errors


def _call_ai_rss_feeds() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    feeds = [
        ("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("venturebeat_ai", "https://venturebeat.com/category/ai/feed/"),
        ("verge_ai", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("mit_ai", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
        ("marktechpost", "https://www.marktechpost.com/feed/"),
        ("a16z", "https://a16z.com/feed/"),
        ("openai_blog", "https://openai.com/news/rss.xml"),
        ("anthropic_news", "https://www.anthropic.com/news/rss.xml"),
        ("google_blog_ai", "https://blog.google/technology/ai/rss/"),
        ("semafor_ai", "https://www.semafor.com/topic/ai/rss.xml"),
        ("hackernews_front", "https://news.ycombinator.com/rss"),
        ("nvidia_blog", "https://blogs.nvidia.com/feed/"),
    ]
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for label, url in feeds:
        proc = _safe_curl([url], timeout_flag="18")
        if proc.returncode != 0:
            errors.append({"query_label": f"rss:{label}", "error": f"curl_exit_{proc.returncode}"})
            continue

        xml = proc.stdout or ""
        blocks = re.findall(r"<item>(.*?)</item>", xml, flags=re.S)
        if not blocks:
            blocks = re.findall(r"<entry>(.*?)</entry>", xml, flags=re.S)

        for block in blocks[:20]:
            t = re.search(r"<title>(.*?)</title>", block, flags=re.S)
            l = re.search(r"<link>(.*?)</link>", block, flags=re.S)
            if not l:
                l = re.search(r'link[^>]+href="([^"]+)"', block, flags=re.S)
            d = (
                re.search(r"<pubDate>(.*?)</pubDate>", block, flags=re.S)
                or re.search(r"<published>(.*?)</published>", block, flags=re.S)
                or re.search(r"<updated>(.*?)</updated>", block, flags=re.S)
            )
            desc = (
                re.search(r"<description>(.*?)</description>", block, flags=re.S)
                or re.search(r"<summary>(.*?)</summary>", block, flags=re.S)
            )
            title = _strip_xml_text(t.group(1) if t else "")
            link = _strip_xml_text(l.group(1) if l else "")
            desc_text = _strip_xml_text(desc.group(1) if desc else "")[:500]
            event_dt = _parse_any_datetime(d.group(1) if d else "")

            if not title or not link:
                continue

            item = {
                "url": link,
                "source": f"rss:{label}",
                "source_type": "web",
                "source_layer": "aux",
                "title": title,
                "content": desc_text,
                "score": 0.62,
                "query_label": f"rss:{label}",
            }
            if _normalize_item_time(item, event_dt):
                item["category"] = _infer_category(item)
                out.append(item)

    return out, errors


def _extract_dates_from_tavily_result_row(row: dict[str, Any]) -> list[dt.datetime]:
    dates: list[dt.datetime] = []
    for key in ("published_date", "published", "date", "updated_at", "created_at"):
        d = _parse_any_datetime(row.get(key))
        if d:
            dates.append(d)
    title = str(row.get("title") or "")
    content = str(row.get("content") or "")
    url = str(row.get("url") or "")
    d2 = _extract_time_from_text(title, content, url)
    if d2:
        dates.append(d2)
    return dates


def _reverse_verify_origin_time(items: list[dict[str, Any]], tavily_key: str, errors: list[dict[str, str]]) -> tuple[int, int]:
    """Reverse search each item and use earliest observed public date as filter baseline."""
    if not tavily_key:
        return 0, 0

    checked = 0
    shifted = 0

    # Check most relevant/newest candidates first.
    candidates = sorted(
        items,
        key=lambda x: (x.get("event_time_iso", ""), float(x.get("score") or 0.0)),
        reverse=True,
    )

    for item in candidates:
        if checked >= MAX_REVERSE_CHECK:
            break
        # X tweet snowflake is already an origin timestamp, no need to reverse-search.
        if str(item.get("source_type") or "") == "x":
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = "x_origin_snowflake"
            item["cross_verified"] = True
            item["cross_domain_count"] = 1
            continue

        # Trusted domains with explicit timestamps are accepted as authoritative
        # without mandatory reverse search to avoid over-dropping high-quality items.
        base_dt = _parse_any_datetime(item.get("event_time_iso"))
        if base_dt and _is_trusted_time_item(item):
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = "trusted_source_timestamp"
            item["cross_verified"] = True
            item["cross_domain_count"] = max(1, int(item.get("cross_domain_count") or 0))
            continue

        title = str(item.get("title") or "").strip()
        if len(title) < 12:
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = "event_time_only"
            item["cross_verified"] = False
            item["cross_domain_count"] = 0
            continue

        checked += 1
        query = f'"{title[:140]}" earliest date source'
        resp = _call_tavily(tavily_key, query=query, max_results=5, days=7)
        if resp.get("error"):
            errors.append({"query_label": f"reverse:{item.get('query_label', 'item')}", "error": str(resp.get("error"))})
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = "event_time_fallback"
            item["cross_verified"] = False
            item["cross_domain_count"] = 0
            continue

        base_dt = _parse_any_datetime(item.get("event_time_iso"))
        observed: list[dt.datetime] = [base_dt] if base_dt else []
        domains: set[str] = set()
        base_domain = _domain_of(str(item.get("url") or ""))
        if base_domain:
            domains.add(base_domain)
        for row in resp.get("results", []) or []:
            observed.extend(_extract_dates_from_tavily_result_row(row))
            d = _domain_of(str(row.get("url") or ""))
            if d:
                domains.add(d)

        observed = [d for d in observed if d]
        if not observed:
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = "event_time_fallback"
            item["cross_verified"] = False
            item["cross_domain_count"] = max(0, len(domains))
            continue

        earliest = min(observed)
        earliest_iso, earliest_h = _format_bj(earliest)
        item["origin_first_seen_iso"] = earliest_iso
        item["origin_first_seen_bj"] = earliest_h
        item["filter_time_iso"] = earliest_iso
        item["time_filter_basis"] = "reverse_verified_earliest"
        item["cross_domain_count"] = len(domains)
        item["cross_verified"] = len(domains) >= 2

        ev = _parse_any_datetime(item.get("event_time_iso"))
        if ev and earliest < ev:
            shifted += 1

    # Ensure every item has filter_time fallback.
    for item in items:
        if not item.get("filter_time_iso"):
            item["filter_time_iso"] = str(item.get("event_time_iso") or "")
            item["time_filter_basis"] = item.get("time_filter_basis") or "event_time_only"
        if "cross_verified" not in item:
            item["cross_verified"] = False
        if "cross_domain_count" not in item:
            item["cross_domain_count"] = 0

    return checked, shifted


def _is_within_48h(ts: dt.datetime, now: dt.datetime) -> tuple[bool, float]:
    age_h = (now - ts.astimezone(BJT)).total_seconds() / 3600.0
    return (0 <= age_h <= MAX_AGE_HOURS), age_h


def _rank_and_filter(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = dt.datetime.now(tz=BJT)
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []

    dropped_no_time = 0
    dropped_old = 0
    dropped_dup = 0
    dropped_unverified = 0
    dropped_irrelevant = 0

    for item in items:
        unique_key = str(item.get("status_id") or item.get("url") or "").strip()
        if not unique_key:
            dropped_dup += 1
            continue
        if unique_key in seen:
            dropped_dup += 1
            continue
        seen.add(unique_key)

        if not _is_ai_relevant(item):
            dropped_irrelevant += 1
            continue

        ts = _parse_any_datetime(item.get("filter_time_iso") or item.get("event_time_iso") or item.get("beijing_time"))
        if not ts:
            dropped_no_time += 1
            continue

        ok, age_h = _is_within_48h(ts, now)
        if not ok:
            dropped_old += 1
            continue

        src_type = str(item.get("source_type") or "")
        # Strict gate: non-X items must either:
        # 1) have trusted-source timestamp, or
        # 2) pass reverse verification + cross-domain corroboration.
        if src_type != "x":
            basis = str(item.get("time_filter_basis") or "")
            if basis == "trusted_source_timestamp":
                pass
            elif basis == "reverse_verified_earliest" and bool(item.get("cross_verified")):
                pass
            else:
                dropped_unverified += 1
                continue

        recency_bonus = max(0.0, MAX_AGE_HOURS - age_h) / MAX_AGE_HOURS
        source_type = src_type
        source_bonus = {
            "x": 0.10,
            "paper": 0.10,
            "github": 0.08,
            "web": 0.04,
        }.get(source_type, 0.0)
        layer_bonus = 0.06 if str(item.get("source_layer") or "") == "main" else 0.0

        item["age_hours"] = round(age_h, 2)
        item["_rank"] = float(item.get("score", 0.0)) * 0.58 + recency_bonus * 0.34 + source_bonus + layer_bonus
        kept.append(item)

    kept.sort(key=lambda x: (x.get("_rank", 0.0), x.get("filter_time_iso", "")), reverse=True)

    channel_cap = {"x": 14, "paper": 6, "github": 10, "web": 12}
    channel_used: dict[str, int] = {}
    balanced_stage: list[dict[str, Any]] = []
    for item in kept:
        c = str(item.get("source_type") or "web")
        cap = channel_cap.get(c, 6)
        if channel_used.get(c, 0) >= cap:
            continue
        channel_used[c] = channel_used.get(c, 0) + 1
        balanced_stage.append(item)

    # Ensure category diversity so digest isn't dominated by a single type (e.g. only papers).
    category_cap = {"论文": 6, "开源项目": 8, "创业融资": 8, "大佬发言": 8, "AI产品": 6, "行业动态": 6}
    category_used: dict[str, int] = {}
    balanced: list[dict[str, Any]] = []
    for item in balanced_stage:
        cat = str(item.get("category") or "行业动态")
        cap = category_cap.get(cat, 6)
        if category_used.get(cat, 0) >= cap:
            continue
        category_used[cat] = category_used.get(cat, 0) + 1
        balanced.append(item)

    category_stats: dict[str, int] = {}
    for item in balanced:
        cat = str(item.get("category") or "未分类")
        category_stats[cat] = category_stats.get(cat, 0) + 1

    stats: dict[str, Any] = {
        "dropped_no_time": dropped_no_time,
        "dropped_outside_48h": dropped_old,
        "dropped_duplicates": dropped_dup,
        "dropped_unverified": dropped_unverified,
        "dropped_irrelevant": dropped_irrelevant,
        "kept_after_48h_filter": len(balanced),
        "category_distribution": category_stats,
    }
    return balanced, stats


def _is_big_tech_item(item: dict[str, Any]) -> bool:
    txt = f"{item.get('title', '')} {item.get('content', '')} {item.get('source', '')}".lower()
    keys = [
        "openai",
        "anthropic",
        "deepmind",
        "google",
        "microsoft",
        "meta",
        "nvidia",
        "amazon",
        "aws",
        "apple",
        "xai",
        "mistral",
    ]
    return any(k in txt for k in keys)


def _is_exec_scientist_voice(item: dict[str, Any]) -> bool:
    src = str(item.get("source_type") or "")
    label = str(item.get("query_label") or "").lower()
    txt = f"{item.get('title', '')} {item.get('content', '')}".lower()
    if src == "x":
        return True
    if "发言" in label or "said" in txt or "interview" in txt or "statement" in txt:
        return True
    return _is_big_tech_item(item) and ("said" in txt or "announced" in txt or "wrote" in txt or "blog" in txt)


def _is_exec_tech_watch_item(item: dict[str, Any]) -> bool:
    txt = f"{item.get('title', '')} {item.get('content', '')} {item.get('source', '')}".lower()
    cn_bigtech = [
        "baidu",
        "alibaba",
        "tencent",
        "bytedance",
        "huawei",
        "xiaomi",
        "jd",
        "meituan",
        "快手",
        "百度",
        "阿里",
        "腾讯",
        "字节",
        "华为",
        "小米",
    ]
    role_words = [
        "ceo",
        "cto",
        "chief scientist",
        "vp",
        "head of",
        "researcher",
        "engineer",
        "技术负责人",
        "研究员",
        "科学家",
        "高管",
        "负责人",
    ]
    has_company = _is_big_tech_item(item) or any(k in txt for k in cn_bigtech)
    has_role = any(k in txt for k in role_words)
    return has_company and has_role


def _is_startup_item(item: dict[str, Any]) -> bool:
    txt = f"{item.get('title', '')} {item.get('content', '')} {item.get('query_label', '')}".lower()
    return (
        str(item.get("category") or "") == "创业融资"
        or "startup" in txt
        or "seed" in txt
        or "series a" in txt
        or "series b" in txt
        or "raised" in txt
        or "funding" in txt
        or "accelerator" in txt
        or "y combinator" in txt
        or "yc " in txt
    )


def _build_modules(top: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    hot = top[:10]
    exec_voice = [x for x in top if _is_exec_scientist_voice(x)][:10]
    exec_tech_watch = [x for x in top if _is_exec_tech_watch_item(x)][:10]
    startup = [x for x in top if _is_startup_item(x)][:10]
    big_tech = [x for x in top if _is_big_tech_item(x)][:10]
    papers = [
        x
        for x in top
        if str(x.get("source_type") or "") == "paper" or "arxiv.org" in str(x.get("url") or "").lower()
    ][:10]

    if len(exec_voice) < 4:
        for x in top:
            if x in exec_voice:
                continue
            if _is_big_tech_item(x) or str(x.get("source_type") or "") == "x":
                exec_voice.append(x)
            if len(exec_voice) >= 8:
                break

    if len(startup) < 4:
        for x in top:
            if x in startup:
                continue
            txt = f"{x.get('title', '')} {x.get('content', '')} {x.get('query_label', '')}".lower()
            if any(k in txt for k in ["startup", "yc", "seed", "series", "funding", "raised", "incubator"]):
                startup.append(x)
            if len(startup) >= 8:
                break

    if len(exec_tech_watch) < 4:
        for x in exec_voice:
            if x in exec_tech_watch:
                continue
            exec_tech_watch.append(x)
            if len(exec_tech_watch) >= 8:
                break

    return {
        "hot_info": hot,
        "exec_scientist_bigtech_voice": exec_voice[:10],
        "exec_tech_bigtech_watch": exec_tech_watch[:10],
        "startup_updates": startup[:10],
        "bigtech_updates": big_tech,
        "quality_papers_arxiv": papers,
    }


def main() -> int:
    query_pack = _build_queries()
    errors: list[dict[str, str]] = []
    all_items: list[dict[str, Any]] = []

    twikit_items, twikit_errors = asyncio.run(_primary_from_twikit())
    all_items.extend(twikit_items)
    errors.extend(twikit_errors)

    twscrape_items, twscrape_errors = asyncio.run(_primary_from_twscrape())
    all_items.extend(twscrape_items)
    errors.extend(twscrape_errors)

    tavily_key = _load_tavily_key()
    tavily_used = False
    ddgs_used = False
    if tavily_key:
        for label, query in query_pack:
            resp = _call_tavily(tavily_key, query, max_results=6, days=2)
            if resp.get("error"):
                errors.append({"query_label": f"tavily:{label}", "error": str(resp.get("error"))})
                continue
            all_items.extend(_pick_items(resp, label))
        tavily_used = True
    else:
        errors.append({"query_label": "tavily", "error": "missing_tavily_api_key"})

    ddgs_items, ddgs_errors, ddgs_used = _call_ddgs_free_search()
    all_items.extend(ddgs_items)
    errors.extend(ddgs_errors)

    github_items, github_errors = _call_github_search()
    all_items.extend(github_items)
    errors.extend(github_errors)

    arxiv_items, arxiv_errors = _call_arxiv_recent()
    all_items.extend(arxiv_items)
    errors.extend(arxiv_errors)

    hn_items, hn_errors = _call_hn_recent()
    all_items.extend(hn_items)
    errors.extend(hn_errors)

    reddit_items, reddit_errors = _call_reddit_ai_recent()
    all_items.extend(reddit_items)
    errors.extend(reddit_errors)

    rss_items, rss_errors = _call_ai_rss_feeds()
    all_items.extend(rss_items)
    errors.extend(rss_errors)

    reverse_checked, reverse_shifted = _reverse_verify_origin_time(all_items, tavily_key, errors)

    ranked, filter_stats = _rank_and_filter(all_items)
    top = ranked[:36]
    modules = _build_modules(top)
    generated_iso = dt.datetime.now(tz=BJT).isoformat(timespec="seconds")
    generated_bj = dt.datetime.now(tz=BJT).strftime("%Y-%m-%d %H:%M:%S")
    learning_input_stats = {
        **filter_stats,
        "raw_collected": len(all_items),
        "after_filter": len(ranked),
    }
    learning = _build_learning_report(generated_iso, learning_input_stats, top, modules, errors)

    out = {
        "ok": True,
        "generated_at_bj": generated_bj,
        "generated_at_iso": generated_iso,
        "source": "multi_source_ai_digest_v7",
        "architecture": {
            "mode": "one-main-many-aux",
            "main": ["x_twikit", "x_twscrape"],
            "aux": [
                "tavily_web",
                "ddgs_free_search",
                "github_search",
                "arxiv_api",
                "hn_algolia",
                "reddit_new",
                "rss_media_expanded",
            ],
            "official_skills_enabled": [
                "duckduckgo-search",
                "domain-intel",
                "blogwatcher",
                "scrapling",
                "parallel-cli(optional)",
            ],
        },
        "time_filter_policy": {
            "timezone": "Asia/Shanghai",
            "required_timestamp": True,
            "max_age_hours": int(MAX_AGE_HOURS),
            "normalized_format": "ISO-8601 with timezone offset (+08:00)",
            "filter_baseline": "origin_first_seen_if_available_else_event_time",
            "reverse_verification": {
                "enabled": True,
                "checked_items": reverse_checked,
                "earliest_time_shifted_items": reverse_shifted,
                "strict_cross_verification": "hybrid",
            },
        },
        "collection_stats": {
            "raw_collected": len(all_items),
            "after_filter": len(ranked),
            "returned": len(top),
            "tavily_used": tavily_used,
            "ddgs_used": ddgs_used,
            "query_count": len(query_pack),
            **filter_stats,
        },
        "errors": errors,
        "learning": learning,
        "modules": modules,
        "items": top,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
