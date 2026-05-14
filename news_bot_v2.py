#!/usr/bin/env python3
"""
📰 Detective Crypto — News Bot V2
===================================
Bot de noticias con investigación automática de tokens.

Detecta eventos de alto impacto:
  🏦 Listings en Binance, Coinbase, OKX, Bybit
  🤝 Alianzas estratégicas y partnerships
  🔓 Unlocks masivos de tokens
  🔥 Token burns
  ✈️  Airdrops
  ⚠️  Hacks y exploits
  📋 ETF filings / aprobaciones

Cuando detecta un evento → investiga automáticamente:
  • Precio, market cap, volumen (CoinGecko)
  • Seguridad del contrato (GoPlus)
  • Liquidez en DEX (DexScreener)
  • Redes sociales y comunidad
  • Impacto histórico estimado

Corre 24/7 en Railway.app
"""

import os
import json
import time
import re
import requests
import logging
import feedparser
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "8298428814:AAHtYqO--Fo3GKJiP13u85uKLof4hQOSvT4")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "1190004564")
COINGECKO_API_KEY   = os.getenv("COINGECKO_API_KEY", "")
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

# Credenciales Telethon para monitorear canales
TELEGRAM_API_ID     = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH   = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION    = os.getenv("TELEGRAM_SESSION", "")
CLAUDE_API_KEY      = os.getenv("CLAUDE_API_KEY", "")

# Canales de Telegram a monitorear
TELEGRAM_CHANNELS = [
    "WatcherGuru",    # Breaking news crypto
    "whale_alert",    # Movimientos de ballenas
]

# Cliente Telethon global (conexión persistente)
telethon_client = None

POLL_INTERVAL       = 600    # cada 10 minutos
CACHE_FILE          = Path(__file__).parent / "cache_v2.json"

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "news_bot_v2.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("detective_v2")

# ─────────────────────────────────────────────
#  IMPACTO HISTÓRICO POR TIPO DE EVENTO
# ─────────────────────────────────────────────
HISTORICAL_IMPACT = {
    "binance_listing":    {"emoji": "🟡", "rango": "+30% a +50%", "ventana": "48-72h", "tipo": "ALCISTA"},
    "coinbase_listing":   {"emoji": "🔵", "rango": "+25% a +40%", "ventana": "48-72h", "tipo": "ALCISTA"},
    "okx_listing":        {"emoji": "⚫", "rango": "+15% a +25%", "ventana": "24-48h", "tipo": "ALCISTA"},
    "bybit_listing":      {"emoji": "🟠", "rango": "+10% a +20%", "ventana": "24-48h", "tipo": "ALCISTA"},
    "exchange_listing":   {"emoji": "🏦", "rango": "+10% a +35%", "ventana": "24-72h", "tipo": "ALCISTA"},
    "strategic_alliance": {"emoji": "🤝", "rango": "+20% a +40%", "ventana": "48h",    "tipo": "ALCISTA"},
    "etf_filing":         {"emoji": "📋", "rango": "+30% a +60%", "ventana": "72h",    "tipo": "MUY ALCISTA"},
    "etf_approval":       {"emoji": "✅", "rango": "+40% a +100%","ventana": "72h",    "tipo": "MUY ALCISTA"},
    "airdrop":            {"emoji": "✈️", "rango": "+20% a +40%", "ventana": "72h",    "tipo": "ALCISTA"},
    "token_burn":         {"emoji": "🔥", "rango": "+10% a +25%", "ventana": "24h",    "tipo": "ALCISTA"},
    "token_unlock":       {"emoji": "🔓", "rango": "-15% a -30%", "ventana": "24-48h", "tipo": "BAJISTA"},
    "hack":               {"emoji": "☠️", "rango": "-40% a -80%", "ventana": "inmediato","tipo": "MUY BAJISTA"},
    "delisting":          {"emoji": "❌", "rango": "-20% a -40%", "ventana": "inmediato","tipo": "BAJISTA"},
    "partnership":        {"emoji": "🤝", "rango": "+15% a +35%", "ventana": "48h",    "tipo": "ALCISTA"},
    "regulation":         {"emoji": "⚖️", "rango": "-20% a -50%", "ventana": "inmediato","tipo": "MUY BAJISTA"},
}

