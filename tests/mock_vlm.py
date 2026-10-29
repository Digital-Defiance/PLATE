"""Tiny OpenAI-compatible server for testing the VLM stage without LM Studio."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def serve(handler_reply):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": "mock-vl"}]}).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = body["messages"][0]["content"][0]["text"]
            out = {"choices": [{"message": {"content": handler_reply(text)}}]}
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(out).encode())
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1"
