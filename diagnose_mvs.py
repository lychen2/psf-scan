"""绕过 GUI 直接调 MVS 驱动，把每一步的 SDK 返回码打到 stdout。"""
from __future__ import annotations

import os
import sys
import time
from ctypes import POINTER, byref, c_ubyte, cast

# 让 vendor 路径可见
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# 触发 MVCAM_COMMON_RUNENV 自动设置
from psf_scan.drivers import camera_mvs  # noqa: F401
from psf_scan.vendor.MvImport import (
    MV_ACCESS_Exclusive,
    MV_CC_DEVICE_INFO,
    MV_CC_DEVICE_INFO_LIST,
    MV_FRAME_OUT_INFO_EX,
    MV_GIGE_DEVICE,
    MV_USB_DEVICE,
    MVCC_INTVALUE,
    MvCamera,
)


def hx(r: int) -> str:
    return f"0x{r & 0xFFFFFFFF:08x}"


def step(label: str, ret: int) -> None:
    tag = "OK " if ret == 0 else "ERR"
    print(f"[{tag}] {label:35s} ret={hx(ret)}", flush=True)


def main() -> int:
    info_list = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, info_list)
    step("EnumDevices", ret)
    print(f"      nDeviceNum = {info_list.nDeviceNum}")
    if ret != 0 or info_list.nDeviceNum == 0:
        return 1

    cam = MvCamera()
    info = cast(info_list.pDeviceInfo[0], POINTER(MV_CC_DEVICE_INFO)).contents
    step("CreateHandle", cam.MV_CC_CreateHandle(info))
    step("OpenDevice (Exclusive)", cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0))

    # 列出关键参数当前值
    for key in ("AcquisitionMode", "TriggerMode", "ExposureAuto",
                "PixelFormat", "TriggerSource"):
        from psf_scan.vendor.MvImport import MVCC_ENUMVALUE
        v = MVCC_ENUMVALUE()
        r = cam.MV_CC_GetEnumValue(key, v)
        print(f"      {key:18s} ret={hx(r)} cur={v.nCurValue}")

    # 显式设连续 + 关触发
    step("Set AcquisitionMode=Continuous",
         cam.MV_CC_SetEnumValueByString("AcquisitionMode", "Continuous"))
    step("Set TriggerMode=Off",
         cam.MV_CC_SetEnumValueByString("TriggerMode", "Off"))
    step("Set ExposureAuto=Off",
         cam.MV_CC_SetEnumValueByString("ExposureAuto", "Off"))
    step("Set ExposureTime=10000",
         cam.MV_CC_SetFloatValue("ExposureTime", 10_000.0))

    wv, hv, payload = MVCC_INTVALUE(), MVCC_INTVALUE(), MVCC_INTVALUE()
    cam.MV_CC_GetIntValue("Width", wv)
    cam.MV_CC_GetIntValue("Height", hv)
    cam.MV_CC_GetIntValue("PayloadSize", payload)
    print(f"      Width={wv.nCurValue} Height={hv.nCurValue} PayloadSize={payload.nCurValue}")

    step("StartGrabbing", cam.MV_CC_StartGrabbing())

    buf_size = max(int(payload.nCurValue), int(wv.nCurValue) * int(hv.nCurValue) * 2)
    buf = (c_ubyte * buf_size)()
    info_ex = MV_FRAME_OUT_INFO_EX()

    print("--- 试取 5 帧 (timeout=1000ms each) ---", flush=True)
    for i in range(5):
        t0 = time.time()
        r = cam.MV_CC_GetOneFrameTimeout(
            cast(buf, POINTER(c_ubyte)), buf_size, info_ex, 1000)
        dt = (time.time() - t0) * 1000
        if r == 0:
            print(f"  frame {i}: OK  {info_ex.nWidth}x{info_ex.nHeight} "
                  f"len={info_ex.nFrameLen} pix=0x{info_ex.enPixelType:x} ({dt:.1f}ms)")
        else:
            print(f"  frame {i}: ERR ret={hx(r)} ({dt:.1f}ms)")

    cam.MV_CC_StopGrabbing()
    cam.MV_CC_CloseDevice()
    cam.MV_CC_DestroyHandle()
    return 0


if __name__ == "__main__":
    sys.exit(main())
