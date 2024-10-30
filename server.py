import http.server, socketserver, os, socket, base64, win32api

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"File Server\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        try:
            if self.headers.get('Authorization') is None:
                self.do_AUTHHEAD()
                self.wfile.write(bytes('No authorization header received', 'utf-8'))
                return

            elif self.headers.get('Authorization') == 'Basic ' + base64.b64encode(
                    bytes("admin:password", "utf-8")).decode("ascii"):

                if self.path == '/':
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    drives = get_available_drives()
                    links = ""
                    for drive in drives:
                        try:
                            drive_name = win32api.GetVolumeInformation(drive + "\\")[0]
                            links += f"<a href='/{drive}/'>{drive} - {drive_name}</a><br>"
                        except:
                            links += f"<a href='/{drive}/'>{drive}</a><br>"

                    html = f"<html><head><title>Drive Index</title></head><body><h1>Available Drives:</h1>{links}</body></html>"
                    self.wfile.write(bytes(html, "utf-8"))

                else:
                    drive_letter = self.path.split('/')[1]
                    if drive_letter in get_available_drives():
                        os.chdir(drive_letter + "\\")
                        self.path = self.path.replace(f"/{drive_letter}/", "/")
                        super().do_GET()
                    else:
                        self.send_error(404, "Drive not found")

            else:
                self.do_AUTHHEAD()
                self.wfile.write(bytes('Not authenticated', 'utf-8'))

        except Exception as e:
            print(f"Error handling GET request: {e}")
            self.send_error(500, "Internal Server Error")

    def translate_path(self, path):
        drive_letter = path.split('/')[1]
        path = path.replace(f"/{drive_letter}/", "/")
        path = super().translate_path(path)
        return path

def get_available_drives():
    import string
    available_drives = []
    for letter in string.ascii_uppercase:
        if os.path.exists(letter + ":\\"):
            available_drives.append(letter + ":")
    return available_drives

if __name__ == '__main__':
    with socketserver.TCPServer(("", 8000), MyHTTPRequestHandler) as httpd:
        print(f"Server running at: {socket.gethostbyname(socket.gethostname())}:8000")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server...")
            httpd.shutdown()
            print("Server stopped.")



