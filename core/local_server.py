# core/local_server.py

import json
import socket
import subprocess
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from PyQt6.QtCore import QThread, pyqtSignal

class ServerThread(QThread):
    urls_received = pyqtSignal(list)
    
    def __init__(self, port=8765, main_window=None):
        super().__init__()
        self.port = port
        self.main_window = main_window
        self.server = None
        self.running = False
    
    def run(self):
        try:
            self.server = HTTPServer(('localhost', self.port), Handler)
            self.server.server_thread = self
            self.running = True
            print(f"✅ Local server running on http://localhost:{self.port}")
            
            while self.running:
                try:
                    self.server.handle_request()
                except Exception as e:
                    if self.running:
                        print(f"Server error: {e}")
                    break
                    
        except Exception as e:
            print(f"❌ Server failed: {e}")
    
    def stop(self):
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except:
                pass
        self.quit()
        self.wait()
        print("🛑 Server stopped")


class Handler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
    
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/add':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode())
                urls = data.get('urls', [])
                
                print(f"📥 Received {len(urls)} URL(s)")  # دیباگ
                
                if urls and hasattr(self.server, 'server_thread'):
                    thread = self.server.server_thread
                    if thread.main_window:
                        # حالت GUI - از main_window استفاده کن
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: thread.main_window._add_downloads_from_extension(urls))
                    else:
                        # 🔥 حالت Daemon - اجرای مستقیم با --add
                        print(f"🚀 Daemon mode: Launching FelfelDM with {len(urls)} URL(s)")
                        self._launch_with_urls(urls)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                
            except Exception as e:
                print(f"POST error: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _launch_with_urls(self, urls):
        """Launch FelfelDM with URLs in daemon mode"""
        try:
            # مسیر فایل اجرایی
            exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "FelfelDM"
            
            # اجرا با --add
            cmd = [exe_path, "--add"] + urls
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            print(f"✅ Launched: {' '.join(cmd)}")
        except Exception as e:
            print(f"❌ Failed to launch: {e}")
    
    def log_message(self, *args):
        pass


class LocalServer:
    
    def __init__(self, main_window=None):
        self.main_window = main_window
        self.thread = None
    
    def start(self, port=8765):
        if self.thread and self.thread.isRunning():
            return True
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                print(f"⚠️ Port {port} already in use")
                return True
            
            self.thread = ServerThread(port, self.main_window)
            
            if self.main_window:
                self.thread.urls_received.connect(self.main_window._add_downloads_from_extension)
            
            self.thread.start()
            return True
            
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False
    
    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None
    
    def is_running(self):
        return self.thread and self.thread.isRunning()