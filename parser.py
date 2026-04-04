import json
import time
from pathlib import Path
from urllib.parse import quote
from curl_cffi import requests
import pandas as pd
from playwright.sync_api import sync_playwright
import re

query = "пальто из натуральной шерсти"
url = "https://search.wb.ru/exactmatch/ru/common/v18/search"
detail_url = "https://www.wildberries.ru/__internal/card/cards/v4/detail"

DEST = "-1185367"
SPP = "30"

USER_DATA_DIR = Path.cwd() / ".wb-data"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
    "User-Agent": USER_AGENT,
}

search_headers = {
    **BASE_HEADERS,
    "Origin": "https://www.wildberries.ru",
    "Referer": f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote(query)}",
}

JS_WARM_DETAIL = """
async (params) => {
    const qs = new URLSearchParams(params).toString();
    const url = `/__internal/card/cards/v4/detail?${qs}`;

    try {
        await fetch(url, {
            method: "GET",
            credentials: "include",
            headers: {
                "accept": "*/*",
                "x-requested-with": "XMLHttpRequest",
                "x-spa-version": "14.4.0"
            }
        });
    } catch (e) {}
}
"""

session = requests.Session()
session.headers.update(BASE_HEADERS)

rows = []
page = 1
ids_set = set()
product_counter = 0


def detail_headers(article):
    return {
        **BASE_HEADERS,
        "Accept": "*/*",
        "Referer": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
        "X-Requested-With": "XMLHttpRequest",
        "X-SPA-Version": "14.4.0",
    }


def get_with_retry(url, params=None, headers=None, max_attempts=6, timeout=30):
    response = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(
                url,
                params=params,
                headers=headers or BASE_HEADERS,
                impersonate="chrome",
                timeout=timeout,
            )
        except Exception as e:
            wait = min(attempt, 3)
            print(
                f"request error for {url} try {attempt}/{max_attempts} err {e} waiting {wait}s"
            )
            time.sleep(wait)
            continue

        if response.status_code == 200:
            return response

        if response.status_code in (429, 500, 502, 503, 504):
            wait = min(1.5 * attempt, 6)
            print(
                f"retry {response.status_code} {url} try {attempt}/{max_attempts} waitin {wait}"
            )
            time.sleep(wait)
            continue

        return response

    return response


def get_products(payload):
    if not isinstance(payload, dict):
        return []

    products = payload.get("products")
    if isinstance(products, list):
        return products

    data = payload.get("data")
    if isinstance(data, dict):
        products = data.get("products")
        if isinstance(products, list):
            return products

    return []


