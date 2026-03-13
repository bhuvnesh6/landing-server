from flask import Flask, send_from_directory, render_template, request, redirect
import os

app = Flask(__name__)

LANDING_FOLDER = "landing_pages"

os.makedirs(LANDING_FOLDER, exist_ok=True)

# dashboard
@app.route("/")
def dashboard():
    pages = os.listdir(LANDING_FOLDER)
    pages = [p.replace(".html","") for p in pages]
    return render_template("dashboard.html", pages=pages)


# serve landing page
@app.route("/<page>")
def serve_page(page):
    return send_from_directory(LANDING_FOLDER, page + ".html")


# upload page
@app.route("/upload", methods=["GET","POST"])
def upload():
    if request.method == "POST":

        file = request.files["file"]

        if file.filename.endswith(".html"):
            filepath = os.path.join(LANDING_FOLDER, file.filename)
            file.save(filepath)

        return redirect("/")

    return render_template("upload.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7080)
