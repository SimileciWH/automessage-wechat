"""
app.py — 船员打卡消息 Web 控制台 Flask 后端
"""

import csv
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

# ── AI 客户端 ──────────────────────────────────────────────────────────────────

_ai_client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
_ai_model = os.environ.get("OPENAI_MODEL", "deepseek-v3-0324")

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


def _call_ai(name: str, checkins: int, comment: str) -> str:
    user_prompt = (
        f"姓名：{name}\n"
        f"打卡次数：{checkins}\n"
        f"今日打卡内容评价：{comment}"
    )
    resp = _ai_client.chat.completions.create(
        model=_ai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


# ── 心跳 Watchdog ──────────────────────────────────────────────────────────────

_last_heartbeat = time.time()
_send_process: subprocess.Popen | None = None


def _watchdog():
    while True:
        time.sleep(5)
        if _send_process is None:
            if time.time() - _last_heartbeat > 20:
                os.kill(os.getpid(), signal.SIGTERM)


threading.Thread(target=_watchdog, daemon=True).start()

# ── 路由 ───────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()
    return jsonify({"ok": True})


@app.route("/api/load-csv", methods=["POST"])
def load_csv_api():
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400

    f = request.files["file"]
    content = f.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    rows = []
    for row in reader:
        clean = {k: v for k, v in row.items() if k and k.strip()}
        rows.append(clean)

    if not rows:
        return jsonify({"error": "CSV 文件为空"}), 400

    required = {"微信名称", "姓名", "打卡次数", "评价"}
    missing = required - set(rows[0].keys())
    if missing:
        return jsonify({"error": f"CSV 缺少必要列：{missing}"}), 400

    crew = []
    for i, row in enumerate(rows, 2):
        try:
            checkins = int(row["打卡次数"])
        except ValueError:
            return jsonify({"error": f"第 {i} 行「打卡次数」不是整数"}), 400
        crew.append({
            "wechat_name": row["微信名称"].strip(),
            "name":        row["姓名"].strip(),
            "checkins":    checkins,
            "comment":     row["评价"].strip(),
            "message":     row.get("message", "").strip(),
            "skip":        False,
        })

    # 保存文件到本地供 crew_sender.py 使用
    save_path = Path(__file__).parent / f.filename
    save_path.write_text(content, encoding="utf-8")

    return jsonify({
        "filename": f.filename,
        "filepath": str(save_path),
        "crew": crew,
    })


@app.route("/api/generate", methods=["POST"])
def generate_one():
    data = request.get_json()
    try:
        msg = _call_ai(data["name"], int(data["checkins"]), data["comment"])
        return jsonify({"message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-all")
def generate_all():
    raw = request.args.get("crew", "[]")
    crew = json.loads(raw)

    def stream():
        total = len(crew)
        for i, row in enumerate(crew):
            if row.get("skip"):
                continue
            try:
                msg = _call_ai(row["name"], int(row["checkins"]), row["comment"])
            except Exception as e:
                msg = f"[生成失败: {e}]"
            payload = json.dumps(
                {"index": i, "total": total, "name": row["name"], "message": msg},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
        yield "data: DONE\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@app.route("/api/save-csv", methods=["POST"])
def save_csv_api():
    data = request.get_json()
    filepath = data.get("filepath")
    crew = data.get("crew", [])

    if not filepath:
        return jsonify({"error": "未提供 filepath"}), 400

    fieldnames = ["微信名称", "姓名", "打卡次数", "评价", "message"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in crew:
        writer.writerow({
            "微信名称": row.get("wechat_name", ""),
            "姓名":    row.get("name", ""),
            "打卡次数": row.get("checkins", 0),
            "评价":    row.get("comment", ""),
            "message": row.get("message", ""),
        })

    Path(filepath).write_text(buf.getvalue(), encoding="utf-8")
    return jsonify({"saved": len(crew)})


@app.route("/api/execute")
def execute():
    global _send_process
    filepath = request.args.get("filepath", "crew_today.csv")
    mode     = request.args.get("mode", "normal")
    skip_raw = request.args.get("skip", "")

    cmd = [
        sys.executable, "crew_sender.py", filepath,
        "--no-confirm", "--json-progress",
    ]
    if mode == "safe":
        cmd.append("--safe")
    elif mode == "dry-run":
        cmd.append("--dry-run")
    if skip_raw:
        cmd += ["--skip", skip_raw]

    def stream():
        global _send_process
        _send_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=Path(__file__).parent,
        )
        for line in _send_process.stdout:
            line = line.strip()
            if line:
                yield f"data: {line}\n\n"
        _send_process.wait()
        _send_process = None
        yield "data: STREAM_END\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@app.route("/api/stop", methods=["POST"])
def stop_execution():
    global _send_process
    if _send_process and _send_process.poll() is None:
        _send_process.terminate()
        _send_process = None
        return jsonify({"stopped": True})
    return jsonify({"stopped": False})


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5001))
    if os.environ.get("FLASK_PORT") is None:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
