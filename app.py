import csv
from io import StringIO
from flask import make_response, jsonify
from flask import Flask, render_template, request, session, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
import os
from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

app = Flask(__name__)
app.secret_key = "hejun_attendance_system_secret_key"

# ==================== 班次开始时间配置 ====================
SHIFT_START_TIMES = {
    "一到二节课": "08:00",
    "三到四节课": "10:00",
    "五到六节课": "14:30",
    "七到八节课": "16:30",
}
LATE_THRESHOLD_MINUTES = 5


def determine_status(shift, check_time_str):
    """根据班次和打卡时间判定迟到状态"""
    start_time_str = SHIFT_START_TIMES.get(shift)
    if not start_time_str:
        return "未迟到"
    start_h, start_m = map(int, start_time_str.split(":"))
    shift_start = datetime.now().replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    late_threshold = shift_start + timedelta(minutes=LATE_THRESHOLD_MINUTES)
    check_h, check_m, check_s = map(int, check_time_str.split(":"))
    check_dt = datetime.now().replace(hour=check_h, minute=check_m, second=check_s, microsecond=0)
    return "迟到" if check_dt > late_threshold else "未迟到"


# ==================== IP 白名单配置 ====================
ALLOWED_IPS = ["10.151.89.34"]


def is_ip_allowed(ip):
    """检查 IP 是否在白名单中"""
    return ip in ALLOWED_IPS


def get_client_ip():
    """获取客户端真实 IP（支持 Nginx 反向代理）"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For 格式: client_ip, proxy1, proxy2, ...
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or "未知"


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        member_id = request.form["member_id"]
        shift = request.form["shift"]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. 验证学号是否存在
        cursor.execute("SELECT name FROM members WHERE member_id=?", (member_id,))
        result = cursor.fetchone()
        if result is None:
            conn.close()
            return """<h2>错误的学号，或者为非部门人员！</h2><a href="/">返回</a>"""
        name = result[0]

        # 2. IP 验证
        client_ip = get_client_ip()
        if not is_ip_allowed(client_ip):
            conn.close()
            return f"""<h2>当前设备不允许打卡！</h2><p>您的IP地址：{client_ip}</p><p>请使用专用设备进行打卡。</p><br><a href="/">返回</a>"""

        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        # 3. 防重复打卡
        cursor.execute("SELECT 1 FROM attendance WHERE member_id = ? AND date = ? AND shift = ?", (member_id, date, shift))
        if cursor.fetchone():
            conn.close()
            return f"""<h2>您今天在 【{shift}】 已经打过卡了，请勿重复打卡！</h2><p>姓名：{name}</p><p>日期：{date}</p><br><a href="/">返回</a>"""

        # 4. 判定迟到状态
        status = determine_status(shift, time)

        # 5. 写入打卡记录
        cursor.execute("INSERT INTO attendance(member_id, name, shift, date, time, status) VALUES (?, ?, ?, ?, ?, ?)", (member_id, name, shift, date, time, status))
        conn.commit()
        conn.close()

        return f"""<h2>打卡成功！</h2>编号：{member_id}<br>姓名：{name}<br>班次：{shift}<br>日期：{date}<br>时间：{time}<br>状态：{status}<br><br><a href="/">返回</a>"""

    return render_template("index.html")


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if "user" in session:
        return redirect(url_for("query"))
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
        user_record = cursor.fetchone()
        conn.close()
        if user_record:
            password_hash, role = user_record
            if check_password_hash(password_hash, password):
                session["user"] = username
                session["role"] = role
                return redirect(url_for("query"))
        flash("账号或密码错误，请重新输入！")
        return redirect(url_for("admin_login"))
    return render_template("admin.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/query")
def query():
    if "user" in session:
        search_date = request.args.get("date", "")
        search_shift = request.args.get("shift", "")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        sql = "SELECT id, member_id, name, shift, date, time, status FROM attendance"
        conditions = []
        params = []
        if search_date:
            conditions.append("date = ?")
            params.append(search_date)
        if search_shift:
            conditions.append("shift = ?")
            params.append(search_shift)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY date DESC, time DESC"
        cursor.execute(sql, params)
        records = cursor.fetchall()
        conn.close()
        return render_template("query.html", records=records, current_user=session["user"], selected_date=search_date, selected_shift=search_shift)
    return """<h2>抱歉，您无权访问该页面，请先进行管理员登录！</h2><a href="/admin">前往管理员登录页</a>"""


@app.route("/update_status", methods=["POST"])
def update_status():
    if "user" not in session:
        return jsonify({"success": False, "message": "未登录"}), 403
    record_id = request.form.get("id", "")
    new_status = request.form.get("status", "")
    valid_statuses = ["未迟到", "迟到", "迟到（已提前报备）"]
    if new_status not in valid_statuses:
        return jsonify({"success": False, "message": "无效的状态值"}), 400
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE attendance SET status = ? WHERE id = ?", (new_status, record_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "状态已更新"})


@app.route("/export_csv", methods=["GET"])
def export_csv():
    if "user" not in session:
        return redirect(url_for("admin_login"))
    search_date = request.args.get("date", "")
    search_shift = request.args.get("shift", "")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = "SELECT member_id, name, shift, date, time, status FROM attendance"
    conditions = []
    params = []
    if search_date:
        conditions.append("date = ?")
        params.append(search_date)
    if search_shift:
        conditions.append("shift = ?")
        params.append(search_shift)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id DESC"
    cursor.execute(sql, tuple(params))
    records = cursor.fetchall()
    conn.close()
    si = StringIO()
    si.write('\ufeff')
    cw = csv.writer(si)
    cw.writerow(['学号/编号', '姓名', '班次', '打卡日期', '打卡具体时间', '状态'])
    cw.writerows(records)
    output = make_response(si.getvalue())
    filename = f"attendance_{search_date if search_date else 'all'}.csv"
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=True)
