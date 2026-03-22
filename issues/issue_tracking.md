# Issue Tracking

---

## [FIXED] BUG-002 — 通过 Web 控制台执行时 WeChat 联系人搜索失败

- **发现时间**: 2026-03-22 16:00
- **修复时间**: 2026-03-22 17:30
- **严重级别**: High
- **验证截图**: `validation/bug002_fixed_pasted.png`

### 现象

通过 Web 控制台点击"执行"按钮触发 `crew_sender.py` 时，第一个用户（明烨，`wechat_name="[老][2026Q1][AI 编程] 好运-明烨"`）搜索失败：
```
未找到联系人「[老][2026Q1][AI 编程] 好运-明烨」，请检查微信备注名是否与 CSV 一致
```

### 根本原因

`app.py` 中 subprocess 使用字符串 `'python'` 启动 `crew_sender.py`，该命令在 cwd 环境中解析到 `/Users/admin/.venv/whisper/bin/python`（Python 3.14），而 Python 3.14 未安装 OpenCV，导致 `pyautogui.locate()` 的 `confidence` 参数抛出 `NotImplementedError`，模板匹配全部失败，联系人搜索结果无法识别。

### 修复

`app.py` 中将 subprocess 命令从 `'python'` 改为 `sys.executable`，确保子进程与 Flask 使用同一个 Python 3.11（含 OpenCV）：

```python
import sys

cmd = [
    sys.executable, "crew_sender.py", filepath,  # 原为: "python"
    "--no-confirm", "--json-progress",
]
```

同时在 `crew_sender.py` 的 `detect_contact_in_results` 中增加了：
- `recently_used_label.png` 作为 `contacts_label.png` 的回退锚点（confidence=0.55）
- 策略二兜底：两个标签都找不到时，用 `get_wechat_window()` 坐标定位区域
- `_count_info_buttons` 增加 `NotImplementedError` 处理，兼容无 OpenCV 环境

### 验证结果

安全模式执行，明烨状态从 `FAIL ✗` → `PASTED ✓`，COMM LOG 显示 `📋 [01/01] 明烨 已粘贴`。

---

## [FIXED] BUG-001 — CSS `hidden` 属性被 `display: flex` 覆盖导致空状态遮挡表格

- **发现时间**: 2026-03-22 15:52
- **修复时间**: 2026-03-22 16:00
- **修复**: 在 `static/style.css` reset 区添加 `[hidden] { display: none !important; }`

### 现象

CSV 加载成功后（控制台显示"已加载 27 位成员"，统计数字正确），主内容区仍显示空状态"请从左侧导入 CSV 文件"，看不到成员表格。

### 根因

`.empty-state` CSS 明确设置 `display: flex`，覆盖了 HTML `hidden` 属性的 `display: none` 效果。
