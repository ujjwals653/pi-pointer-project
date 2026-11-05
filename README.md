# Pi Pointer

An experimental motion-tracking pointer: a Raspberry Pi combines an MPU6050
gyroscope with camera tracking of ArUco markers, then sends cursor coordinates
to a Windows or macOS computer over UDP.

## How it works

1. The host displays four ArUco markers around the edges of its screen.
2. The Pi camera tracks those markers while the MPU6050 measures controller
   motion.
3. The Pi sends normalized cursor coordinates to the host on UDP port `5005`
   and orientation data on UDP port `5006`.
4. The host receiver smooths the coordinates and moves the system cursor.

The camera is optional at runtime. Start the Pi program with `--no-cam` to use
the IMU without marker tracking.

## Hardware

- Raspberry Pi with a camera
- MPU6050 connected over I2C
- Windows or macOS host computer on the same local network

### Connect the Raspberry Pi hardware

With the Pi powered off, connect a standard MPU6050 breakout to the Pi's 40-pin
GPIO header:

| MPU6050 | Raspberry Pi |
|---|---|
| VCC | 3.3V (physical pin 1) |
| GND | Ground (physical pin 6) |
| SDA | GPIO2 / SDA1 (physical pin 3) |
| SCL | GPIO3 / SCL1 (physical pin 5) |

Use a breakout that supports 3.3V I2C logic; never connect a 5V logic signal to
the Pi GPIO. The code expects the sensor's default I2C address, `0x68`.

Connect the camera to the Pi's camera (CSI) connector with a ribbon cable
compatible with your Pi model. Disconnect power before inserting the cable;
the connector and cable orientation differ between models, so follow the
Raspberry Pi camera instructions for your board. The camera should face the
host display so it can see the markers.

For headless setup, use Raspberry Pi Imager to configure Wi-Fi and enable SSH.
Connect the Pi and host to the same local network. You can find the Pi's
address with `hostname -I`; the pointer command needs the **host's** address,
not the Pi's.

## Setup

### Windows host

Install Python 3, then install the host dependencies:

```powershell
py -m pip install opencv-contrib-python numpy
```

### macOS host

Install Python 3, then install the host dependencies:

```sh
python3 -m pip install opencv-contrib-python numpy
```

When prompted, grant Accessibility permission to the terminal or app running
the receiver under **System Settings → Privacy & Security → Accessibility**.

### Raspberry Pi

The following instructions target a 32-bit Raspberry Pi OS installation. Use
the OS-provided OpenCV and NumPy packages, and install only `smbus2` in the
virtual environment:

```sh
sudo apt update
sudo apt install -y python3-opencv python3-numpy v4l-utils i2c-tools
sudo raspi-config nonint do_i2c 0
i2cdetect -y 1
python3 -m venv --system-site-packages ~/aruco-env
source ~/aruco-env/bin/activate
python -m pip install smbus2
```

After enabling I2C, `i2cdetect -y 1` should show the sensor at `68`. If it
doesn't, power off and check the wiring, sensor address, and I2C setting.

Do not install pip versions of OpenCV or NumPy into this environment; the
virtual environment is configured to use the compatible OS packages.

## Run

All devices must be on the same network. Allow inbound UDP traffic on ports
`5005` and `5006` in the host firewall; allow `5007` as well if using bridge
button input. Use one of the following host workflows.

### Native system cursor

1. On the host, start the cursor receiver:

   **Windows**

   ```powershell
   py pc\receiver.py
   ```

   **macOS**

   ```sh
   python3 pc/receiver_mac.py
   ```

   Press Esc to quit. On macOS, Ctrl+C also exits.

### Browser demos (bridge)

Instead of a native cursor receiver, the bridge receives Pi data and serves the
browser demos in `pc/demo/`. Run it from the project root on the host:

```sh
python pc/bridge.py
```

It opens the demo hub in a browser and prints the host LAN IP and listening
ports. Open a demo page from the hub. Add `--system-cursor` if you also want
the bridge to move the host's system cursor and handle button clicks; macOS
requires Accessibility permission for this. Do not run the bridge and a native
receiver at the same time: both workflows use UDP port `5005`.

