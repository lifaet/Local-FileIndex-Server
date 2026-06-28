from flask import Flask, request, session, redirect, url_for, render_template, jsonify, send_file, make_response, Response
from pathlib import Path
import platform, string, os, uuid, time, random
from urllib.parse import unquote

app = Flask(__name__)
app.secret_key = "secret"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
PUBLIC_ACCESS_KEYS = {"1234", "567890"}

ACTIVE_SESSIONS = {}
BLOCKED_USERS = set()

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


def create_access_key():
    while True:
        length = random.randint(4, 6)
        key = ''.join(str(random.randint(0, 9)) for _ in range(length))
        if key not in PUBLIC_ACCESS_KEYS:
            return key


def create_session(username, role):
    session_id = str(uuid.uuid4())
    session["session_id"] = session_id
    session["logged_in"] = True
    session["username"] = username
    session["role"] = role
    ACTIVE_SESSIONS[session_id] = {
        "username": username,
        "role": role,
        "login_time": time.time(),
        "last_seen": time.time(),
        "current_path": "/",
        "current_file": "",
        "action": "Logged in",
        "ip": request.remote_addr or "unknown"
    }


def remove_session(session_id):
    ACTIVE_SESSIONS.pop(session_id, None)


def update_session_activity(action, current_path=None, current_file=None):
    session_id = session.get("session_id")
    if not session_id:
        return
    info = ACTIVE_SESSIONS.get(session_id)
    if not info:
        return
    info["last_seen"] = time.time()
    info["action"] = action
    if current_path is not None:
        info["current_path"] = current_path
    if current_file is not None:
        info["current_file"] = current_file


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        session_id = session.get("session_id")
        username = session.get("username")
        if not session.get("logged_in") or not session_id or session_id not in ACTIVE_SESSIONS:
            session.clear()
            return redirect(url_for("login"))
        if username in BLOCKED_USERS:
            remove_session(session_id)
            session.clear()
            return render_template("login.html", error="This account has been blocked.")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

@app.before_request
def track_session_activity():
    session_id = session.get("session_id")
    if session_id and session_id in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS[session_id]["last_seen"] = time.time()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_type = request.form.get("login_type", "public")
        if login_type == "admin":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
                return render_template("login.html", error="Invalid admin credentials")
            if username in BLOCKED_USERS:
                return render_template("login.html", error="This account has been blocked.")
            create_session(username, "admin")
            return redirect(url_for("admin_dashboard"))

        display_name = request.form.get("display_name", "").strip()
        access_key = request.form.get("access_key", "").strip()
        if not display_name or not access_key:
            return render_template("login.html", error="Name and access key are required")
        if access_key not in PUBLIC_ACCESS_KEYS:
            return render_template("login.html", error="Invalid access key")
        if display_name in BLOCKED_USERS:
            return render_template("login.html", error="This public user has been blocked.")
        create_session(display_name, "public")
        return redirect(url_for("index"))
    return render_template("login.html", error="")

@app.route("/logout")
def logout():
    session_id = session.get("session_id")
    if session_id:
        remove_session(session_id)
    session.clear()
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    return render_template("admin.html", sessions=ACTIVE_SESSIONS.values(), blocked=list(BLOCKED_USERS))

@app.route("/admin/api/sessions")
@login_required
@admin_required
def admin_sessions():
    return jsonify({
        "sessions": [
            {
                "session_id": sid,
                "username": info["username"],
                "role": info["role"],
                "login_time": info["login_time"],
                "last_seen": info["last_seen"],
                "current_path": info["current_path"],
                "current_file": info["current_file"],
                "action": info["action"],
                "ip": info["ip"]
            }
            for sid, info in ACTIVE_SESSIONS.items()
        ],
        "blocked": sorted(list(BLOCKED_USERS)),
        "access_keys": sorted(list(PUBLIC_ACCESS_KEYS))
    })

@app.route("/admin/api/action", methods=["POST"])
@login_required
@admin_required
def admin_action():
    payload = request.get_json() or {}
    action = payload.get("action")
    target_sid = payload.get("session_id")
    target_username = payload.get("username")

    if action == "force_logout" and target_sid:
        remove_session(target_sid)
        return jsonify({"success": True, "message": "User has been logged out."})

    if action == "block_user" and target_username:
        BLOCKED_USERS.add(target_username)
        for sid, info in list(ACTIVE_SESSIONS.items()):
            if info["username"] == target_username:
                remove_session(sid)
        return jsonify({"success": True, "message": f"User {target_username} has been blocked."})

    return jsonify({"success": False, "message": "Invalid action."}), 400

@app.route("/admin/api/keys", methods=["POST"])
@login_required
@admin_required
def admin_keys():
    payload = request.get_json() or {}
    action = payload.get("action")
    if action == "generate_key":
        new_key = create_access_key()
        PUBLIC_ACCESS_KEYS.add(new_key)
        return jsonify({"success": True, "key": new_key, "access_keys": sorted(list(PUBLIC_ACCESS_KEYS))})
    if action == "remove_key":
        key = payload.get("key")
        if key and key in PUBLIC_ACCESS_KEYS:
            PUBLIC_ACCESS_KEYS.remove(key)
            return jsonify({"success": True, "access_keys": sorted(list(PUBLIC_ACCESS_KEYS))})
        return jsonify({"success": False, "message": "Key not found."}), 404
    return jsonify({"success": False, "message": "Invalid action."}), 400

@app.route("/")
@login_required
def index():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    drives = list_drives()
    initial = {"folders": drives, "files": [], "current_path": "/"}
    resp = make_response(render_template("index.html", initial_data=initial, user_role=session.get("role"), username=session.get("username")))
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
    update_session_activity("Browsing directory", current_path=str(full_path), current_file="")
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
    update_session_activity("Viewing file", current_file=str(file_path), current_path=str(file_path.parent))
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
    update_session_activity("Streaming video", current_file=str(file_path), current_path=str(file_path.parent))
    
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
