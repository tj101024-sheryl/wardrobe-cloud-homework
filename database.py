import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "wardrobe.db"

DEFAULT_CATEGORIES = ["上衣", "褲子", "外套", "襪子", "鞋子", "配件", "其他"]

DEFAULT_TAGS = ["春", "夏", "秋", "冬", "休閒", "正式", "約會", "運動"]

SEED_ITEMS = [
    {"name": "白色T-shirt", "category": "上衣", "url": "", "image": "", "price": "", "shop": ""},
    {"name": "牛仔褲", "category": "褲子", "url": "", "image": "", "price": "", "shop": ""},
    {"name": "連帽外套", "category": "外套", "url": "", "image": "", "price": "", "shop": ""},
    {"name": "運動長褲", "category": "褲子", "url": "", "image": "", "price": "", "shop": ""},
    {"name": "白色短襪", "category": "襪子", "url": "", "image": "", "price": "", "shop": ""},
    {"name": "黑色長襪", "category": "襪子", "url": "", "image": "", "price": "", "shop": ""},
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            category   TEXT NOT NULL DEFAULT '其他',
            url        TEXT DEFAULT '',
            image      TEXT DEFAULT '',
            price      TEXT DEFAULT '',
            shop       TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outfits (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            wear_date  TEXT NOT NULL UNIQUE,
            photo      TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outfit_items (
            outfit_id INTEGER NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
            item_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            PRIMARY KEY (outfit_id, item_id)
        );

        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS outfit_tags (
            outfit_id INTEGER NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
            tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (outfit_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        """
    )
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        for cat_name in DEFAULT_CATEGORIES:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
    for (cat_name,) in conn.execute("SELECT DISTINCT category FROM items").fetchall():
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
    if conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0:
        for tag_name in DEFAULT_TAGS:
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
    if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
        today = date.today().isoformat()
        for it in SEED_ITEMS:
            conn.execute(
                "INSERT INTO items (name, category, url, image, price, shop, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (it["name"], it["category"], it["url"], it["image"], it["price"], it["shop"], today),
            )
    conn.commit()
    conn.close()


def list_categories():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def category_names():
    return [c["name"] for c in list_categories()]


def add_category(name):
    name = name.strip()
    if not name:
        return None
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return None
    conn.close()
    return new_id


def rename_category(cat_id, name):
    name = name.strip()
    if not name:
        return False, "分類名稱不能空白"
    conn = get_conn()
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        conn.close()
        return False, "分類不存在"
    old_name = row["name"]
    if name != old_name and conn.execute(
        "SELECT 1 FROM categories WHERE name = ? AND id != ?", (name, cat_id)
    ).fetchone():
        conn.close()
        return False, "分類名稱重複了"
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, cat_id))
    conn.execute("UPDATE items SET category = ? WHERE category = ?", (name, old_name))
    conn.commit()
    conn.close()
    return True, "分類已更新"


def delete_category(cat_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    cats = [dict(r) for r in rows]
    target = next((c for c in cats if c["id"] == cat_id), None)
    if not target:
        conn.close()
        return False, "分類不存在"
    if len(cats) <= 1:
        conn.close()
        return False, "至少要保留一個分類"
    others = [c for c in cats if c["id"] != cat_id]
    fallback = next((c for c in others if c["name"] == "其他"), others[0])
    cur = conn.execute(
        "UPDATE items SET category = ? WHERE category = ?", (fallback["name"], target["name"])
    )
    moved = cur.rowcount
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    if moved:
        return True, f"已刪除分類，{moved} 件單品移到「{fallback['name']}」"
    return True, "已刪除分類"


def _normalize_category(category):
    names = category_names()
    if category in names:
        return category
    if "其他" in names:
        return "其他"
    return names[0] if names else "其他"


def list_items(category=""):
    conn = get_conn()
    if category and category in category_names():
        rows = conn.execute(
            "SELECT * FROM items WHERE category = ? ORDER BY id DESC", (category,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_item(name, category, url="", image="", price="", shop=""):
    category = _normalize_category(category)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (name, category, url, image, price, shop, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, category, url, image, price, shop, date.today().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_item(item_id, name, category):
    category = _normalize_category(category)
    conn = get_conn()
    conn.execute("UPDATE items SET name = ?, category = ? WHERE id = ?", (name, category, item_id))
    conn.commit()
    conn.close()


def delete_item(item_id):
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def list_tags():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tags ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_tag(name):
    name = name.strip()
    if not name:
        return None
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return None
    conn.close()
    return new_id


def rename_tag(tag_id, name):
    name = name.strip()
    if not name:
        return False
    conn = get_conn()
    try:
        conn.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    conn.close()
    return ok


def delete_tag(tag_id):
    conn = get_conn()
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def tag_counts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.id, t.name, COUNT(ot.outfit_id) AS n FROM tags t"
        " LEFT JOIN outfit_tags ot ON ot.tag_id = t.id"
        " GROUP BY t.id ORDER BY t.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _attach_tags(conn, outfits):
    for outfit in outfits:
        rows = conn.execute(
            "SELECT t.id, t.name FROM tags t JOIN outfit_tags ot ON ot.tag_id = t.id"
            " WHERE ot.outfit_id = ? ORDER BY t.id",
            (outfit["id"],),
        ).fetchall()
        outfit["tags"] = [dict(r) for r in rows]
        outfit["tag_ids"] = [r["id"] for r in rows]
    return outfits


def get_outfit_by_date(wear_date):
    conn = get_conn()
    row = conn.execute("SELECT * FROM outfits WHERE wear_date = ?", (wear_date,)).fetchone()
    if not row:
        conn.close()
        return None
    outfit = dict(row)
    items = conn.execute(
        "SELECT i.* FROM items i JOIN outfit_items oi ON oi.item_id = i.id"
        " WHERE oi.outfit_id = ? ORDER BY i.id",
        (outfit["id"],),
    ).fetchall()
    outfit["items"] = [dict(i) for i in items]
    _attach_tags(conn, [outfit])
    conn.close()
    return outfit


def save_outfit(wear_date, item_ids, photo="", tag_ids=None):
    conn = get_conn()
    row = conn.execute("SELECT id FROM outfits WHERE wear_date = ?", (wear_date,)).fetchone()
    if row:
        outfit_id = row["id"]
        if photo:
            conn.execute("UPDATE outfits SET photo = ? WHERE id = ?", (photo, outfit_id))
        conn.execute("DELETE FROM outfit_items WHERE outfit_id = ?", (outfit_id,))
    else:
        cur = conn.execute(
            "INSERT INTO outfits (wear_date, photo, created_at) VALUES (?, ?, ?)",
            (wear_date, photo, date.today().isoformat()),
        )
        outfit_id = cur.lastrowid
    for item_id in item_ids:
        conn.execute(
            "INSERT OR IGNORE INTO outfit_items (outfit_id, item_id) VALUES (?, ?)",
            (outfit_id, item_id),
        )
    if tag_ids is not None:
        conn.execute("DELETE FROM outfit_tags WHERE outfit_id = ?", (outfit_id,))
        valid = {r["id"] for r in conn.execute("SELECT id FROM tags").fetchall()}
        for tag_id in tag_ids:
            if tag_id in valid:
                conn.execute(
                    "INSERT OR IGNORE INTO outfit_tags (outfit_id, tag_id) VALUES (?, ?)",
                    (outfit_id, tag_id),
                )
    conn.commit()
    conn.close()
    return outfit_id


def update_outfit_photo(wear_date, photo):
    conn = get_conn()
    conn.execute("UPDATE outfits SET photo = ? WHERE wear_date = ?", (photo, wear_date))
    conn.commit()
    conn.close()


def list_history(limit=60, tag=""):
    conn = get_conn()
    if tag:
        rows = conn.execute(
            "SELECT DISTINCT o.* FROM outfits o"
            " JOIN outfit_tags ot ON ot.outfit_id = o.id"
            " JOIN tags t ON t.id = ot.tag_id"
            " WHERE t.name = ? ORDER BY o.wear_date DESC LIMIT ?",
            (tag, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM outfits ORDER BY wear_date DESC LIMIT ?", (limit,)
        ).fetchall()
    result = [dict(r) for r in rows]
    for outfit in result:
        items = conn.execute(
            "SELECT i.* FROM items i JOIN outfit_items oi ON oi.item_id = i.id"
            " WHERE oi.outfit_id = ? ORDER BY i.id",
            (outfit["id"],),
        ).fetchall()
        outfit["items"] = [dict(i) for i in items]
    _attach_tags(conn, result)
    conn.close()
    return result