# Palabras clave para clasificar noticias por tipo
EVENT_KEYWORDS = {
    "binance_listing":    ["lists on binance", "binance lists", "listed on binance", "now trading on binance",
                           "binance spot", "binance will list", "launching on binance", "binance perpetual"],
    "coinbase_listing":   ["lists on coinbase", "coinbase lists", "listed on coinbase", "coinbase adds",
                           "now on coinbase", "coinbase will list", "launching on coinbase", "coinbase advanced"],
    "okx_listing":        ["lists on okx", "okx lists", "listed on okx", "okx adds", "okx will list"],
    "bybit_listing":      ["lists on bybit", "bybit lists", "listed on bybit", "bybit adds", "bybit will list"],
    "exchange_listing":   ["listed on", "lists on", "now trading on", "spot trading", "new listing",
                           "launches on", "available on", "trading live"],
    "strategic_alliance": ["strategic partnership", "strategic alliance", "partners with", "collaboration with",
                           "integrates with", "joins forces with", "teams up with", "deal with", "agreement with"],
    "etf_filing":         ["etf filing", "etf application", "files for etf", "spot etf", "etf submitted",
                           "etf proposal", "etf request", "bitcoin etf", "ethereum etf", "crypto etf",
                           "yanked", "inflows", "outflows", "etf flows", "etf fund"],
    "etf_approval":       ["etf approved", "etf approval", "sec approves etf", "etf greenlit", "sec greenlights"],
    "airdrop":            ["airdrop", "token airdrop", "claim airdrop", "free tokens", "snapshot",
                           "eligible for", "token distribution", "community rewards"],
    "token_burn":         ["token burn", "burn event", "tokens burned", "burning tokens", "deflationary burn",
                           "buyback and burn", "supply reduction", "burn mechanism"],
    "token_unlock":       ["token unlock", "vesting unlock", "tokens unlocked", "cliff unlock", "tokens released",
                           "vesting schedule", "unlock event", "tokens vested"],
    "hack":               ["hacked", "exploited", "hack", "exploit", "stolen", "rug pull", "breach", "attack",
                           "drained", "vulnerability", "security incident", "funds stolen", "million stolen",
                           "billion stolen", "flash loan", "phishing", "scam", "fraud"],
    "delisting":          ["delisted", "delisting", "removed from", "suspended trading", "trading suspended"],
    "partnership":        ["partnership", "partners with", "integrates", "collaboration", "joins forces",
                           "backed by", "investment from", "raises", "funding round", "series a", "series b"],
    "regulation":         ["sec charges", "sec sues", "cftc", "doj charges", "arrested", "charged with",
                           "banned", "crackdown", "regulatory", "compliance", "lawsuit"],
}

# RSS feeds de medios crypto
RSS_FEEDS = [
    ("CoinDesk",       "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph",  "https://cointelegraph.com/rss"),
    ("Decrypt",        "https://decrypt.co/feed"),
    ("The Block",      "https://www.theblock.co/rss.xml"),
    ("Blockworks",     "https://blockworks.co/feed"),
]

# ─────────────────────────────────────────────
#  CACHÉ
# ─────────────────────────────────────────────
def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {
        "binance_symbols":  [],
        "coinbase_symbols": [],
        "okx_symbols":      [],
        "bybit_symbols":    [],
        "seen_news":        [],
        "investigated":     [],
    }

def save_cache(cache: dict):
    cache["seen_news"]    = cache["seen_news"][-1000:]
    cache["investigated"] = cache["investigated"][-500:]
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

cache = load_cache()

# ─────────────────────────────────────────────
#  TRADUCCIÓN
# ─────────────────────────────────────────────
def translate_to_spanish(text: str) -> str:
    """Traduce texto al español usando Google Translate (sin API key)."""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "en",
            "tl": "es",
            "dt": "t",
            "q": text
        }
        r = requests.get(url, params=params, timeout=8)
        result = r.json()
        translated = "".join([chunk[0] for chunk in result[0] if chunk[0]])
        return translated if translated else text
    except Exception:
        return text  # Si falla, devuelve el original

# ─────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(text: str, parse_mode: str = "HTML"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n" + "═"*60 + "\n" + text + "\n" + "═"*60)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }, timeout=15)
        if r.status_code == 200:
            log.info("✅ Mensaje enviado a Telegram")
        elif r.status_code == 400:
            # Si HTML falla, reenviar sin formato
            log.warning(f"HTML parse error, reintentando sin formato: {r.text[:100]}")
            r2 = requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": re.sub(r'<[^>]+>', '', text),  # quitar tags HTML
                "disable_web_page_preview": False
            }, timeout=15)
            if r2.status_code == 200:
                log.info("✅ Mensaje enviado (sin formato)")
            else:
                log.error(f"Telegram error {r2.status_code}: {r2.text[:200]}")
        else:
            log.error(f"Telegram error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Error Telegram: {e}")

# ─────────────────────────────────────────────
#  CLASIFICAR TIPO DE EVENTO
# ─────────────────────────────────────────────
def classify_event(title: str) -> str:
    title_lower = title.lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return event_type
    return ""

