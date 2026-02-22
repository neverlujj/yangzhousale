import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# 初始化数据库
def init_db():
    conn = sqlite3.connect('sales.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER, date TEXT, product TEXT, amount REAL, create_time TEXT)''')
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect('sales.db')

# 登录注册
def login(username, password):
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user[2], password):
        return user[0]
    return None

def register(username, password):
    try:
        conn = get_conn()
        pwd = generate_password_hash(password)
        conn.execute("INSERT INTO users (username,password) VALUES (?,?)", (username,pwd))
        conn.commit()
        conn.close()
        return True
    except:
        return False

# 数据操作
def add_sale(user_id, date, product, amount):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_conn()
    conn.execute("INSERT INTO sales (user_id,date,product,amount,create_time) VALUES (?,?,?,?,?)",
                 (user_id, date, product, amount, now))
    conn.commit()
    conn.close()

def get_user_sales(user_id):
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM sales WHERE user_id=?", conn, params=(user_id,))
    conn.close()
    return df

# 页面开始
st.set_page_config(page_title="销售看板", layout="wide")
init_db()

# 登录状态
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# 登录注册
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["登录", "注册"])
    with tab1:
        username = st.text_input("账号")
        password = st.text_input("密码", type="password")
        if st.button("登录"):
            uid = login(username, password)
            if uid:
                st.session_state.user_id = uid
                st.success("登录成功")
                st.rerun()
            else:
                st.error("账号或密码错误")
    with tab2:
        username2 = st.text_input("注册账号")
        password2 = st.text_input("注册密码", type="password")
        if st.button("注册"):
            if register(username2, password2):
                st.success("注册成功，请登录")
            else:
                st.error("账号已存在")
    st.stop()

# 已登录 → 看板
st.title("📊 个人销售看板")

df = get_user_sales(st.session_state.user_id)

# 统计
total = df["amount"].sum() if not df.empty else 0
today = datetime.now().strftime("%Y-%m-%d")
df_today = df[df["date"].str.startswith(today)] if not df.empty else pd.DataFrame()
amt_today = df_today["amount"].sum() if not df_today.empty else 0

month = today[:7]
df_month = df[df["date"].str.startswith(month)] if not df.empty else pd.DataFrame()
amt_month = df_month["amount"].sum() if not df_month.empty else 0

# 展示看板
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("今日销售额", f"{amt_today:.2f}")
with col2:
    st.metric("本月销售额", f"{amt_month:.2f}")
with col3:
    st.metric("累计销售额", f"{total:.2f}")

# 录入
st.subheader("➕ 录入销售数据")
d = st.date_input("日期")
p = st.text_input("产品")
a = st.number_input("金额", min_value=0.0)
if st.button("提交"):
    add_sale(st.session_state.user_id, str(d), p, a)
    st.success("上传成功")
    st.rerun()

# 排行
st.subheader("🏆 产品销售排行")
if not df.empty:
    top = df.groupby("product")["amount"].sum().sort_values(ascending=False).head(5)
    st.dataframe(top, use_container_width=True)

# 记录
st.subheader("📋 最近记录")
if not df.empty:
    st.dataframe(df.sort_values("id", ascending=False), use_container_width=True)
else:
    st.info("暂无数据")

if st.button("退出登录"):
    st.session_state.user_id = None
    st.rerun()
