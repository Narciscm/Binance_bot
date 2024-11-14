"""
Scriptul verifica cea mai buna optiune dintr-o lista de active crypto
si da o notificare pentru ea cu ce cantitate ar trebui cumparata de 10$
Indicatori: > si > + 3%
"""
from binance.client import Client
import numpy as np
import talib
import time

# Configurarea cheilor API
api_key = '4Hebb8D6vDbP7xDWuZrpcnAoSALeHaGJeqhtvDwF6IcBwxU4jyQibnTgXRqHA8zC'  # Introdu cheia API generată
api_secret = '7eBApG93xzVymhpwIcDVj1NP99mfZTozNDWECYCA9FSfUiSZ7RCNTLGChH6vrKfm'  # Introdu cheia secretă generată

# Conectarea la API-ul Binance
client = Client(api_key, api_secret)

# Parametri pentru algoritm
#crypto_pairs = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'EGLDUSDT', 'DOGEUSDT','FTMUSDT', 'PEPEUSDT'] # Lista de perechi crypto
allocation_amount = 10 # Suma pe care o dorim să o investim (în USDT)
rsi_overbought = 70  # Pragul RSI pentru supracumpărare
rsi_oversold = 30  # Pragul RSI pentru supravânzare
short_ma_period = 7  # Perioada pentru Moving Average scurt
long_ma_period = 25  # Perioada pentru Moving Average lung
profit_threshold = 2.08  # Pragul de creștere de 3%
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


def evaluate_indicators(closes):
    """Evaluare bazată doar pe indicatori tehnici, fără estimare de creștere procentuală."""

    if len(closes) == 0:
        print("Nu există suficiente date pentru această pereche.")
        return False
    rsi, short_ma, long_ma, macd, macd_signal, upper_band, lower_band, middle_band = apply_indicators(closes)

    current_price = closes[-1]
    previous_price = closes[-2]

    # Verificăm dacă există potențial de creștere cu cel puțin 3%
    expected_growth = current_price / previous_price

    # Adăugăm mesaje de debug pentru a verifica valorile indicatorilor
    print(f"Evaluare pentru perechea analizată: Preț curent: {current_price}, RSI: {rsi[-1]:.4f}, MA scurt: {short_ma[-1]:.4f}, MA lung: {long_ma[-1]:.4f}, MACD: {macd[-1]:.4f}, MACD semnal: {macd_signal[-1]:.4f}")

    # Semnal de cumpărare: RSI sub pragul de supravânzare, MA scurt peste MA lung, MACD peste linia de semnal și preț aproape de banda inferioară a Bollinger Bands
    if expected_growth < profit_threshold and rsi[-1] < rsi_overbought and short_ma[-1] > long_ma[-1] and macd[-1] > macd_signal[-1] and current_price < middle_band[-1]:
        print(f'Indicatorii semnalează o potențială oportunitate pentru perechea analizată.')
        return True

    print(f'Nu a fost găsită nicio oportunitate pentru această pereche.')
    return False


# Înlocuim funcția de plasare a ordinului de cumpărare cu o notificare
def place_order_notification(symbol, usdt_amount):
    try:
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        quantity = usdt_amount / price
        print(f'[NOTIFICARE CUMPĂRARE] Ar trebui să cumpăr {quantity:.6f} din {symbol} la prețul de {price} USDT.')
        return price, quantity
    except Exception as e:
        print(f"Error simulating buy order for {symbol}: {e}")
        return None, None

def get_step_size(symbol):
    """Obțineți step_size-ul necesar pentru rotunjirea cantităților de active"""
    info = client.get_symbol_info(symbol)
    step_size = info['filters'][2]['stepSize']
    return step_size


# Înlocuim monitorizarea pieței cu notificări, fără ordine de vânzare efectivă
def monitor_market_notification(symbol, buy_price, quantity):
    while True:
        try:
            current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            price_change = current_price / buy_price

            # Verificăm dacă prețul a scăzut cu mai mult de 5% (stop-loss)
            if price_change <= stop_loss_threshold:
                print(f'[NOTIFICARE STOP-LOSS] Scădere de {price_change:.2%}. Ar trebui să activez stop-loss pentru {quantity:.6f} din {symbol}.')
                break
        except Exception as e:
            print(f"Error monitoring market for {symbol}: {e}")

        time.sleep(60)


# Buclă principală de verificare a pieței pentru mai multe perechi
while True:
    best_pair = None
    best_growth = 0

    best_rsi = float('inf')  # Începi cu o valoare mare pentru RSI
    best_macd_signal_diff = float('-inf')  # Diferența dintre MACD și linia de semnal
    best_short_long_diff = float('-inf')  # Diferența dintre MA scurt și MA lung

    # Iterăm prin perechile de crypto pentru a găsi cea mai bună oportunitate/Citim perechile de active din fișierul de favorite

    crypto_pairs = get_favorite_pairs()
    print(f"Verificăm perechile favorite: {crypto_pairs}")

    for pair in crypto_pairs:
        closes = get_historical_klines(pair)

        if len(closes) == 0:
            continue  # Treci la următoarea pereche dacă nu avem date

            # Aplicăm indicatorii tehnici pe perechea actuală
        rsi, short_ma, long_ma, macd, macd_signal, upper_band, lower_band, middle_band = apply_indicators(closes)
        current_price = closes[-1]

        # Calculăm creșterea potențială
        expected_growth = closes[-1] / closes[-2]

        # Verificăm dacă creșterea potențială este de cel puțin 3%
        if expected_growth >= profit_threshold:
            print(f'Perechea {pair} are o creștere potențială de {expected_growth:.2%}, ceea ce depășește pragul de 3%.')
        else:
            print(f'Perechea {pair} nu are o creștere potențială suficientă. Ignorăm.')
            continue  # Trecem la următoarea pereche dacă nu îndeplinește condiția de creștere de 3%

        # Verificăm dacă indicatorii îndeplinesc condițiile noastre
        if rsi[-1] < rsi_overbought and short_ma[-1] > long_ma[-1] and macd[-1] > macd_signal[-1] and current_price < middle_band[-1]:
            # Calculăm diferențele de indicatori
            macd_signal_diff = macd[-1] - macd_signal[-1]
            short_long_diff = short_ma[-1] - long_ma[-1]

            # Comparam RSI, MACD și MA pentru a alege cea mai bună pereche
            if rsi[-1] < best_rsi or \
                    (rsi[-1] == best_rsi and macd_signal_diff > best_macd_signal_diff) or \
                    (rsi[-1] == best_rsi and macd_signal_diff == best_macd_signal_diff and short_long_diff > best_short_long_diff):
                best_pair = pair
                best_rsi = rsi[-1]
                best_macd_signal_diff = macd_signal_diff
                best_short_long_diff = short_long_diff
                if evaluate_indicators(closes):
                    # Actualizăm perechea cea mai favorabilă pentru tranzacționare
                    best_pair = pair
                    best_growth = closes[-1] / closes[-2]

            # Dacă am găsit o pereche cu oportunitate bazată pe indicatori, notificăm
    if best_pair:
        print(f'Perechea selectată pentru tranzacționare este {best_pair}.')
        buy_price, quantity = place_order_notification(best_pair, allocation_amount)
        if buy_price and quantity:
            monitor_market_notification(best_pair, buy_price, quantity)
    else:
        print("Nu a fost găsită nicio oportunitate de tranzacționare.")

    # Pauză de 1 minut între verificări
    time.sleep(60)
    print("Verifica piata pana gasesti o pereche")