def is_high_impact(event_type: str) -> bool:
    high_impact = [
        "binance_listing", "coinbase_listing", "okx_listing", "bybit_listing",
        "strategic_alliance", "etf_filing", "etf_approval", "airdrop",
        "token_burn", "token_unlock", "hack", "partnership", "exchange_listing",
        "regulation", "delisting"
    ]
    return event_type in high_impact

def extract_token_symbol(title: str) -> str:
    """Extrae el símbolo del token del título de la noticia."""

    # ── 1. Mapa de nombres completos → símbolo ──
    NAME_MAP = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "binance coin": "BNB", "bnb": "BNB", "ripple": "XRP", "xrp": "XRP",
        "cardano": "ADA", "dogecoin": "DOGE", "shiba inu": "SHIB",
        "avalanche": "AVAX", "chainlink": "LINK", "polkadot": "DOT",
        "uniswap": "UNI", "litecoin": "LTC", "tron": "TRX",
        "stellar": "XLM", "monero": "XMR", "cosmos": "ATOM",
        "near protocol": "NEAR", "near": "NEAR",
        "aptos": "APT", "sui": "SUI", "arbitrum": "ARB",
        "optimism": "OP", "polygon": "POL", "matic": "POL",
        "injective": "INJ", "render": "RENDER", "ondo": "ONDO",
        "aave": "AAVE", "compound": "COMP", "maker": "MKR",
        "curve": "CRV", "synthetix": "SNX", "yearn": "YFI",
        "the graph": "GRT", "filecoin": "FIL", "theta": "THETA",
        "internet computer": "ICP", "icp": "ICP",
        "hedera": "HBAR", "hbar": "HBAR",
        "pepe": "PEPE", "bonk": "BONK", "wif": "WIF",
        "floki": "FLOKI", "brett": "BRETT",
        "worldcoin": "WLD", "wld": "WLD",
        "sei": "SEI", "mantle": "MNT", "blast": "BLAST",
        "jupiter": "JUP", "jito": "JTO", "pyth": "PYTH",
        "wormhole": "W", "starknet": "STRK",
        "morpho": "MORPHO", "pendle": "PENDLE",
        "ethena": "ENA", "kelp": "KELP",
        "hyperliquid": "HYPE", "virtuals": "VIRTUAL",
        "bio protocol": "BIO", "bio": "BIO",
        "knc": "KNC", "kyber": "KNC",
        "amp": "AMP", "rez": "REZ",
    }

    title_lower = title.lower()

    # ── 2. Buscar por nombre completo en el título ──
    for name, symbol in NAME_MAP.items():
        if re.search(r'\b' + re.escape(name) + r'\b', title_lower):
            return symbol

    # ── 3. Patrones de símbolo explícito ──
    NOISE = {
        "USD", "USDT", "USDC", "NFT", "DAO", "TVL", "CEO", "SEC",
        "ETF", "API", "USA", "FOR", "NOT", "THE", "DeFi", "DEX",
        "CEX", "ALL", "NEW", "TOP", "CAN", "HIT", "NOW", "GET",
        "BIG", "KEY", "LAW", "TAX", "HOW", "WHY", "IRS", "UK",
        "EU", "AI", "DeFi", "WEB", "NFTs", "DAO", "IPO", "ICO",
        "P2P", "KYC", "AML", "TGE", "IDO", "IEO", "RPC", "EVM",
    }

    patterns = [
        r'\$([A-Z]{2,10})\b',                          # $TOKEN
        r'\b([A-Z]{2,8})\s+token\b',                   # TOKEN token
        r'\b([A-Z]{2,8})\s+coin\b',                    # TOKEN coin
        r'\(([A-Z]{2,8})\)',                            # (TOKEN)
        r'\blists?\s+([A-Z]{2,8})\b',                  # lists TOKEN
        r'\b([A-Z]{2,8})\s+(?:lists?|spot|trading)\b', # TOKEN lists/spot
        r'\b([A-Z]{2,8})\s+(?:hack|exploit|stolen)\b', # TOKEN hack
        r'\b([A-Z]{2,8})\s+(?:airdrop|burn|unlock)\b', # TOKEN airdrop/burn/unlock
        r'\b([A-Z]{2,8})\s+(?:etf|filing)\b',          # TOKEN etf
        r'\badds?\s+([A-Z]{2,8})\b',                   # adds TOKEN
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            symbol = match.group(1).upper()
            if symbol not in NOISE and len(symbol) >= 2:
                return symbol

    return ""

# ─────────────────────────────────────────────
#  INVESTIGACIÓN DEL TOKEN
# ─────────────────────────────────────────────

def get_coingecko_data(symbol: str) -> dict:
    """Busca el token en CoinGecko y retorna sus datos."""
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        # Buscar por símbolo
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": symbol},
            headers=headers,
            timeout=10
        )
        coins = r.json().get("coins", [])
        if not coins:
            return {}

        # Tomar el primer resultado relevante
        coin = next((c for c in coins if c.get("symbol", "").upper() == symbol.upper()), coins[0])
        coin_id = coin.get("id", "")

        # Obtener datos completos
        r2 = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}",
            params={"localization": "false", "tickers": "false", "community_data": "true", "developer_data": "false"},
            headers=headers,
            timeout=15
        )
        data = r2.json()

        market = data.get("market_data", {})
        community = data.get("community_data", {})

        return {
            "name":           data.get("name", ""),
            "symbol":         data.get("symbol", "").upper(),
            "id":             coin_id,
            "price":          market.get("current_price", {}).get("usd", 0),
            "market_cap":     market.get("market_cap", {}).get("usd", 0),
            "volume_24h":     market.get("total_volume", {}).get("usd", 0),
            "change_24h":     market.get("price_change_percentage_24h", 0),
            "change_7d":      market.get("price_change_percentage_7d", 0),
            "ath":            market.get("ath", {}).get("usd", 0),
            "ath_change_pct": market.get("ath_change_percentage", {}).get("usd", 0),
            "total_supply":   market.get("total_supply", 0),
            "circ_supply":    market.get("circulating_supply", 0),
            "rank":           data.get("market_cap_rank", 0),
            "age_days":       (datetime.now() - datetime.strptime(data.get("genesis_date", "2020-01-01") or "2020-01-01", "%Y-%m-%d")).days if data.get("genesis_date") else 0,
            "twitter":        community.get("twitter_followers", 0),
            "reddit":         community.get("reddit_subscribers", 0),
            "telegram":       community.get("telegram_channel_user_count", 0),
            "website":        (data.get("links", {}).get("homepage", [""])[0] or ""),
            "contract":       list((data.get("platforms") or {}).values())[0] if data.get("platforms") else "",
            "chain":          list((data.get("platforms") or {}).keys())[0] if data.get("platforms") else "",
        }
    except Exception as e:
        log.warning(f"CoinGecko error para {symbol}: {e}")
        return {}

