"""
Scriptul verifica cea mai buna optiune dintr-o lista de active crypto,
care are posibilitatea de crestere de 3%, cf unor indicatori
si creeaza un ordin de cumparare si de vanzare cu stop loss
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
profit_threshold = 1.03  # Pragul de creștere de 3%
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
def get_historical_klines(symbol, interval='1m', limit=500):
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

    # Calcularea MACD (12, 26, 9)
    macd, macd_signal, macd_hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)

    atr = talib.ATR(closes, closes, closes, timeperiod=14)  # Average True Range

    # Calcularea Bollinger Bands
    upper_band, middle_band, lower_band = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)

    return rsi, macd, macd_signal, upper_band, lower_band


def estimate_growth_potential(closes):
    """Estimarea potențialului de creștere a unei perechi cu cel puțin 3%"""

    if len(closes) == 0:
        return False
    rsi, macd, macd_signal, upper_band, lower_band = apply_indicators(closes)

    # Estimare pe baza indicatorilor și a prețului actual
    current_price = closes[-1]
    previous_price = closes[-2]

    # Verificăm dacă există potențial de creștere cu cel puțin 3%
    expected_growth = current_price / previous_price

    # Criteriul de cumpărare: RSI sub 30, MACD peste semnal, preț aproape de banda inferioară și o potențială creștere de 3%
    if expected_growth < profit_threshold and rsi[-1] < rsi_oversold and macd[-1] > macd_signal[-1] and current_price < \
            lower_band[-1]:
        print(f'{expected_growth:.2f} Creștere anticipată pentru perechea analizată')
        return True
    return False


# Funcția de plasare a ordinului de cumpărare
def place_order(symbol, usdt_amount):
    """Plasează ordine de cumpărare pentru perechea selectată în limita sumei alocate"""
    # Obțineți prețul curent
    try:
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        step_size = get_step_size(symbol)  # Obținem step_size pentru a rotunji corect cantitatea
        quantity = usdt_amount / price

         # Plasează ordin de cumpărare
        client.order_market_buy(symbol=symbol, quantity=quantity)
        print(f'Ordine de cumpărare plasată pentru {symbol}: {quantity} la prețul de {price} USDT')
        return price, quantity
    except Exception as e:
        print(f"Error placing buy order for {symbol}: {e}")
        return None, None

def get_step_size(symbol):
    """Obțineți step_size-ul necesar pentru rotunjirea cantităților de active"""
    info = client.get_symbol_info(symbol)
    step_size = info['filters'][2]['stepSize']
    return step_size


def monitor_market(symbol, buy_price, quantity):
    """Monitorizează piața și verifică creșterea de 3% sau scăderea de 5%"""
    while True:
        try:
            # Obțineți prețul curent
            current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])

            # Calculați creșterea procentuală
            price_change = current_price / buy_price

            # Verifică dacă prețul a crescut cu 3%
            if price_change >= profit_threshold:
                print(f'Creștere de {price_change:.2%} atinsă. Vânzare activ {symbol}.')
                client.order_market_sell(symbol=symbol, quantity=quantity)
                break
            # Verifică dacă prețul a scăzut cu mai mult de 5%
            elif price_change <= stop_loss_threshold:
                print(f'Prețul a scăzut cu {price_change:.2%}. Stop-loss activat. Vânzare activ {symbol}.')
                client.order_market_sell(symbol=symbol, quantity=quantity)
                break

        except Exception as e:
            print(f"Error monitoring market for {symbol}: {e}")

        # Pauză de 1 minut între verificări
        time.sleep(60)
        print(f"Verifica daca pretul a crescut sau scazut pentru perechea cumparata {symbol}")



# Buclă principală de verificare a pieței pentru mai multe perechi
while True:
    best_pair = None
    best_growth = 0

    # Iterăm prin perechile de crypto pentru a găsi cea mai bună oportunitate/Citim perechile de active din fișierul de favorite

    crypto_pairs = get_favorite_pairs()

    for pair in crypto_pairs:
        closes = get_historical_klines(pair)

        if estimate_growth_potential(closes):
            # Actualizăm perechea cea mai favorabilă pentru tranzacționare
            best_pair = pair
            best_growth = closes[-1] / closes[-2]

    # Dacă am găsit o pereche cu potențial de creștere, plasăm ordinul
    if best_pair:
        print(
            f'Perechea selectată pentru tranzacționare este {best_pair} cu o creștere anticipată de {best_growth:.2%}')
        buy_price, quantity = place_order(best_pair, allocation_amount)
        # Monitorizează prețul după cumpărare
        if buy_price and quantity:
            monitor_market(best_pair, buy_price, quantity)

    # Pauză de 1 minut între verificări
    time.sleep(60)
    print("Verifica piata pana gasesti o pereche")