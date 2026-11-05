#!/usr/bin/env python3
"""
Pi-Pointer WebSocket Bridge  (v5 — zero external dependencies)
================================================================
Uses ONLY Python stdlib: asyncio + socket + hashlib + base64
(No 'websockets' package needed at all.)

UDP :5005  →  normalised cursor  "x,y"              → {"type":"cursor","x":…,"y":…}
UDP :5006  →  3×3 rotation matrix "r00,...,r22"     → {"type":"imu","r":[…9…]}
UDP :5007  →  button state "1" (held) / "0"         → {"type":"button","down":true|false}

Broadcasts to all connected browser clients on ws://localhost:8765.
With --system-cursor the button also presses/releases the left mouse button.

Usage (no venv needed — pure stdlib):
    python3 pc/demo/bridge.py
"""

import asyncio, json, socket, hashlib, base64, struct, sys, time, math
import os, threading, webbrowser, http.server, functools

WS_HOST    = "localhost"
WS_PORT    = 8765
UDP_CURSOR = 5005
UDP_IMU    = 5006
UDP_BUTTON = 5007

MOVE_CURSOR = "--system-cursor" in sys.argv or "--move-cursor" in sys.argv

# ── Optional OS cursor control (macOS CoreGraphics or Windows user32) ─────────
set_os_cursor = None
os_click = None
SW, SH = 1920, 1080
if MOVE_CURSOR:
    try:
        import ctypes
        if sys.platform == "darwin":
            from ctypes import c_uint32, c_double, Structure, c_void_p
            cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
            cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            class CGPoint(Structure):
                _fields_ = [('x', c_double), ('y', c_double)]
            class CGRect(Structure):
                _fields_ = [('origin', CGPoint), ('size', CGPoint)]
            cg.CGMainDisplayID.restype = c_uint32
            cg.CGDisplayBounds.argtypes = [c_uint32]
            cg.CGDisplayBounds.restype = CGRect
            main_disp = cg.CGMainDisplayID()
            bounds = cg.CGDisplayBounds(main_disp)
            SW, SH = int(bounds.size.x), int(bounds.size.y)
            cg.CGDisplayMoveCursorToPoint.argtypes = [c_uint32, CGPoint]
            cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_uint32, CGPoint, c_uint32]
            cg.CGEventCreateMouseEvent.restype = c_void_p
            cg.CGEventPost.argtypes = [c_uint32, c_void_p]
            cf.CFRelease.argtypes = [c_void_p]
            def set_os_cursor(u, v):
                pt = CGPoint(float(u * (SW - 1)), float(v * (SH - 1)))
                cg.CGDisplayMoveCursorToPoint(main_disp, pt)
                ev = cg.CGEventCreateMouseEvent(None, 5, pt, 0)
                if ev:
                    cg.CGEventPost(0, ev)
                    cf.CFRelease(ev)
            def os_click(down):
                # 1 = left mouse down, 2 = left mouse up (needs Accessibility permission)
                pt = CGPoint(float(STATE["imu_x"] * (SW - 1)), float(STATE["imu_y"] * (SH - 1)))
                ev = cg.CGEventCreateMouseEvent(None, 1 if down else 2, pt, 0)
                if ev:
                    cg.CGEventPost(0, ev)
                    cf.CFRelease(ev)
            print(f"[bridge] macOS system cursor control enabled ({SW}x{SH})")
        elif sys.platform == "win32":
            u32 = ctypes.windll.user32
            u32.SetProcessDPIAware()
            SW, SH = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
            def set_os_cursor(u, v):
                u32.SetCursorPos(int(round(u * (SW - 1))), int(round(v * (SH - 1))))
            def os_click(down):
                u32.mouse_event(0x0002 if down else 0x0004, 0, 0, 0, 0)   # left down / left up
            print(f"[bridge] Windows system cursor control enabled ({SW}x{SH})")
    except Exception as e:
        print(f"[bridge] Warning: Could not initialize OS cursor control: {e}")

# ── Tracking state ────────────────────────────────────────────────────────────
STATE = {
    "last_5005_time": 0.0,
    "last_yaw": None,
    "last_pitch": None,
    "imu_x": 0.5,
    "imu_y": 0.5,
    "btn": False,
    "pkts_5005": 0,
    "pkts_5006": 0,
    "pkts_5007": 0
}

# ── Connected clients (raw asyncio StreamWriter handles) ──────────────────────
CLIENTS: set = set()

