"""
Afiseaza lista de active crypto din contul de Binance
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

# Obține lista de perechi de active bazate pe balanța contului utilizatorului
def get_favorite_pairs():
    account_info = client.get_account()
    balances = account_info['balances']
    favorite_pairs = []

    for balance in balances:
        asset = balance['asset']
        free_balance = float(balance['free'])

        if free_balance > 0 and asset != 'USDT':  # Ignorăm USDT și activele cu balanță zero
            pair = asset + 'USDT'
            favorite_pairs.append(pair)

 # Afișăm lista de perechi favorite
    print("Perechi de active favorite:")
    for pair in favorite_pairs:
        print(pair)

    return favorite_pairs

# Apelăm funcția pentru a afișa perechile de active
get_favorite_pairs()