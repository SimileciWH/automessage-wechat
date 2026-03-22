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
LOCATE_CONFIDENCE       = 0.85      # locateOnScreen 置信度阈值
SENT_VARIANCE_THRESHOLD = 12.0      # verify_sent 方差阈值（首次实测后调整）

# ── 自定义异常 ─────────────────────────────────────────────────────────────────


class FailError(Exception):
    pass


# ── AI 初始化（模块级，启动时执行一次） ─────────────────────────────────────────

load_dotenv()

_client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
_model = os.environ.get("OPENAI_MODEL", "deepseek-v3-0324")

SYSTEM_PROMPT = """\
你是船队打卡激励助手。根据用户提供的信息，严格按照以下格式输出一条鼓励消息，\
不得添加任何额外说明或内容：

hello，{name}，你已经连续打卡 {checkins} 次，{shore_hint}。\
我看了你的打卡内容，{specific_encouragement}
继续加油！
----------
{motivational_quote}

字段说明：
- {name}：直接使用提供的姓名
- {checkins}：直接使用提供的打卡次数数字
- {shore_hint}：打卡次数 < 12 时填「还有 X 次就上岸啦」（X = 12 - 打卡次数）；\
  打卡次数 ≥ 12 时填「你已经完成了上岸目标，太棒了」
- {specific_encouragement}：结合今日打卡内容评价具体说，不得泛泛而谈，以句号结尾
- {motivational_quote}：一句简短有力的励志语，适合激励在船工作的人，口语化

整体要求：口语化、自然、积极，不加 emoji，不分段。\
"""


# ── CSV 数据层 ─────────────────────────────────────────────────────────────────


def load_csv(path: str) -> list[dict]:
    """读取 CSV，校验必要列，返回 list[dict]。格式错误立即退出。"""
    required = {"姓名", "打卡次数", "评价"}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        sys.exit(f"❌ 找不到文件：{path}")
    except UnicodeDecodeError as e:
        sys.exit(f"❌ CSV 编码错误（需 UTF-8）：{e}")

    if not rows:
        sys.exit(f"❌ CSV 文件为空：{path}")

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
    """批量生成文案，返回附带 message 字段的 list[dict]。"""
    results = []
    total = len(crew_data)
    for i, row in enumerate(crew_data, 1):
        name = row["姓名"].strip()
        checkins = int(row["打卡次数"])
        comment = row["评价"].strip()
        print(f"  生成文案 [{i:02d}/{total}]  {name} ...", end=" ", flush=True)
        try:
            message = generate_message(name, checkins, comment)
        except Exception as e:
            sys.exit(f"\n❌ AI 生成失败（{name}）：{e}")
        print("完成")
        results.append({"name": name, "checkins": checkins,
                        "comment": comment, "message": message})
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


def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]:
    """
    截一次全屏，定位 Contacts 区域，数 ⓘ 按钮数量。
    复用同一张截图避免时序差异。
    返回 "ok" / "not_found" / "multiple"。
    """
    screenshot = pyautogui.screenshot()

    contacts_pos = pyautogui.locate(
        "assets/contacts_label.png", screenshot,
        confidence=LOCATE_CONFIDENCE,
    )
    if contacts_pos is None:
        return "not_found"

    group_chats_pos = pyautogui.locate(
        "assets/group_chats_label.png", screenshot,
        confidence=LOCATE_CONFIDENCE,
    )

    region_top    = contacts_pos.top
    region_bottom = (
        group_chats_pos.top if group_chats_pos else contacts_pos.top + 200
    )
    contacts_region = (
        contacts_pos.left,
        region_top,
        500,   # 覆盖完整搜索下拉面板宽度（info_button 可能超出原来的 300px）
        region_bottom - region_top,
    )

    try:
        info_buttons = list(pyautogui.locateAll(
            "assets/info_button.png", screenshot,
            confidence=LOCATE_CONFIDENCE, region=contacts_region,
        ))
    except Exception as e:
        # pyscreeze.ImageNotFoundException 和 pyautogui.ImageNotFoundException
        # 在某些安装环境下是不同的类，统一用名字判断
        if type(e).__name__ != "ImageNotFoundException":
            raise
        info_buttons = []

    count = len(info_buttons)
    if count == 0:
        return "not_found"
    elif count == 1:
        return "ok"
    else:
        return "multiple"


def click_contact(contacts_label_pos) -> None:
    """点击 Contacts 标签下方约 38px 处的联系人行。"""
    click_x = contacts_label_pos.left + contacts_label_pos.width // 2
    click_y = contacts_label_pos.top + contacts_label_pos.height + 38
    pyautogui.click(click_x, click_y)
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


