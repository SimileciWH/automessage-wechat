#!/usr/bin/env python3
"""
crew_sender.py — 船员打卡消息自动发送系统

用法：
    python3 crew_sender.py [csv文件]            # 正常发送
    python3 crew_sender.py [csv文件] --dry-run  # 只检测不发送
"""

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pyautogui
import pyperclip
from dotenv import load_dotenv
from openai import OpenAI

# ── 配置区 ────────────────────────────────────────────────────────────────────
CHECKINS_REQUIRED       = 12        # 打卡满多少次可上岸领 199 元
SKIP_NAMES: list[str]   = []        # 固定跳过的姓名列表，每次运行均跳过
DEFAULT_CSV             = "crew_today.csv"
SEND_INTERVAL           = 4.0       # 每条发完后冷却秒数
SEARCH_WAIT             = 1.5       # 粘贴姓名后等待搜索结果秒数
OPEN_WAIT               = 1.2       # 点击联系人后等待对话窗口打开秒数
LOCATE_CONFIDENCE       = 0.85      # locateOnScreen 置信度阈值（通用）
INFO_BTN_CONFIDENCE     = 0.75      # ⓘ 按钮专用阈值（深色模式模板匹配 0.9+，0.60 会产生像素级重复误报）
SENT_VARIANCE_THRESHOLD = 12.0      # verify_sent 方差阈值（首次实测后调整）

# ── 自定义异常 ─────────────────────────────────────────────────────────────────


class FailError(Exception):
    pass


# ── JSON 进度输出（供 Web SSE 解析） ──────────────────────────────────────────

_json_progress = False


def _emit(obj: dict) -> None:
    """输出 JSON Lines 进度，仅在 --json-progress 模式下启用。"""
    if _json_progress:
        print(json.dumps(obj, ensure_ascii=False), flush=True)


# ── AI 初始化（模块级，启动时执行一次） ─────────────────────────────────────────

load_dotenv()

_client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
_model = os.environ.get("OPENAI_MODEL", "deepseek-v3-0324")

SYSTEM_PROMPT = """\
你是一位高情商的船队打卡激励助手，说话风格像一个真心关心船员的老朋友——活泼、热情、有温度，\
不说废话，不讲套路，让人看了真的开心和被鼓励到。

严格按照以下格式输出，不得添加任何额外说明或内容：

hello，{name}，你已经连续打卡 {checkins} 次，{shore_hint}。

我看了你的打卡内容，{specific_encouragement}

继续冲！
----------
{motivational_quote}

字段说明：

- {name}：直接使用提供的姓名

- {checkins}：直接使用提供的打卡次数数字

- {shore_hint}：
  打卡次数 < 12 时，填「还有 X 次就上岸啦」（X = 12 - 打卡次数），\
语气要带点兴奋感，让人感觉上岸近在眼前；
  打卡次数 ≥ 12 时，填「你已经上岸啦，真的太厉害了」，语气要发自内心地激动和骄傲

- {specific_encouragement}：
  这是最重要的部分。用户给的评价可能很口语、很简短，你需要高情商地润色和扩写，\
紧紧抓住打卡内容的具体亮点来写，让对方感受到「你真的认真看了我写的东西」。
  要求：
  · 绝对不能泛泛而谈（禁止出现「很棒」「很好」「不错」这类空洞词）
  · 要挖掘出这个行为背后的精神或态度，说出来让对方有共鸣
  · 语气热情、真诚，像朋友在聊天，不像领导在点评
  · 2～3句话，以句号结尾

- {motivational_quote}：
  一句充满感情、正能量爆棚的励志语，要求：
  · 口语化，像真人脱口而出的，不要文绉绉
  · 有画面感或情绪感染力，让人看了想立刻行动
  · 适合在船上工作的人，贴近他们的生活状态
  · 每次都要不一样，禁止重复使用同一句话

格式要求：
- 正文连续文字超过 3 行时，需在适当位置插入一个空行，保持阅读节奏
- 不加 emoji，不加多余标点
- 整体语气：活泼、积极、高情商、有情绪感染力\
"""


