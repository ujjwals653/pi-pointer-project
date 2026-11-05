# Camera + MPU6050 pointer. Usage: python pointer_imu.py <PC_IP> [--small] [--show]
import cv2, numpy as np, socket, sys, time, threading, collections
from smbus2 import SMBus

PC_IP = next(a for a in sys.argv[1:] if not a.startswith("--"))
PORT, VPORT = 5005, 5006               # cursor, orientation matrix
W, H = (640, 480) if "--small" in sys.argv else (1280, 720)
SHOW = "--show" in sys.argv
NO_CAM = "--no-cam" in sys.argv

# ---- tune these (replace GX/GY/K/axes/signs with your own tuned values) ----
GX, GY = 0.05, 0.09        # screen fraction per degree (about right at 1 m)
K = 0.08                   # camera correction strength per fix
CAM_LAT = 0.06             # seconds from exposure to fix arriving; tune 0.03-0.10
DEADBAND = 0.4             # deg/s; gyro below this is ignored for the cursor
AX_YAW, AX_PITCH = 1, 0    # which gyro axis is yaw / pitch (0=x, 1=y, 2=z)
SX, SY = 1, -1             # flip signs if the cursor moves the wrong way
hist = collections.deque(maxlen=300)   # (time, cursor position) history

# ---- IMU setup ----
ADDR = 0x68
bus = SMBus(1)
bus.write_byte_data(ADDR, 0x6B, 0)       # wake
bus.write_byte_data(ADDR, 0x1A, 3)       # low-pass filter ~44 Hz
bus.write_byte_data(ADDR, 0x1B, 0x08)    # +-500 deg/s

def gyro():
    d = bus.read_i2c_block_data(ADDR, 0x43, 6)
    v = [((d[i] << 8) | d[i+1]) for i in (0, 2, 4)]
    return [(x - 65536 if x > 32767 else x) / 65.5 for x in v]

def accel():                               # in g, default +-2 g range
    d = bus.read_i2c_block_data(ADDR, 0x3B, 6)
    v = [((d[i] << 8) | d[i+1]) for i in (0, 2, 4)]
    return np.array([(x - 65536 if x > 32767 else x) / 16384.0 for x in v])

# sensor axes -> display axes (x right, y down, z forward), from the tuned constants
AXM = np.zeros((3, 3))
AXM[0, AX_PITCH] = -SY
AXM[1, AX_YAW] = SX
AXM[2] = np.cross(AXM[0], AXM[1])

print("Hold the controller still for 2 s (gyro bias)...")
acc = np.zeros(3)
for _ in range(200):
    acc += gyro(); time.sleep(0.01)
bias = acc / 200
print("bias", bias.round(2))

# ---- shared state + IMU thread ----
lock = threading.Lock()
# Initialize cursor at screen centre (0.5, 0.5) so IMU works immediately without camera!
st = {"p": np.array([0.5, 0.5]), "vis": None, "run": True}

