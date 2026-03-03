import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash, g
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cram_school_secret_key_2024")

DATABASE = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "cram_school.db"))

INTERVIEW_TYPES = ["入塾面談", "定期面談", "進路面談"]
GRADES = ["小1", "小2", "小3", "小4", "小5", "小6",
          "中1", "中2", "中3",
          "高1", "高2", "高3", "既卒"]
LEVELS = ["基礎", "標準", "応用", "発展"]
SUBJECTS = ["国語", "数学", "英語", "理科", "社会", "その他"]


# ─── DB接続 ───────────────────────────────────────────────────────
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                grade TEXT,
                school TEXT,
                level TEXT,
                parent_name TEXT,
                parent_phone TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                interview_type TEXT NOT NULL,
                interview_date TEXT NOT NULL,
                interviewer TEXT,
                study_status TEXT,
                issues TEXT,
                next_goals TEXT,
                parent_contact TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
        """)
        db.commit()


# ─── ダッシュボード ────────────────────────────────────────────────
@app.route("/")
def index():
    db = get_db()
    recent_interviews = db.execute("""
        SELECT i.*, s.name as student_name, s.grade
        FROM interviews i
        JOIN students s ON i.student_id = s.id
        ORDER BY i.interview_date DESC
        LIMIT 10
    """).fetchall()

    counts = {}
    for t in INTERVIEW_TYPES:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM interviews WHERE interview_type = ?", (t,)
        ).fetchone()
        counts[t] = row["cnt"]

    student_count = db.execute("SELECT COUNT(*) as cnt FROM students").fetchone()["cnt"]

    return render_template("index.html",
                           recent_interviews=recent_interviews,
                           counts=counts,
                           student_count=student_count,
                           interview_types=INTERVIEW_TYPES)


# ─── 生徒管理 ─────────────────────────────────────────────────────
@app.route("/students")
def students():
    db = get_db()
    q = request.args.get("q", "")
    if q:
        rows = db.execute(
            "SELECT * FROM students WHERE name LIKE ? OR school LIKE ? ORDER BY name",
            (f"%{q}%", f"%{q}%")
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM students ORDER BY name").fetchall()
    return render_template("students.html", students=rows, q=q)


@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("生徒氏名は必須です", "error")
            return redirect(url_for("add_student"))
        db = get_db()
        db.execute("""
            INSERT INTO students (name, grade, school, level, parent_name, parent_phone, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            request.form.get("grade", ""),
            request.form.get("school", ""),
            request.form.get("level", ""),
            request.form.get("parent_name", ""),
            request.form.get("parent_phone", ""),
            request.form.get("notes", ""),
        ))
        db.commit()
        flash(f"生徒「{name}」を登録しました", "success")
        return redirect(url_for("students"))
    return render_template("student_form.html", student=None, grades=GRADES, levels=LEVELS)


