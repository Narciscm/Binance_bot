"""
Scriptul verifica cea mai buna optiune dintr-o lista de active crypto
si da o notificare pentru ea cu ce cantitate ar trebui cumparata de 10$
Indicatori: > si >
Conditii: RSI < prag, MA scrut > MA lung, MACD > signal, Pret < banda mediana Bollinger
Trend ascendent, ieftine momentan, cu potential de crestere
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


def evaluate_pair(symbol, closes):
    """Evaluează o pereche folosind indicatorii TA-Lib"""
    if len(closes) < 30:
        return None
    rsi = talib.RSI(closes, timeperiod=14)
    macd, signal, _ = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2)

    rsi_now = rsi[-1]
    macd_now = macd[-1]
    signal_now = signal[-1]
    price = closes[-1]
    middle_band = middle[-1]

    score = 0
    if rsi_now < rsi_oversold:
        score += 1
    if macd_now > signal_now:
        score += 1
    if price < middle_band:
        score += 1

    return {
        "symbol": symbol,
        "score": score,
        "rsi": round(rsi_now, 2),
        "macd": round(macd_now, 5),
        "signal": round(signal_now, 5),
        "price": round(price, 5)
    }


# Bucla principală
while True:
    # Obținem lista de perechi din fișier
    crypto_pairs = get_favorite_pairs()
    print(f"Verific perechile favorite: {crypto_pairs}")
    results = []
    for pair in crypto_pairs:
        closes = get_historical_klines(pair)
        evaluation = evaluate_pair(pair, closes)
        if evaluation:
            results.append(evaluation)
    # Sortăm după scor descrescător
    results = sorted(results, key=lambda x: x['score'], reverse=True)

    if results:
        top3 = results[:3]
        print("\n📊 Cele mai bune 3 perechi de urmărit:")
        for r in top3:
            qty = allocation_amount / r["price"]
            print(f"- {r['symbol']} | Preț: {r['price']:.6f} | RSI: {r['rsi']:.2f} | "
                  f"MACD: {r['macd']:.4f} vs {r['signal']:.4f} | Cantitate: {qty:.6f}")
    else:
        print("❌ Nicio oportunitate de tranzacționare identificată.")

    # Pauză de 60 de secunde
    time.sleep(60)