def imu_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    vsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    R, cnt, t = np.eye(3), 0, time.time()
    tp = t
    while st["run"]:
        raw = np.array(gyro())
        if np.all(np.abs(raw - bias) < 0.8):            # still: track bias slowly
            bias[:] = bias + 0.0005 * (raw - bias)
        r = raw - bias
        rc = np.where(np.abs(r) < DEADBAND, 0.0, r)     # deadbanded copy for the cursor
        now = time.time(); dt = now - t; t = now

        # --- orientation (body-to-world rotation matrix) ---
        a = AXM @ accel()
        R = R @ cv2.Rodrigues(np.radians(AXM @ r) * dt)[0]
        g = np.linalg.norm(a)
        if 0.8 < g < 1.2:                               # trust gravity only when not accelerating
            R = R @ cv2.Rodrigues(0.02 * np.cross(a / g, R.T @ np.array([0., -1., 0.])))[0]
        cnt += 1
        if cnt % 4 == 0:
            u, _, vt = np.linalg.svd(R); R = u @ vt      # keep R a proper rotation
            vsock.sendto(",".join(f"{x:.4f}" for x in R.ravel()).encode(), (PC_IP, VPORT))
        if cnt % 400 == 0:
            print(f"imu loop {400 / (now - tp):.0f} Hz"); tp = now

        # --- cursor integration + camera fusion (camera is optional) ---
        with lock:
            vis = st["vis"]; st["vis"] = None
            p = st["p"]
            if p is None:
                p = np.array([0.5, 0.5])
            p = p + np.array([SX * rc[AX_YAW] * GX, SY * rc[AX_PITCH] * GY]) * dt
            if vis is not None:
                tcap, v = vis
                ph = None
                for th, q in reversed(hist):        # cursor position at capture time
                    if th <= tcap:
                        ph = q; break
                if ph is not None:
                    e = v - ph
                    shift = (0.5 if np.hypot(*e) > 0.2 else K) * e   # re-acquire faster if far off
                    p = p + shift
                    h = [(th, q + shift) for th, q in hist]          # keep history consistent
                    hist.clear(); hist.extend(h)
            p = np.clip(p, 0, 1)
            st["p"] = p
            hist.append((now, p.copy()))
        if cnt % 2 == 0:
            sock.sendto(f"{p[0]:.4f},{p[1]:.4f}".encode(), (PC_IP, PORT))
        time.sleep(0.004)

threading.Thread(target=imu_loop, daemon=True).start()

# ---- camera loop: publishes timestamped vision fixes (optional) ----
if NO_CAM:
    print(f"IMU-only pointer active -> sending to {PC_IP}:5005 & 5006")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        st["run"] = False
else:
    SW, SH, S, M = 1920, 1080, 300, 60       # must match pc/show_markers.py (M = marker margin)
    pos = {0: (M, M), 1: (SW-M-S, M), 2: (SW-M-S, SH-M-S), 3: (M, SH-M-S)}
    screen = {i: np.float32([[x, y], [x+S, y], [x+S, y+S], [x, y+S]]) for i, (x, y) in pos.items()}

    try:
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)      # may be ignored by some drivers; harmless
        W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        center = np.float32([[[W / 2, H / 2]]])

        ar = cv2.aruco
        if hasattr(ar, "ArucoDetector"):
            prm = ar.DetectorParameters()
            prm.cornerRefinementMethod = ar.CORNER_REFINE_SUBPIX
            detect = ar.ArucoDetector(ar.getPredefinedDictionary(ar.DICT_4X4_50), prm).detectMarkers
        else:
            d, pr = ar.Dictionary_get(ar.DICT_4X4_50), ar.DetectorParameters_create()
            pr.cornerRefinementMethod = ar.CORNER_REFINE_SUBPIX
            detect = lambda g: ar.detectMarkers(g, d, parameters=pr)

        n, t0 = 0, time.time()
        print(f"Camera opened ({W}x{H}). Looking for markers (IMU cursor is active in parallel)...")
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame drop; continuing with IMU only...")
                time.sleep(0.05)
                continue
            tc = time.time() - CAM_LAT
            corners, ids, _ = detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            src, dst = [], []
            if ids is not None:
                for c, i in zip(corners, ids.ravel()):
                    if i in screen:
                        src.append(c.reshape(4, 2)); dst.append(screen[i])
            if len(src) >= 2:
                Hm, _ = cv2.findHomography(np.vstack(src), np.vstack(dst), 0)
                if Hm is not None:
                    x, y = cv2.perspectiveTransform(center, Hm)[0, 0]
                    with lock:
                        st["vis"] = (tc, np.array([x / SW, y / SH]))
            n += 1
            if time.time() - t0 >= 1:
                cur = None if st['p'] is None else st['p'].round(3)
                print(f"{n} fps, markers {len(src)}, cursor {cur}")
                n, t0 = 0, time.time()
            if SHOW:
                if ids is not None:
                    ar.drawDetectedMarkers(frame, corners, ids)
                cv2.imshow("pointer", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    except Exception as e:
        print(f"Camera unavailable ({e}); running on IMU gyro only...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        st["run"] = False
