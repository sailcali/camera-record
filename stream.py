# Web streaming example
# Source code from the official PiCamera package
# http://picamera.readthedocs.io/en/latest/recipes2.html#web-streaming

from cProfile import run
import io
import picamera
import logging
import socketserver
from threading import Condition
from http import server
import threading
from record import record
import datetime


PAGE="""\
<html>
<head>
<title>Kiowa Surveillance Camera</title>
</head>
<body>
<form>
 <input type="button" value="Go back!" onclick="history.back()">
</form>
<center><h1>Kiowa - Backyard Surveillance Camera</h1></center>
<center><img src="stream.mjpg" width="640" height="480"></center>
</body>
</html>
"""

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(shutdown_hour=None):
    global camera
    global my_server
    with picamera.PiCamera(resolution='640x480', framerate=24) as camera:
        global output
        output = StreamingOutput()
        #Uncomment the next line to change your Pi's Camera rotation (in degrees)
        #camera.rotation = 90
        camera.start_recording(output, format='mjpeg')
        try:
            address = ('', 8000)
            my_server = StreamingServer(address, StreamingHandler)
            # If a shutdown hour is passed to the method, it will shutdown and return at the top of that given hour
            if shutdown_hour:
                thread = threading.Thread(target=shutdown_loop, args=(shutdown_hour,))
                thread.start()
            # Either way we will stream the server
            my_server.serve_forever()
        finally:
            camera.stop_recording()

def shutdown_loop(shutdown_hour):
    dt = datetime.datetime.now()
    stop_time = datetime.datetime(dt.year,dt.month,dt.day,shutdown_hour,0,0,0)
    while True:
        if datetime.datetime.now().hour == stop_time.hour:
            my_server.shutdown()
            my_server.server_close()
            break

if __name__ == "__main__":
    
    serve()

