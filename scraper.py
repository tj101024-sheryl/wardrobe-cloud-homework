import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IMAGE_DIR = Path(__file__).parent / "static" / "images"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ScrapeError(Exception):
    pass


def _clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _iter_jsonld(node):
    if isinstance(node, list):
        for child in node:
            yield from _iter_jsonld(child)
    elif isinstance(node, dict):
        yield node
        for child in node.values():
            yield from _iter_jsonld(child)


def _pick_product_jsonld(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _iter_jsonld(data):
            node_type = node.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if any("product" in str(t).lower() for t in types):
                return node
    return None


def _image_from_value(value, base_url):
    if isinstance(value, str):
        value = value.strip()
        return urljoin(base_url, value) if value else ""
    if isinstance(value, dict):
        for key in ("url", "contentUrl", "@id"):
            if value.get(key):
                return _image_from_value(value[key], base_url)
    if isinstance(value, list):
        for child in value:
            found = _image_from_value(child, base_url)
            if found:
                return found
    return ""


def _price_from_product(product):
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return ""
    price = offers.get("price") or offers.get("lowPrice") or ""
    currency = offers.get("priceCurrency") or ""
    if price and currency:
        return f"{price} {currency}"
    return str(price)


def _normalize_url(url):
    url = url.strip()
    if not url:
        raise ScrapeError("請先貼上商品連結")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _get(url, timeout=15):
    try:
        return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=True)
    except requests.exceptions.SSLError:
        # 部分台灣電商網站憑證鏈不完整，改用不驗證憑證重試
        return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=False)


def fetch_page(url):
    try:
        resp = _get(url)
    except requests.RequestException as e:
        raise ScrapeError(f"連線失敗：{e.__class__.__name__}")
    if resp.status_code >= 400:
        raise ScrapeError(f"網站回應 {resp.status_code}，無法讀取")
    if "html" not in resp.headers.get("Content-Type", "") and "<" not in resp.text[:200]:
        raise ScrapeError("這個連結不是商品頁（回應不是網頁）")
    return resp


def parse_product(url, html):
    soup = BeautifulSoup(html, "lxml")
    base_url = url
    result = {"name": "", "image": "", "price": "", "shop": "", "url": base_url}

    product = _pick_product_jsonld(soup)
    if product:
        result["name"] = _clean_text(str(product.get("name", "")))
        result["image"] = _image_from_value(product.get("image", ""), base_url)
        result["price"] = _price_from_product(product)
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name", "")
        if brand:
            result["shop"] = _clean_text(str(brand))

    og = {
        m.get("property", ""): m.get("content", "")
        for m in soup.find_all("meta", attrs={"property": True})
    }
    tw = {
        m.get("name", ""): m.get("content", "")
        for m in soup.find_all("meta", attrs={"name": True})
    }

    if not result["name"]:
        result["name"] = _clean_text(og.get("og:title") or tw.get("twitter:title"))
    if not result["name"] and soup.title:
        result["name"] = _clean_text(soup.title.get_text())
    if not result["image"]:
        result["image"] = _image_from_value(
            og.get("og:image") or og.get("og:image:url") or tw.get("twitter:image", ""), base_url
        )
    if not result["image"]:
        for img in soup.find_all("img"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src or src.startswith("data:"):
                continue
            if any(key in src.lower() for key in ("logo", "icon", "sprite", "banner")):
                continue
            result["image"] = urljoin(base_url, src)
            break
    if not result["shop"]:
        result["shop"] = _clean_text(og.get("og:site_name"))
    if not result["shop"]:
        netloc = urlparse(base_url).netloc
        result["shop"] = netloc.replace("www.", "")

    result["name"] = result["name"][:80] or "未命名商品"
    if not result["image"]:
        raise ScrapeError("找不到商品圖，請改用「手動上傳照片」或貼圖片網址")
    return result


def download_image(image_url, page_url=""):
    parsed = urlparse(image_url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    name = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:16] + ext
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = IMAGE_DIR / name
    if target.exists():
        return f"images/{name}"
    try:
        resp = _get(image_url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        if page_url:
            return ""
        raise ScrapeError("商品圖下載失敗")
    target.write_bytes(resp.content)
    return f"images/{name}"


def scrape_product(raw_url):
    url = _normalize_url(raw_url)
    resp = fetch_page(url)
    # 傳 bytes 給 BeautifulSoup，讓它自動偵測編碼（有些台灣網站沒設 charset）
    info = parse_product(str(resp.url), resp.content)
    try:
        local = download_image(info["image"], page_url=str(resp.url))
        info["image"] = local or info["image"]
    except ScrapeError:
        pass
    return info