# ── CSV 数据层 ─────────────────────────────────────────────────────────────────


def load_csv(path: str) -> list[dict]:
    """读取 CSV，校验必要列，返回 list[dict]。格式错误立即退出。

    CSV 必须包含四列：微信名称（搜索用）、姓名（消息称谓）、打卡次数、评价。
    Excel 导出时末尾可能有多余空列（,,,,,）自动忽略。
    可选第五列 message：已有内容则直接使用，不再调用 AI。
    """
    required = {"微信名称", "姓名", "打卡次数", "评价"}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        sys.exit(f"❌ 找不到文件：{path}")
    except UnicodeDecodeError as e:
        sys.exit(f"❌ CSV 编码错误（需 UTF-8）：{e}")

    if not rows:
        sys.exit(f"❌ CSV 文件为空：{path}")

    # 过滤 Excel 导出时产生的空列名（如 ",,,,,,,,,," 对应的空字符串 key）
    rows = [{k: v for k, v in row.items() if k.strip()} for row in rows]

    missing = required - set(rows[0].keys())
    if missing:
        sys.exit(f"❌ CSV 缺少必要列：{missing}")

    for i, row in enumerate(rows, 2):
        try:
            int(row["打卡次数"])
        except ValueError:
            sys.exit(f"❌ 第 {i} 行「打卡次数」不是整数：{row['打卡次数']!r}")

    return rows


# ── AI 文案生成层 ──────────────────────────────────────────────────────────────


def generate_message(name: str, checkins: int, comment: str) -> str:
    """调用七牛云 DeepSeek API 生成单条鼓励消息。"""
    user_prompt = (
        f"姓名：{name}\n"
        f"打卡次数：{checkins}\n"
        f"今日打卡内容评价：{comment}"
    )
    resp = _client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def generate_all_messages(crew_data: list[dict]) -> list[dict]:
    """批量生成文案，返回附带 message 字段的 list[dict]。

    若 CSV 已有 message 列且非空，则直接复用，不调用 AI。
    """
    results = []
    total = len(crew_data)
    for i, row in enumerate(crew_data, 1):
        wechat_name = row["微信名称"].strip()
        name        = row["姓名"].strip()
        checkins    = int(row["打卡次数"])
        comment     = row["评价"].strip()
        existing_msg = row.get("message", "").strip()

        if existing_msg:
            print(f"  复用消息 [{i:02d}/{total}]  {name}")
            message = existing_msg
        else:
            print(f"  生成文案 [{i:02d}/{total}]  {name} ...", end=" ", flush=True)
            try:
                message = generate_message(name, checkins, comment)
            except Exception as e:
                sys.exit(f"\n❌ AI 生成失败（{name}）：{e}")
            print("完成")

        results.append({
            "wechat_name": wechat_name,
            "name":        name,
            "checkins":    checkins,
            "comment":     comment,
            "message":     message,
        })
    return results


# ── 预览与确认层 ───────────────────────────────────────────────────────────────


def preview_and_confirm(crew_messages: list[dict], initial_skip: set) -> set:
    """打印所有文案，允许操作者追加跳过，返回最终 skip 集合。"""
    skip = set(initial_skip)
    print("\n" + "=" * 60)
    print("📋  文案预览")
    print("=" * 60)
    for i, item in enumerate(crew_messages, 1):
        tag = "  ⏭ 跳过" if item["name"] in skip else ""
        print(f"\n[{i:02d}]  {item['name']}  (打卡 {item['checkins']} 次){tag}")
        print(f"      {item['message']}")
    print("\n" + "=" * 60)

    raw = input("输入要临时跳过的姓名（逗号分隔），留空则不跳过：\n> ").strip()
    if raw:
        for n in raw.split(","):
            skip.add(n.strip())

    ans = input("\n确认发送？输入 yes 开始，其他任意键取消：\n> ").strip().lower()
    if ans != "yes":
        print("已取消。")
        sys.exit(0)

    return skip


