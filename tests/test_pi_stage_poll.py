from __future__ import annotations

from psf_scan.drivers.stage_pi import PIStage


def test_pi_poll_skips_ont_and_signal_when_idle_unchanged(qapp):
    stage = PIStage()
    dev = _FakeDevice(pos_mm=0.0, on_target=True)
    stage._dev = dev
    stage._axis_id = "1"
    stage._connected = True
    stage._moving = False
    seen: list[tuple[float, float, float]] = []
    stage.position_changed.connect(lambda x, y, z: seen.append((x, y, z)))

    stage._poll()

    assert dev.qpos_calls == 1
    assert dev.qont_calls == 0
    assert seen == []


def test_pi_poll_checks_ont_and_emits_while_moving(qapp):
    stage = PIStage()
    dev = _FakeDevice(pos_mm=0.010, on_target=False)
    stage._dev = dev
    stage._axis_id = "1"
    stage._connected = True
    stage._moving = True
    seen: list[tuple[float, float, float]] = []
    stage.position_changed.connect(lambda x, y, z: seen.append((x, y, z)))

    stage._poll()

    assert dev.qpos_calls == 1
    assert dev.qont_calls == 1
    assert seen[-1] == (0.0, 0.0, 10.0)


class _FakeDevice:
    def __init__(self, *, pos_mm: float, on_target: bool) -> None:
        self._pos_mm = float(pos_mm)
        self._on_target = bool(on_target)
        self.qpos_calls = 0
        self.qont_calls = 0

    def qPOS(self, axis: str) -> dict[str, float]:
        self.qpos_calls += 1
        return {axis: self._pos_mm}

    def qONT(self, axis: str) -> dict[str, bool]:
        self.qont_calls += 1
        return {axis: self._on_target}