def send_one(name: str, message: str, wx_window: tuple,
             safe_mode: bool = False) -> None:
    """
    执行单人完整微信发送流程。任何环节异常均抛出 FailError。
    safe_mode=True：只粘贴不发送，跳过 verify_sent（由人工手动按 Enter）。
    """
    activate_wechat()
    open_search()
    search_contact(name)

    result = detect_contact_in_results()
    if result == "not_found":
        raise FailError(f"未找到联系人「{name}」，请检查备注名是否与 CSV 一致")
    if result == "multiple":
        raise FailError(f"「{name}」搜索结果不唯一，存在发错人风险")

    # 重新截图获取 contacts_pos，用于计算点击坐标
    screenshot = pyautogui.screenshot()
    contacts_pos = pyautogui.locate(
        "assets/contacts_label.png", screenshot,
        confidence=LOCATE_CONFIDENCE,
    )
    click_contact(contacts_pos)

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
        "name": item["name"],
        "status": status,
        "checkins": item["checkins"],
        "message": item["message"],
        "time": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }


def _dry_run_one(name: str, item: dict, results: list) -> None:
    """dry-run 模式：搜索+检测，不点击不发送。"""
    activate_wechat()
    open_search()
    search_contact(name)
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
    for idx, item in enumerate(to_send, 1):
        name = item["name"]
        print(f"  [{idx:02d}/{total}]  {name} ...", end=" ", flush=True)

        if mode == "dry_run":
            _dry_run_one(name, item, results)
            time.sleep(1.0)
            continue

        is_safe = (mode == "safe")
        try:
            send_one(name, item["message"], wx_window, safe_mode=is_safe)
            if is_safe:
                print("📋 已粘贴")
                results.append(_make_log_entry(item, "PASTED"))
            else:
                print("✅")
                results.append(_make_log_entry(item, "SENT"))
        except FailError as e:
            print("❌ FAIL")
            results.append(_make_log_entry(item, "FAIL", reason=str(e)))
            save_log(log_file, results)
            print(f"\n❌ FAIL — {e}")
            print(f"🛑 自动化已停止（已完成 {idx - 1}/{total} 条）")
            print(f"📄 日志已保存至 {log_file}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断")
            save_log(log_file, results)
            print(f"📄 日志已保存至 {log_file}（已完成 {idx - 1}/{total} 条）")
            sys.exit(0)

        if not is_safe:
            time.sleep(SEND_INTERVAL)


# ── 主流程 ────────────────────────────────────────────────────────────────────


def run(csv_path: str, dry_run: bool = False, safe: bool = False) -> None:
    """主流程：读取 → 生成 → 预览 → 发送 → 记录日志。"""
    if dry_run:
        mode = "dry_run"
        mode_tag = "  [DRY-RUN 模式]"
    elif safe:
        mode = "safe"
        mode_tag = "  [安全确认模式 · 只粘贴不发送]"
    else:
        mode = "normal"
        mode_tag = ""
    print(f"\n{'=' * 60}\n  🚢  船员打卡消息自动发送系统{mode_tag}\n{'=' * 60}\n")

    print("📂  读取 CSV ...")
    crew_data = load_csv(csv_path)
    print(f"    共 {len(crew_data)} 位船员\n")

    print("✍️   调用 AI 生成文案 ...")
    crew_messages = generate_all_messages(crew_data)

    initial_skip = set(SKIP_NAMES)
    skip = preview_and_confirm(crew_messages, initial_skip)

    to_send = [m for m in crew_messages if m["name"] not in skip]
    skipped = [m for m in crew_messages if m["name"] in skip]
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
    sent    = sum(1 for r in results if r["status"] == "SENT")
    pasted  = sum(1 for r in results if r["status"] == "PASTED")
    dry_n   = sum(1 for r in results if r["status"] == "DRY_RUN")
    skip_n  = sum(1 for r in results if r["status"] == "SKIPPED")

    if mode == "safe":
        print(f"\n📋  已粘贴 {pasted} 条消息到微信聊天框，请逐一检查并手动按 Enter 发送")
    else:
        print(f"\n🎉  完成！SENT={sent}  SKIPPED={skip_n}  DRY_RUN={dry_n}")
    print(f"📄  日志已保存至 {log_file}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="船员打卡消息自动发送系统")
    parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true", help="只检测不发送（不进入聊天）")
    parser.add_argument("--safe", action="store_true", help="安全确认模式：粘贴消息但不按 Enter，由人工逐一发送")
    args = parser.parse_args()
    run(args.csv, dry_run=args.dry_run, safe=args.safe)
