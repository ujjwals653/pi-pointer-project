import cv2, numpy as np, sys, ctypes
from ctypes import c_uint32, c_double, Structure

# Attempt to auto-detect Mac display resolution (in logical points)
try:
    cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    class CGPoint(Structure):
        _fields_ = [('x', c_double), ('y', c_double)]
    class CGRect(Structure):
        _fields_ = [('origin', CGPoint), ('size', CGPoint)]
    cg.CGMainDisplayID.restype = c_uint32
    cg.CGDisplayBounds.argtypes = [c_uint32]
    cg.CGDisplayBounds.restype = CGRect
    bounds = cg.CGDisplayBounds(cg.CGMainDisplayID())
    detected_W, detected_H = int(bounds.size.x), int(bounds.size.y)
except Exception:
    detected_W, detected_H = 1920, 1080

# Default to 1920x1080 (which matches pi/pointer_imu.py default), or pass --native
if "--native" in sys.argv:
    W, H = detected_W, detected_H
    S = int(min(W, H) * 0.28)  # proportional marker size
    M = int(min(W, H) * 0.05)  # proportional margin
    print(f"Using native Mac screen size: {W}x{H}, S={S}, M={M}")
    print(f"NOTE: If using --native, you must also update SW, SH, S, M in pi/pointer_imu.py to: {W}, {H}, {S}, {M}!")
else:
    W, H = 1920, 1080   # Default screen resolution matching pi/pointer_imu.py
    S = 300             # marker side in px (includes black border)
    M = 60              # gap from screen edge to marker edge
    print(f"Using standard 1920x1080 canvas (matches pi/pointer_imu.py default).")
    print(f"(Pass --native if you want to size markers to your native Mac screen: {detected_W}x{detected_H})")

ar = cv2.aruco
dict_4x4 = ar.getPredefinedDictionary(ar.DICT_4X4_50) if hasattr(ar, "getPredefinedDictionary") else ar.Dictionary_get(ar.DICT_4X4_50)

def draw_marker(d, mid, side):
    if hasattr(ar, "generateImageMarker"):
        return ar.generateImageMarker(d, mid, side)
    return ar.drawMarker(d, mid, side)

img = np.full((H, W), 255, np.uint8)
pos = {0: (M, M), 1: (W-M-S, M), 2: (W-M-S, H-M-S), 3: (M, H-M-S)}  # TL TR BR BL
for mid, (x, y) in pos.items():
    img[y:y+S, x:x+S] = draw_marker(dict_4x4, mid, S)

cv2.imwrite("markers.png", img)

cv2.namedWindow("markers", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("markers", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("markers", img)
print("Displaying markers fullscreen. Press Esc to quit.")
while cv2.waitKey(50) & 0xFF != 27:   # Esc to quit
    pass
cv2.destroyAllWindows()