def int_converter(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    try:
        return int(str(value).strip().replace(" ", ""))
    except Exception:
        return None


def fix_size_naming(value):
    if not value:
        return None

    value = str(value).strip()
    value = re.sub(r"\s*\(НА ФОТО\)\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def scan_for_price(product):
    for size in product.get("sizes") or []:
        price_info = size.get("price") or {}
        raw_price = (
            price_info.get("product")
            or price_info.get("total")
            or price_info.get("basic")
        )
        if raw_price is not None:
            return raw_price / 100
    return None


def text_converter(grouped_options):
    parts = []

    for group in grouped_options or []:
        group_name = group.get("group_name")
        group_options = group.get("options") or []

        if group_name:
            parts.append(f"[{group_name}]")

        for opt in group_options:
            name = opt.get("name")
            value = opt.get("value")
            if name:
                parts.append(f"{name}: {value}")

        parts.append("")

    return "\n".join(parts).strip()


def find_value(grouped_options, option_name):
    for group in grouped_options or []:
        for opt in group.get("options") or []:
            if opt.get("name") == option_name:
                return opt.get("value")
    return None


def get_card_json(article, basket_cache):
    vol = article // 100000
    part = article // 1000

    basket_order = []

    cached_basket = basket_cache.get(part)
    if cached_basket:
        basket_order.append(cached_basket)

    basket_order.extend(basket for basket in range(1, 41) if basket != cached_basket)

    for basket in basket_order:
        card_url = (
            f"https://basket-{basket:02d}.wbbasket.ru/"
            f"vol{vol}/part{part}/{article}/info/ru/card.json"
        )

        response = get_with_retry(
            card_url,
            headers=search_headers,
            timeout=20,
            max_attempts=2,
        )

        if not response or response.status_code != 200:
            continue

        try:
            card_json = response.json()
        except Exception:
            continue

        if card_json.get("nm_id") == article:
            basket_cache[part] = basket
            return card_json, card_url

    return None, None


def images_url_builder(card_url, photo_count):
    if not card_url or not photo_count:
        return ""

    base = card_url.replace("/info/ru/card.json", "")
    return ", ".join(f"{base}/images/big/{n}.webp" for n in range(1, photo_count + 1))


def get_sizes_from_detail(detail_product):
    result = []

    if not detail_product:
        return ""

    for size in detail_product.get("sizes") or []:
        size_name = fix_size_naming(size.get("origName") or size.get("name"))
        if size_name:
            result.append(size_name)

    return ", ".join(dict.fromkeys(result))


def get_sizes_from_card_json(card_json):
    result = []

    values = card_json.get("sizes_table", {}).get("values") or []
    for item in values:
        tech_size = fix_size_naming(item.get("tech_size"))
        if tech_size:
            result.append(tech_size)

    return ", ".join(dict.fromkeys(result))


def get_stock_total(detail_product):
    if not detail_product:
        return None

    stock_sum = 0
    found = False

    for size in detail_product.get("sizes") or []:
        for stock in size.get("stocks") or []:
            qty = int_converter(stock.get("qty"))
            if qty is not None:
                stock_sum += qty
                found = True

    if found:
        return stock_sum

    total_quantity = int_converter(detail_product.get("totalQuantity"))
    return total_quantity


def build_seller_url(supplier_id):
    if not supplier_id:
        return None
    return f"https://www.wildberries.ru/seller/{supplier_id}"


def fix_country(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def get_color_ids(card_json, article):
    result = []

    for item in card_json.get("full_colors") or []:
        nm_id = item.get("nm_id")
        if isinstance(nm_id, int):
            result.append(nm_id)

    if not result:
        for nm_id in card_json.get("colors") or []:
            if isinstance(nm_id, int):
                result.append(nm_id)

    if not result:
        result = [article]

    return list(dict.fromkeys(result))


def get_detail_map(article_ids, referer_article):
    if not article_ids:
        return {}

    params = {
        "appType": "1",
        "curr": "rub",
        "dest": DEST,
        "spp": SPP,
        "hide_vflags": "4294967296",
        "mdg": "100",
        "ab_testing": "false",
        "lang": "ru",
        "nm": ";".join(str(x) for x in article_ids),
    }

    response = get_with_retry(
        detail_url,
        params=params,
        headers=detail_headers(referer_article),
        timeout=30,
    )

    if not response or response.status_code != 200:
        return {}

    try:
        data = response.json()
    except Exception:
        return {}

    result = {}
    for p in get_products(data):
        product_id = p.get("id")
        if product_id:
            result[product_id] = p

    return result


def warm_wb_session(seed_article):
    product_url = f"https://www.wildberries.ru/catalog/{seed_article}/detail.aspx"

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            headless=True,
            locale="ru-RU",
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            """
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(product_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)

        page.evaluate(
            JS_WARM_DETAIL,
            {
                "appType": "1",
                "curr": "rub",
                "dest": DEST,
                "spp": SPP,
                "hide_vflags": "4294967296",
                "mdg": "100",
                "ab_testing": "false",
                "lang": "ru",
                "nm": str(seed_article),
            },
        )

        deadline = time.time() + 15
        while time.time() < deadline:
            cookies_map = {
                c["name"]: c["value"]
                for c in context.cookies(["https://www.wildberries.ru"])
            }
            if "x_wbaas_token" in cookies_map:
                break
            page.wait_for_timeout(1000)

        cookies = context.cookies(["https://www.wildberries.ru"])
        context.close()
        return cookies


def steal_cookies(cookies):
    for cookie in cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )


while True:
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": DEST,
        "lang": "ru",
        "page": page,
        "query": query,
        "resultset": "catalog",
        "sort": "popular",
        "spp": SPP,
    }

    response = get_with_retry(
        url,
        params=params,
        headers=search_headers,
        timeout=30,
    )

    if not response or response.status_code != 200:
        raise Exception(f"search failed on page {page}")

    data = response.json()

    products = get_products(data)

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

        rows.append(
            {
                "id": product_id,
                "name": p.get("name"),
                "brand": p.get("brand"),
                "supplier": p.get("supplier"),
                "price": scan_for_price(p),
                "product_url": f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx",
                "search_rating": (
                    p.get("reviewRating") or p.get("nmReviewRating") or p.get("rating")
                ),
                "search_reviews_count": (p.get("nmFeedbacks") or p.get("feedbacks")),
            }
        )

    print(f"Page #{page} done, {new_for_page} new products")
    print("Total products:", product_counter)

    if new_for_page == 0:  # might delete later
        print("no new products")
        break
    page += 1
    time.sleep(1)

print("Finished searching products, getting wb session")

cookies = warm_wb_session(rows[0]["id"])
steal_cookies(cookies)

print("Session ready")
basket_cache = {}
detail_cache = {}

for i, row in enumerate(rows, 1):
    article = row["id"]

    card_json, card_url = get_card_json(article, basket_cache)

    color_ids = get_color_ids(card_json, article) if card_json else [article]
    family_key = tuple(color_ids)

    if family_key not in detail_cache:
        detail_cache[family_key] = get_detail_map(color_ids, article)
        time.sleep(0.15)

    detail_product = detail_cache[family_key].get(article)

    grouped_options = card_json.get("grouped_options") if card_json else []

    supplier_id = None
    if detail_product:
        supplier_id = detail_product.get("supplierId")
    elif card_json:
        supplier_id = card_json.get("selling", {}).get("supplier_id")

    seller_url = build_seller_url(supplier_id)

    sizes = get_sizes_from_detail(detail_product)
    if not sizes and card_json:
        sizes = get_sizes_from_card_json(card_json)

    seller_name = row.get("supplier")
    if detail_product and detail_product.get("supplier"):
        seller_name = detail_product.get("supplier")

    row["article"] = article
    row["title"] = row["name"]
    row["description"] = card_json.get("description") if card_json else None
    row["image_urls"] = images_url_builder(
        card_url,
        (card_json.get("media", {}).get("photo_count") if card_json else 0),
    )
    row["characteristics"] = text_converter(grouped_options)
    row["seller_name"] = seller_name
    row["seller_url"] = seller_url
    row["sizes"] = sizes
    row["stock_total"] = get_stock_total(detail_product)

    if detail_product:
        row["rating"] = (
            detail_product.get("reviewRating")
            or detail_product.get("nmReviewRating")
            or detail_product.get("rating")
        )
        row["reviews_count"] = detail_product.get("nmFeedbacks") or detail_product.get(
            "feedbacks"
        )
    else:
        row["rating"] = row.get("search_rating")
        row["reviews_count"] = row.get("search_reviews_count")

    row["country"] = find_value(grouped_options, "Страна производства")
    row["supplier_id"] = supplier_id

    print(
        f"{i}/{len(rows)} "
        f"id={article} "
        f"detail={'ok' if detail_product else 'no'} "
        f"card={'ok' if card_json else 'no'} "
        f"rating={row['rating']} "
        f"reviews={row['reviews_count']} "
        f"stock={row['stock_total']}"
    )

print("Done with cards")

final_rows = []
for row in rows:
    final_rows.append(
        {
            "Ссылка на товар": row.get("product_url"),
            "Артикул": row.get("article"),
            "Название": row.get("title"),
            "Цена": row.get("price"),
            "Описание": row.get("description"),
            "Ссылки на изображения": row.get("image_urls"),
            "Характеристики": row.get("characteristics"),
            "Название селлера": row.get("seller_name"),
            "Ссылка на селлера": row.get("seller_url"),
            "Размеры товара": row.get("sizes"),
            "Остатки по товару": row.get("stock_total"),
            "Рейтинг": row.get("rating"),
            "Количество отзывов": row.get("reviews_count"),
            "Страна производства": row.get("country"),
        }
    )

df = pd.DataFrame(final_rows)
df.to_excel("product_list.xlsx", index=False)

filtered_df = df.copy()
filtered_df["Цена"] = pd.to_numeric(filtered_df["Цена"], errors="coerce")
filtered_df["Рейтинг"] = pd.to_numeric(filtered_df["Рейтинг"], errors="coerce")

filtered_df = filtered_df[
    (filtered_df["Рейтинг"] >= 4.5)
    & (filtered_df["Цена"] <= 10000)
    & (filtered_df["Страна производства"].fillna("").map(fix_country) == "россия")
]

filtered_df.to_excel("product_list_filtered.xlsx", index=False)

print("Done")
