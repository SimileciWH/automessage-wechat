"""
tests/test_performance.py — 页面卡顿自动化检测

指标定义（W3C Long Task API）：
  - Long Task：主线程单次任务阻塞 > 50ms
  - TBT (Total Blocking Time)：所有 Long Task 超出 50ms 部分之和
  - 通过阈值：
      * 关键操作期间 Long Task 次数 = 0（无卡顿）
      * 最长 Long Task < 100ms
      * TBT < 200ms
      * Console DOM 节点 ≤ 200
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_CSV = FIXTURES_DIR / "test_crew.csv"
APP_PORT = 5099  # 独立端口，不干扰主服务
APP_URL = f"http://localhost:{APP_PORT}"

# ── 卡顿阈值 ──────────────────────────────────────────────────────────────────
MAX_LONG_TASK_MS = 100      # 单次 Long Task 上限
MAX_TBT_MS = 200            # Total Blocking Time 上限
MAX_CONSOLE_NODES = 200     # Console 区 DOM 节点上限

# ── 注入 PerformanceObserver 的 JS ────────────────────────────────────────────
INJECT_OBSERVER_JS = """
() => {
    window.__longTasks = [];
    const obs = new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
            window.__longTasks.push({
                duration: entry.duration,
                startTime: entry.startTime,
            });
        }
    });
    obs.observe({ type: 'longtask', buffered: true });
}
"""

COLLECT_METRICS_JS = """
() => {
    const tasks = window.__longTasks || [];
    const count = tasks.length;
    const maxDuration = count > 0 ? Math.max(...tasks.map(t => t.duration)) : 0;
    const tbt = tasks.reduce((acc, t) => acc + Math.max(0, t.duration - 50), 0);
    return { count, maxDuration, tbt, tasks };
}
"""

RESET_OBSERVER_JS = "() => { window.__longTasks = []; }"


# ── Flask 服务 fixture ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def flask_server():
    """启动测试用 Flask 实例，session 结束后自动关闭。"""
    env = os.environ.copy()
    env.update({
        "OPENAI_BASE_URL": "http://localhost:9999/v1",  # 不需要真实 AI
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "test-model",
    })
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=Path(__file__).parent.parent,
        env={**env, "FLASK_PORT": str(APP_PORT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # 等待服务就绪
    for _ in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(f"{APP_URL}/", timeout=1)
            break
        except Exception:
            pass
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture()
def page_with_csv(flask_server):
    """返回已上传测试 CSV 的页面，Long Task observer 已注入。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        page.goto(APP_URL)
        page.evaluate(INJECT_OBSERVER_JS)

        # 上传测试 CSV
        with page.expect_file_chooser() as fc_info:
            page.click("#fileDrop")
        fc_info.value.set_files(str(TEST_CSV))
        page.wait_for_selector("#tableBody tr", timeout=5000)

        yield page
        browser.close()


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def assert_no_jank(page: Page, label: str):
    """断言上次 reset 以来无卡顿，失败时打印详情。"""
    metrics = page.evaluate(COLLECT_METRICS_JS)
    count = metrics["count"]
    max_dur = metrics["maxDuration"]
    tbt = metrics["tbt"]

    print(f"\n[{label}] Long Tasks={count}, max={max_dur:.1f}ms, TBT={tbt:.1f}ms")
    for t in metrics.get("tasks", []):
        print(f"  └─ task duration={t['duration']:.1f}ms @ {t['startTime']:.0f}ms")

    assert count == 0, (
        f"[{label}] 检测到 {count} 个 Long Task（>50ms）\n"
        f"  最长: {max_dur:.1f}ms（阈值 {MAX_LONG_TASK_MS}ms）\n"
        f"  TBT : {tbt:.1f}ms（阈值 {MAX_TBT_MS}ms）"
    )


def reset_metrics(page: Page):
    page.evaluate(RESET_OBSERVER_JS)


