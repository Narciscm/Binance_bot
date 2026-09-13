"""
BINANCE V6 PRO v4.1
===================

Balanced Crypto Scanner + Signal Validation

IMPORTANT:
- ANALYSIS ONLY
- NU EXECUTA ORDINE
- Foloseste numai lumanari inchise
- Pastreaza semnalele in signals_v4.csv
- Valideaza semnalele la 1h / 4h / 8h / 24h
- TP/SL si MFE/MAE sunt evaluate strict in primele 24h
- WATCH nu mai creeaza semnale noi in jurnalul principal
- Evita duplicatele pentru acelasi simbol in fereastra de 24h
- Foloseste UTC pentru timestamp-uri si validare

Scoring:
Trend      30
Momentum   25
Entry      20
Volume     10
Risk       15
TOTAL     100
"""

from binance.client import Client
import numpy as np
import talib
import time
from pathlib import Path
import configparser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import csv
import shutil


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_FILE = BASE_DIR / "config.ini"
FAVORITES_FILE = BASE_DIR / "favorites.txt"

# V3 ramane intact
SIGNALS_V3_FILE = BASE_DIR / "signals.csv"

# V4/V4.1 foloseste acelasi jurnal
SIGNALS_FILE = BASE_DIR / "signals_v4.csv"


# ============================================================
# SETTINGS
# ============================================================

ALLOCATION_USDT = 10.0

SCAN_INTERVAL_SECONDS = 300

TOP_N = 5

VALIDATION_HOURS = 24

# Dupa cate ore poate exista un nou semnal
# pentru acelasi simbol.
SIGNAL_COOLDOWN_HOURS = 24

# Fuse orare pentru migrarea vechilor timestamp-uri
# V4 salva timpul local al PC-ului.
LOCAL_TIMEZONE = ZoneInfo("Europe/Bucharest")


# ============================================================
# BUY FILTERS
# ============================================================

BUY_SCORE = 75
STRONG_BUY_SCORE = 85

MIN_BUY_TREND = 18
MIN_BUY_MOMENTUM = 15
MIN_BUY_ENTRY = 10
MIN_BUY_VOLUME = 3
MIN_BUY_RISK = 7

MIN_STRONG_TREND = 25
MIN_STRONG_MOMENTUM = 20
MIN_STRONG_ENTRY = 14
MIN_STRONG_VOLUME = 3
MIN_STRONG_RISK = 7


# ============================================================
# INDICATORS
# ============================================================

RSI_PERIOD = 14

EMA_FAST = 9
EMA_SLOW = 21

SMA_FAST = 25
SMA_SLOW = 50

BB_PERIOD = 20
BB_STD = 2

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ATR_PERIOD = 14


# ============================================================
# VALIDATION
# ============================================================

VALIDATION_HORIZONS = [
    1,
    4,
    8,
    24
]


# ============================================================
# CONFIG
# ============================================================

if not CONFIG_FILE.exists():
    raise FileNotFoundError(
        f"\n❌ Nu am gasit config.ini:\n{CONFIG_FILE}"
    )


if not FAVORITES_FILE.exists():
    raise FileNotFoundError(
        f"\n❌ Nu am gasit favorites.txt:\n{FAVORITES_FILE}"
    )


config = configparser.ConfigParser()
config.read(CONFIG_FILE)


if "binance" not in config:
    raise ValueError(
        "❌ Sectiunea [binance] lipseste din config.ini"
    )


api_key = config["binance"].get(
    "api_key",
    ""
).strip()

api_secret = config["binance"].get(
    "api_secret",
    ""
).strip()


if not api_key or not api_secret:
    raise ValueError(
        "❌ api_key sau api_secret lipseste din config.ini"
    )


client = Client(
    api_key,
    api_secret
)


# ============================================================
# HELPERS
# ============================================================

def is_valid(value):

    try:
        return np.isfinite(float(value))
    except Exception:
        return False


def safe_float(value):

    try:
        return float(value)
    except Exception:
        return np.nan


def format_number(value, decimals=4):

    if not is_valid(value):
        return "N/A"

    return f"{float(value):.{decimals}f}"


def utc_now():

    return datetime.now(
        timezone.utc
    )


def format_utc(dt):

    if dt is None:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    dt = dt.astimezone(
        timezone.utc
    )

    return dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def parse_timestamp(value):

    if not value:
        return None

    value = str(value).strip()

    # --------------------------------------------------------
    # Format nou V4.1:
    # 2026-09-13T16:58:35Z
    # --------------------------------------------------------

    try:

        if value.endswith("Z"):

            return datetime.fromisoformat(
                value[:-1] + "+00:00"
            )

        dt = datetime.fromisoformat(
            value
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=LOCAL_TIMEZONE
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        pass


    # --------------------------------------------------------
    # Format vechi V4:
    # 2026-09-13 19:58:35
    #
    # V4 folosea ora locala a calculatorului.
    # O interpretam ca Europe/Bucharest.
    # --------------------------------------------------------

    try:

        dt = datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S"
        )

        dt = dt.replace(
            tzinfo=LOCAL_TIMEZONE
        )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:

        return None


def generate_signal_id(
    symbol,
    signal_time
):

    clean_symbol = (
        str(symbol)
        .upper()
        .replace("/", "")
        .replace("-", "")
    )

    timestamp_part = signal_time.strftime(
        "%Y%m%d_%H%M%S"
    )

    return (
        f"{clean_symbol}_{timestamp_part}"
    )


# ============================================================
# FAVORITES
# ============================================================

