"""
Scriptul verifica cea mai buna optiune dintr-o lista de active crypto
si da o notificare pentru ea cu ce cantitate ar trebui cumparata de 10$
Indicatori: < si >
"""
from binance.client import Client
import numpy as np
import talib
import time
import configparser

# Citește cheile din fișierul config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# Configurarea cheilor API
api_key = config['binance']['api_key']  # Introdu cheia API generată
api_secret = config['binance']['api_secret']  # Introdu cheia secretă generată

# Conectarea la API-ul Binance
client = Client(api_key, api_secret)



# Parametri pentru algoritm
#crypto_pairs = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'EGLDUSDT', 'DOGEUSDT','FTMUSDT', 'PEPEUSDT'] # Lista de perechi crypto
allocation_amount = 10 # Suma pe care o dorim să o investim (în USDT)
rsi_overbought = 70  # Pragul RSI pentru supracumpărare
rsi_oversold = 30  # Pragul RSI pentru supravânzare
short_ma_period = 7  # Perioada pentru Moving Average scurt
long_ma_period = 25  # Perioada pentru Moving Average lung
#profit_threshold = 1.03  # Pragul de creștere de 3%
stop_loss_threshold = 0.95  # Pragul de scădere de -5% (stop-loss)



# Funcția pentru obținerea perechilor din favorite (dintr-un fișier local)
def get_favorite_pairs():
    """Obține lista de perechi crypto din fișierul 'favorites.txt'"""
    try:
        with open("favorites.txt", "r") as file:
            pairs = [line.strip() for line in file.readlines()]
        return pairs
    except Exception as e:
        print(f"Error reading favorites: {e}")
        return []


# Funcția pentru obținerea datelor istorice
def get_historical_klines(symbol, interval='1d', limit=500):
    """Obține date istorice pentru simbolul specificat"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        closes = [float(kline[4]) for kline in klines]  # Prețul de închidere (close price)
        return np.array(closes)
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return np.array([])


def apply_indicators(closes):
    """Calcularea indicatorilor tehnici"""
    # Calcularea RSI
    rsi = talib.RSI(closes, timeperiod=14)

    # Calcularea Moving Averages
    short_ma = talib.SMA(closes, timeperiod=short_ma_period)
    long_ma = talib.SMA(closes, timeperiod=long_ma_period)

    # Calcularea MACD (12, 26, 9)
    macd, macd_signal, macd_hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)

    atr = talib.ATR(closes, closes, closes, timeperiod=14)  # Average True Range

    # Calcularea Bollinger Bands
    upper_band, middle_band, lower_band = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)

    return rsi, short_ma, long_ma, macd, macd_signal, upper_band, lower_band, middle_band


# Funcția pentru analiza unei singure perechi
def analyze_pair(pair, allocation_amount):
    """Analizează o pereche și returnează informații despre potențialul său."""
    closes = get_historical_klines(pair)

    if len(closes) < 30:  # Necesităm cel puțin 30 de puncte pentru indicatori
        print(f"Nu sunt suficiente date pentru {pair}.")
        return None

    # Calculăm indicatorii tehnici
    rsi, short_ma, long_ma, macd, macd_signal, upper_band, lower_band, middle_band = apply_indicators(closes)
    current_price = closes[-1]

    # Evaluăm condițiile de cumpărare
    if rsi[-1] < rsi_overbought and short_ma[-1] < long_ma[-1] and macd[-1] > macd_signal[-1] and current_price < \
            middle_band[-1]:
        # Calculăm scorul compozit
        macd_signal_diff = macd[-1] - macd_signal[-1]
        short_long_diff = short_ma[-1] - long_ma[-1]
        score = (100 - rsi[-1]) + (macd_signal_diff * 10) + (short_long_diff * 5)  # Ponderăm indicatorii
        return {"pair": pair, "score": score, "price": current_price, "quantity": allocation_amount / current_price}

    return None


# Funcția pentru găsirea celor mai bune trei perechi
def find_top_pairs(crypto_pairs, allocation_amount, top_n=3):
    """Găsește cele mai bune N perechi din lista analizată."""
    analyzed_pairs = []

    for pair in crypto_pairs:
        result = analyze_pair(pair, allocation_amount)
        if result:
            analyzed_pairs.append(result)

    # Sortăm perechile în funcție de scor, descrescător
    analyzed_pairs = sorted(analyzed_pairs, key=lambda x: x['score'], reverse=True)

    # Returnăm primele N perechi
    return analyzed_pairs[:top_n]


# Bucla principală
while True:
    # Obținem lista de perechi din fișier
    crypto_pairs = get_favorite_pairs()
    if not crypto_pairs:
        print("Nu există perechi favorite în fișier.")
        break

    # Găsim cele mai bune 3 perechi
    top_pairs = find_top_pairs(crypto_pairs, allocation_amount, top_n=3)

    if top_pairs:
        print("🏆 Cele mai bune 3 perechi selectate pentru tranzacționare:")
        for idx, pair_info in enumerate(top_pairs, start=1):
            print(f"{idx}. {pair_info['pair']} - Scor: {pair_info['score']:.6f}, Preț: {pair_info['price']:.6f} USDT")
            print(
                f"[NOTIFICARE] Cumpără {pair_info['quantity']:.6f} din {pair_info['pair']} la prețul de {pair_info['price']:.6f} USDT.")
    else:
        print("❌ Nicio oportunitate de tranzacționare identificată.")

    # Pauză de 60 de secunde
    time.sleep(60)