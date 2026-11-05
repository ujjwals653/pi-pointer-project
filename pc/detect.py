import cv2

CAM = 1   # try 0 first; USB webcam is often 1 on laptops
cap = cv2.VideoCapture(CAM, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("actual:", cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
      cap.get(cv2.CAP_PROP_FPS))

d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())

last = None
while True:
    ok, frame = cap.read()
    if not ok:
        print("no frame"); break
    corners, ids, _ = det.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    if ids is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        seen = sorted(ids.ravel().tolist())
    else:
        seen = []
    if seen != last:
        print("detected:", seen); last = seen
    cv2.imshow("detect", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break
cap.release()