def get_favorite_pairs():

    pairs = []

    try:

        with open(
            FAVORITES_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                pairs.append(
                    line.upper()
                )

    except Exception as e:

        print(
            f"❌ Eroare favorites.txt: {e}"
        )

        return []


    return list(
        dict.fromkeys(pairs)
    )


# ============================================================
# MARKET DATA
# ============================================================

def get_klines(
    symbol,
    interval,
    limit=200
):

    try:

        klines = client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        if not klines:
            return None

        if len(klines) < 60:
            return None


        return {

            "open": np.array([
                safe_float(k[1])
                for k in klines
            ]),

            "high": np.array([
                safe_float(k[2])
                for k in klines
            ]),

            "low": np.array([
                safe_float(k[3])
                for k in klines
            ]),

            "close": np.array([
                safe_float(k[4])
                for k in klines
            ]),

            "volume": np.array([
                safe_float(k[5])
                for k in klines
            ])
        }

    except Exception as e:

        print(
            f"\n⚠️ {symbol} {interval}: {e}"
        )

        return None


def remove_open_candle(data):

    if data is None:
        return None

    return {
        key: value[:-1]
        for key, value in data.items()
    }


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(data):

    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]


    rsi = talib.RSI(
        close,
        timeperiod=RSI_PERIOD
    )


    ema9 = talib.EMA(
        close,
        timeperiod=EMA_FAST
    )


    ema21 = talib.EMA(
        close,
        timeperiod=EMA_SLOW
    )


    sma25 = talib.SMA(
        close,
        timeperiod=SMA_FAST
    )


    sma50 = talib.SMA(
        close,
        timeperiod=SMA_SLOW
    )


    macd, macd_signal, macd_hist = talib.MACD(
        close,
        fastperiod=MACD_FAST,
        slowperiod=MACD_SLOW,
        signalperiod=MACD_SIGNAL
    )


    bb_upper, bb_middle, bb_lower = talib.BBANDS(
        close,
        timeperiod=BB_PERIOD,
        nbdevup=BB_STD,
        nbdevdn=BB_STD,
        matype=0
    )


    atr = talib.ATR(
        high,
        low,
        close,
        timeperiod=ATR_PERIOD
    )


    return {

        "rsi": rsi,
        "ema9": ema9,
        "ema21": ema21,
        "sma25": sma25,
        "sma50": sma50,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "atr": atr,
        "volume": volume
    }


# ============================================================
# TREND - 30
# ============================================================

def analyze_trend(
    indicators,
    price
):

    ema9 = indicators["ema9"][-1]
    ema21 = indicators["ema21"][-1]
    sma25 = indicators["sma25"][-1]
    sma50 = indicators["sma50"][-1]


    score = 0
    reasons = []


    if not all(
        is_valid(x)
        for x in [
            ema9,
            ema21,
            sma25,
            sma50,
            price
        ]
    ):

        return 0, [
            "Trend indisponibil"
        ]


    if ema9 > ema21:

        score += 10

        reasons.append(
            "4H EMA9 > EMA21"
        )

    else:

        reasons.append(
            "4H EMA9 < EMA21"
        )


    if sma25 > sma50:

        score += 10

        reasons.append(
            "4H SMA25 > SMA50"
        )

    else:

        reasons.append(
            "4H SMA25 < SMA50"
        )


    if price > sma25:

        score += 5

        reasons.append(
            "4H pret peste SMA25"
        )

    else:

        reasons.append(
            "4H pret sub SMA25"
        )


    ema_distance = (
        abs(ema9 - ema21)
        / price
    ) * 100


    if ema_distance >= 1.0:

        score += 5

        reasons.append(
            f"Trend 4H puternic ({ema_distance:.2f}%)"
        )

    elif ema_distance >= 0.4:

        score += 3

        reasons.append(
            f"Trend 4H moderat ({ema_distance:.2f}%)"
        )

    else:

        reasons.append(
            "Trend 4H slab"
        )


    return score, reasons


# ============================================================
# MOMENTUM - 25
# ============================================================

def analyze_momentum(indicators):

    rsi = indicators["rsi"][-1]

    macd = indicators["macd"][-1]

    signal = indicators["macd_signal"][-1]

    histogram = indicators["macd_hist"][-1]


    score = 0
    reasons = []


    if not all(
        is_valid(x)
        for x in [
            rsi,
            macd,
            signal,
            histogram
        ]
    ):

        return 0, [
            "Momentum indisponibil"
        ]


    if 45 <= rsi <= 60:

        score += 10

        reasons.append(
            "RSI 45-60 - zona sanatoasa"
        )

    elif 40 <= rsi < 45:

        score += 8

        reasons.append(
            "RSI moderat - potential rebound"
        )

    elif 30 <= rsi < 40:

        score += 5

        reasons.append(
            "RSI scazut - rebound posibil"
        )

    elif 60 < rsi <= 68:

        score += 7

        reasons.append(
            "RSI bullish"
        )

    elif 68 < rsi <= 75:

        score += 3

        reasons.append(
            "RSI ridicat - risc crescut"
        )

    elif rsi < 30:

        reasons.append(
            "RSI oversold extrem"
        )

    else:

        reasons.append(
            "RSI supracumparat"
        )


    if macd > signal:

        score += 7

        reasons.append(
            "MACD bullish"
        )

    else:

        reasons.append(
            "MACD bearish"
        )


    if histogram > 0:

        score += 5

        reasons.append(
            "MACD histogram pozitiva"
        )

    else:

        reasons.append(
            "MACD histogram negativa"
        )


    macd_reference = abs(macd)


    if (
        macd_reference > 0
        and histogram > 0
        and abs(histogram) / macd_reference > 0.25
    ):

        score += 3

        reasons.append(
            "Momentum MACD puternic"
        )


    score = min(
        score,
        25
    )


    return score, reasons


