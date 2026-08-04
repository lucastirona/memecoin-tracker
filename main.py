import requests
import time

# DexPaprika endpoint for SOL
url = "https://api.dexpaprika.com/networks/solana/tokens/So11111111111111111111111111111111111111112"

def fetch_sol_data():
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()

        name = data.get("name")
        symbol = data.get("symbol")
        price = data["summary"]["price_usd"]
        volume_5m = data["summary"]["5m"]["volume_usd"]
        liquidity = data["summary"]["liquidity_usd"]

        print(f"\n{name} ({symbol})")
        print(f"Price: ${price:,.2f}")
        print(f"5m Volume: ${volume_5m:,.2f}")
        print(f"Liquidity: ${liquidity:,.2f}")

    except Exception as e:
        print(f"Error: {e}")

#while True:
    fetch_sol_data()
    time.sleep(15)