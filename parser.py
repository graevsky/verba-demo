import json
import time
from pathlib import Path
from urllib.parse import quote
from curl_cffi import requests


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
        print(f"{attempt}/5 wait{wait}")
        time.sleep(wait)
        continue

    raise Exception(f"HTTP {response.status_code}\n{response.text[:1000]}")
else:
    raise Exception(response.text[:1000])


data = response.json()
Path("json_dump.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
