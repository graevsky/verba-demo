import json
import time
from pathlib import Path
from urllib.parse import quote
from curl_cffi import requests
import pandas as pd

query = "пальто из натуральной шерсти"
url = "https://search.wb.ru/exactmatch/ru/common/v18/search"


headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote(query)}",
}

rows = []
page = 1
ids_set = set()
product_counter = 0

while True:
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": -1257786,
        "lang": "ru",
        "page": page,
        "query": query,
        "resultset": "catalog",
        "sort": "popular",
        "spp": 30,
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
            print(f"{attempt}/6 wait {wait}s")
            time.sleep(wait)
            continue

        raise Exception(f"HTTP {response.status_code}\n{response.text[:1000]}")
    else:
        raise Exception(response.text[:1000])

    data = response.json()

    products = data.get("data", {}).get("products") or data.get("products", [])

    if not products:
        print(f"page {page}, no products, stopping")
        break


    new_for_page = 0

    for p in products:
        product_id = p.get("id")
        if not product_id or product_id in ids_set:
            continue

        ids_set.add(product_id)
        new_for_page += 1
        product_counter += 1

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

    print(f"Page #{page} done, {new_for_page} new products")
    print("Total products:", product_counter)

    if new_for_page == 0: # might delete later
        print("no newp roducs")
        break
    page += 1
    time.sleep(1)

df = pd.DataFrame(rows)
df.to_excel("product_list.xlsx", index=False)
