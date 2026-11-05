import cv2, sys, time

DEV = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
HEADLESS = "--headless" in sys.argv   # no window; saves last.jpg once per second
W, H = (640, 480) if "--small" in sys.argv else (1280, 720)

cap = cv2.VideoCapture(DEV, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
print("cv2", cv2.__version__)
print("actual:", cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
      cap.get(cv2.CAP_PROP_FPS))

ar = cv2.aruco
if hasattr(ar, "ArucoDetector"):                       # OpenCV >= 4.7
    d = ar.getPredefinedDictionary(ar.DICT_4X4_50)
    det = ar.ArucoDetector(d, ar.DetectorParameters())
    detect = det.detectMarkers
else:                                                  # OpenCV 4.6 and older
    d = ar.Dictionary_get(ar.DICT_4X4_50)
    p = ar.DetectorParameters_create()
    detect = lambda g: ar.detectMarkers(g, d, parameters=p)

last, n, t0 = None, 0, time.time()
while True:
    ok, frame = cap.read()
    if not ok:
        print("no frame"); break
    corners, ids, _ = detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    seen = sorted(ids.ravel().tolist()) if ids is not None else []
    if ids is not None:
        ar.drawDetectedMarkers(frame, corners, ids)
    if seen != last:
        print("detected:", seen); last = seen

    n += 1
    if time.time() - t0 >= 1.0:
        print(f"{n / (time.time() - t0):.1f} fps")
        if HEADLESS:
            cv2.imwrite("last.jpg", frame)
        n, t0 = 0, time.time()

    if not HEADLESS:
        cv2.imshow("detect", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
cap.release()