@app.route("/students/<int:student_id>")
def student_detail(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        flash("生徒が見つかりません", "error")
        return redirect(url_for("students"))
    interviews = db.execute(
        "SELECT * FROM interviews WHERE student_id = ? ORDER BY interview_date DESC",
        (student_id,)
    ).fetchall()
    return render_template("student_detail.html", student=student, interviews=interviews)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        flash("生徒が見つかりません", "error")
        return redirect(url_for("students"))
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("生徒氏名は必須です", "error")
            return redirect(url_for("edit_student", student_id=student_id))
        db.execute("""
            UPDATE students SET name=?, grade=?, school=?, level=?,
            parent_name=?, parent_phone=?, notes=?
            WHERE id=?
        """, (
            name,
            request.form.get("grade", ""),
            request.form.get("school", ""),
            request.form.get("level", ""),
            request.form.get("parent_name", ""),
            request.form.get("parent_phone", ""),
            request.form.get("notes", ""),
            student_id,
        ))
        db.commit()
        flash(f"生徒情報を更新しました", "success")
        return redirect(url_for("student_detail", student_id=student_id))
    return render_template("student_form.html", student=student, grades=GRADES, levels=LEVELS)


# ─── 面談記録 ─────────────────────────────────────────────────────
@app.route("/students/<int:student_id>/interview/new", methods=["GET", "POST"])
def new_interview(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        flash("生徒が見つかりません", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        interview_type = request.form["interview_type"]
        interview_date = request.form["interview_date"]
        if not interview_date:
            flash("面談日は必須です", "error")
            return redirect(url_for("new_interview", student_id=student_id))

        study_status = request.form.get("study_status", "")
        issues = request.form.get("issues", "")
        next_goals = request.form.get("next_goals", "")

        # 保護者連絡文の自動生成
        parent_contact = _generate_parent_contact(
            student["name"], interview_type, interview_date,
            study_status, issues, next_goals
        )

        db.execute("""
            INSERT INTO interviews
            (student_id, interview_type, interview_date, interviewer,
             study_status, issues, next_goals, parent_contact)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            interview_type,
            interview_date,
            request.form.get("interviewer", ""),
            study_status,
            issues,
            next_goals,
            parent_contact,
        ))
        db.commit()
        flash("面談記録を保存しました", "success")
        return redirect(url_for("student_detail", student_id=student_id))

    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("interview_form.html",
                           student=student,
                           interview=None,
                           interview_types=INTERVIEW_TYPES,
                           today=today)


@app.route("/interviews/<int:interview_id>")
def interview_detail(interview_id):
    db = get_db()
    interview = db.execute("""
        SELECT i.*, s.name as student_name, s.grade, s.school,
               s.parent_name, s.level
        FROM interviews i
        JOIN students s ON i.student_id = s.id
        WHERE i.id = ?
    """, (interview_id,)).fetchone()
    if not interview:
        flash("面談記録が見つかりません", "error")
        return redirect(url_for("index"))
    return render_template("interview_detail.html", interview=interview)


@app.route("/interviews/<int:interview_id>/edit", methods=["GET", "POST"])
def edit_interview(interview_id):
    db = get_db()
    interview = db.execute("""
        SELECT i.*, s.name as student_name
        FROM interviews i JOIN students s ON i.student_id = s.id
        WHERE i.id = ?
    """, (interview_id,)).fetchone()
    if not interview:
        flash("面談記録が見つかりません", "error")
        return redirect(url_for("index"))

    student = db.execute("SELECT * FROM students WHERE id = ?", (interview["student_id"],)).fetchone()

    if request.method == "POST":
        study_status = request.form.get("study_status", "")
        issues = request.form.get("issues", "")
        next_goals = request.form.get("next_goals", "")
        parent_contact = _generate_parent_contact(
            interview["student_name"], interview["interview_type"],
            request.form["interview_date"],
            study_status, issues, next_goals
        )
        db.execute("""
            UPDATE interviews SET interview_date=?, interviewer=?,
            study_status=?, issues=?, next_goals=?, parent_contact=?
            WHERE id=?
        """, (
            request.form["interview_date"],
            request.form.get("interviewer", ""),
            study_status, issues, next_goals, parent_contact,
            interview_id,
        ))
        db.commit()
        flash("面談記録を更新しました", "success")
        return redirect(url_for("interview_detail", interview_id=interview_id))

    return render_template("interview_form.html",
                           student=student,
                           interview=interview,
                           interview_types=INTERVIEW_TYPES,
                           today=interview["interview_date"])


# ─── レポート ─────────────────────────────────────────────────────
@app.route("/reports")
def reports():
    db = get_db()
    data = {}
    for t in INTERVIEW_TYPES:
        rows = db.execute("""
            SELECT i.*, s.name as student_name, s.grade
            FROM interviews i JOIN students s ON i.student_id = s.id
            WHERE i.interview_type = ?
            ORDER BY i.interview_date DESC
        """, (t,)).fetchall()
        data[t] = rows
    return render_template("reports.html", data=data, interview_types=INTERVIEW_TYPES)


# ─── 保護者連絡文の自動生成 ──────────────────────────────────────────
def _generate_parent_contact(student_name, interview_type, interview_date,
                              study_status, issues, next_goals):
    date_str = ""
    try:
        d = datetime.strptime(interview_date, "%Y-%m-%d")
        date_str = d.strftime("%-m月%-d日")
    except Exception:
        date_str = interview_date

    lines = [f"保護者様"]
    lines.append("")
    lines.append(f"いつもお世話になっております。")
    lines.append(f"{date_str}に{interview_type}を実施しましたのでご報告いたします。")
    lines.append("")

    if study_status:
        lines.append("【学習状況・成績】")
        lines.append(study_status)
        lines.append("")

    if issues:
        lines.append("【課題・改善点】")
        lines.append(issues)
        lines.append("")

    if next_goals:
        lines.append("【次回までの目標・取り組み】")
        lines.append(next_goals)
        lines.append("")

    lines.append("ご不明な点がございましたら、お気軽にお問い合わせください。")
    lines.append("引き続きよろしくお願いいたします。")

    return "\n".join(lines)


# ─── 起動 ─────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