async def broadcast(msg: str):
    payload = msg.encode()
    frame = _ws_frame(payload)
    dead = set()
    for writer in CLIENTS:
        try:
            writer.write(frame)
            await writer.drain()
        except Exception:
            dead.add(writer)
    CLIENTS.difference_update(dead)
    for writer in dead:
        try: writer.close()
        except Exception: pass

def _ws_frame(payload: bytes) -> bytes:
    ln = len(payload)
    if ln < 126:
        hdr = bytes([0x81, ln])
    elif ln < 65536:
        hdr = bytes([0x81, 126]) + struct.pack(">H", ln)
    else:
        hdr = bytes([0x81, 127]) + struct.pack(">Q", ln)
    return hdr + payload

def _ws_handshake_response(key: str) -> bytes:
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1((key + magic).encode()).digest()
    accept = base64.b64encode(digest).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    ).encode()

# ── WebSocket server ──────────────────────────────────────────────────────────
async def ws_client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        headers_raw = b""
        while b"\r\n\r\n" not in headers_raw:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
            if not chunk:
                return
            headers_raw += chunk

        key = None
        for line in headers_raw.decode(errors="replace").splitlines():
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break
        if not key:
            writer.close()
            return

        writer.write(_ws_handshake_response(key))
        await writer.drain()

        CLIENTS.add(writer)
        addr = writer.get_extra_info("peername")
        print(f"[bridge] Browser connected ({len(CLIENTS)} active) {addr}")

        while True:
            try:
                hdr = await asyncio.wait_for(reader.readexactly(2), timeout=60)
                opcode = hdr[0] & 0x0F
                masked  = (hdr[1] & 0x80) != 0
                plen    = hdr[1] & 0x7F
                if plen == 126:
                    plen = struct.unpack(">H", await reader.readexactly(2))[0]
                elif plen == 127:
                    plen = struct.unpack(">Q", await reader.readexactly(8))[0]
                mask_key = await reader.readexactly(4) if masked else b""
                payload  = await reader.readexactly(plen)
                if opcode == 8:
                    break
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionResetError):
                break
    except Exception:
        pass
    finally:
        CLIENTS.discard(writer)
        print(f"[bridge] Browser disconnected ({len(CLIENTS)} active)")
        try: writer.close()
        except Exception: pass

# ── UDP datagram protocols ────────────────────────────────────────────────────
class CursorProtocol(asyncio.DatagramProtocol):
    """UDP :5005 — 'x,y' normalised cursor from pointer_imu.py"""
    def datagram_received(self, data, addr):
        try:
            parts = data.decode().strip().split(",")
            x, y = float(parts[0]), float(parts[1])
            x = min(max(x, 0.0), 1.0)
            y = min(max(y, 0.0), 1.0)
            STATE["last_5005_time"] = time.time()
            STATE["pkts_5005"] += 1
            STATE["imu_x"] = x
            STATE["imu_y"] = y

            msg = json.dumps({"type": "cursor", "x": round(x, 5), "y": round(y, 5), "source": "fused"})
            asyncio.get_event_loop().create_task(broadcast(msg))

            if set_os_cursor:
                set_os_cursor(x, y)
        except Exception:
            pass

class ImuProtocol(asyncio.DatagramProtocol):
    """UDP :5006 — 9 floats (3×3 rotation matrix) from pointer_imu.py"""
    def datagram_received(self, data, addr):
        try:
            vals = [float(v) for v in data.decode().strip().split(",")]
            if len(vals) == 9:
                STATE["pkts_5006"] += 1
                now = time.time()

                # Always broadcast IMU matrix
                msg = json.dumps({"type": "imu", "r": vals})
                asyncio.get_event_loop().create_task(broadcast(msg))

                # If no UDP 5005 packets recently arrived (>0.25s), derive cursor from IMU!
                yaw = math.degrees(math.atan2(vals[2], vals[8]))
                pitch = math.degrees(math.asin(max(-1.0, min(1.0, -vals[5]))))

                if (now - STATE["last_5005_time"]) > 0.25:
                    if STATE["last_yaw"] is not None and STATE["last_pitch"] is not None:
                        dyaw = yaw - STATE["last_yaw"]
                        dpitch = pitch - STATE["last_pitch"]
                        if dyaw > 180: dyaw -= 360
                        elif dyaw < -180: dyaw += 360
                        if dpitch > 180: dpitch -= 360
                        elif dpitch < -180: dpitch += 360

                        # Screen sensitivity: ~0.05 screen fraction per degree
                        STATE["imu_x"] = min(max(STATE["imu_x"] + dyaw * 0.05, 0.0), 1.0)
                        STATE["imu_y"] = min(max(STATE["imu_y"] + dpitch * 0.07, 0.0), 1.0)

                        cur_msg = json.dumps({
                            "type": "cursor",
                            "x": round(STATE["imu_x"], 5),
                            "y": round(STATE["imu_y"], 5),
                            "source": "imu_derived"
                        })
                        asyncio.get_event_loop().create_task(broadcast(cur_msg))

                        if set_os_cursor:
                            set_os_cursor(STATE["imu_x"], STATE["imu_y"])

                STATE["last_yaw"] = yaw
                STATE["last_pitch"] = pitch
        except Exception:
            pass

