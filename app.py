import os
import io
import zipfile
from datetime import datetime, timezone

from flask import (
    Flask, send_from_directory, render_template, request,
    redirect, jsonify, send_file, flash
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv()  # reads MONGO_URI and DB_NAME from .env

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

LANDING_FOLDER = "landing_pages"
os.makedirs(LANDING_FOLDER, exist_ok=True)

MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("DB_NAME")

mongo_ok = False
pages_col = None
links_col = None

if MONGO_URI and DB_NAME:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")  # fail fast if unreachable
        db = client[DB_NAME]
        pages_col = db["landing_pages"]   # stores html content of uploaded pages
        links_col = db["links"]           # stores entries for the Links manager tool
        mongo_ok = True
    except Exception as e:
        print(f"[warn] Could not connect to MongoDB: {e}")
else:
    print("[warn] MONGO_URI / DB_NAME not set in .env — running without MongoDB persistence.")


def safe_name(page: str) -> str:
    """Prevent path traversal; returns a filesystem-safe base name (no extension)."""
    name = secure_filename(page)
    return name.rsplit(".html", 1)[0] if name.endswith(".html") else name


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    pages = sorted(f for f in os.listdir(LANDING_FOLDER) if f.endswith(".html"))
    pages = [p.replace(".html", "") for p in pages]
    return render_template("dashboard.html", pages=pages, mongo_ok=mongo_ok)


# ---------------------------------------------------------------------------
# Serve a landing page (falls back to MongoDB copy if the file isn't on disk)
# ---------------------------------------------------------------------------
@app.route("/<page>")
def serve_page(page):
    name = safe_name(page)
    filepath = os.path.join(LANDING_FOLDER, name + ".html")

    if not os.path.exists(filepath) and mongo_ok:
        doc = pages_col.find_one({"filename": name + ".html"})
        if doc:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(doc["content"])

    if not os.path.exists(filepath):
        return "Page not found", 404

    return send_from_directory(LANDING_FOLDER, name + ".html")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename.endswith(".html"):
            filename = secure_filename(file.filename)
            content = file.read().decode("utf-8", errors="ignore")

            filepath = os.path.join(LANDING_FOLDER, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            if mongo_ok:
                pages_col.update_one(
                    {"filename": filename},
                    {"$set": {
                        "filename": filename,
                        "content": content,
                        "uploaded_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )
        return redirect("/")

    return render_template("upload.html", mongo_ok=mongo_ok)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
@app.route("/delete/<page>", methods=["POST"])
def delete_page(page):
    name = safe_name(page)
    filepath = os.path.join(LANDING_FOLDER, name + ".html")

    if os.path.exists(filepath):
        os.remove(filepath)

    if mongo_ok:
        pages_col.delete_one({"filename": name + ".html"})

    return redirect("/")


# ---------------------------------------------------------------------------
# Backup — download all current landing pages as a single .zip
# ---------------------------------------------------------------------------
@app.route("/backup")
def backup():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(LANDING_FOLDER):
            if fname.endswith(".html"):
                zf.write(os.path.join(LANDING_FOLDER, fname), fname)
    buf.seek(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"landing_pages_backup_{stamp}.zip",
    )


# ---------------------------------------------------------------------------
# Links manager (Nisha Homes tool) — UI unchanged, backed by MongoDB now
# ---------------------------------------------------------------------------
@app.route("/links")
def links_page():
    return render_template("links.html")



@app.route("/links/load")
def links_load():
    if not mongo_ok:
        return jsonify([])  # front-end falls back to its built-in preview seed data
    docs = list(links_col.find({}, {"_id": 0}))
    return jsonify(docs)


@app.route("/links/save", methods=["POST"])
def links_save():
    if not mongo_ok:
        return jsonify({"status": "error", "message": "MongoDB not configured"}), 503

    data = request.get_json(force=True, silent=True) or []
    links_col.delete_many({})
    if data:
        links_col.insert_many(data)
    return jsonify({"status": "ok", "count": len(data)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7080)