# ── 微信控制层 ─────────────────────────────────────────────────────────────────


def get_wechat_window() -> tuple[int, int, int, int]:
    """通过 AppleScript 获取微信窗口 (x, y, w, h)。"""
    script = """
    tell application "System Events" to tell process "WeChat"
        set p to position of window 1
        set s to size of window 1
        return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ¬
               ((item 1 of s) as text) & "," & ((item 2 of s) as text)
    end tell
    """
    out = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    x, y, w, h = map(int, out.split(","))
    return x, y, w, h


def _wechat_hotkey(key: str, modifier: str = "command") -> None:
    """
    通过 AppleScript keystroke 向 WeChat 进程发送快捷键。
    绕过输入法（IME）拦截，比 pyautogui.hotkey 更可靠。
    """
    script = (
        f'tell application "System Events" to tell process "WeChat" '
        f'to keystroke "{key}" using {modifier} down'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)


def _wechat_keycode(code: int) -> None:
    """通过 AppleScript key code 向 WeChat 发送按键（无修饰键）。"""
    script = (
        f'tell application "System Events" to tell process "WeChat" '
        f'to key code {code}'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)


def activate_wechat() -> None:
    """激活微信至前台。"""
    subprocess.run(
        ["osascript", "-e", 'tell application "WeChat" to activate'],
        capture_output=True, timeout=5,
    )
    time.sleep(0.8)


def open_search() -> None:
    """Cmd+F 打开微信搜索框（AppleScript 绕过输入法）。"""
    _wechat_hotkey("f")
    time.sleep(0.6)


def search_contact(name: str) -> None:
    """清空搜索框，粘贴联系人姓名，等待结果渲染。"""
    _wechat_hotkey("a")          # Cmd+A 全选
    time.sleep(0.1)
    pyperclip.copy(name)
    _wechat_hotkey("v")          # Cmd+V 粘贴
    time.sleep(SEARCH_WAIT)


def _try_locate(asset: str, screenshot, confidence: float = LOCATE_CONFIDENCE) -> object:
    """尝试在截图中定位模板，找不到或异常均返回 None。"""
    try:
        return pyautogui.locate(asset, screenshot, confidence=confidence)
    except Exception:
        return None


def _get_scale() -> float:
    """返回 Retina 缩放因子（物理像素 / 逻辑像素）。"""
    ss_w = pyautogui.screenshot().size[0]
    return ss_w / pyautogui.size().width


def _to_logical(x: int, y: int, scale: float) -> tuple[int, int]:
    """将 locate() 返回的物理像素坐标转换为 pyautogui.click() 所需的逻辑坐标。"""
    return int(x / scale), int(y / scale)


# 记录上一次 detect_contact_in_results 的诊断信息，供错误消息使用
_detect_diag: str = ""


