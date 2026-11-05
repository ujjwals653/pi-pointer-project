import cv2, numpy as np

W, H, SQ = 1920, 1080, 120
COLS, ROWS = 10, 7                       # squares -> 9x6 inner corners
img = np.full((H, W), 255, np.uint8)
x0, y0 = (W - COLS * SQ) // 2, (H - ROWS * SQ) // 2
for r in range(ROWS):
    for c in range(COLS):
        if (r + c) % 2 == 0:
            img[y0 + r*SQ : y0 + (r+1)*SQ, x0 + c*SQ : x0 + (c+1)*SQ] = 0

cv2.namedWindow("board", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("board", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("board", img)
while cv2.waitKey(50) & 0xFF != 27:      # Esc to quit
    pass
