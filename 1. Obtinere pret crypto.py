"""
Introduci un activ crypto si iti obtine pretul de pe Binance
"""
from binance.client import Client

# Configurarea cheilor API
api_key = '4Hebb8D6vDbP7xDWuZrpcnAoSALeHaGJeqhtvDwF6IcBwxU4jyQibnTgXRqHA8zC'  # Introdu cheia API generată de la Binance
api_secret = '7eBApG93xzVymhpwIcDVj1NP99mfZTozNDWECYCA9FSfUiSZ7RCNTLGChH6vrKfm'  # Introdu cheia secretă generată

# Conectarea la API-ul Binance
client = Client(api_key, api_secret)

# Solicităm perechea de monede de la utilizator
moneda = input("Introduceți perechea de monede (ex: BTCUSDT, ETHUSDT): ")

# Obținerea prețului curent al monedei introduse
price = client.get_symbol_ticker(symbol=moneda.upper())  # Convertim inputul la majuscule pentru compatibilitate
print(f"Prețul curent al Bitcoin: {price['price']}")