def _save_debug_screenshot(screenshot, tag: str) -> None:
    """保存调试截图到 logs/ 目录，文件名含时间戳和标签。"""
    from datetime import datetime
    ts = datetime.now().strftime("%H%M%S")
    path = Path(f"logs/debug_{ts}_{tag}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    screenshot.save(str(path))


def _dedup_boxes(boxes, min_dist: int = 30) -> list:
    """去除像素级重复匹配（同一按钮在相邻坐标多次命中）。"""
    unique = []
    for b in boxes:
        if not any(abs(b.left - u.left) < min_dist and abs(b.top - u.top) < min_dist
                   for u in unique):
            unique.append(b)
    return unique


def _count_info_buttons(screenshot, region: tuple) -> int:
    """在指定区域内数 ⓘ 按钮数量，去重后返回，异常视为 0。"""
    try:
        buttons = _dedup_boxes(list(pyautogui.locateAll(
            "assets/info_button.png", screenshot,
            confidence=INFO_BTN_CONFIDENCE, region=region,
        )))
        return len(buttons)
    except NotImplementedError:
        # OpenCV 未安装时不支持 confidence，退回无置信度匹配
        try:
            buttons = _dedup_boxes(list(pyautogui.locateAll(
                "assets/info_button.png", screenshot, region=region,
            )))
            return len(buttons)
        except Exception as e2:
            if type(e2).__name__ != "ImageNotFoundException":
                raise
            return 0
    except Exception as e:
        if type(e).__name__ != "ImageNotFoundException":
            raise
        return 0


def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]:
    """
    截一次全屏，定位联系人区域，数 ⓘ 按钮数量。
    复用同一张截图避免时序差异。
    返回 "ok" / "not_found" / "multiple"。
    失败时将诊断信息写入模块变量 _detect_diag。

    策略一（模板匹配）：用 contacts_label / recently_used_label 定位区域边界。
    策略二（兜底）：模板匹配失败时，用 get_wechat_window() 坐标直接定位
      微信左侧面板搜索下拉区域，避免因 DPI 缩放导致模板匹配失败。
    """
    global _detect_diag
    screenshot = pyautogui.screenshot()

    # 策略一：模板匹配定位上边界
    contacts_pos = _try_locate("assets/contacts_label.png", screenshot)
    recently_pos = _try_locate("assets/recently_used_label.png", screenshot, confidence=0.75)
    ref_pos = contacts_pos or recently_pos
    strategy = "contacts_label" if contacts_pos else ("recently_used_label" if recently_pos else None)

    if ref_pos is not None:
        # 找下边界
        lower_bounds = []
        for asset in ("assets/group_chats_label.png",
                      "assets/internet_search_label.png"):
            pos = _try_locate(asset, screenshot)
            if pos is not None:
                lower_bounds.append(pos.top)
        region_bottom = min(lower_bounds) if lower_bounds else ref_pos.top + 200
        # 宽度用 800px 覆盖 Retina 2x 下微信搜索面板全宽（ⓘ 按钮在右侧约 600px 处）
        region = (ref_pos.left, ref_pos.top, 800, region_bottom - ref_pos.top)
        count = _count_info_buttons(screenshot, region)
        _detect_diag = (
            f"策略一({strategy})：区域 {region}，ⓘ 按钮数={count}"
        )
    else:
        # 策略二：模板匹配失败，用微信窗口坐标兜底
        _save_debug_screenshot(screenshot, "detect_fallback")
        try:
            wx_x, wx_y, wx_w, wx_h = get_wechat_window()
        except Exception:
            _detect_diag = "策略二：获取微信窗口坐标失败"
            return "not_found"
        panel_region = (wx_x, wx_y + 50, 300, 450)
        count = _count_info_buttons(screenshot, panel_region)
        _detect_diag = (
            f"策略二(坐标兜底)：两个标签均未匹配，"
            f"扫描区域 {panel_region}，ⓘ 按钮数={count}；"
            f"请重新截取 assets/recently_used_label.png"
        )

    if count == 0:
        _save_debug_screenshot(screenshot, "detect_not_found")
        return "not_found"
    elif count == 1:
        _detect_diag = ""
        return "ok"
    else:
        return "multiple"


def click_contact(contacts_label_pos) -> None:
    """点击 Contacts/Recently Used 标签下方联系人行（自动转换 Retina 物理→逻辑坐标）。"""
    scale = _get_scale()
    phys_x = contacts_label_pos.left + contacts_label_pos.width // 2
    phys_y = contacts_label_pos.top + contacts_label_pos.height + 38
    lx, ly = _to_logical(phys_x, phys_y, scale)
    pyautogui.click(lx, ly)
    time.sleep(OPEN_WAIT)