# ============================================================
# ENTRY - 20
# ============================================================

def analyze_entry(
    indicators,
    price
):

    ema21 = indicators["ema21"][-1]

    lower = indicators["bb_lower"][-1]

    upper = indicators["bb_upper"][-1]


    score = 0
    reasons = []


    if not all(
        is_valid(x)
        for x in [
            ema21,
            lower,
            upper,
            price
        ]
    ):

        return 0, [
            "Entry zone indisponibila"
        ]


    distance_ema21 = (
        abs(price - ema21)
        / price
    ) * 100


    if distance_ema21 <= 0.75:

        score += 10

        reasons.append(
            "Pret aproape de EMA21 - entry bun"
        )

    elif distance_ema21 <= 1.5:

        score += 7

        reasons.append(
            "Pret relativ aproape de EMA21"
        )

    else:

        score += 2

        reasons.append(
            "Pret departe de EMA21"
        )


    band_width = upper - lower


    if band_width <= 0:

        return score, reasons


    position = (
        price - lower
    ) / band_width


    if 0.25 <= position <= 0.50:

        score += 10

        reasons.append(
            "Entry in zona favorabila Bollinger"
        )

    elif 0.50 < position <= 0.70:

        score += 6

        reasons.append(
            "Pret moderat in Bollinger"
        )

    elif position < 0.25:

        score += 4

        reasons.append(
            "Pret foarte jos Bollinger"
        )

    else:

        reasons.append(
            "Pret prea sus Bollinger"
        )


    return min(score, 20), reasons


# ============================================================
# VOLUME - 10
# ============================================================

def analyze_volume(indicators):

    volume = indicators["volume"]


    if len(volume) < 21:

        return 0, []


    current_volume = volume[-1]

    avg_volume = np.mean(
        volume[-21:-1]
    )


    if (
        not is_valid(current_volume)
        or not is_valid(avg_volume)
        or avg_volume <= 0
    ):

        return 0, []


    ratio = (
        current_volume
        / avg_volume
    )


    if ratio >= 2.0:

        return 10, [
            f"Volum foarte puternic ({ratio:.1f}x)"
        ]

    elif ratio >= 1.5:

        return 8, [
            f"Volum puternic ({ratio:.1f}x)"
        ]

    elif ratio >= 1.1:

        return 6, [
            f"Volum peste medie ({ratio:.1f}x)"
        ]

    elif ratio >= 0.8:

        return 3, [
            f"Volum normal ({ratio:.1f}x)"
        ]

    else:

        return 1, [
            f"Volum scazut ({ratio:.1f}x)"
        ]


# ============================================================
# RISK - 15
# ============================================================

def calculate_risk(
    indicators,
    price
):

    atr = indicators["atr"][-1]


    if (
        not is_valid(atr)
        or atr <= 0
        or not is_valid(price)
        or price <= 0
    ):

        return None


    atr_percent = (
        atr / price
    ) * 100


    stop_loss = price - (
        atr * 1.5
    )


    take_profit = price + (
        atr * 3
    )


    risk_amount = (
        price - stop_loss
    )


    reward_amount = (
        take_profit - price
    )


    risk_reward = (
        reward_amount / risk_amount
        if risk_amount > 0
        else 0
    )


    if 0.5 <= atr_percent <= 2.5:

        risk_score = 15

        risk_label = "Risc ATR foarte bun"

    elif atr_percent <= 4:

        risk_score = 12

        risk_label = "Risc ATR acceptabil"

    elif atr_percent <= 6:

        risk_score = 7

        risk_label = "Volatilitate ridicata"

    elif atr_percent <= 8:

        risk_score = 3

        risk_label = "Volatilitate foarte ridicata"

    else:

        risk_score = 0

        risk_label = "Volatilitate extrema"


    return {

        "atr": atr,

        "atr_percent": atr_percent,

        "stop_loss": stop_loss,

        "take_profit": take_profit,

        "risk_reward": risk_reward,

        "risk_score": risk_score,

        "risk_label": risk_label
    }


# ============================================================
# VERDICT
# ============================================================

