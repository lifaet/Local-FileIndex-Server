from flask import Flask, request, session, redirect, url_for, render_template, jsonify, send_file, abort, send_from_directory, Response
from pathlib import Path
import platform
import string
from ctypes import windll
from urllib.parse import unquote

app = Flask(__name__)
app.secret_key = "your-secret-key"

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def list_drives():
    system = platform.system()
    drives = []
    if system == "Windows":
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:/")
            bitmask >>= 1
    else:
        drives.append("/")
    return drives

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == "admin" and password == "admin":
            session["logged_in"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html", error="")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/api/list/", defaults={"path": ""})
@app.route("/api/list/<path:path>")
@login_required
def api_list(path):
    decoded_path = unquote(path)

    if decoded_path == "":
        drives = list_drives()
        return jsonify({
            "folders": drives,
            "files": []
        })

    if platform.system() == "Windows" and len(decoded_path) == 3 and decoded_path[1] == ":" and decoded_path[2] == "/":
        full_path = Path(decoded_path)
    else:
        full_path = Path(decoded_path).resolve()

    if not full_path.exists() or not full_path.is_dir():
        return jsonify({"error": "Directory not found"}), 404

    folders = []
    files = []
    try:
        for entry in full_path.iterdir():
            if entry.is_dir():
                folders.append(entry.name)
            elif entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "path": str(entry)
                })
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    return jsonify({
        "folders": sorted(folders),
        "files": sorted(files, key=lambda x: x["name"].lower())
    })

@app.route("/api/view/<path:filepath>")
@login_required
def api_view(filepath):
    decoded_path = unquote(filepath)
    file_path = Path(decoded_path).resolve()

    if not file_path.exists() or not file_path.is_file():
        abort(404)
    try:
        return send_file(str(file_path), as_attachment=False)
    except PermissionError:
        abort(403)

@app.route("/api/stream/<path:filepath>")
@login_required
def stream_video(filepath):
    decoded_path = unquote(filepath)
    file_path = Path(decoded_path).resolve()

    if not file_path.exists() or not file_path.is_file():
        abort(404)

    file_size = file_path.stat().st_size
    range_header = request.headers.get('Range', None)

    if not range_header:
        return send_file(str(file_path), mimetype="video/mp4")

    start, end = range_header.replace('bytes=', '').split('-')
    start = int(start)
    end = int(end) if end else file_size - 1
    length = end - start + 1

    with open(file_path, 'rb') as f:
        f.seek(start)
        data = f.read(length)

    response = Response(data, 206, mimetype="video/mp4", direct_passthrough=True)
    response.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
    response.headers.add('Accept-Ranges', 'bytes')
    return response

@app.route('/files/', defaults={'path': ''})
@app.route('/files/<path:path>')
def serve_files(path):
    # Serve your index.html regardless of path, so frontend JS handles routing
    return send_from_directory('static', 'index.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)