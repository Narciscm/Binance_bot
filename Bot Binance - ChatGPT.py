from binance.client import Client

# Configurarea cheilor API
api_key = '4Hebb8D6vDbP7xDWuZrpcnAoSALeHaGJeqhtvDwF6IcBwxU4jyQibnTgXRqHA8zC'  # Introdu cheia API generată de la Binance
api_secret = '7eBApG93xzVymhpwIcDVj1NP99mfZTozNDWECYCA9FSfUiSZ7RCNTLGChH6vrKfm'  # Introdu cheia secretă generată

# Conectarea la API-ul Binance
client = Client(api_key, api_secret)

# Obținerea prețului curent al Bitcoin
price = client.get_symbol_ticker(symbol="BTCUSDT")
print(f"Prețul curent al Bitcoin: {price['price']}")