### Start the pointer

For marker tracking, display markers fullscreen on the host in a separate
terminal:

**Windows**

```powershell
py pc\show_markers.py
```

**macOS**

```sh
python3 pc/show_markers_mac.py
```

The standard marker layout is designed for a 1920×1080 display. Keep the marker
screen visible to the Pi camera. The macOS script also accepts `--native`, but
its dimensions must then match the marker layout constants in
`pi/pointer_imu.py`.

On the Pi, activate the virtual environment and start the pointer, replacing
`<HOST_IP>` with the host's LAN IP (the bridge prints it when running):

```sh
source ~/aruco-env/bin/activate
python pi/pointer_imu.py <HOST_IP> --small
```

Keep the controller still for the initial two-second gyro-bias measurement.
The default camera resolution is 1280×720; `--small` selects 640×480. Add
`--show` to preview camera tracking or `--no-cam` for IMU-only operation:

```sh
python pi/pointer_imu.py <HOST_IP> --small --show
python pi/pointer_imu.py <HOST_IP> --no-cam
```

## Tuning

The main tuning constants are near the top of `pi/pointer_imu.py`:

- `GX`, `GY`: cursor movement per degree of rotation
- `K`: camera correction strength
- `CAM_LAT`: estimated delay between camera exposure and marker correction
- `DEADBAND`: gyro rate below which cursor motion is ignored
- `AX_YAW`, `AX_PITCH`, `SX`, `SY`: sensor-axis and direction mapping

The Windows and macOS receivers also define One Euro filter settings
(`MINCUT`, `BETA`, and `DCUT`) for cursor smoothing.

If the cursor moves in the wrong direction, adjust `SX` or `SY`. If the
orientation axes are incorrect, adjust `AX_YAW` and `AX_PITCH`.

## Testing and calibration utilities

- **Test the host camera:** run `py pc\detect.py` on Windows or
  `python3 pc/detect_mac.py` on macOS. The macOS script accepts a camera index,
  for example `python3 pc/detect_mac.py 1`.
- **Test Pi camera and marker detection:** activate the Pi environment and run
  `python pi/detect_pi.py`. Use `--small` for 640×480, `--headless` to save
  periodic frames to `last.jpg`, or pass a camera index such as
  `python pi/detect_pi.py 1`.
- **Test the MPU6050:** run `python pi/imu_test.py` on the Pi to print gyro
  readings. Stop it with Ctrl+C.
- **Calibrate the camera:** display the checkerboard on the host with
  `py pc\show_chessboard.py` (Windows) or
  `python3 pc/show_chessboard.py` (macOS), then on the Pi run
  `python pi/calibrate.py 1280 720`. Capture at least 10 different stable board
  views; the script saves results as `calib_1280x720.npz`. The calibration
  output is not currently loaded by `pointer_imu.py`.
- **View orientation:** run `python pc/viewer.py` on the host to visualize
  orientation data from UDP port `5006`.

These are diagnostic tools; run them as separate processes instead of the
pointer application when they need the same camera or hardware.

## Project layout

- `pi/pointer_imu.py` — Pi camera/IMU fusion and UDP sender
- `pi/calibrate.py`, `pc/show_chessboard.py` — camera calibration
- `pi/detect_pi.py`, `pi/imu_test.py` — Pi camera and IMU tests
- `pc/receiver.py`, `pc/receiver_mac.py` — Windows and macOS cursor receivers
- `pc/show_markers.py`, `pc/show_markers_mac.py` — fullscreen marker display
- `pc/detect.py`, `pc/detect_mac.py` — host camera diagnostics
- `pc/bridge.py` — WebSocket/UDP bridge and browser demo server
- `pc/viewer.py` — orientation viewer listening on UDP port `5006`
- `pc/demo/` — browser-based demo pages

## Limitations

This is a prototype. The calibration utility is standalone, and its output is
not currently loaded by the pointer application. Cursor behavior depends on
camera placement, marker visibility, display dimensions, and per-device motion
tuning.