def get_security_data(contract: str, chain: str) -> dict:
    """Analiza la seguridad del contrato con GoPlus Security."""
    if not contract or not chain:
        return {}

    chain_ids = {
        "ethereum": "1", "binance-smart-chain": "56", "polygon-pos": "137",
        "avalanche": "43114", "arbitrum-one": "42161", "optimism": "10",
        "base": "8453", "solana": "solana",
    }
    chain_id = chain_ids.get(chain.lower(), "1")

    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
        r = requests.get(url, params={"contract_addresses": contract}, timeout=10)
        result = r.json().get("result", {})
        data = result.get(contract.lower(), {})

        if not data:
            return {}

        return {
            "is_honeypot":       data.get("is_honeypot", "0") == "1",
            "has_mint":          data.get("is_mintable", "0") == "1",
            "can_blacklist":     data.get("is_blacklisted", "0") == "1",
            "owner_percent":     float(data.get("owner_percent", 0) or 0),
            "creator_percent":   float(data.get("creator_percent", 0) or 0),
            "lp_locked":         data.get("lp_locked_percent", None),
            "is_open_source":    data.get("is_open_source", "0") == "1",
            "holders":           int(data.get("holder_count", 0) or 0),
            "top10_percent":     float(data.get("top10_holder_percent", 0) or 0) * 100,
            "buy_tax":           float(data.get("buy_tax", 0) or 0),
            "sell_tax":          float(data.get("sell_tax", 0) or 0),
        }
    except Exception as e:
        log.warning(f"GoPlus error: {e}")
        return {}

