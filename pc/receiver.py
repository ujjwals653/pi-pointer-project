# Cursor receiver with fixed-rate output and One Euro smoothing. Hold Esc to quit.
import socket, ctypes, math, time

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
ctypes.windll.winmm.timeBeginPeriod(1)          # 1 ms timer, otherwise sleep is ~15 ms
SW, SH = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
MINCUT, BETA, DCUT, RATE = 1.5, 0.01, 1.0, 125  # tune: lower MINCUT = less jitter, higher BETA = less fast lag
print("screen", SW, SH, "- UDP 5005, hold Esc to quit")

class OneEuro:
    def __init__(s): s.x = None
    def __call__(s, v, dt):
        al = lambda fc: 1 / (1 + 1 / (2 * math.pi * fc * dt))
        if s.x is None:
            s.x, s.dx = v, 0.0; return v
        s.dx += al(DCUT) * ((v - s.x) / dt - s.dx)
        s.x += al(MINCUT + BETA * abs(s.dx)) * (v - s.x)
        return s.x

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 5005)); sock.setblocking(False)
fx, fy, tgt, t = OneEuro(), OneEuro(), None, time.time()
while not (u32.GetAsyncKeyState(0x1B) & 0x8000):
    try:
        while True:                              # drain; keep the newest packet
            u, v = map(float, sock.recv(64).decode().split(","))
            tgt = (min(max(u, 0), 1) * (SW - 1), min(max(v, 0), 1) * (SH - 1))
    except (BlockingIOError, ValueError):
        pass
    now = time.time(); dt = max(now - t, 1e-3); t = now
    if tgt:
        u32.SetCursorPos(int(round(fx(tgt[0], dt))), int(round(fy(tgt[1], dt))))
    time.sleep(max(0, 1 / RATE - (time.time() - now)))
