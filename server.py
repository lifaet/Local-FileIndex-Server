import http.server, socketserver, os, socket, string, threading

stop_event = threading.Event()  # Event to signal server shutdown

def start_drive_server(drive_letter, port):
    class DriveRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            try:
                if self.path == '/':
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()

                    os.chdir(drive_letter + "\\")
                    items = os.listdir(".")
                    links = ""
                    for item in items:
                        links += f"<a href='/{item}'>{item}</a><br>"

                    html = f"<html><head><title>Index of {drive_letter}</title></head><body><h1>Directory listing for {drive_letter}</h1>{links}</body></html>"
                    self.wfile.write(bytes(html, "utf-8"))

                else:
                    os.chdir(drive_letter + "\\")
                    super().do_GET()

            except Exception as e:
                print(f"Error handling GET request for {drive_letter}: {e}")
                self.send_error(500, "Internal Server Error")

    with socketserver.TCPServer(("", port), DriveRequestHandler) as httpd:
        print(f"Server for {drive_letter} running at: http://{socket.gethostbyname(socket.gethostname())}:{port}")
        while not stop_event.is_set():
            httpd.handle_request()  # Handle one request at a time
        httpd.server_close()  # Close the server when stop_event is set

def start_index_server(drives, port):
    class IndexRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            links = ""
            for drive, port in drives.items():
                links += f"<a href='http://{socket.gethostbyname(socket.gethostname())}:{port}/'>{drive}</a><br>"

            html = f"<html><head><title>Drive Index</title></head><body><h1>Available Drives:</h1>{links}</body></html>"
            self.wfile.write(bytes(html, "utf-8"))

    with socketserver.TCPServer(("", port), IndexRequestHandler) as httpd:
        print(f"Index server running at: http://{socket.gethostbyname(socket.gethostname())}:{port}")
        while not stop_event.is_set():
            httpd.handle_request()
        httpd.server_close()

if __name__ == '__main__':
    available_drives = {}
    for letter in string.ascii_uppercase:
        if os.path.exists(letter + ":\\"):
            available_drives[letter + ":"] = None

    start_port = 8000
    threads = []
    for drive in available_drives:
        available_drives[drive] = start_port
        thread = threading.Thread(target=start_drive_server, args=(drive, start_port))
        threads.append(thread)
        thread.start()
        start_port += 1

    index_port = start_port
    index_thread = threading.Thread(target=start_index_server, args=(available_drives, index_port))
    index_thread.start()

    try:
        while True:
            user_input = input()
            if user_input.lower() == "kill":
                print("Stopping servers...")
                stop_event.set()  # Signal all threads to stop
                for thread in threads:
                    thread.join()  # Wait for threads to finish
                index_thread.join()
                break
    except KeyboardInterrupt:
        print("Stopping servers...")
        stop_event.set()
        for thread in threads:
            thread.join()
        index_thread.join()