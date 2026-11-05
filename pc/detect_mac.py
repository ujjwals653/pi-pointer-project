import cv2, sys

# Allow camera index as CLI argument: python detect_mac.py [cam_index]
# On Mac, built-in camera is usually 0, external USB / Continuity webcam is 1 or 2
CAM = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0

print(f"Opening camera index {CAM} with AVFoundation backend...")
cap = cv2.VideoCapture(CAM, cv2.CAP_AVFOUNDATION)
if not cap.isOpened():
    print(f"Failed with CAP_AVFOUNDATION, trying default backend for camera {CAM}...")
    cap = cv2.VideoCapture(CAM)

if not cap.isOpened():
    sys.exit(f"Could not open camera {CAM}. Try specifying another index (e.g. python detect_mac.py 1)")

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("actual:", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
      f"@{cap.get(cv2.CAP_PROP_FPS):.1f} fps")

ar = cv2.aruco
dict_4x4 = ar.getPredefinedDictionary(ar.DICT_4X4_50) if hasattr(ar, "getPredefinedDictionary") else ar.Dictionary_get(ar.DICT_4X4_50)

if hasattr(ar, "ArucoDetector"):
    prm = ar.DetectorParameters()
    det = ar.ArucoDetector(dict_4x4, prm)
    detect_func = det.detectMarkers
else:
    prm = ar.DetectorParameters_create()
    detect_func = lambda g: ar.detectMarkers(g, dict_4x4, parameters=prm)

print("Starting detection preview. Press Esc in the preview window to quit.")
last = None
try:
    while True:
        ok, frame = cap.read()
        if not ok:
            print("no frame")
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detect_func(gray)
        if ids is not None:
            ar.drawDetectedMarkers(frame, corners, ids)
            seen = sorted(ids.ravel().tolist())
        else:
            seen = []
        if seen != last:
            print("detected marker IDs:", seen)
            last = seen
        cv2.imshow("detect (Mac)", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