def get_dexscreener_data(symbol: str) -> dict:
    """Obtiene datos de liquidez en DEX desde DexScreener."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search/?q={symbol}",
            timeout=10
        )
        pairs = r.json().get("pairs", [])
        if not pairs:
            return {}

        # Tomar el par con más liquidez
        best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        return {
            "liquidity_usd": float(best.get("liquidity", {}).get("usd", 0) or 0),
            "volume_24h":    float(best.get("volume", {}).get("h24", 0) or 0),
            "dex_name":      best.get("dexId", ""),
            "url":           best.get("url", ""),
        }
    except Exception as e:
        log.warning(f"DexScreener error: {e}")
        return {}

def investigate_token(symbol: str, event_type: str, news_title: str, news_link: str) -> str:
    """
    Investiga un token completo y genera el reporte para Telegram.
    """
    log.info(f"🔍 Investigando token: {symbol} | Evento: {event_type}")

    cg   = get_coingecko_data(symbol)
    sec  = {}
    dex  = {}

    if cg.get("contract"):
        sec = get_security_data(cg["contract"], cg.get("chain", "ethereum"))
        time.sleep(0.5)

    if not cg.get("market_cap"):
        dex = get_dexscreener_data(symbol)

    impact = HISTORICAL_IMPACT.get(event_type, {})

    # ── Construir el mensaje ──────────────────
    lines = []

    # Header según tipo de evento
    event_emojis = {
        "binance_listing":    "🚨 LISTING EN BINANCE",
        "coinbase_listing":   "🚨 LISTING EN COINBASE",
        "okx_listing":        "🚨 LISTING EN OKX",
        "bybit_listing":      "🚨 LISTING EN BYBIT",
        "exchange_listing":   "🚨 NUEVO LISTING",
        "strategic_alliance": "🤝 ALIANZA ESTRATÉGICA",
        "etf_filing":         "📋 SOLICITUD DE ETF",
        "etf_approval":       "✅ ETF APROBADO",
        "airdrop":            "✈️ AIRDROP ANUNCIADO",
        "token_burn":         "🔥 TOKEN BURN",
        "token_unlock":       "🔓 UNLOCK DE TOKENS",
        "hack":               "☠️ HACK / EXPLOIT",
        "delisting":          "❌ DELISTING",
        "partnership":        "🤝 PARTNERSHIP IMPORTANTE",
    }
    header = event_emojis.get(event_type, "📰 NOTICIA DE ALTO IMPACTO")

    lines.append(f"{header}")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━")

    # Noticia
    lines.append(f"📌 <b>{news_title[:120]}</b>")
    lines.append("")

    # Datos del token
    if cg:
        name   = cg.get("name", symbol)
        price  = cg.get("price", 0)
        mcap   = cg.get("market_cap", 0)
        vol    = cg.get("volume_24h", 0)
        chg24  = cg.get("change_24h", 0)
        chg7d  = cg.get("change_7d", 0)
        rank   = cg.get("rank", 0)
        ath_p  = cg.get("ath_change_pct", 0)
        circ   = cg.get("circ_supply", 0)
        total  = cg.get("total_supply", 0)

        def fmt_usd(n):
            if n >= 1e9:  return f"${n/1e9:.2f}B"
            if n >= 1e6:  return f"${n/1e6:.1f}M"
            if n >= 1e3:  return f"${n/1e3:.1f}K"
            return f"${n:.4f}"

        chg24_str = f"{'🟢' if chg24 >= 0 else '🔴'} {chg24:+.1f}%"
        chg7d_str = f"{'🟢' if chg7d >= 0 else '🔴'} {chg7d:+.1f}%"

        lines.append(f"📊 <b>{name} (${symbol})</b>  #{rank}")
        lines.append(f"  💵 Precio: <b>{fmt_usd(price)}</b>")
        lines.append(f"  📈 24h: {chg24_str}  |  7d: {chg7d_str}")
        lines.append(f"  🏦 Market Cap: <b>{fmt_usd(mcap)}</b>")
        lines.append(f"  📦 Volumen 24h: {fmt_usd(vol)}")
        if ath_p:
            lines.append(f"  📉 Vs ATH: {ath_p:.1f}%")
        if circ and total:
            pct_circ = (circ / total * 100) if total else 0
            lines.append(f"  🔄 Circulante: {pct_circ:.1f}% del supply total")
    elif dex:
        lines.append(f"📊 <b>${symbol}</b> (token en DEX)")
        lines.append(f"  💧 Liquidez: {fmt_usd(dex.get('liquidity_usd', 0))}")
        lines.append(f"  📦 Volumen 24h: {fmt_usd(dex.get('volume_24h', 0))}")

    # Comunidad
    tw = cg.get("twitter", 0)
    tg = cg.get("telegram", 0)
    rd = cg.get("reddit", 0)
    if tw or tg or rd:
        lines.append("")
        lines.append("📱 <b>Comunidad:</b>")
        if tw: lines.append(f"  🐦 Twitter: {tw:,} seguidores")
        if tg: lines.append(f"  💬 Telegram: {tg:,} miembros")
        if rd: lines.append(f"  👽 Reddit: {rd:,} suscriptores")

    # Seguridad
    lines.append("")
    lines.append("🔒 <b>Seguridad del contrato:</b>")
    if sec:
        honey  = sec.get("is_honeypot", False)
        mint   = sec.get("has_mint", False)
        black  = sec.get("can_blacklist", False)
        src    = sec.get("is_open_source", False)
        t10    = sec.get("top10_percent", 0)
        b_tax  = sec.get("buy_tax", 0)
        s_tax  = sec.get("sell_tax", 0)
        hold   = sec.get("holders", 0)

        lines.append(f"  {'✅' if not honey else '🚨'} Honeypot: {'SÍ ⚠️' if honey else 'No'}")
        lines.append(f"  {'✅' if src else '⚠️'} Código fuente: {'Verificado' if src else 'No verificado'}")
        lines.append(f"  {'⚠️' if mint else '✅'} Función mint: {'SÍ (riesgo)' if mint else 'No'}")
        lines.append(f"  {'⚠️' if black else '✅'} Blacklist: {'SÍ (riesgo)' if black else 'No'}")
        if t10:
            alert = "⚠️" if t10 > 50 else "✅"
            lines.append(f"  {alert} Top 10 holders: {t10:.1f}% del supply")
        if hold:
            lines.append(f"  👥 Holders totales: {hold:,}")
        if b_tax or s_tax:
            lines.append(f"  💸 Impuesto: compra {b_tax:.1f}% | venta {s_tax:.1f}%")
    elif cg.get("rank", 0) and cg.get("rank", 0) < 200:
        lines.append("  ✅ Proyecto establecido (top 200 CoinGecko)")
    else:
        lines.append("  ⚠️ Sin datos de contrato — verifica en TokenSniffer")

    # Impacto histórico
    if impact:
        tipo_color = {"ALCISTA": "🟢", "MUY ALCISTA": "💚", "BAJISTA": "🔴", "MUY BAJISTA": "💔"}.get(impact["tipo"], "🟡")
        lines.append("")
        lines.append("📈 <b>Impacto histórico de este tipo de evento:</b>")
        lines.append(f"  {tipo_color} Dirección: <b>{impact['tipo']}</b>")
        lines.append(f"  📊 Rango promedio: <b>{impact['rango']}</b>")
        lines.append(f"  ⏱ Ventana típica: {impact['ventana']}")

    # Links
    lines.append("")
    explorer_link = ""
    if cg.get("chain") == "ethereum" and cg.get("contract"):
        explorer_link = f" | <a href='https://etherscan.io/token/{cg['contract']}'>Etherscan</a>"
    elif cg.get("chain") == "binance-smart-chain" and cg.get("contract"):
        explorer_link = f" | <a href='https://bscscan.com/token/{cg['contract']}'>BSCScan</a>"

    dex_link = ""
    if dex.get("url"):
        dex_link = f" | <a href='{dex['url']}'>DEXScreener</a>"
    elif cg.get("symbol"):
        dex_link = f" | <a href='https://dexscreener.com/search?q={symbol}'>DEXScreener</a>"

    cg_link = f"<a href='https://www.coingecko.com/en/coins/{cg.get('id', symbol.lower())}'>CoinGecko</a>" if cg.get("id") else ""

    news_link_str = f" | <a href='{news_link}'>Ver noticia</a>" if news_link else ""

    links_line = " ".join(filter(None, [cg_link])) + dex_link + explorer_link + news_link_str
    if links_line.strip():
        lines.append(f"🔗 {links_line}")

    lines.append(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M UTC')}")

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  MONITOR DE EXCHANGE LISTINGS
# ─────────────────────────────────────────────

def get_exchange_symbols(exchange: str) -> set:
    urls = {
        "binance":  ("https://api.binance.com/api/v3/exchangeInfo", lambda d: {s["baseAsset"] for s in d.get("symbols", []) if s.get("status") == "TRADING"}),
        "coinbase": ("https://api.exchange.coinbase.com/products", lambda d: {p["base_currency"] for p in d if p.get("status") == "online"}),
        "okx":      ("https://www.okx.com/api/v5/public/instruments", lambda d: {i["baseCcy"] for i in d.get("data", []) if i.get("state") == "live"}, {"params": {"instType": "SPOT"}}),
        "bybit":    ("https://api.bybit.com/v5/market/instruments-info", lambda d: {i["baseCoin"] for i in d.get("result", {}).get("list", []) if i.get("status") == "Trading"}, {"params": {"category": "spot"}}),
    }
    config = urls.get(exchange)
    if not config:
        return set()

    url, parser = config[0], config[1]
    kwargs = config[2] if len(config) > 2 else {}

    try:
        r = requests.get(url, timeout=10, **kwargs)
        try:
            data = r.json()
        except Exception:
            return set()  # JSON inválido, ignorar silenciosamente
        return parser(data)
    except Exception as e:
        if exchange != "bybit":  # bybit falla frecuentemente, no loguear
            log.warning(f"Error {exchange}: {e}")
        return set()

def check_new_listings() -> list:
    global cache
    alerts = []

    exchanges = [
        ("binance",  "binance_symbols",  "binance_listing"),
        ("coinbase", "coinbase_symbols", "coinbase_listing"),
        ("okx",      "okx_symbols",      "okx_listing"),
        ("bybit",    "bybit_symbols",    "bybit_listing"),
    ]

    for exchange, cache_key, event_type in exchanges:
        current  = get_exchange_symbols(exchange)
        previous = set(cache.get(cache_key, []))

        if previous and current:
            new_tokens = current - previous
            new_tokens = {t for t in new_tokens if len(t) >= 2 and not t.startswith("LD")}
            for token in new_tokens:
                log.info(f"🏦 Nuevo listing: {token} en {exchange}")
                alerts.append({
                    "symbol":     token,
                    "event_type": event_type,
                    "title":      f"{token} now listed on {exchange.capitalize()} Spot",
                    "link":       f"https://www.{exchange}.com",
                })

        if current:
            cache[cache_key] = list(current)

    return alerts

# ─────────────────────────────────────────────
#  MONITOR DE NOTICIAS (RSS)
# ─────────────────────────────────────────────

def parse_rss(feed_url: str, source: str, max_age_hours: int = 12) -> list:
    """Parsea feed RSS usando feedparser — más robusto que XML manual."""
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        now = datetime.now(timezone.utc)

        for entry in feed.entries[:20]:
            title = (entry.get("title") or "").strip()
            link  = (entry.get("link")  or "").strip()
            guid  = (entry.get("id")    or link).strip()

            if not title:
                continue

            # Filtrar por antigüedad
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                try:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    age_hours = (now - pub_dt).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        continue
                except Exception:
                    pass

            articles.append({"title": title, "link": link, "guid": guid, "source": source})
    except Exception as e:
        log.debug(f"RSS {source}: {e}")
    return articles

def check_news_events() -> list:
    global cache
    alerts = []
    seen_titles_this_cycle = set()  # deduplicar entre feeds en el mismo ciclo

    for source, url in RSS_FEEDS:
        for article in parse_rss(url, source):
            guid  = article["guid"]
            title = article["title"]
            title_key = title[:60].lower().strip()  # clave corta para dedup por título

            if guid in cache["seen_news"]:
                continue
            if title_key in seen_titles_this_cycle:
                continue

            event_type = classify_event(title)
            if not event_type or not is_high_impact(event_type):
                cache["seen_news"].append(guid)  # marcar como visto aunque no sea de alto impacto
                continue

            symbol = extract_token_symbol(title)
            cache["seen_news"].append(guid)
            seen_titles_this_cycle.add(title_key)

            title_es = translate_to_spanish(title)
            alerts.append({
                "symbol":     symbol,
                "event_type": event_type,
                "title":      title_es,
                "title_orig": title,
                "link":       article["link"],
                "source":     source,
            })
            log.info(f"📰 Evento detectado [{event_type}]: {title[:70]}…")

    return alerts

# ─────────────────────────────────────────────
#  MONITOR DE CANALES TELEGRAM
# ─────────────────────────────────────────────

def init_telethon():
    """Inicia conexión persistente con Telegram (una sola vez al arrancar)."""
    global telethon_client
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION:
        log.warning("⚠️ Telethon: credenciales no configuradas")
        return
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        telethon_client = TelegramClient(StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH)
        telethon_client.connect()
        if telethon_client.is_user_authorized():
            log.info("📡 Telethon conectado permanentemente ✅")
        else:
            log.error("❌ Telethon: sesión no autorizada")
            telethon_client = None
    except Exception as e:
        log.error(f"❌ Error iniciando Telethon: {e}")
        telethon_client = None

def check_telegram_channels() -> list:
    """Lee los últimos mensajes de WatcherGuru y whale_alert."""
    global telethon_client
    if not telethon_client:
        return []

    alerts = []
    try:
        for channel in TELEGRAM_CHANNELS:
            try:
                messages = telethon_client.get_messages(channel, limit=15)
                log.info(f"📡 Canal @{channel}: {len(messages)} mensajes obtenidos")
                for msg in messages:
                    if not msg.text:
                        continue

                    text = msg.text.strip()
                    msg_id = f"tg_{channel}_{msg.id}"

                    if msg_id in cache["seen_news"]:
                        continue

                    # Filtrar mensajes de más de 12 horas
                    msg_time = msg.date.replace(tzinfo=timezone.utc)
                    age_hours = (datetime.now(timezone.utc) - msg_time).total_seconds() / 3600
                    if age_hours > 12:
                        cache["seen_news"].append(msg_id)
                        continue

                    # Clasificar el mensaje
                    event_type = classify_event(text)
                    if not event_type or not is_high_impact(event_type):
                        cache["seen_news"].append(msg_id)
                        continue

                    symbol = extract_token_symbol(text)
                    title_es = translate_to_spanish(text[:200])
                    cache["seen_news"].append(msg_id)

                    log.info(f"📡 Canal [{channel}] [{event_type}]: {text[:70]}…")
                    alerts.append({
                        "symbol":     symbol,
                        "event_type": event_type,
                        "title":      title_es,
                        "title_orig": text[:200],
                        "link":       f"https://t.me/{channel}",
                        "source":     f"Telegram @{channel}",
                    })
            except Exception as e:
                log.warning(f"Error leyendo canal {channel}: {e}")
    except Exception as e:
        log.error(f"❌ Error Telethon en ciclo: {type(e).__name__}: {e}")
        # Reconectar si la conexión se perdió
        init_telethon()

    return alerts

# ─────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────

def analyze_with_claude(title: str, event_type: str, market_data: dict) -> str:
    """Usa Claude para analizar el impacto real de la noticia."""
    if not CLAUDE_API_KEY:
        return ""
    try:
        price = market_data.get("price", 0)
        mcap  = market_data.get("market_cap", 0)
        chg24 = market_data.get("change_24h", 0)

        prompt = f"""Eres un analista experto en criptomonedas. Analiza esta noticia en máximo 2 oraciones en español.