def determine_verdict(
    score,
    trend_score,
    momentum_score,
    entry_score,
    volume_score,
    risk_score,
    rsi
):

    if score >= STRONG_BUY_SCORE:

        if (
            trend_score >= MIN_STRONG_TREND
            and momentum_score >= MIN_STRONG_MOMENTUM
            and entry_score >= MIN_STRONG_ENTRY
            and volume_score >= MIN_STRONG_VOLUME
            and risk_score >= MIN_STRONG_RISK
            and rsi >= 30
        ):

            return "STRONG BUY SETUP"


    if score >= BUY_SCORE:

        if (
            trend_score >= MIN_BUY_TREND
            and momentum_score >= MIN_BUY_MOMENTUM
            and entry_score >= MIN_BUY_ENTRY
            and volume_score >= MIN_BUY_VOLUME
            and risk_score >= MIN_BUY_RISK
            and rsi >= 30
        ):

            return "BUY SETUP"


    if score >= 55:

        return "WATCH"


    return "WAIT"


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(symbol):

    data_4h = get_klines(
        symbol,
        "4h",
        200
    )


    data_1h = get_klines(
        symbol,
        "1h",
        200
    )


    if (
        data_4h is None
        or data_1h is None
    ):

        return None


    data_4h = remove_open_candle(
        data_4h
    )


    data_1h = remove_open_candle(
        data_1h
    )


    ind_4h = calculate_indicators(
        data_4h
    )


    ind_1h = calculate_indicators(
        data_1h
    )


    price = data_1h["close"][-1]


    if not is_valid(price):

        return None


    trend_score, trend_reasons = analyze_trend(
        ind_4h,
        data_4h["close"][-1]
    )


    momentum_score, momentum_reasons = analyze_momentum(
        ind_1h
    )


    entry_score, entry_reasons = analyze_entry(
        ind_1h,
        price
    )


    volume_score, volume_reasons = analyze_volume(
        ind_1h
    )


    risk = calculate_risk(
        ind_1h,
        price
    )


    risk_score = (
        risk["risk_score"]
        if risk
        else 0
    )


    score = (
        trend_score
        + momentum_score
        + entry_score
        + volume_score
        + risk_score
    )


    score = min(
        score,
        100
    )


    rsi = ind_1h["rsi"][-1]


    if not is_valid(rsi):

        return None


    verdict = determine_verdict(
        score,
        trend_score,
        momentum_score,
        entry_score,
        volume_score,
        risk_score,
        rsi
    )


    reasons = []

    reasons.extend(
        trend_reasons
    )

    reasons.extend(
        momentum_reasons
    )

    reasons.extend(
        entry_reasons
    )

    reasons.extend(
        volume_reasons
    )


    if risk:

        reasons.append(
            risk["risk_label"]
        )


    quantity = (
        ALLOCATION_USDT / price
    )


    return {

        "timestamp": format_utc(
            utc_now()
        ),

        "symbol": symbol,

        "score": score,

        "verdict": verdict,

        "price": price,

        "quantity": quantity,

        "rsi": rsi,

        "trend_score": trend_score,

        "momentum_score": momentum_score,

        "entry_score": entry_score,

        "volume_score": volume_score,

        "risk_score": risk_score,

        "ema9": ind_1h["ema9"][-1],

        "ema21": ind_1h["ema21"][-1],

        "macd": ind_1h["macd"][-1],

        "signal": ind_1h["macd_signal"][-1],

        "risk": risk,

        "reasons": reasons
    }


# ============================================================
# V4.1 CSV HEADER
# ============================================================

V41_HEADER = [

    "signal_id",
    "signal_time",
    "symbol",
    "score",
    "verdict",
    "entry_price",
    "rsi",

    "trend_score",
    "momentum_score",
    "entry_score",
    "volume_score",
    "risk_score",

    "atr_percent",
    "stop_loss",
    "take_profit",
    "risk_reward",

    "h1_price",
    "h1_return_pct",

    "h4_price",
    "h4_return_pct",

    "h8_price",
    "h8_return_pct",

    "h24_price",
    "h24_return_pct",

    "max_favorable_pct",
    "max_adverse_pct",

    "tp_hit",
    "sl_hit",

    "validation_status",
    "final_result"
]


# ============================================================
# BACKUP
# ============================================================

def create_backup():

    if not SIGNALS_FILE.exists():

        return None


    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )


    backup_file = (
        BASE_DIR
        / f"signals_v4_backup_{timestamp}.csv"
    )


    try:

        shutil.copy2(
            SIGNALS_FILE,
            backup_file
        )

        print(
            f"💾 Backup creat:\n"
            f"   {backup_file}"
        )

        return backup_file

    except Exception as e:

        print(
            f"⚠️ Nu am putut crea backup: {e}"
        )

        return None


# ============================================================
# MIGRATION
# ============================================================

