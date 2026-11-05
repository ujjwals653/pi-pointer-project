import cv2, numpy as np, socket, math

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 5006)); s.setblocking(False)

WN, HN, F = 800, 600, 700
Kc = np.array([[F, 0, WN/2], [0, F, HN/2], [0, 0, 1]], np.float64)
Rv = cv2.Rodrigues(np.array([0.5, 0, 0]))[0] @ cv2.Rodrigues(np.array([0, 0.6, 0]))[0]
rv, tv = cv2.Rodrigues(Rv)[0], np.array([0, 0, 7.0])      # camera: behind, above, to the side

def proj(p):
    q, _ = cv2.projectPoints(np.asarray(p, np.float64).reshape(-1, 1, 3), rv, tv, Kc, None)
    return q.reshape(-1, 2).astype(int)

box = np.array([[x*0.6, y*0.2, z*1.5] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)])
edges = [(i, j) for i in range(8) for j in range(i+1, 8) if bin(i ^ j).count("1") == 1]
axes = np.array([[0, 0, 0], [2.2, 0, 0], [0, 2.2, 0], [0, 0, 2.5]], np.float64)
grid = [(np.array([a, 1.8, -3.0]), np.array([a, 1.8, 3.0])) for a in np.arange(-3, 3.1, 1.5)] + \
       [(np.array([-3.0, 1.8, a]), np.array([3.0, 1.8, a])) for a in np.arange(-3, 3.1, 1.5)]

cv2.namedWindow("controller")
cv2.moveWindow("controller", 560, 240)                    # centre of a 1920x1080 screen
if hasattr(cv2, "WND_PROP_TOPMOST"):
    cv2.setWindowProperty("controller", cv2.WND_PROP_TOPMOST, 1)

R, yaw0, got = np.eye(3), None, False
while True:
    try:
        while True:                                       # drain the socket, keep newest packet
            v = [float(x) for x in s.recv(256).decode().split(",")]
            if len(v) == 9:
                R, got = np.array(v).reshape(3, 3), True
    except BlockingIOError:
        pass
    except ValueError:
        pass
    if got and yaw0 is None:
        yaw0 = math.atan2(R[0, 2], R[2, 2])               # zero yaw on first packet

    c, sn = math.cos(-(yaw0 or 0)), math.sin(-(yaw0 or 0))
    Rd = np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]]) @ R

    img = np.full((HN, WN, 3), 30, np.uint8)
    for a, b in grid:
        p = proj([a, b]); cv2.line(img, tuple(p[0]), tuple(p[1]), (70, 70, 70), 1)
    pts = proj(box @ Rd.T)
    for i, j in edges:
        front = (i & 1) and (j & 1)                       # the pointing (camera) end
        cv2.line(img, tuple(pts[i]), tuple(pts[j]), (0, 200, 255) if front else (220, 220, 220), 3 if front else 2)
    ax = proj(axes @ Rd.T)
    for k, col in zip((1, 2, 3), ((0, 0, 255), (0, 255, 0), (255, 100, 0))):   # x red, y green, z blue (BGR)
        cv2.arrowedLine(img, tuple(ax[0]), tuple(ax[k]), col, 2)

    yaw = math.degrees(math.atan2(Rd[0, 2], Rd[2, 2]))
    pitch = math.degrees(math.asin(max(-1, min(1, -Rd[1, 2]))))
    roll = math.degrees(math.asin(max(-1, min(1, Rd[1, 0]))))
    txt = f"yaw {yaw:6.1f}  pitch {pitch:6.1f}  roll {roll:6.1f}" if got else "waiting for Pi..."
    cv2.putText(img, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(img, "r = zero yaw, Esc = quit", (20, HN - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (160, 160, 160), 1)
    cv2.imshow("controller", img)
    k = cv2.waitKey(15) & 0xFF
    if k == 27:
        break
    if k == ord("r"):
        yaw0 = math.atan2(R[0, 2], R[2, 2])