Noticia: {title}
Tipo de evento: {event_type}
Precio actual: ${price:,.4f} | Cambio 24h: {chg24:+.1f}% | Market cap: ${mcap/1e6:.0f}M

Responde SOLO con: 1) Si es alcista o bajista para el precio. 2) Qué acción concreta tomarías (comprar, vender, esperar, investigar más). Sin preámbulos."""

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        log.debug(f"Claude API: {e}")
    return ""

def main():
    log.info("🚀 Detective Crypto V2 — Bot de Investigación iniciado")
    log.info(f"   Revisión cada {POLL_INTERVAL // 60} minutos | 24/7")

    # Iniciar conexión persistente con Telegram
    init_telethon()

    send_telegram(
        "🤖 <b>Detective Crypto V2 — Activo</b>\n\n"
        "Monitoreando eventos de alto impacto:\n"
        "🏦 Listings: Binance, Coinbase, OKX, Bybit\n"
        "🤝 Alianzas y partnerships estratégicos\n"
        "🔓 Unlocks masivos de tokens\n"
        "🔥 Token burns y airdrops\n"
        "☠️ Hacks y exploits\n\n"
        "📊 Cada alerta incluye investigación automática del token.\n"
        f"⏱ Revisión cada {POLL_INTERVAL // 60} min"
    )

    # Carga inicial sin alertas
    log.info("📥 Cargando baseline de exchanges...")
    for exc, key, _ in [("binance","binance_symbols",""), ("coinbase","coinbase_symbols",""),
                          ("okx","okx_symbols",""), ("bybit","bybit_symbols","")]:
        if not cache.get(key):
            syms = get_exchange_symbols(exc)
            if syms:
                cache[key] = list(syms)
                log.info(f"  {exc}: {len(syms)} tokens")
    save_cache(cache)

    while True:
        log.info("─── Ciclo de monitoreo ───")

        all_alerts = []

        try:
            all_alerts += check_new_listings()
        except Exception as e:
            log.error(f"Error listings: {e}")

        try:
            all_alerts += check_news_events()
        except Exception as e:
            log.error(f"Error noticias: {e}")

        try:
            all_alerts += check_telegram_channels()
        except Exception as e:
            log.error(f"Error canales Telegram: {e}")

        save_cache(cache)

        for alert in all_alerts:
            symbol     = alert.get("symbol", "")
            event_type = alert.get("event_type", "")
            title      = alert.get("title", "")
            link       = alert.get("link", "")

            inv_key = f"{symbol}_{event_type}_{title[:30]}"
            if inv_key in cache["investigated"]:
                continue
            cache["investigated"].append(inv_key)

            if symbol:
                report = investigate_token(symbol, event_type, title, link)
                # Agregar análisis de Claude al reporte
                if CLAUDE_API_KEY:
                    cg_data = get_coingecko_data(symbol) or {}
                    claude_opinion = analyze_with_claude(title, event_type, cg_data)
                    if claude_opinion:
                        report += f"\n\n🤖 <b>Análisis IA:</b>\n{claude_opinion}"
            else:
                # Sin símbolo — enviar alerta básica
                impact = HISTORICAL_IMPACT.get(event_type, {})
                report = (
                    f"📰 <b>EVENTO DE ALTO IMPACTO</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<b>{title}</b>\n\n"
                    f"📈 Impacto histórico: {impact.get('rango','?')} ({impact.get('ventana','?')})\n"
                    f"🔗 <a href='{link}'>Ver noticia completa</a>\n"
                    f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )

            send_telegram(report)
            time.sleep(2)

        save_cache(cache)
        log.info(f"Esperando {POLL_INTERVAL // 60} min...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot detenido. 👋")