def verify_window_title(name: str) -> bool:
    """
    WeChat 4.x 的自定义渲染框架不通过 accessibility API 暴露聊天文本，
    改用截图间接验证：点击联系人后搜索下拉框消失 = 已成功进入聊天窗口。
    结合 detect_contact_in_results 已验证"唯一联系人"，安全性足够。
    """
    screenshot = pyautogui.screenshot()
    try:
        contacts_pos = pyautogui.locate(
            "assets/contacts_label.png", screenshot,
            confidence=LOCATE_CONFIDENCE,
        )
    except Exception:
        contacts_pos = None
    # 搜索下拉消失（contacts_label 不再出现）= 已进入聊天，视为验证通过
    return contacts_pos is None


def send_message(message: str, wx_window: tuple, paste_only: bool = False) -> None:
    """
    点击输入框，粘贴消息。
    paste_only=False（默认）：粘贴后按 Enter 发送。
    paste_only=True（安全确认模式）：只粘贴，不按 Enter，由人工发送。
    """
    wx_x, wx_y, wx_w, wx_h = wx_window
    input_x = wx_x + wx_w - 370    # 右侧聊天面板中心
    input_y = wx_y + wx_h - 55
    pyautogui.click(input_x, input_y)
    time.sleep(0.3)
    _wechat_hotkey("a")             # Cmd+A 清空防残留
    time.sleep(0.1)
    pyperclip.copy(message)
    _wechat_hotkey("v")             # Cmd+V 粘贴
    time.sleep(0.4)
    if not paste_only:
        _wechat_keycode(36)         # key code 36 = Return
        time.sleep(0.5)


def verify_sent(wx_window: tuple) -> bool:
    """
    截取输入框区域，计算灰度像素标准差。
    有文字时方差大，清空后接近纯色方差小。
    校准：首次运行后观察打印的实际方差值，调整 SENT_VARIANCE_THRESHOLD。
    """
    wx_x, wx_y, wx_w, wx_h = wx_window
    region = (wx_x + wx_w - 600, wx_y + wx_h - 100, 500, 60)
    screenshot = pyautogui.screenshot(region=region)
    arr = np.array(screenshot.convert("L"))
    variance = float(arr.std())
    print(f"[verify_sent std={variance:.2f} threshold={SENT_VARIANCE_THRESHOLD}]",
          end=" ", flush=True)
    return variance < SENT_VARIANCE_THRESHOLD


# ── 单人完整流程 ───────────────────────────────────────────────────────────────


def send_one(wechat_name: str, name: str, message: str, wx_window: tuple,
             safe_mode: bool = False) -> None:
    """
    执行单人完整微信发送流程。任何环节异常均抛出 FailError。
    wechat_name：用于微信搜索（CSV 的「微信名称」列）。
    name：用于错误信息和日志（CSV 的「姓名」列）。
    safe_mode=True：只粘贴不发送，跳过 verify_sent（由人工手动按 Enter）。
    """
    activate_wechat()
    open_search()
    search_contact(wechat_name)     # 用微信名称搜索

    result = detect_contact_in_results()
    if result == "not_found":
        diag = f"（{_detect_diag}）" if _detect_diag else ""
        raise FailError(
            f"未找到联系人「{wechat_name}」，请检查微信备注名是否与 CSV 一致{diag}")
    if result == "multiple":
        raise FailError(
            f"「{wechat_name}」搜索结果不唯一，存在发错人风险")

    # 重新截图获取点击参考位置
    screenshot = pyautogui.screenshot()
    scale = _get_scale()
    ref_pos = _try_locate("assets/contacts_label.png", screenshot)
    if ref_pos is None:
        ref_pos = _try_locate("assets/recently_used_label.png", screenshot,
                              confidence=0.75)

    if ref_pos is not None:
        click_contact(ref_pos)
    else:
        # 兜底：找 ⓘ 按钮，点击其左侧联系人行（同样需要转逻辑坐标）
        info_pos = _try_locate("assets/info_button.png", screenshot,
                               confidence=INFO_BTN_CONFIDENCE)
        if info_pos is None:
            raise FailError(f"「{name}」点击前定位失败，找不到联系人行")
        phys_x = info_pos.left - 80
        phys_y = info_pos.top + info_pos.height // 2
        lx, ly = _to_logical(phys_x, phys_y, scale)
        pyautogui.click(lx, ly)

    if not verify_window_title(name):
        raise FailError(f"「{name}」窗口标题验证失败，实际打开了其他对话")

    send_message(message, wx_window, paste_only=safe_mode)

    if not safe_mode and not verify_sent(wx_window):
        raise FailError(f"「{name}」消息发送未确认，请手动检查微信")


