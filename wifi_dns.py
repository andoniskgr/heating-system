"""
Minimal DNS server for captive portal.
Responds to all A-record queries with our AP IP so devices hit our web server.
"""


def create_response(data, ip_addr):
    """
    Create a DNS response packet that points any query to ip_addr.
    data: raw DNS request bytes
    ip_addr: "192.168.4.1" format
    Returns response bytes.
    """
    if len(data) < 12:
        return b""
    # Header: copy ID, set response flags, 1 question, 1 answer
    packet = data[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
    # Question section (from byte 12 to end of request)
    packet += data[12:]
    # Answer: pointer to name at 0x0c, A record, IN, TTL 60, len 4, IP
    packet += b"\xC0\x0C\x00\x01\x00\x01\x00\x00\x00\x3C\x00\x04"
    packet += bytes(map(int, ip_addr.split(".")))
    return packet
