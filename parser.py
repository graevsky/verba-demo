import json
import time
from pathlib import Path
from urllib.parse import quote
from curl_cffi import requests
import pandas as pd

query = "пальто из натуральной шерсти"
url = "https://search.wb.ru/exactmatch/ru/common/v18/search"

params = {
    "appType": 1,
    "curr": "rub",
    "dest": -1257786,
    "lang": "ru",
    "page": 1,
    "query": query,
    "resultset": "catalog",
    "sort": "popular",
    "spp": 30,
}

headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote(query)}",
}

response = None

for attempt in range(1, 7):
    response = requests.get(
        url,
        params=params,
        headers=headers,
        impersonate="chrome",
        timeout=30,
    )

    if response.status_code == 200:
        break

    if response.status_code == 429:
        wait = attempt * 3
        print(f"{attempt}/5 wait {wait}s")
        time.sleep(wait)
        continue

    raise Exception(f"HTTP {response.status_code}\n{response.text[:1000]}")
else:
    raise Exception(response.text[:1000])


data = response.json()

products = data.get("data", {}).get("products") or data.get("products", [])
rows = []

for i, p in enumerate(products, 1):
    price = None
    sizes = p.get("sizes") or []
    if sizes:
        price_info = sizes[0].get("price", {})
        raw_price = (
            price_info.get("product")
            or price_info.get("total")
            or price_info.get("basic")
        )
        if raw_price is not None:
            price = raw_price / 100

    product_id = p.get("id")
    product_url = (
        f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx"
        if product_id
        else None
    )

    rows.append(
        {
            "id": product_id,
            "name": p.get("name"),
            "brand": p.get("brand"),
            "supplier": p.get("supplier"),
            "price": price,
            "product_url": product_url,
        }
    )

df = pd.DataFrame(rows)
df.to_excel("product_list.xlsx", index=False)