def migrate_existing_file():

    if not SIGNALS_FILE.exists():

        return


    try:

        with open(
            SIGNALS_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(
                file
            )

            old_fieldnames = (
                reader.fieldnames
                or []
            )

            rows = list(reader)

    except Exception as e:

        print(
            f"⚠️ Nu pot citi jurnalul existent: {e}"
        )

        return


    # Deja migrat
    if (
        "signal_id" in old_fieldnames
        and old_fieldnames == V41_HEADER
    ):

        return


    print(
        "\n🔧 Migrez signals_v4.csv -> V4.1..."
    )


    create_backup()


    migrated_rows = []


    for index, row in enumerate(
        rows,
        start=1
    ):

        symbol = (
            row.get("symbol", "")
            .strip()
            .upper()
        )


        parsed_time = parse_timestamp(
            row.get(
                "signal_time",
                ""
            )
        )


        if parsed_time is None:

            parsed_time = utc_now()


        signal_time = format_utc(
            parsed_time
        )


        existing_id = (
            row.get(
                "signal_id",
                ""
            )
            or ""
        ).strip()


        if existing_id:

            signal_id = existing_id

        else:

            signal_id = generate_signal_id(
                symbol,
                parsed_time
            )


            # Protectie suplimentara
            if any(
                r.get("signal_id")
                == signal_id
                for r in migrated_rows
            ):

                signal_id = (
                    f"{signal_id}_{index}"
                )


        new_row = {

            field: row.get(
                field,
                ""
            )

            for field in V41_HEADER
        }


        new_row["signal_id"] = signal_id

        new_row["signal_time"] = signal_time

        new_row["symbol"] = symbol


        migrated_rows.append(
            new_row
        )


    try:

        with open(
            SIGNALS_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=V41_HEADER
            )

            writer.writeheader()

            writer.writerows(
                migrated_rows
            )


        print(
            f"✅ Migrare terminata: "
            f"{len(migrated_rows)} semnale pastrate."
        )


    except Exception as e:

        print(
            f"❌ Eroare migrare: {e}"
        )

        raise


# ============================================================
# CSV INITIALIZATION
# ============================================================

def ensure_signal_file():

    if not SIGNALS_FILE.exists():

        with open(
            SIGNALS_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=V41_HEADER
            )

            writer.writeheader()

        return


    migrate_existing_file()


# ============================================================
# LOAD SIGNALS
# ============================================================

def load_signals():

    ensure_signal_file()

    rows = []

    try:

        with open(
            SIGNALS_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(
                file
            )

            for row in reader:

                rows.append(row)

    except Exception as e:

        print(
            f"⚠️ Nu pot citi signals_v4.csv: {e}"
        )


    return rows


# ============================================================
# SAVE ALL SIGNALS
# ============================================================

def save_all_signals(rows):

    try:

        with open(
            SIGNALS_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=V41_HEADER
            )

            writer.writeheader()

            writer.writerows(
                rows
            )

        return True

    except Exception as e:

        print(
            f"⚠️ Eroare actualizare jurnal: {e}"
        )

        return False


# ============================================================
# DUPLICATE / ACTIVE SIGNAL CHECK
# ============================================================

def has_active_signal(
    rows,
    symbol,
    now
):

    symbol = symbol.upper()


    for row in rows:

        row_symbol = (
            row.get(
                "symbol",
                ""
            )
            .strip()
            .upper()
        )


        if row_symbol != symbol:
            continue


        verdict = row.get(
            "verdict",
            ""
        )


        if verdict not in [
            "BUY SETUP",
            "STRONG BUY SETUP"
        ]:
            continue


        status = row.get(
            "validation_status",
            ""
        )


        if status not in [
            "OPEN"
        ]:
            continue


        signal_time = parse_timestamp(
            row.get(
                "signal_time",
                ""
            )
        )


        if signal_time is None:
            continue


        age = (
            now - signal_time
        ).total_seconds() / 3600


        if (
            0 <= age < SIGNAL_COOLDOWN_HOURS
        ):

            return True


    return False


# ============================================================
# SAVE NEW SIGNAL
# ============================================================

def save_signal(
    result,
    existing_rows
):

    # --------------------------------------------------------
    # V4.1:
    # WATCH NU mai este salvat ca semnal nou.
    # --------------------------------------------------------

    if result["verdict"] not in [
        "STRONG BUY SETUP",
        "BUY SETUP"
    ]:

        return False


    now = utc_now()


    # --------------------------------------------------------
    # Avoid duplicate signals
    # --------------------------------------------------------

    if has_active_signal(
        existing_rows,
        result["symbol"],
        now
    ):

        return False


    signal_time = now


    signal_id = generate_signal_id(
        result["symbol"],
        signal_time
    )


    # Protectie suplimentara
    existing_ids = {
        row.get(
            "signal_id",
            ""
        )
        for row in existing_rows
    }


    base_id = signal_id

    counter = 2


    while signal_id in existing_ids:

        signal_id = (
            f"{base_id}_{counter}"
        )

        counter += 1


    risk = result["risk"]


    if risk:

        atr_percent = risk["atr_percent"]
        stop_loss = risk["stop_loss"]
        take_profit = risk["take_profit"]
        risk_reward = risk["risk_reward"]

    else:

        atr_percent = ""
        stop_loss = ""
        take_profit = ""
        risk_reward = ""


    row = {

        "signal_id": signal_id,

        "signal_time": format_utc(
            signal_time
        ),

        "symbol": result["symbol"],

        "score": round(
            result["score"],
            2
        ),

        "verdict": result["verdict"],

        "entry_price": result["price"],

        "rsi": round(
            result["rsi"],
            2
        ),

        "trend_score": result["trend_score"],

        "momentum_score": result["momentum_score"],

        "entry_score": result["entry_score"],

        "volume_score": result["volume_score"],

        "risk_score": result["risk_score"],

        "atr_percent": atr_percent,

        "stop_loss": stop_loss,

        "take_profit": take_profit,

        "risk_reward": risk_reward,

        "h1_price": "",

        "h1_return_pct": "",

        "h4_price": "",

        "h4_return_pct": "",

        "h8_price": "",

        "h8_return_pct": "",

        "h24_price": "",

        "h24_return_pct": "",

        "max_favorable_pct": "",

        "max_adverse_pct": "",

        "tp_hit": "",

        "sl_hit": "",

        "validation_status": "OPEN",

        "final_result": ""
    }


    existing_rows.append(
        row
    )


    return True


# ============================================================
# GET CLOSED 1H KLINES FOR VALIDATION
# ============================================================

def get_validation_klines(
    symbol,
    signal_time
):

    try:

        validation_end = (
            signal_time
            + timedelta(
                hours=VALIDATION_HOURS
            )
        )


        now = utc_now()


        # Nu cerem date din viitor
        effective_end = min(
            now,
            validation_end
        )


        start_ms = int(
            signal_time.timestamp()
            * 1000
        )


        end_ms = int(
            effective_end.timestamp()
            * 1000
        )


        if end_ms <= start_ms:

            return []


        klines = client.get_klines(
            symbol=symbol,
            interval="1h",
            startTime=start_ms,
            endTime=end_ms,
            limit=30
        )


        if not klines:

            return []


        closed_klines = []


        now = utc_now()


        for candle in klines:

            candle_close = datetime.fromtimestamp(
                candle[6] / 1000,
                tz=timezone.utc
            )


            # Numai lumanari complet inchise
            if candle_close > now:
                continue


            # Strict in fereastra de 24h
            if candle_close > validation_end:
                continue


            closed_klines.append(
                candle
            )


        return closed_klines


    except Exception as e:

        print(
            f"⚠️ Validare {symbol}: {e}"
        )

        return []


# ============================================================
# HISTORICAL PRICE AT CHECKPOINT
# ============================================================

def get_price_at_or_after(
    symbol,
    target_time,
    validation_end
):

    try:

        start_ms = int(
            target_time.timestamp()
            * 1000
        )


        end_time = min(
            target_time + timedelta(hours=2),
            validation_end
        )


        end_ms = int(
            end_time.timestamp()
            * 1000
        )


        if end_ms <= start_ms:
            return None


        klines = client.get_klines(
            symbol=symbol,
            interval="1h",
            startTime=start_ms,
            endTime=end_ms,
            limit=5
        )


        if not klines:

            return None


        now = utc_now()


        for candle in klines:

            candle_close = datetime.fromtimestamp(
                candle[6] / 1000,
                tz=timezone.utc
            )


            if candle_close > now:
                continue


            if candle_close > validation_end:
                continue


            if candle_close >= target_time:

                return safe_float(
                    candle[4]
                )


        return None


    except Exception:

        return None


# ============================================================
# VALIDATE TP / SL CHRONOLOGICALLY
# ============================================================

def evaluate_tp_sl(
    klines,
    take_profit,
    stop_loss
):

    tp_hit = False
    sl_hit = False

    first_result = ""


    if (
        not is_valid(take_profit)
        or not is_valid(stop_loss)
    ):

        return (
            tp_hit,
            sl_hit,
            first_result
        )


    for candle in klines:

        high = safe_float(
            candle[2]
        )

        low = safe_float(
            candle[3]
        )


        if (
            not is_valid(high)
            or not is_valid(low)
        ):

            continue


        hit_tp = (
            high >= take_profit
        )


        hit_sl = (
            low <= stop_loss
        )


        # ----------------------------------------------------
        # Ambele in aceeasi lumanare.
        # Nu stim care a fost atins primul.
        # ----------------------------------------------------

        if hit_tp and hit_sl:

            tp_hit = True
            sl_hit = True
            first_result = "TP_AND_SL"

            return (
                tp_hit,
                sl_hit,
                first_result
            )


        # ----------------------------------------------------
        # TP atins primul
        # ----------------------------------------------------

        if hit_tp:

            tp_hit = True
            first_result = "TP"

            return (
                tp_hit,
                sl_hit,
                first_result
            )


        # ----------------------------------------------------
        # SL atins primul
        # ----------------------------------------------------

        if hit_sl:

            sl_hit = True
            first_result = "SL"

            return (
                tp_hit,
                sl_hit,
                first_result
            )


    return (
        tp_hit,
        sl_hit,
        first_result
    )


# ============================================================
# VALIDATE SIGNAL
# ============================================================

def validate_signal(row):

    signal_time = parse_timestamp(
        row.get(
            "signal_time",
            ""
        )
    )


    if signal_time is None:

        return row


    symbol = row.get(
        "symbol",
        ""
    ).strip().upper()


    entry_price = safe_float(
        row.get(
            "entry_price",
            ""
        )
    )


    stop_loss = safe_float(
        row.get(
            "stop_loss",
            ""
        )
    )


    take_profit = safe_float(
        row.get(
            "take_profit",
            ""
        )
    )


    if not is_valid(entry_price):

        return row


    now = utc_now()


    validation_end = (
        signal_time
        + timedelta(
            hours=VALIDATION_HOURS
        )
    )


    # ========================================================
    # CHECKPOINTS
    # ========================================================

    checkpoint_fields = {

        1: (
            "h1_price",
            "h1_return_pct"
        ),

        4: (
            "h4_price",
            "h4_return_pct"
        ),

        8: (
            "h8_price",
            "h8_return_pct"
        ),

        24: (
            "h24_price",
            "h24_return_pct"
        )
    }


    for hours, fields in checkpoint_fields.items():

        price_field, return_field = fields


        if row.get(price_field):

            continue


        target_time = (
            signal_time
            + timedelta(hours=hours)
        )


        if now < target_time:

            continue


        price = get_price_at_or_after(
            symbol,
            target_time,
            validation_end
        )


        if price is None:

            continue


        return_pct = (
            (
                price
                - entry_price
            )
            / entry_price
        ) * 100


        row[price_field] = str(
            price
        )


        row[return_field] = str(
            round(
                return_pct,
                4
            )
        )


    # ========================================================
    # VALIDATION CANDLES
    # ========================================================

    klines = get_validation_klines(
        symbol,
        signal_time
    )


    # ========================================================
    # TP / SL
    # ========================================================

    if (
        row.get("tp_hit", "") == ""
        and row.get("sl_hit", "") == ""
    ):

        if klines:

            (
                tp_hit,
                sl_hit,
                first_result
            ) = evaluate_tp_sl(
                klines,
                take_profit,
                stop_loss
            )


            row["tp_hit"] = str(
                tp_hit
            )


            row["sl_hit"] = str(
                sl_hit
            )


            if first_result:

                row["_first_hit"] = (
                    first_result
                )


    # ========================================================
    # MFE / MAE
    # ========================================================

    if klines:

        max_high = None
        min_low = None


        for candle in klines:

            high = safe_float(
                candle[2]
            )

            low = safe_float(
                candle[3]
            )


            if is_valid(high):

                if (
                    max_high is None
                    or high > max_high
                ):

                    max_high = high


            if is_valid(low):

                if (
                    min_low is None
                    or low < min_low
                ):

                    min_low = low


        if max_high is not None:

            mfe = (
                (
                    max_high
                    - entry_price
                )
                / entry_price
            ) * 100


            row["max_favorable_pct"] = str(
                round(
                    mfe,
                    4
                )
            )


        if min_low is not None:

            mae = (
                (
                    min_low
                    - entry_price
                )
                / entry_price
            ) * 100


            row["max_adverse_pct"] = str(
                round(
                    mae,
                    4
                )
            )


    # ========================================================
    # STATUS
    # ========================================================

    h24_done = (
        now >= validation_end
        and bool(
            row.get(
                "h24_price"
            )
        )
    )


    first_hit = row.get(
        "_first_hit",
        ""
    )


    tp_hit = (
        row.get("tp_hit")
        == "True"
    )


    sl_hit = (
        row.get("sl_hit")
        == "True"
    )


    # --------------------------------------------------------
    # TP + SL in same candle
    # --------------------------------------------------------

    if first_hit == "TP_AND_SL":

        row["validation_status"] = (
            "AMBIGUOUS"
        )

        row["final_result"] = (
            "TP_AND_SL"
        )


    # --------------------------------------------------------
    # TP hit first
    # --------------------------------------------------------

    elif first_hit == "TP":

        row["validation_status"] = (
            "CLOSED"
        )

        row["final_result"] = (
            "WIN"
        )


    # --------------------------------------------------------
    # SL hit first
    # --------------------------------------------------------

    elif first_hit == "SL":

        row["validation_status"] = (
            "CLOSED"
        )

        row["final_result"] = (
            "LOSS"
        )


    # --------------------------------------------------------
    # 24h timeout
    # --------------------------------------------------------

    elif h24_done:

        final_return = safe_float(
            row.get(
                "h24_return_pct",
                ""
            )
        )


        if is_valid(final_return):

            if final_return > 0:

                row["final_result"] = (
                    "PROFIT"
                )

            elif final_return < 0:

                row["final_result"] = (
                    "LOSS"
                )

            else:

                row["final_result"] = (
                    "FLAT"
                )


        row["validation_status"] = (
            "CLOSED"
        )


    else:

        row["validation_status"] = (
            "OPEN"
        )


    # Camp intern - nu il scriem in CSV
    row.pop(
        "_first_hit",
        None
    )


    return row


# ============================================================
# UPDATE ALL OPEN SIGNALS
# ============================================================

def validate_all_signals():

    rows = load_signals()


    if not rows:

        return


    changed = False


    for row in rows:

        if row.get(
            "validation_status"
        ) in [
            "CLOSED",
            "AMBIGUOUS"
        ]:

            continue


        old_row = row.copy()


        row = validate_signal(
            row
        )


        if row != old_row:

            changed = True


    if not changed:

        return


    save_all_signals(
        rows
    )


# ============================================================
# VALIDATION SUMMARY
# ============================================================

def print_validation_summary():

    rows = load_signals()


    if not rows:

        return


    # --------------------------------------------------------
    # Doar BUY / STRONG BUY sunt statistica principala
    # --------------------------------------------------------

    primary_rows = [

        row

        for row in rows

        if row.get("verdict")
        in [
            "BUY SETUP",
            "STRONG BUY SETUP"
        ]
    ]


    closed = [

        row

        for row in primary_rows

        if row.get(
            "validation_status"
        ) == "CLOSED"
    ]


    wins = [

        row

        for row in closed

        if row.get(
            "final_result"
        ) in [
            "WIN",
            "PROFIT"
        ]
    ]


    losses = [

        row

        for row in closed

        if row.get(
            "final_result"
        ) == "LOSS"
    ]


    ambiguous = [

        row

        for row in primary_rows

        if row.get(
            "final_result"
        ) == "TP_AND_SL"
    ]


    open_signals = [

        row

        for row in primary_rows

        if row.get(
            "validation_status"
        ) == "OPEN"
    ]


    print(
        "\n📊 VALIDARE SEMNALE BUY"
    )


    print(
        f"   Total BUY       : "
        f"{len(primary_rows)}"
    )


    print(
        f"   OPEN            : "
        f"{len(open_signals)}"
    )


    print(
        f"   Inchise         : "
        f"{len(closed)}"
    )


    print(
        f"   WIN/PROFIT      : "
        f"{len(wins)}"
    )


    print(
        f"   LOSS            : "
        f"{len(losses)}"
    )


    print(
        f"   Ambigue         : "
        f"{len(ambiguous)}"
    )


    if closed:

        effective_closed = (
            len(closed)
            - len(ambiguous)
        )


        if effective_closed > 0:

            win_rate = (
                len(wins)
                / effective_closed
            ) * 100


            print(
                f"   Win rate        : "
                f"{win_rate:.1f}%"
            )


# ============================================================
# DISPLAY
# ============================================================

def print_result(
    result,
    rank
):

    print(
        f"\n{'─' * 70}"
    )


    print(
        f"{rank}. {result['symbol']}"
    )


    print(
        f"   SCORE       : "
        f"{result['score']:.1f}/100"
    )


    print(
        f"   VERDICT     : "
        f"{result['verdict']}"
    )


    print(
        f"   PRICE       : "
        f"{format_number(result['price'], 8)} USDT"
    )


    print(
        f"   RSI         : "
        f"{format_number(result['rsi'], 2)}"
    )


    print(
        f"   Trend 4H    : "
        f"{result['trend_score']}/30"
    )


    print(
        f"   Momentum 1H : "
        f"{result['momentum_score']}/25"
    )


    print(
        f"   Entry Zone  : "
        f"{result['entry_score']}/20"
    )


    print(
        f"   Volume      : "
        f"{result['volume_score']}/10"
    )


    print(
        f"   Risk        : "
        f"{result['risk_score']}/15"
    )


    print(
        f"   EMA9/EMA21  : "
        f"{format_number(result['ema9'], 8)} / "
        f"{format_number(result['ema21'], 8)}"
    )


    print(
        f"   MACD/Signal : "
        f"{format_number(result['macd'], 6)} / "
        f"{format_number(result['signal'], 6)}"
    )


    print(
        f"   Simulare $10: "
        f"{result['quantity']:.8f}"
    )


    if result["risk"]:

        risk = result["risk"]


        print(
            f"   ATR         : "
            f"{risk['atr_percent']:.2f}%"
        )


        print(
            f"   Stop Loss   : "
            f"{format_number(risk['stop_loss'], 8)}"
        )


        print(
            f"   Take Profit : "
            f"{format_number(risk['take_profit'], 8)}"
        )


        print(
            f"   Risk/Reward : "
            f"1:{risk['risk_reward']:.2f}"
        )


    print(
        "   Motive:"
    )


    for reason in result["reasons"][:8]:

        print(
            f"      • {reason}"
        )


# ============================================================
# SCANNER
# ============================================================

def run_scanner():

    print(
        "\n" + "=" * 70
    )


    print(
        "🚀 BINANCE V6 PRO v4.1"
    )


    print(
        "⚖️ BALANCED CRYPTO SCANNER"
    )


    print(
        "🧪 SIGNAL VALIDATION ENABLED"
    )


    print(
        "⚠️ ANALIZA ONLY - NU EXECUTA ORDINE"
    )


    print(
        f"💰 Alocare simulata: "
        f"{ALLOCATION_USDT:.2f} USDT"
    )


    print(
        f"⏱️ Scanare: "
        f"{SCAN_INTERVAL_SECONDS // 60} minute"
    )


    print(
        "📊 Scoring: "
        "Trend 30 + Momentum 25 + "
        "Entry 20 + Volume 10 + Risk 15"
    )


    print(
        "🛡️ Validare: strict 24h"
    )


    print(
        "=" * 70
    )


    # --------------------------------------------------------
    # Validate previous signals
    # --------------------------------------------------------

    print(
        "\n🔄 Verific semnalele anterioare..."
    )


    validate_all_signals()


    print_validation_summary()


    # --------------------------------------------------------
    # Favorites
    # --------------------------------------------------------

    pairs = get_favorite_pairs()


    if not pairs:

        print(
            "\n❌ favorites.txt este gol."
        )

        return


    print(
        f"\n🔎 Analizez "
        f"{len(pairs)} perechi..."
    )


    results = []


    for index, symbol in enumerate(
        pairs,
        start=1
    ):

        print(
            f"[{index}/{len(pairs)}] {symbol}",
            end="\r",
            flush=True
        )


        result = analyze_pair(
            symbol
        )


        if result:

            results.append(
                result
            )


    print("\n")


    if not results:

        print(
            "❌ Nu au fost obtinute rezultate."
        )

        return


    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    # --------------------------------------------------------
    # TOP
    # --------------------------------------------------------

    print(
        "\n🏆 TOP OPORTUNITATI"
    )


    print(
        "-" * 70
    )


    for rank, result in enumerate(
        results[:TOP_N],
        start=1
    ):

        print_result(
            result,
            rank
        )


    # --------------------------------------------------------
    # Save only BUY / STRONG BUY
    # --------------------------------------------------------

    existing_rows = load_signals()

    new_signals = 0


    for result in results:

        saved = save_signal(
            result,
            existing_rows
        )


        if saved:

            new_signals += 1


    if new_signals:

        save_all_signals(
            existing_rows
        )


    # --------------------------------------------------------
    # BUY SETUPS
    # --------------------------------------------------------

    buy_setups = [

        r

        for r in results

        if r["verdict"] in [
            "STRONG BUY SETUP",
            "BUY SETUP"
        ]
    ]


    watch_setups = [

        r

        for r in results

        if r["verdict"] == "WATCH"
    ]


    print(
        "\n" + "=" * 70
    )


    print(
        f"🟢 BUY SETUPS: "
        f"{len(buy_setups)}"
    )


    if buy_setups:

        for result in buy_setups[:TOP_N]:

            print(
                f"🟢 {result['symbol']} "
                f"| {result['verdict']} "
                f"| Score: "
                f"{result['score']:.1f} "
                f"| RSI: "
                f"{result['rsi']:.2f}"
            )

    else:

        print(
            "Nu exista setup-uri suficient de puternice."
        )


    print(
        f"\n👀 WATCH: "
        f"{len(watch_setups)}"
    )


    if watch_setups:

        for result in watch_setups[:TOP_N]:

            print(
                f"👀 {result['symbol']} "
                f"| Score: "
                f"{result['score']:.1f}"
            )


    print(
        f"\n💾 Semnale BUY noi salvate: "
        f"{new_signals}"
    )


    print(
        "\n📁 Jurnal V4.1:"
    )


    print(
        f"   {SIGNALS_FILE}"
    )


    print(
        "=" * 70
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "\n📁 Folder script:"
    )

    print(
        f"   {BASE_DIR}"
    )


    print(
        "\n📄 Config:"
    )

    print(
        f"   {CONFIG_FILE}"
    )


    print(
        "\n⭐ Favorites:"
    )

    print(
        f"   {FAVORITES_FILE}"
    )


    print(
        "\n📊 Signal journal V4.1:"
    )

    print(
        f"   {SIGNALS_FILE}"
    )


    print(
        "\n🕐 Timezone validare: UTC"
    )


    ensure_signal_file()


    while True:

        try:

            start_time = utc_now()


            print(
                f"\n⏰ Scanare UTC: "
                f"{start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )


            run_scanner()


            print(
                f"\n⏳ Urmatoarea scanare in "
                f"{SCAN_INTERVAL_SECONDS // 60} minute..."
            )


            time.sleep(
                SCAN_INTERVAL_SECONDS
            )


        except KeyboardInterrupt:

            print(
                "\n\n🛑 Scanner oprit de utilizator."
            )

            break


        except Exception as e:

            print(
                f"\n❌ Eroare principala: {e}"
            )

            print(
                "Scannerul va incerca din nou in 30 secunde..."
            )

            time.sleep(30)