# ── 测试用例 ──────────────────────────────────────────────────────────────────

class TestPagePerformance:
    """页面卡顿检测测试套件。"""

    def test_csv_upload_render_no_jank(self, flask_server):
        """CSV 上传 + 表格渲染期间无 Long Task。"""
        import csv as _csv
        # 统计 CSV 数据行数（跳过 header，不受多行 message 影响）
        with TEST_CSV.open(newline='', encoding='utf-8') as f:
            row_count = sum(1 for _ in _csv.DictReader(f))

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(APP_URL)
            page.evaluate(INJECT_OBSERVER_JS)
            # 等待页面稳定（JS 解析、CSS 动画启动等初始化任务完成）
            page.wait_for_timeout(800)
            # 清除页面初始化期间的 Long Task，只测量后续用户操作
            page.evaluate(RESET_OBSERVER_JS)

            # 上传 CSV（这是最容易触发卡顿的操作）
            with page.expect_file_chooser() as fc_info:
                page.click("#fileDrop")
            fc_info.value.set_files(str(TEST_CSV))
            # 等待所有分批渲染完成（最后一行出现）
            page.wait_for_selector(
                f"#tableBody tr:nth-child({row_count})",
                timeout=8000,
            )
            page.wait_for_timeout(300)
            assert_no_jank(page, "CSV上传+渲染")
            browser.close()

    def test_checkbox_toggle_no_jank(self, page_with_csv):
        """批量勾选跳过框无 Long Task。"""
        page = page_with_csv
        reset_metrics(page)

        # 勾选所有跳过框
        page.evaluate("""
        () => {
            document.querySelectorAll('tbody input[type=checkbox]').forEach(cb => {
                cb.checked = true;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }
        """)
        page.wait_for_timeout(200)
        assert_no_jank(page, "批量勾选")

    def test_row_expand_collapse_no_jank(self, page_with_csv):
        """展开/收起消息编辑区无 Long Task。"""
        page = page_with_csv
        reset_metrics(page)

        # 展开第一行
        page.click("#tableBody tr:first-child .msg-preview")
        page.wait_for_selector(".expand-row", timeout=2000)
        page.wait_for_timeout(200)

        # 收起
        page.click("#tableBody tr:first-child .msg-preview")
        page.wait_for_timeout(200)
        assert_no_jank(page, "展开/收起行")

    def test_console_log_node_limit(self, page_with_csv):
        """Console 区快速写入 300 条日志后，app 自动裁剪，DOM 节点不超过 MAX_CONSOLE_NODES。"""
        page = page_with_csv

        # 先清空 console，确保从 0 开始计数
        page.click("#consoleClear")
        page.wait_for_timeout(100)

        # 直接调用 app.js 的 log() 函数写入 300 条（由 app 自己处理裁剪）
        page.evaluate("""
        () => {
            for (let i = 0; i < 300; i++) {
                window.log(`日志测试 ${i}`);
            }
        }
        """)
        node_count = page.evaluate(
            "() => document.getElementById('consoleBody').children.length"
        )
        assert node_count <= MAX_CONSOLE_NODES, (
            f"Console DOM 节点 {node_count} 超过上限 {MAX_CONSOLE_NODES}，"
            f"app.js 的 log() 函数需要自动裁剪旧节点"
        )

    def test_stats_update_no_jank(self, page_with_csv):
        """频繁触发 updateStats 无 Long Task（模拟 SSE 高频事件）。"""
        page = page_with_csv
        reset_metrics(page)

        # 连续触发 50 次 checkbox change，模拟 SSE 高频更新
        page.evaluate("""
        () => {
            const checkboxes = document.querySelectorAll('tbody input[type=checkbox]');
            for (let i = 0; i < 50; i++) {
                const cb = checkboxes[i % checkboxes.length];
                cb.checked = !cb.checked;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        """)
        page.wait_for_timeout(300)
        assert_no_jank(page, "频繁stats更新")
