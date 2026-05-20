# PSF Scan 开发者接手文档

本文给新接手开发者：先了解分层，再改动，再验证。

## 1. 项目结构

核心目录：

- `src/psf_scan/core`：抽象接口与业务核心
- `src/psf_scan/drivers`：硬件驱动实现（PI/MVS/Mock）
- `src/psf_scan/ui`：Qt 界面与可视化
- `src/psf_scan/vendor`：第三方 SDK Python 绑定（MVS）
- `installer`：Windows 打包脚本与资源
- `docs`：设计、计划、TODO

入口：

- 模块入口：`src/psf_scan/__main__.py`
- 主窗口：`src/psf_scan/app.py`

## 2. 分层原则

1. `core` 不依赖具体驱动实现
2. `drivers` 实现 `core` 定义的抽象接口
3. `ui` 只通过信号/槽与 `app.py` 交互
4. 设备相关安全逻辑优先放 `app.py + core/safety.py`，硬件约束放 driver 内部

## 3. i18n key 命名约定

位置：`src/psf_scan/core/i18n.py`

规则：

1. `<domain>.<name>` 形式，如 `panel.connect`、`settings.data_dir`
2. `domain` 常见分组：`common` `panel` `camera` `scan` `settings` `pi` `safety` `exit`
3. 新增 UI 文案必须先补 key，再在界面中 `tr("...")` 使用
4. key 不要复用成歧义语义（避免一个 key 表示多个上下文）

漏 key 检查参考：

```bash
comm -23 <(rg -No 'tr\("[a-z][a-z_.]*"' src | sed -E 's/.*tr\("([^"]*)".*/"\1"/' | sort -u) <(rg -No '"[a-z][a-z_.]*"\s*:' src/psf_scan/core/i18n.py | sed -E 's/:$//' | sort -u)
```

## 4. 新增位移台驱动步骤

以 `newstage` 为例：

1. 在 `src/psf_scan/drivers/stage_newstage.py` 新建类，继承 `StageBase`
2. 最少实现：
- `connect/disconnect`
- `move_to`
- `position/is_connected/is_moving`
- 可选：`stop/set_zero/reference/reset_range/set_invert_z/travel_limits_um`
3. 在 `src/psf_scan/core/stage.py`：
- 把 `newstage` 加入 `AVAILABLE_STAGES`
- 在 `make_stage` 增加分支
4. 若有特定配置项：
- 在 `UserSettings` 增加读写
- 在对应设置 UI 增加入口
5. 验证：
- mock 流程不受影响
- 连接失败路径能给出明确错误

## 5. 新增相机驱动步骤

以 `newcam` 为例：

1. 在 `src/psf_scan/drivers/camera_newcam.py` 新建类，继承 `CameraBase`
2. 最少实现：
- `connect/disconnect`
- `start_streaming/stop_streaming`
- `grab_one`
- `set_exposure_us/set_gain`
3. 能力接口按支持情况返回：
- gamma/black/fps/pixel format 不支持时返回 `None` 或空 tuple
4. 在 `src/psf_scan/core/camera.py`：
- 把 `newcam` 加入 `AVAILABLE_CAMERAS`
- 在 `make_camera` 增加分支
5. 验证：
- `CameraView.configure_camera/configure_advanced` 正常
- 扫描线程中 `grab_one` 可稳定返回

## 6. 安全相关改动注意

1. 软限位由 `core/safety.py` 定义，`app.py` 在 `_on_move/_on_scan_start` 执行检查
2. PI driver 内部还有硬件坐标 guard（`pi_travel.py`），两层保护都要保留
3. 任何放宽限位或跳过检查的改动都应写明风险，并默认关闭

## 7. 开发与验证

安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

运行：

```bash
python -m psf_scan
```

基础检查：

```bash
python -m compileall -q src
```

测试（若环境已安装 pytest）：

```bash
python -m pytest -q
```

## 8. 打包相关

Windows 打包资源和脚本位于 `installer/`：

- `installer/build.ps1`
- `installer/psf_scan.spec`
- `installer/PsfScan.iss`

版本信息同步脚本：`installer/bump_version.py`。

## 9. 提交前清单

1. 新增 UI 文案是否全部 i18n 化
2. 安全流程是否保持：软限位 + 大幅移动确认 + 急停
3. mock 流程是否可跑通
4. 数据保存格式是否保持兼容（h5/tif/mat/csv/json）
