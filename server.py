import base64, http.server, os, socket, socketserver, string, threading, win32api, urllib.parse, time

stop_event = threading.Event()
authenticated_event = threading.Event()


def start_drive_server(drive_letter, port):

    class DriveRequestHandler(http.server.SimpleHTTPRequestHandler):

        def do_AUTHHEAD(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="File Server"')
            self.send_header("Content-type", "text/html")
            self.end_headers()

        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            if not authenticated_event.is_set():
                self.do_AUTHHEAD()
                self.wfile.write(bytes("Not authenticated", "utf-8"))
                return

            try:
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()

                    os.chdir(drive_letter + "\\")
                    items = os.listdir(".")
                    links = ""
                    for item in items:
                        links += f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid #eee;'><a href='/{item}' style='text-decoration:none;color:#333;'>{item}</a></div>"

                    html = f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>Index of {drive_letter}</title><style>body{{font-family:sans-serif;}} a{{color:#333;}}</style></head><body><h1>Directory listing for {drive_letter}</h1><a href='http://{socket.gethostbyname(socket.gethostname())}:{index_port}/' style='text-decoration:none;display:block;padding:5px 10px;margin-bottom:5px;'><strong>&#8592; Back to Index</strong></a><div style='border:1px solid #eee;border-radius:4px;overflow:hidden;'>{links}</div></body></html>"
                    self.wfile.write(bytes(html, "utf-8"))

                else:
                    os.chdir(drive_letter + "\\")
                    current_dir = urllib.parse.unquote(self.path[1:])

                    requested_path = os.path.join(drive_letter + "\\", current_dir)

                    if os.path.isfile(requested_path):
                        try:
                            with open(requested_path, "rb") as f:
                                self.send_response(200)
                                self.send_header(
                                    "Content-type", "application/octet-stream"
                                )
                                self.end_headers()
                                self.wfile.write(f.read())
                        except Exception as e:
                            print(f"Error opening file: {e}")
                            self.send_error(500, "Error opening file")

                    else:
                        back_link = ""
                        if current_dir != "":
                            parent_dir = os.path.normpath(
                                os.path.join(current_dir, os.pardir)
                            )

                            # Fix for first child directory
                            if parent_dir == ".":
                                parent_dir_name = drive_letter  # Show drive letter
                            else:
                                parent_dir_name = os.path.basename(parent_dir)
                            back_link = f"<a href='/{parent_dir}' style='text-decoration:none;display:block;padding:5px 10px;margin-bottom:5px;'><strong>&#8592; {parent_dir_name}</strong></a>"

                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    items = os.listdir(current_dir)
                    links = ""
                    for item in items:
                        item_path = os.path.join(current_dir, item)
                        item_path = urllib.parse.quote(os.path.join(current_dir, item))
                        links += f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid #eee;'><a href='/{item_path}' style='text-decoration:none;color:#333;'>{item}</a></div>"

                    # Consistent HTML structure for all directories
                    html = f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>Index of {current_dir}</title><style>body{{font-family:sans-serif;}} a{{color:#333;}}</style></head><body><h1>Directory listing for {current_dir}</h1>{back_link}<div style='border:1px solid #eee;border-radius:4px;overflow:hidden;'>{links}</div></body></html>"
                    self.wfile.write(bytes(html, "utf-8"))

            except Exception as e:
                print(f"Error handling GET request for {drive_letter}: {e}")
                self.send_error(500, "Internal Server Error")

    def serve_forever(httpd):
        with httpd:
            httpd.timeout = 1
            try:
                while not stop_event.is_set():
                    httpd.handle_request()
                    time.sleep(0.1)
            finally:
                httpd.server_close()

    # Use the original socketserver.TCPServer
    httpd = socketserver.TCPServer(("", port), DriveRequestHandler)
    server_thread = threading.Thread(target=serve_forever, args=(httpd,))
    server_thread.start()
    return server_thread


def start_index_server(drives, port, username, password):

    class IndexRequestHandler(http.server.SimpleHTTPRequestHandler):

        def do_AUTHHEAD(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="File Server"')
            self.send_header("Content-type", "text/html")
            self.end_headers()

        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            try:
                if self.headers.get("Authorization") is None:
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes("No authorization header received", "utf-8"))
                    return

                auth_header = self.headers.get("Authorization")
                auth_type, encoded_credentials = auth_header.split(" ", 1)
                if auth_type.lower() != "basic":
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes("Invalid authentication type", "utf-8"))
                    return

                decoded_credentials = base64.b64decode(encoded_credentials).decode(
                    "utf-8"
                )
                input_username, input_password = decoded_credentials.split(":", 1)

                if input_username != username or input_password != password:
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes("Invalid credentials", "utf-8"))
                    return

                authenticated_event.set()

                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                links = ""
                for drive in sorted(drives):
                    port = drives[drive]
                    try:
                        drive_name = win32api.GetVolumeInformation(drive + "\\")[0]
                        # Use the same div structure for links as in subdirectories
                        links += f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid #eee;'><a href='http://{socket.gethostbyname(socket.gethostname())}:{port}/' style='text-decoration:none;color:#333;'>{drive_name} ({drive})</a></div>"
                    except:
                        links += f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid #eee;'><a href='http://{socket.gethostbyname(socket.gethostname())}:{port}/' style='text-decoration:none;color:#333;'>{drive}</a></div>"

                # Consistent HTML structure for the index page
                html = f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>Drive Index</title><style>body{{font-family:sans-serif;}} a{{color:#333;}}</style></head><body><h1>Available Drives:</h1><div style='border:1px solid #eee;border-radius:4px;overflow:hidden;'>{links}</div></body></html>"
                self.wfile.write(bytes(html, "utf-8"))
            except Exception as e:
                print(f"Error handling GET request for index server: {e}")
                self.send_error(500, "Internal Server Error")

    def serve_forever(httpd):
        drive_list = ", ".join(drives.keys())
        print(
            f"Servers of {drive_list} are running at: http://{socket.gethostbyname(socket.gethostname())}:{port}"
        )
        with httpd:
            httpd.timeout = 1
            try:
                while not stop_event.is_set():
                    httpd.handle_request()
                    time.sleep(0.1)
            finally:
                print("Servers Shutdown!")
                httpd.server_close()

    # Use the original socketserver.TCPServer
    httpd = socketserver.TCPServer(("", port), IndexRequestHandler)
    server_thread = threading.Thread(target=serve_forever, args=(httpd,))
    server_thread.start()
    return server_thread


if __name__ == "__main__":
    available_drives = {}
    for letter in string.ascii_uppercase:
        if letter != "C" and os.path.exists(letter + ":\\"):
            available_drives[letter + ":"] = None

    username = "zrootdisk"
    password = "Zr00TD1sK!$%"

    index_port = 8000
    index_thread = threading.Thread(
        target=start_index_server,
        args=(available_drives, index_port, username, password),
    )
    index_thread.start()
    start_port = index_port + 1
    threads = []
    for drive in available_drives:
        available_drives[drive] = start_port
        thread = threading.Thread(target=start_drive_server, args=(drive, start_port))
        threads.append(thread)
        thread.start()
        start_port += 1

    def shuttingDownServers():
        print("Shutting servers...")
        stop_event.set()
        for thread in threads:
            thread.join()
        index_thread.join()

    try:
        while True:
            user_input = input()
            if user_input.lower() == "kill":
                shuttingDownServers()
            break
    except KeyboardInterrupt:
        shuttingDownServers()
