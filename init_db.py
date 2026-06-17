import os
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.abspath("attendance.db")
print("数据库绝对路径:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    
     # 3. 创建管理员用户表（如果不存在）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)
    
     # 4. 检查是否已有管理员，若没有则自动添加一个初始管理员
    # 账号: admin  密码: 157671
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        default_password = "157671"
        # 使用 sha256 安全哈希加密密码
        hashed_password = generate_password_hash(default_password)
        cursor.execute("""
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
        """, ("admin", hashed_password, "admin1"))
        print("【提示】默认管理员账号创建成功！")
        print(">> 账号: admin")
        print(">> 密码: 157671")
        
    conn.commit()
    print("数据库结构初始化/更新成功！")
except Exception as e:
    print("数据库操作错误：", e)
finally:
    
     # 1. 创建部门成员表（如果不存在）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members(
         member_id TEXT PRIMARY KEY,
         name TEXT NOT NULL
     )
     """)
     
     # 2. 创建打卡记录表（如果不存在）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         member_id TEXT NOT NULL,
         name TEXT NOT NULL,
         shift TEXT NOT NULL,
         date TEXT NOT NULL,
         time TEXT NOT NULL,
         status TEXT DEFAULT '未迟到'
     )
     """)
conn.close()