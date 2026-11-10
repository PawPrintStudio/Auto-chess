"""Getting pictures from the camera (the Logitech BRIO, /dev/video0), or from stand-ins for tests."""
import sys
import time

import cv2
import numpy as np


class Camera:
    def __init__(self, device=0, size=(1920, 1080), warmup=10, focus=None):
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(device, backend)
        if not self.cap.isOpened():
            raise RuntimeError(f"can't open the camera ({device}). Is it plugged in, and is another program "
                               f"using it (Robo, another game)?")
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if focus is not None:                       # a focus that hunts blurs the markers: fix it
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            self.cap.set(cv2.CAP_PROP_FOCUS, focus)
        for _ in range(warmup):                     # exposure and white balance settle
            self.cap.read()

    def frame(self):
        """One fresh picture (BGR). The first read after a pause can be a stale one, so read twice."""
        ok = False
        for _ in range(2):
            ok, img = self.cap.read()
        if not ok:
            raise RuntimeError("the camera stopped giving pictures")
        return img

    def still_frame(self, n=3, gap=0.1):
        """The median of n pictures a moment apart: noise (and a fast hand) averages out."""
        shots = []
        for i in range(n):
            shots.append(self.frame())
            if i < n - 1:
                time.sleep(gap)
        return np.median(np.stack(shots), axis=0).astype(np.uint8)

    def close(self):
        self.cap.release()


class ImageCamera:
    """Pictures from a list (shown in turn, the last one repeated), or from a function that makes one."""

    def __init__(self, source):
        self.source = source
        self._i = 0

    def frame(self):
        if callable(self.source):
            return self.source()
        img = self.source[min(self._i, len(self.source) - 1)]
        self._i += 1
        return img

    still_frame = frame

    def close(self):
        pass
