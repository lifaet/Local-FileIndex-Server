import base64
import http.server
import os
import socket
import socketserver
import string
import threading

stop_event = threading.Event()
authenticated_event = threading.Event()

def start_drive_server(drive_letter, port):
    class DriveRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_AUTHHEAD(self):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm=\"File Server\"')
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            # Check authentication status BEFORE processing any request
            if not authenticated_event.is_set():
                self.do_AUTHHEAD()
                self.wfile.write(bytes('Not authenticated', 'utf-8'))
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
        try:
            while not stop_event.is_set():
                httpd.handle_request()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()

def start_index_server(drives, port, username, password):
    class IndexRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_AUTHHEAD(self):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm=\"File Server\"')
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self):
            if stop_event.is_set():
                self.send_error(503, "Server is shutting down")
                return

            try:
                # Always require authentication on index server
                if self.headers.get('Authorization') is None:
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes('No authorization header received', 'utf-8'))
                    return

                auth_header = self.headers.get('Authorization')
                auth_type, encoded_credentials = auth_header.split(' ', 1)
                if auth_type.lower() != 'basic':
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes('Invalid authentication type', 'utf-8'))
                    return

                decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
                input_username, input_password = decoded_credentials.split(':', 1)

                if input_username != username or input_password != password:
                    self.do_AUTHHEAD()
                    self.wfile.write(bytes('Invalid credentials', 'utf-8'))
                    return

                authenticated_event.set()  # Set authentication on success

                # Now serve the index page
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                links = ""
                for drive, port in drives.items():
                    links += f"<a href='http://{socket.gethostbyname(socket.gethostname())}:{port}/'>{drive}</a><br>"

                html = f"<html><head><title>Drive Index</title></head><body><h1>Available Drives:</h1>{links}</body></html>"
                self.wfile.write(bytes(html, "utf-8"))

            except Exception as e:
                print(f"Error handling GET request for index server: {e}")
                self.send_error(500, "Internal Server Error")

    with socketserver.TCPServer(("", port), IndexRequestHandler) as httpd:
        print(f"Index server running at: http://{socket.gethostbyname(socket.gethostname())}:{port}")
        try:
            while not stop_event.is_set():
                httpd.handle_request()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()

if __name__ == '__main__':
    available_drives = {}
    for letter in string.ascii_uppercase:
        if os.path.exists(letter + ":\\"):
            available_drives[letter + ":"] = None

    username = "your_username"
    password = "your_password"

    start_port = 8000
    threads = []
    for drive in available_drives:
        available_drives[drive] = start_port
        thread = threading.Thread(target=start_drive_server, args=(drive, start_port))
        threads.append(thread)
        thread.start()
        start_port += 1

    index_port = start_port
    index_thread = threading.Thread(target=start_index_server, args=(available_drives, index_port, username, password))
    index_thread.start()

    try:
        while True:
            user_input = input()
            if user_input.lower() == "kill":
                print("Stopping servers...")
                stop_event.set()
                for thread in threads:
                    thread.join()
                index_thread.join()
                break
    except KeyboardInterrupt:
        print("\nStopping servers...")
        stop_event.set()
        for thread in threads:
            thread.join()
        index_thread.join()
        print("Servers stopped.")