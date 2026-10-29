import hashlib
import random
from datetime import date
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import database as db
from scraper import ScrapeError, scrape_product

app = Flask(__name__)
app.secret_key = "wardrobe-dev-secret"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
db.init_db()

UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def save_upload(file):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD:
        raise ValueError("只接受 jpg / png / webp / gif 圖片")
    if not file.filename:
        raise ValueError("請選擇照片")
    name = hashlib.sha1((file.filename + str(date.today().isoformat())).encode()).hexdigest()[:16] + ext
    file.save(UPLOAD_DIR / name)
    return f"uploads/{name}"


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/wardrobe")
def wardrobe_view():
    category = request.args.get("category", "")
    items = db.list_items(category)
    cats = db.category_names()
    counts = {c: len(db.list_items(c)) for c in cats}
    return render_template(
        "wardrobe.html",
        items=items,
        categories=cats,
        current=category,
        counts=counts,
    )


@app.route("/preview", methods=["POST"])
def preview():
    url = request.form.get("url", "")
    try:
        info = scrape_product(url)
        return jsonify({"ok": True, **info})
    except ScrapeError as e:
        return jsonify({"ok": False, "error": str(e)}), 422


@app.route("/items/add", methods=["POST"])
def add_item():
    source = request.form.get("source", "manual")
    if source == "link":
        name = request.form.get("name", "").strip()
        if not name:
            flash("請填商品名稱", "error")
            return redirect(url_for("wardrobe_view"))
        db.add_item(
            name=name,
            category=request.form.get("category", "其他"),
            url=request.form.get("url", "").strip(),
            image=request.form.get("image", "").strip(),
            price=request.form.get("price", "").strip(),
            shop=request.form.get("shop", "").strip(),
        )
        flash("已放入衣櫃", "ok")
    else:
        name = request.form.get("name", "").strip()
        file = request.files.get("photo")
        image = ""
        if file and file.filename:
            try:
                image = save_upload(file)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("wardrobe_view"))
        if not name and not image:
            flash("請填名稱或上傳照片", "error")
            return redirect(url_for("wardrobe_view"))
        db.add_item(
            name=name or "未命名單品",
            category=request.form.get("category", "其他"),
            image=image,
        )
        flash("已放入衣櫃", "ok")
    return redirect(url_for("wardrobe_view"))


@app.route("/items/<int:item_id>/edit", methods=["POST"])
def edit_item(item_id):
    name = request.form.get("name", "").strip()
    if not name:
        flash("名稱不能空白", "error")
    else:
        db.update_item(item_id, name, request.form.get("category", "其他"))
        flash("已更新", "ok")
    return redirect(request.referrer or url_for("wardrobe_view"))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    db.delete_item(item_id)
    flash("已刪除", "ok")
    return redirect(request.referrer or url_for("wardrobe_view"))


@app.route("/today")
def today():
    return render_outfit_page(date.today().isoformat())


def render_outfit_page(wear_date):
    outfit = db.get_outfit_by_date(wear_date)
    cats = db.category_names()
    by_category = {c: db.list_items(c) for c in cats}
    return render_template(
        "outfit.html",
        wear_date=wear_date,
        outfit=outfit,
        by_category=by_category,
        categories=cats,
        tags=db.list_tags(),
        is_today=wear_date == date.today().isoformat(),
    )


@app.route("/settings")
def settings():
    cats = db.list_categories()
    return render_template(
        "settings.html",
        tags=db.list_tags(),
        categories=cats,
        counts={c["name"]: len(db.list_items(c["name"])) for c in cats},
        tag_usage={t["id"]: t["n"] for t in db.tag_counts()},
    )


@app.route("/settings/tags/add", methods=["POST"])
def add_tag():
    name = request.form.get("name", "").strip()
    if not name:
        flash("分類名稱不能空白", "error")
    elif db.add_tag(name):
        flash(f"已新增穿搭分類「{name}」", "ok")
    else:
        flash("這個分類已經存在了", "error")
    return redirect(url_for("settings"))


@app.route("/settings/tags/<int:tag_id>/rename", methods=["POST"])
def rename_tag(tag_id):
    name = request.form.get("name", "").strip()
    if not name:
        flash("分類名稱不能空白", "error")
    elif db.rename_tag(tag_id, name):
        flash("穿搭分類已更新", "ok")
    else:
        flash("分類名稱重複了", "error")
    return redirect(url_for("settings"))


@app.route("/settings/tags/<int:tag_id>/delete", methods=["POST"])
def delete_tag(tag_id):
    db.delete_tag(tag_id)
    flash("已刪除穿搭分類", "ok")
    return redirect(url_for("settings"))


@app.route("/settings/categories/add", methods=["POST"])
def add_category():
    name = request.form.get("name", "").strip()
    if not name:
        flash("分類名稱不能空白", "error")
    elif db.add_category(name):
        flash(f"已新增單品分類「{name}」", "ok")
    else:
        flash("這個分類已經存在了", "error")
    return redirect(url_for("settings"))


@app.route("/settings/categories/<int:cat_id>/rename", methods=["POST"])
def rename_category(cat_id):
    name = request.form.get("name", "").strip()
    ok, msg = db.rename_category(cat_id, name)
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/settings/categories/<int:cat_id>/delete", methods=["POST"])
def delete_category(cat_id):
    ok, msg = db.delete_category(cat_id)
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/today", methods=["POST"])
def save_today():
    selected = request.form.getlist("item_id")
    ids = [int(i) for i in selected if i.isdigit()]
    if not ids:
        flash("請至少選一件衣服", "error")
        return redirect(url_for("today"))
    tag_ids = [int(i) for i in request.form.getlist("tag_id") if i.isdigit()]
    db.save_outfit(date.today().isoformat(), ids, tag_ids=tag_ids)
    flash("今日穿搭已儲存", "ok")
    return redirect(url_for("today"))


@app.route("/today/random", methods=["POST"])
def random_outfit():
    chosen = []
    for category in db.category_names():
        if category == "其他":
            continue
        pool = db.list_items(category)
        if not pool:
            continue
        if category in ("上衣", "褲子") or random.random() < 0.5:
            chosen.extend(i["id"] for i in random.sample(pool, 1))
    if not chosen:
        flash("衣櫃還沒有單品，先加幾件吧", "error")
        return redirect(url_for("wardrobe_view"))
    db.save_outfit(date.today().isoformat(), chosen)
    flash("已隨機搭配今日穿搭", "ok")
    return redirect(url_for("today"))


@app.route("/today/photo", methods=["POST"])
def upload_outfit_photo():
    file = request.files.get("photo")
    if not file or not file.filename:
        flash("請選擇照片", "error")
        return redirect(url_for("today"))
    try:
        image = save_upload(file)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("today"))
    wear_date = date.today().isoformat()
    outfit = db.get_outfit_by_date(wear_date)
    if not outfit:
        db.save_outfit(wear_date, [], photo=image)
    else:
        db.update_outfit_photo(wear_date, image)
    flash("穿搭照片已上傳", "ok")
    return redirect(url_for("today"))


@app.route("/history")
def history():
    tag = request.args.get("tag", "").strip()
    return render_template(
        "history.html",
        outfits=db.list_history(tag=tag),
        tags=db.tag_counts(),
        current_tag=tag,
    )


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True)
