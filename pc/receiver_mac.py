# Cursor receiver for macOS with fixed-rate output and One Euro smoothing. Hold Esc or Ctrl+C to quit.
import socket, ctypes, math, time, sys
from ctypes import c_uint32, c_double, Structure, c_void_p, c_int32, c_uint16, c_bool

# Load macOS CoreGraphics & CoreFoundation
cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')

class CGPoint(Structure):
    _fields_ = [('x', c_double), ('y', c_double)]

class CGRect(Structure):
    _fields_ = [('origin', CGPoint), ('size', CGPoint)]

# Query main display resolution
cg.CGMainDisplayID.restype = c_uint32
main_disp = cg.CGMainDisplayID()

cg.CGDisplayBounds.argtypes = [c_uint32]
cg.CGDisplayBounds.restype = CGRect
bounds = cg.CGDisplayBounds(main_disp)
SW, SH = int(bounds.size.x), int(bounds.size.y)

# Check Accessibility permissions
try:
    app = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
    app.AXIsProcessTrusted.restype = c_bool
    if not app.AXIsProcessTrusted():
        print("WARNING: Accessibility permissions not granted for this terminal/app.")
        print("Cursor control will be blocked until enabled in:")
        print("System Settings -> Privacy & Security -> Accessibility\n")
except Exception:
    pass

# Setup cursor move functions
cg.CGDisplayMoveCursorToPoint.argtypes = [c_uint32, CGPoint]
cg.CGDisplayMoveCursorToPoint.restype = c_uint32

cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_uint32, CGPoint, c_uint32]
cg.CGEventCreateMouseEvent.restype = c_void_p

cg.CGEventPost.argtypes = [c_uint32, c_void_p]
cg.CGEventPost.restype = None

cf.CFRelease.argtypes = [c_void_p]
cf.CFRelease.restype = None

# Key state check (macOS virtual key code for Esc is 0x35)
cg.CGEventSourceKeyState.argtypes = [c_int32, c_uint16]
cg.CGEventSourceKeyState.restype = c_bool

def set_cursor_pos(x, y):
    pt = CGPoint(float(x), float(y))
    cg.CGDisplayMoveCursorToPoint(main_disp, pt)
    ev = cg.CGEventCreateMouseEvent(None, 5, pt, 0)  # 5 = kCGEventMouseMoved
    if ev:
        cg.CGEventPost(0, ev)                       # 0 = kCGHIDEventTap
        cf.CFRelease(ev)

def is_esc_pressed():
    return cg.CGEventSourceKeyState(0, 0x35)

MINCUT, BETA, DCUT, RATE = 1.5, 0.01, 1.0, 125  # tune: lower MINCUT = less jitter, higher BETA = less fast lag
print(f"Screen: {SW}x{SH} (points) - UDP 5005, hold Esc or Ctrl+C to quit")

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
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", 5005)); sock.setblocking(False)

sock_imu = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_imu.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
sock_imu.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock_imu.bind(("0.0.0.0", 5006)); sock_imu.setblocking(False)

fx, fy, tgt, t = OneEuro(), OneEuro(), None, time.time()
last_5005_time = 0
last_yaw, last_pitch = None, None
imu_px, imu_py = SW / 2, SH / 2
GAIN_X, GAIN_Y = 0.05, 0.07  # screen fraction per degree

print(f"Screen: {SW}x{SH} (points)")
print("Listening on UDP 5005 (cursor) & UDP 5006 (IMU orientation)")
print("Hold Esc or Ctrl+C to quit\n")

try:
    while not is_esc_pressed():
        now = time.time()
        got_5005 = False
        # 1. Drain UDP 5005 (fused or direct cursor)
        try:
            while True:
                u, v = map(float, sock.recv(64).decode().split(","))
                tgt = (min(max(u, 0), 1) * (SW - 1), min(max(v, 0), 1) * (SH - 1))
                got_5005 = True
                last_5005_time = now
        except (BlockingIOError, ValueError):
            pass

        # 2. Drain UDP 5006 (IMU fallback if 5005 is not arriving)
        try:
            while True:
                raw = sock_imu.recv(256).decode().strip()
                v = [float(x) for x in raw.split(",")]
                if len(v) == 9:
                    # Yaw and pitch from 3x3 rotation matrix
                    yaw = math.degrees(math.atan2(v[2], v[8]))
                    pitch = math.degrees(math.asin(max(-1, min(1, -v[5]))))
                    if last_yaw is not None and last_pitch is not None:
                        dyaw = yaw - last_yaw
                        dpitch = pitch - last_pitch
                        if dyaw > 180: dyaw -= 360
                        elif dyaw < -180: dyaw += 360
                        if dpitch > 180: dpitch -= 360
                        elif dpitch < -180: dpitch += 360

                        if (now - last_5005_time) > 0.25:
                            # Use IMU delta to move cursor
                            imu_px += dyaw * GAIN_X * SW
                            imu_py += dpitch * GAIN_Y * SH
                            imu_px = min(max(imu_px, 0), SW - 1)
                            imu_py = min(max(imu_py, 0), SH - 1)
                            tgt = (imu_px, imu_py)
                    last_yaw, last_pitch = yaw, pitch
        except (BlockingIOError, ValueError):
            pass

        dt = max(now - t, 1e-3); t = now
        if tgt:
            set_cursor_pos(round(fx(tgt[0], dt)), round(fy(tgt[1], dt)))
        time.sleep(max(0, 1 / RATE - (time.time() - now)))
except KeyboardInterrupt:
    print("\nExiting receiver...")
finally:
    sock.close()
    sock_imu.close()