# ── 日志层 ────────────────────────────────────────────────────────────────────


def save_log(path: Path, results: list[dict]) -> None:
    """将发送结果写入 JSON 日志文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ── 主流程辅助函数 ────────────────────────────────────────────────────────────


def _make_log_entry(item: dict, status: str, **extra) -> dict:
    """构造单条日志记录。"""
    return {
        "wechat_name": item.get("wechat_name", ""),
        "name":        item["name"],
        "status":      status,
        "checkins":    item["checkins"],
        "message":     item["message"],
        "time":        datetime.now().isoformat(timespec="seconds"),
        **extra,
    }


def _dry_run_one(wechat_name: str, item: dict, results: list) -> None:
    """dry-run 模式：搜索+检测，不点击不发送。"""
    activate_wechat()
    open_search()
    search_contact(wechat_name)
    detect_result = detect_contact_in_results()
    print(f"检测={detect_result}  [DRY_RUN]")
    # 关闭搜索框，避免干扰下次（key code 53 = Escape）
    _wechat_keycode(53)
    time.sleep(0.3)
    results.append(_make_log_entry(item, "DRY_RUN", detect=detect_result))


def _send_loop(
    to_send: list[dict],
    wx_window: tuple,
    log_file: Path,
    results: list[dict],
    mode: str,   # "normal" | "dry_run" | "safe"
) -> None:
    """主发送循环，FAIL 即停，支持 Ctrl+C 中断。"""
    total = len(to_send)
    _emit({"type": "start", "total": total})

    for idx, item in enumerate(to_send, 1):
        name        = item["name"]
        wechat_name = item["wechat_name"]
        if not _json_progress:
            print(f"  [{idx:02d}/{total}]  {name} ...", end=" ", flush=True)
        _emit({"type": "progress", "index": idx, "total": total,
               "name": name, "status": "sending"})

        if mode == "dry_run":
            _dry_run_one(wechat_name, item, results)
            time.sleep(1.0)
            continue

        is_safe = (mode == "safe")
        try:
            send_one(wechat_name, name, item["message"], wx_window, safe_mode=is_safe)
            if is_safe:
                if not _json_progress:
                    print("📋 已粘贴")
                results.append(_make_log_entry(item, "PASTED"))
                _emit({"type": "progress", "index": idx, "total": total,
                       "name": name, "status": "pasted"})
            else:
                if not _json_progress:
                    print("✅")
                results.append(_make_log_entry(item, "SENT"))
                _emit({"type": "progress", "index": idx, "total": total,
                       "name": name, "status": "sent"})
        except FailError as e:
            if not _json_progress:
                print("❌ FAIL")
            results.append(_make_log_entry(item, "FAIL", reason=str(e)))
            _emit({"type": "progress", "index": idx, "total": total,
                   "name": name, "status": "fail", "reason": str(e)})
            save_log(log_file, results)
            if not _json_progress:
                print(f"\n❌ FAIL — {e}")
                print(f"🛑 自动化已停止（已完成 {idx - 1}/{total} 条）")
                print(f"📄 日志已保存至 {log_file}")
            sys.exit(1)
        except KeyboardInterrupt:
            if not _json_progress:
                print("\n\n⚠️  用户中断")
            save_log(log_file, results)
            if not _json_progress:
                print(f"📄 日志已保存至 {log_file}（已完成 {idx - 1}/{total} 条）")
            sys.exit(0)

        if not is_safe:
            time.sleep(SEND_INTERVAL)


# ── 主流程 ────────────────────────────────────────────────────────────────────


def run(
    csv_path: str,
    dry_run: bool = False,
    safe: bool = False,
    no_confirm: bool = False,
    extra_skip: set | None = None,
    json_progress: bool = False,
) -> None:
    """主流程：读取 → 生成 → 预览 → 发送 → 记录日志。

    no_confirm：跳过终端预览确认（Web 后端调用时使用）。
    extra_skip：临时跳过名单（来自 --skip 参数或 Web 后端）。
    json_progress：以 JSON Lines 输出进度，供 Web SSE 解析。
    """
    global _json_progress
    _json_progress = json_progress

    if dry_run:
        mode = "dry_run"
        mode_tag = "  [DRY-RUN 模式]"
    elif safe:
        mode = "safe"
        mode_tag = "  [安全确认模式 · 只粘贴不发送]"
    else:
        mode = "normal"
        mode_tag = ""

    if not json_progress:
        print(f"\n{'=' * 60}\n  🚢  船员打卡消息自动发送系统{mode_tag}\n{'=' * 60}\n")
        print("📂  读取 CSV ...")

    crew_data = load_csv(csv_path)

    if not json_progress:
        print(f"    共 {len(crew_data)} 位船员\n")
        print("✍️   调用 AI 生成文案 ...")

    crew_messages = generate_all_messages(crew_data)

    initial_skip = set(SKIP_NAMES) | (extra_skip or set())
    if no_confirm:
        skip = initial_skip
    else:
        skip = preview_and_confirm(crew_messages, initial_skip)

    to_send = [m for m in crew_messages if m["name"] not in skip]
    skipped = [m for m in crew_messages if m["name"] in skip]

    if not json_progress:
        print(f"\n📤  即将处理 {len(to_send)} 条，跳过 {len(skipped)} 条")

    # dry-run 不需要 wx_window（不点击不发送）
    wx_window = (0, 0, 0, 0)
    if mode != "dry_run":
        try:
            wx_window = get_wechat_window()
        except Exception as e:
            sys.exit(f"❌ 无法获取微信窗口：{e}，请确认微信已打开")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = Path("logs") / f"log_{timestamp}.json"
    results: list[dict] = [_make_log_entry(m, "SKIPPED") for m in skipped]

    _send_loop(to_send, wx_window, log_file, results, mode)

    save_log(log_file, results)
    sent   = sum(1 for r in results if r["status"] == "SENT")
    pasted = sum(1 for r in results if r["status"] == "PASTED")
    dry_n  = sum(1 for r in results if r["status"] == "DRY_RUN")
    skip_n = sum(1 for r in results if r["status"] == "SKIPPED")
    fail_n = sum(1 for r in results if r["status"] == "FAIL")

    _emit({"type": "done", "sent": sent, "pasted": pasted,
           "skipped": skip_n, "failed": fail_n, "dry_run": dry_n})

    if not json_progress:
        if mode == "safe":
            print(f"\n📋  已粘贴 {pasted} 条消息到微信聊天框，请逐一检查并手动按 Enter 发送")
        else:
            print(f"\n🎉  完成！SENT={sent}  SKIPPED={skip_n}  DRY_RUN={dry_n}")
        print(f"📄  日志已保存至 {log_file}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="船员打卡消息自动发送系统")
    parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--safe", action="store_true")
    parser.add_argument("--no-confirm", action="store_true", help="跳过终端预览确认")
    parser.add_argument("--skip", default="", help="临时跳过名单，逗号分隔")
    parser.add_argument("--json-progress", action="store_true", help="JSON Lines 进度输出")
    args = parser.parse_args()

    extra = {n.strip() for n in args.skip.split(",") if n.strip()}
    run(
        args.csv,
        dry_run=args.dry_run,
        safe=args.safe,
        no_confirm=args.no_confirm,
        extra_skip=extra,
        json_progress=args.json_progress,
    )
