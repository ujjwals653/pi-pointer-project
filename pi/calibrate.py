# Usage: python calibrate.py [W H] [--headless]   (board shown by pc/show_chessboard.py)
import cv2, numpy as np, sys

DEV = 0
nums = [int(a) for a in sys.argv[1:] if a.isdigit()]
W, H = (nums[0], nums[1]) if len(nums) >= 2 else (1280, 720)
SHOW = "--headless" not in sys.argv
PAT, NEED = (9, 6), 25                   # inner corners, number of views

cap = cv2.VideoCapture(DEV, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)       # harmless if the camera has no autofocus
W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print("size", W, H)

objp = np.zeros((PAT[0] * PAT[1], 3), np.float32)
objp[:, :2] = np.mgrid[0:PAT[0], 0:PAT[1]].T.reshape(-1, 2)   # units = squares
crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
flags = cv2.CALIB_CB_FAST_CHECK | cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE

obj, pts = [], []
prev = last_cap = None
while len(pts) < NEED:
    ok, frame = cap.read()
    if not ok:
        sys.exit("no frame")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, c = cv2.findChessboardCorners(gray, PAT, flags)
    if found:
        c = cv2.cornerSubPix(gray, c, (11, 11), (-1, -1), crit)
        still = prev is not None and np.abs(c - prev).mean() < 1.0
        new = last_cap is None or np.abs(c - last_cap).mean() > 40
        if still and new:
            obj.append(objp); pts.append(c); last_cap = c
            print(f"captured {len(pts)}/{NEED}")
        prev = c
        if SHOW:
            cv2.drawChessboardCorners(frame, PAT, c, True)
    else:
        prev = None
    if SHOW:
        cv2.putText(frame, f"{len(pts)}/{NEED}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        cv2.imshow("calib", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
cap.release()

if len(pts) < 10:
    sys.exit("too few views, need at least 10")
rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(obj, pts, (W, H), None, None)
print(f"\nRMS reprojection error: {rms:.3f} px")
for i in range(len(obj)):
    p, _ = cv2.projectPoints(obj[i], rvecs[i], tvecs[i], K, dist)
    print(f"  view {i}: {np.sqrt(np.mean(np.sum((p - pts[i])**2, axis=2))):.2f} px")
fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
print(f"fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f}  (image centre {W/2:.1f}, {H/2:.1f})")
print("dist =", dist.ravel())
print(f"horizontal FOV ~ {np.degrees(2 * np.arctan(W / (2 * fx))):.1f} deg")
np.savez(f"calib_{W}x{H}.npz", K=K, dist=dist, size=(W, H), rms=rms)
print(f"saved calib_{W}x{H}.npz")
