import cv2, numpy as np

W, H = 1920, 1080   # screen resolution
S = 300             # marker side in px (includes black border)
M = 60              # gap from screen edge to marker edge

d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
img = np.full((H, W), 255, np.uint8)
pos = {0: (M, M), 1: (W-M-S, M), 2: (W-M-S, H-M-S), 3: (M, H-M-S)}  # TL TR BR BL
for mid, (x, y) in pos.items():
    img[y:y+S, x:x+S] = cv2.aruco.generateImageMarker(d, mid, S)
cv2.imwrite("markers.png", img)

cv2.namedWindow("markers", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("markers", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("markers", img)
while cv2.waitKey(50) & 0xFF != 27:   # Esc to quit
    pass
