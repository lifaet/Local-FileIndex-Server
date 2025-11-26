from flask import Flask, request, session, redirect, url_for, render_template, jsonify, send_file, make_response, Response
from pathlib import Path
import platform, string, os
from urllib.parse import unquote

app = Flask(__name__)
app.secret_key = "secret"

def list_drives():
    system = platform.system()
    drives = []
    if system == "Windows":
        for letter in string.ascii_uppercase:
            if os.path.exists(f"{letter}:\\"):
                drives.append(f"{letter}:\\")
    elif system == "Darwin":
        drives.append("/")
    else:
        try:
            with open("/proc/mounts", "r") as f:
                seen = set()
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mount = parts[1]
                        if not any(mount.startswith(p) for p in ["/sys", "/proc", "/dev", "/run", "/boot", "/snap"]):
                            if mount not in seen and os.path.isdir(mount):
                                try:
                                    os.listdir(mount)
                                    drives.append(mount)
                                    seen.add(mount)
                                except:
                                    pass
        except:
            drives.append("/")
    return sorted(drives)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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
    drives = list_drives()
    initial = {"folders": drives, "files": [], "current_path": "/"}
    resp = make_response(render_template("index.html", initial_data=initial))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route("/api/list/", defaults={"path": ""})
@app.route("/api/list/<path:path>")
@login_required
def api_list(path):
    decoded_path = unquote(request.args.get('path', path))
    if not decoded_path or decoded_path == "/":
        drives = list_drives()
        return jsonify({"folders": drives, "files": [], "current_path": "/"})
    
    decoded_path = os.path.normpath(decoded_path)
    if os.path.isabs(decoded_path) or (platform.system() == "Windows" and len(decoded_path) >= 2 and decoded_path[1] == ":"):
        full_path = Path(decoded_path)
    else:
        full_path = Path(decoded_path).resolve()
    
    if not full_path.exists() or not full_path.is_dir():
        return jsonify({"error": "Not found"}), 404
    
    folders, files = [], []
    try:
        for entry in full_path.iterdir():
            try:
                if entry.is_dir():
                    folders.append(entry.name)
                elif entry.is_file():
                    stat = entry.stat()
                    files.append({"name": entry.name, "size": stat.st_size, "mtime": stat.st_mtime})
            except:
                pass
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403
    except:
        return jsonify({"error": "Error listing directory"}), 500
    
    return jsonify({"folders": sorted(folders), "files": sorted(files, key=lambda x: x["name"].lower()), "current_path": str(full_path)})

@app.route("/api/view/", defaults={"path": ""})
@app.route("/api/view/<path:path>")
@login_required
def api_view(path):
    decoded_path = unquote(request.args.get('path', path))
    decoded_path = os.path.normpath(decoded_path)
    if os.path.isabs(decoded_path) or (platform.system() == "Windows" and len(decoded_path) >= 2 and decoded_path[1] == ":"):
        file_path = Path(decoded_path)
    else:
        file_path = Path(decoded_path).resolve()
    
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    
    try:
        return send_file(str(file_path), as_attachment=False)
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403
    except:
        return jsonify({"error": "Error"}), 500

@app.route("/api/stream/", defaults={"path": ""})
@app.route("/api/stream/<path:path>")
@login_required
def stream_video(path):
    decoded_path = unquote(request.args.get('path', path))
    decoded_path = os.path.normpath(decoded_path)
    if os.path.isabs(decoded_path) or (platform.system() == "Windows" and len(decoded_path) >= 2 and decoded_path[1] == ":"):
        file_path = Path(decoded_path)
    else:
        file_path = Path(decoded_path).resolve()
    
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    
    try:
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
    except:
        return jsonify({"error": "Error"}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)