class ButtonProtocol(asyncio.DatagramProtocol):
    """UDP :5007 — '1' while the button is held, '0' when released (Pi repeats it as a heartbeat)"""
    def datagram_received(self, data, addr):
        try:
            down = data.decode().strip() == "1"
            STATE["pkts_5007"] += 1
            asyncio.get_event_loop().create_task(broadcast(json.dumps({"type": "button", "down": down})))
            if down != STATE["btn"]:             # click the OS only on a change, not on heartbeats
                STATE["btn"] = down
                print(f"[bridge] Button {'DOWN' if down else 'UP'}")
                if os_click:
                    os_click(down)
        except Exception:
            pass

def create_udp_socket(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception: pass
    s.bind(("0.0.0.0", port))
    s.setblocking(False)
    return s

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def start_web(port=8000):
    # inside the .exe, PyInstaller unpacks bundled files to sys._MEIPASS
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    handler = functools.partial(QuietHandler, directory=os.path.join(base, "demo"))
    try:
        srv = http.server.ThreadingHTTPServer(("localhost", port), handler)
    except OSError:
        print(f"[bridge] Port {port} is busy, skipping the web server")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    webbrowser.open(f"http://localhost:{port}/index.html")
    print(f"  Demo hub      : http://localhost:{port}")

# ── Main ──────────────────────────────────────────────────────────────────────
async def monitor_loop():
    while True:
        await asyncio.sleep(2.0)
        p5 = STATE["pkts_5005"]
        p6 = STATE["pkts_5006"]
        p7 = STATE["pkts_5007"]
        if p5 > 0 or p6 > 0 or p7 > 0:
            print(f"[bridge status] Packets: UDP 5005 (cursor) = {p5} | UDP 5006 (IMU) = {p6} | UDP 5007 (button) = {p7} | Connected browsers = {len(CLIENTS)}")

async def main():
    loop = asyncio.get_event_loop()
    lan_ip = get_lan_ip()

    sock5005 = create_udp_socket(UDP_CURSOR)
    sock5006 = create_udp_socket(UDP_IMU)
    sock5007 = create_udp_socket(UDP_BUTTON)

    await loop.create_datagram_endpoint(lambda: CursorProtocol(), sock=sock5005)
    await loop.create_datagram_endpoint(lambda: ImuProtocol(),    sock=sock5006)
    await loop.create_datagram_endpoint(lambda: ButtonProtocol(), sock=sock5007)

    server = await asyncio.start_server(ws_client_handler, WS_HOST, WS_PORT)

    print("═══════════════════════════════════════════════════════════")
    print(f"  Pi-Pointer Universal Bridge (v5)")
    print("═══════════════════════════════════════════════════════════")
    print(f"  Mac/PC LAN IP : {lan_ip}")
    print(f"  Run on Pi     : python pointer_imu.py {lan_ip} [--no-cam]")
    print(f"  UDP Cursor    : port {UDP_CURSOR}")
    print(f"  UDP IMU       : port {UDP_IMU} (auto-fallback if no markers)")
    print(f"  UDP Button    : port {UDP_BUTTON}")
    print(f"  WebSocket     : ws://{WS_HOST}:{WS_PORT}")
    print(f"  OS Cursor Move: {'ON' if set_os_cursor else 'OFF (add --system-cursor to enable)'}")
    print(f"  OS Click      : {'ON' if os_click else 'OFF (needs --system-cursor)'}")
    print("═══════════════════════════════════════════════════════════\n")

    start_web()
    asyncio.create_task(monitor_loop())

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[bridge] stopped.")