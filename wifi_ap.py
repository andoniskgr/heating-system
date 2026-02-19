"""
AP (Access Point) Mode - Configuration portal for WiFi setup.
Creates AP, hosts web server, scans networks, accepts user credentials.
Includes captive portal: DNS server redirects all lookups to our IP,
so connecting devices auto-open the config page.
"""

import network
import socket
try:
    from select import select
except ImportError:
    from uselect import select
import utime
import wifi_config
import wifi_credentials
import wifi_sta
import wifi_dns


def start_ap():
    """Start the Pico as an Access Point."""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(
        essid=wifi_config.AP_SSID,
        password=wifi_config.AP_PASSWORD,
    )
    ap.ifconfig((wifi_config.AP_IP, wifi_config.AP_SUBNET, wifi_config.AP_GATEWAY, wifi_config.AP_DNS))
    utime.sleep(1)
    print(f"AP started: {wifi_config.AP_SSID} @ {wifi_config.AP_IP}")


def scan_networks():
    """Scan for available WiFi networks. Returns list of (ssid, rssi) tuples."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    nets = wlan.scan()
    # nets: (ssid, bssid, channel, rssi, security, hidden)
    result = []
    seen = set()
    for n in nets:
        try:
            ssid = n[0].decode("utf-8") if n[0] else ""
        except Exception:
            ssid = ""
        if ssid and ssid not in seen:
            seen.add(ssid)
            result.append((ssid, n[3]))  # rssi
    result.sort(key=lambda x: x[1], reverse=True)  # Strongest first
    return result


def _html_escape(s):
    """Escape for HTML attribute values."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _html_form(networks):
    """Generate HTML for the configuration page."""
    opts = "".join(
        f'<option value="{_html_escape(n[0])}">{_html_escape(n[0])} (RSSI: {n[1]})</option>'
        for n in networks
    ) if networks else '<option value="">-- No networks found --</option>'
    return b"""<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pico WiFi Setup</title></head>
<body>
<h1>Pico WiFi Setup</h1>
<form action="/save" method="get">
<label>Network:</label><br>
<select name="ssid">""" + opts.encode() + b"""</select><br><br>
<label>Password:</label><br>
<input type="password" name="password" placeholder="WiFi password"><br><br>
<button type="submit">Connect</button>
</form>
<p>Or enter hidden network:</p>
<form action="/save" method="get">
<input type="text" name="ssid" placeholder="SSID"><br>
<input type="password" name="password" placeholder="Password"><br>
<button type="submit">Connect</button>
</form>
</body>
</html>"""


def _parse_query(query):
    """Parse query string into dict."""
    params = {}
    for part in query.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
    return params


def _url_decode(s):
    """Simple URL decode for form values (MicroPython compatible)."""
    if not s:
        return s
    s = s.replace("+", " ")
    result = []
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                result.append(chr(int(s[i + 1 : i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        result.append(s[i])
        i += 1
    return "".join(result)


def run_ap_config_loop():
    """
    Run AP mode configuration loop.
    User connects, selects network, enters password.
    Tries to connect up to MAX_RETRIES times.
    Returns (True, None) on success, (False, ssid) if user provided credentials
    but connection failed after retries.
    On success: credentials are saved and caller should reboot.
    Includes captive portal: DNS + HTTP redirect so browser opens automatically.
    """
    start_ap()

    # DNS server - intercepts all lookups so devices hit our IP
    dns_addr = socket.getaddrinfo("0.0.0.0", 53)[0][-1]
    dns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns_sock.setblocking(False)
    dns_sock.bind(dns_addr)

    # HTTP server
    http_addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    http_sock = socket.socket()
    http_sock.setblocking(False)
    http_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http_sock.bind(http_addr)
    http_sock.listen(1)

    user_ssid = None
    user_pass = ""
    retry_count = 0
    config_url = "http://" + wifi_config.AP_IP + "/"

    try:
        while True:
            readable, _, _ = select([dns_sock, http_sock], [], [], 0.5)

            for s in readable:
                if s is dns_sock:
                    try:
                        data, sender = dns_sock.recvfrom(256)
                        resp = wifi_dns.create_response(data, wifi_config.AP_IP)
                        if resp:
                            dns_sock.sendto(resp, sender)
                    except (OSError, IndexError):
                        pass
                    continue

                if s is http_sock:
                    try:
                        cl, _ = http_sock.accept()
                    except OSError:
                        continue

                    cl.setblocking(True)  # Block for recv/send to avoid EAGAIN
                    try:
                        data = cl.recv(1024)
                        if not data:
                            cl.close()
                            continue

                        req = data.decode("utf-8", "ignore")
                        lines = req.split("\r\n")
                        first = lines[0] if lines else ""
                        parts = first.split(" ")

                        if len(parts) < 2:
                            cl.close()
                            continue

                        method, path = parts[0], parts[1]
                        if "?" in path:
                            path, query = path.split("?", 1)
                        else:
                            query = ""

                        if path == "/save" and "ssid" in query:
                            params = _parse_query(query)
                            user_ssid = _url_decode(params.get("ssid", ""))
                            user_pass = _url_decode(params.get("password", ""))

                            if user_ssid:
                                retry_count += 1
                                if wifi_sta.connect_sta(user_ssid, user_pass):
                                    wifi_credentials.save_credentials(user_ssid, user_pass)
                                    cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
                                    cl.send(b"<h1>Connected! Rebooting...</h1>")
                                    cl.close()
                                    return True
                                elif retry_count >= wifi_config.MAX_RETRIES:
                                    retry_count = 0
                                    cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
                                    cl.send(b"<h1>Connection failed after 3 tries. Try again.</h1><a href='/'>Back</a>")
                                else:
                                    cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
                                    cl.send(b"<h1>Connection failed. Retrying...</h1><a href='/'>Back</a>")
                            else:
                                cl.send(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\nSSID required")

                        elif path == "/" or path == "/index.html":
                            networks = scan_networks()
                            html = _html_form(networks)
                            cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
                            cl.send(html)

                        else:
                            cl.send(b"HTTP/1.1 302 Found\r\nLocation: " + config_url.encode() + b"\r\nConnection: close\r\n\r\n")

                    except Exception as e:
                        print("AP request error:", e)
                    finally:
                        cl.close()

    finally:
        dns_sock.close()
        http_sock.close()
