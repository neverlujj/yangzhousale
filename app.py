import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import re
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import numpy as np
import os

# ======================== 全局配置 ========================
st.set_page_config(
    page_title="航班销售管理系统",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 解决中文乱码
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 预置管理员账号
ADMIN_USER = "admin"
ADMIN_PWD = "Admin123@"

# ======================== 数据库管理（修复Streamlit Cloud兼容问题） ========================
# 确保数据库文件路径可写
DB_PATH = os.path.join(os.getcwd(), 'flight_sales.db')

class DBManager:
    _conn = None
    
    @classmethod
    def get_conn(cls):
        try:
            if cls._conn is None or cls._conn.closed:
                # 修复连接参数，适配云环境
                cls._conn = sqlite3.connect(
                    DB_PATH,
                    check_same_thread=False,
                    timeout=10
                )
                cls._conn.execute("PRAGMA foreign_keys = ON")
            return cls._conn
        except Exception as e:
            st.error(f"数据库连接失败：{str(e)}")
            return None

def init_db():
    conn = DBManager.get_conn()
    if conn is None:
        st.error("无法初始化数据库，请检查连接配置")
        return
    
    c = conn.cursor()
    
    try:
        # 修复建表语句：使用单行字符串，适配云环境语法
        # 1. 销售人员表（简化语法，避免多行字符串问题）
        c.execute('''CREATE TABLE IF NOT EXISTS sales_staff (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT UNIQUE NOT NULL,
                     password_hash TEXT NOT NULL,
                     real_name TEXT NOT NULL,
                     is_admin INTEGER DEFAULT 0,
                     create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # 2. 航班销售数据表（简化语法）
        c.execute('''CREATE TABLE IF NOT EXISTS flight_sales (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     staff_id INTEGER NOT NULL,
                     staff_name TEXT NOT NULL,
                     flight_no TEXT NOT NULL,
                     sale_date TEXT NOT NULL,
                     sale_amount REAL NOT NULL CHECK(sale_amount >= 0),
                     sale_target REAL NOT NULL CHECK(sale_target >= 0),
                     completion_rate REAL DEFAULT 0,
                     create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (staff_id) REFERENCES sales_staff(id))''')
        
        # 创建索引（简化写法）
        c.execute('CREATE INDEX IF NOT EXISTS idx_flight_staff ON flight_sales(staff_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_flight_no ON flight_sales(flight_no)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_flight_date ON flight_sales(sale_date)')
        
        # 初始化管理员账号（增加异常处理）
        c.execute("SELECT id FROM sales_staff WHERE username = ?", (ADMIN_USER,))
        if not c.fetchone():
            admin_pwd_hash = generate_password_hash(ADMIN_PWD, method='pbkdf2:sha256')
            c.execute(
                "INSERT INTO sales_staff (username, password_hash, real_name, is_admin) VALUES (?, ?, ?, 1)",
                (ADMIN_USER, admin_pwd_hash, "系统管理员")
            )
            st.success(f"✅ 管理员账号已创建：{ADMIN_USER} / {ADMIN_PWD}")
        
        conn.commit()
        st.success("✅ 数据库初始化成功")
    except Exception as e:
        st.error(f"数据库初始化失败：{str(e)}")
        conn.rollback()
    finally:
        if conn:
            conn.close()
            DBManager._conn = None  # 重置连接

# ======================== 工具函数 ========================
def is_strong_password(password):
    if len(password) < 6:
        return False, "密码长度不能少于6位"
    if not re.search(r'[A-Z]', password):
        return False, "密码需包含至少一个大写字母"
    if not re.search(r'[0-9]', password):
        return False, "密码需包含至少一个数字"
    return True, "密码强度符合要求"

def format_amount(amount):
    return f"¥{amount:.2f}" if amount else "¥0.00"

def format_rate(rate):
    return f"{rate:.1%}" if rate else "0.0%"

# ======================== 业务逻辑（增加异常处理） ========================
# 登录
def login(username, password):
    if "login_attempts" not in st.session_state:
        st.session_state.login_attempts = 0
    if st.session_state.login_attempts >= 5:
        return None, "登录失败次数过多，请1分钟后再试"
    
    conn = DBManager.get_conn()
    if conn is None:
        return None, "数据库连接失败，请稍后重试"
    
    try:
        user = conn.execute(
            "SELECT id, username, real_name, password_hash, is_admin FROM sales_staff WHERE username = ?",
            (username,)
        ).fetchone()
        
        if user and check_password_hash(user[3], password):
            st.session_state.login_attempts = 0
            return {
                "id": user[0],
                "username": user[1],
                "real_name": user[2],
                "is_admin": user[4]
            }, "登录成功"
        else:
            st.session_state.login_attempts += 1
            return None, f"账号或密码错误（剩余尝试次数：{5 - st.session_state.login_attempts}）"
    except Exception as e:
        st.error(f"登录查询失败：{str(e)}")
        return None, "系统异常，请稍后重试"
    finally:
        conn.close()
        DBManager._conn = None

# 注册（销售人员）
def register(username, password, real_name):
    if not username or not real_name:
        return False, "用户名和真实姓名不能为空"
    is_strong, msg = is_strong_password(password)
    if not is_strong:
        return False, msg
    
    conn = DBManager.get_conn()
    if conn is None:
        return False, "数据库连接失败，请稍后重试"
    
    try:
        pwd_hash = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute(
            "INSERT INTO sales_staff (username, password_hash, real_name) VALUES (?, ?, ?)",
            (username, pwd_hash, real_name)
        )
        conn.commit()
        return True, "注册成功，请登录"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"
    except Exception as e:
        st.error(f"注册失败：{str(e)}")
        conn.rollback()
        return False, "系统异常，请稍后重试"
    finally:
        conn.close()
        DBManager._conn = None

# 新增航班销售数据
def add_flight_sale(staff_id, staff_name, flight_no, sale_date, sale_amount, sale_target):
    if sale_amount <= 0 or sale_target <= 0:
        return False, "销售额和销售指标必须大于0"
    if not flight_no:
        return False, "航班号不能为空"
    
    completion_rate = sale_amount / sale_target if sale_target > 0 else 0
    conn = DBManager.get_conn()
    if conn is None:
        return False, "数据库连接失败，请稍后重试"
    
    try:
        conn.execute(
            "INSERT INTO flight_sales (staff_id, staff_name, flight_no, sale_date, sale_amount, sale_target, completion_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (staff_id, staff_name, flight_no, str(sale_date), sale_amount, sale_target, completion_rate)
        )
        conn.commit()
        return True, "航班销售数据提交成功"
    except Exception as e:
        st.error(f"提交数据失败：{str(e)}")
        conn.rollback()
        return False, "系统异常，请稍后重试"
    finally:
        conn.close()
        DBManager._conn = None

# 删除销售数据
def delete_flight_sale(sale_id, staff_id):
    conn = DBManager.get_conn()
    if conn is None:
        return False, "数据库连接失败，请稍后重试"
    
    try:
        conn.execute("DELETE FROM flight_sales WHERE id = ? AND staff_id = ?", (sale_id, staff_id))
        conn.commit()
        return True, "删除成功"
    except Exception as e:
        st.error(f"删除数据失败：{str(e)}")
        conn.rollback()
        return False, "系统异常，请稍后重试"
    finally:
        conn.close()
        DBManager._conn = None

# 获取单个销售人员数据
def get_staff_sales(staff_id, start_date=None, end_date=None):
    conn = DBManager.get_conn()
    if conn is None:
        return pd.DataFrame()
    
    try:
        query = "SELECT * FROM flight_sales WHERE staff_id = ?"
        params = [staff_id]
        if start_date:
            query += " AND sale_date >= ?"
            params.append(str(start_date))
        if end_date:
            query += " AND sale_date <= ?"
            params.append(str(end_date))
        query += " ORDER BY sale_date DESC, id DESC"
        
        df = pd.read_sql(query, conn, params=params)
        if not df.empty:
            df['sale_amount_formatted'] = df['sale_amount'].apply(format_amount)
            df['sale_target_formatted'] = df['sale_target'].apply(format_amount)
            df['completion_rate_formatted'] = df['completion_rate'].apply(format_rate)
        return df
    except Exception as e:
        st.error(f"查询个人数据失败：{str(e)}")
        return pd.DataFrame()
    finally:
        conn.close()
        DBManager._conn = None

# 获取所有销售人员数据（管理员）
def get_all_staff_sales(start_date=None, end_date=None):
    conn = DBManager.get_conn()
    if conn is None:
        return pd.DataFrame()
    
    try:
        query = "SELECT * FROM flight_sales"
        params = []
        if start_date:
            query += " WHERE sale_date >= ?"
            params.append(str(start_date))
        if end_date:
            query += " AND sale_date <= ?" if start_date else " WHERE sale_date <= ?"
            params.append(str(end_date))
        query += " ORDER BY sale_date DESC"
        
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"查询全平台数据失败：{str(e)}")
        return pd.DataFrame()
    finally:
        conn.close()
        DBManager._conn = None

# 计算销售人员排名
def get_staff_ranking(start_date=None, end_date=None):
    df = get_all_staff_sales(start_date, end_date)
    if df.empty:
        return pd.DataFrame()
    
    # 按销售人员汇总
    ranking_df = df.groupby("staff_name").agg({
        "sale_amount": "sum",
        "sale_target": "sum"
    }).reset_index()
    ranking_df["completion_rate"] = ranking_df["sale_amount"] / ranking_df["sale_target"]
    # 按完成率排名
    ranking_df["rank"] = ranking_df["completion_rate"].rank(ascending=False, method="min").astype(int)
    ranking_df = ranking_df.sort_values("rank")
    
    # 格式化
    ranking_df["sale_amount_formatted"] = ranking_df["sale_amount"].apply(format_amount)
    ranking_df["sale_target_formatted"] = ranking_df["sale_target"].apply(format_amount)
    ranking_df["completion_rate_formatted"] = ranking_df["completion_rate"].apply(format_rate)
    
    return ranking_df

# ======================== 可视化函数（适配云环境） ========================
# 个人销售完成率趋势
def plot_staff_completion_trend(df):
    if df.empty:
        return None
    
    try:
        df_plot = df.copy()
        df_plot["sale_date"] = pd.to_datetime(df_plot["sale_date"])
        df_plot = df_plot.sort_values("sale_date")
        
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(df_plot["sale_date"], df_plot["completion_rate"], marker='o', linewidth=2, color='#2c8ef7')
        ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.7, label='100%完成线')
        
        ax.set_title("每日销售完成率趋势", fontsize=14, pad=20)
        ax.set_ylabel("完成率", fontsize=12)
        ax.set_ylim(0, max(df_plot["completion_rate"].max() * 1.2, 1.2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        plt.xticks(rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成趋势图失败：{str(e)}")
        return None

# 个人航班销售额TOP10
def plot_staff_flight_top10(df):
    if df.empty:
        return None
    
    try:
        flight_sum = df.groupby("flight_no")["sale_amount"].sum().reset_index()
        flight_sum = flight_sum.sort_values("sale_amount", ascending=False).head(10)
        
        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(flight_sum["flight_no"], flight_sum["sale_amount"], color='#4CAF50')
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 50,
                    format_amount(height), ha='center', va='bottom', fontsize=9)
        
        ax.set_title("个人TOP10航班销售额", fontsize=14, pad=20)
        ax.set_ylabel("销售额（元）", fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成航班TOP10图失败：{str(e)}")
        return None

# 月度销售趋势
def plot_monthly_sales_trend(df, is_admin=False):
    if df.empty:
        return None
    
    try:
        df_plot = df.copy()
        df_plot["sale_date"] = pd.to_datetime(df_plot["sale_date"])
        df_plot["month"] = df_plot["sale_date"].dt.to_period("M")
        
        if is_admin:
            agg_df = df_plot.groupby(["month", "staff_name"])["sale_amount"].sum().reset_index()
            pivot_df = agg_df.pivot(index="month", columns="staff_name", values="sale_amount").fillna(0)
        else:
            agg_df = df_plot.groupby("month")["sale_amount"].sum().reset_index()
            pivot_df = agg_df.set_index("month")
        
        fig, ax = plt.subplots(figsize=(12, 5))
        pivot_df.plot(kind='line', marker='o', ax=ax, linewidth=2)
        
        ax.set_title("月度销售额趋势" + ("（全平台）" if is_admin else "（个人）"), fontsize=14, pad=20)
        ax.set_ylabel("销售额（元）", fontsize=12)
        ax.set_xlabel("月份", fontsize=12)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成月度趋势图失败：{str(e)}")
        return None

# 销售额vs指标对比
def plot_sales_vs_target(df):
    if df.empty:
        return None
    
    try:
        df_plot = df.copy()
        df_plot["sale_date"] = pd.to_datetime(df_plot["sale_date"])
        df_plot = df_plot.sort_values("sale_date")
        
        daily_df = df_plot.groupby("sale_date").agg({
            "sale_amount": "sum",
            "sale_target": "sum"
        }).reset_index()
        
        fig, ax = plt.subplots(figsize=(12, 5))
        x = np.arange(len(daily_df))
        width = 0.35
        
        ax.bar(x - width/2, daily_df["sale_amount"], width, label='实际销售额', color='#2196F3')
        ax.bar(x + width/2, daily_df["sale_target"], width, label='销售指标', color='#FF9800')
        
        ax.set_title("每日销售额 vs 销售指标", fontsize=14, pad=20)
        ax.set_ylabel("金额（元）", fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels([d.strftime('%m-%d') for d in daily_df["sale_date"]], rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成销售额对比图失败：{str(e)}")
        return None

# 航班销售占比（饼图）
def plot_flight_sales_pie(df):
    if df.empty:
        return None
    
    try:
        flight_sum = df.groupby("flight_no")["sale_amount"].sum().reset_index()
        flight_sum = flight_sum.sort_values("sale_amount", ascending=False)
        
        top8 = flight_sum.head(8)
        others = pd.DataFrame({
            "flight_no": ["其他"],
            "sale_amount": [flight_sum.tail(-8)["sale_amount"].sum()]
        })
        pie_data = pd.concat([top8, others])
        
        fig, ax = plt.subplots(figsize=(8, 8))
        wedges, texts, autotexts = ax.pie(
            pie_data["sale_amount"],
            labels=pie_data["flight_no"],
            autopct='%1.1f%%',
            startangle=90,
            colors=plt.cm.Set3(np.linspace(0, 1, len(pie_data)))
        )
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title("航班销售额占比", fontsize=14, pad=20)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成饼图失败：{str(e)}")
        return None

# 销售人员排名柱状图
def plot_staff_ranking(ranking_df):
    if ranking_df.empty:
        return None
    
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(ranking_df["staff_name"], ranking_df["completion_rate"], color='#2c8ef7')
        
        ax.set_title("销售人员完成率排名", fontsize=14, pad=20)
        ax.set_ylabel("完成率", fontsize=12)
        ax.set_ylim(0, max(ranking_df["completion_rate"].max() * 1.2, 1.2))
        ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.7, label='100%完成线')
        
        for i, (bar, rank, rate) in enumerate(zip(bars, ranking_df["rank"], ranking_df["completion_rate"])):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                    f'第{rank}名\n{rate:.1%}', ha='center', va='bottom', fontsize=10)
        
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成排名图失败：{str(e)}")
        return None

# 总完成率仪表盘
def plot_total_completion_gauge(total_rate):
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        
        theta = np.linspace(0, np.pi, 100)
        r = np.ones_like(theta)
        
        ax.plot(theta, r, color='#e0e0e0', linewidth=20)
        
        end_theta = np.pi * min(total_rate, 1.0)
        theta_rate = np.linspace(0, end_theta, 100)
        r_rate = np.ones_like(theta_rate)
        color = '#2c8ef7' if total_rate >= 1.0 else '#ff7f0e'
        ax.plot(theta_rate, r_rate, color=color, linewidth=20)
        
        ax.text(np.pi/2, 0, f'{total_rate:.1%}', ha='center', va='center', fontsize=30, fontweight='bold')
        ax.text(np.pi/2, -0.2, "整体完成率", ha='center', va='center', fontsize=16)
        
        ax.set_xlim(0, np.pi)
        ax.set_ylim(0, 1.2)
        ax.axis('off')
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"生成仪表盘失败：{str(e)}")
        return None

# ======================== 页面逻辑 ========================
# 初始化数据库（放在最前面）
init_db()

# 登录状态管理
if "user" not in st.session_state:
    st.session_state.user = None

# ======================== 登录/注册页面 ========================
if st.session_state.user is None:
    st.title("✈️ 航班销售管理系统")
    tab1, tab2 = st.tabs(["登录", "注册"])
    
    # 登录标签页
    with tab1:
        with st.form("login_form", clear_on_submit=True):
            st.subheader("用户登录")
            username = st.text_input("用户名", placeholder=f"管理员账号：{ADMIN_USER}")
            password = st.text_input("密码", type="password", placeholder=f"管理员密码：{ADMIN_PWD}")
            login_btn = st.form_submit_button("登录", type="primary")
            
            if login_btn:
                user, msg = login(username, password)
                if user:
                    st.session_state.user = user
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    # 注册标签页
    with tab2:
        with st.form("register_form", clear_on_submit=True):
            st.subheader("销售人员注册")
            new_username = st.text_input("登录账号")
            new_real_name = st.text_input("真实姓名（销售人员）")
            new_password = st.text_input("登录密码", type="password", placeholder="至少6位，含大写字母+数字")
            confirm_pwd = st.text_input("确认密码", type="password")
            register_btn = st.form_submit_button("注册")
            
            if register_btn:
                if new_password != confirm_pwd:
                    st.error("两次密码不一致")
                else:
                    success, msg = register(new_username, new_password, new_real_name)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    st.stop()

# ======================== 普通销售人员页面 ========================
if not st.session_state.user["is_admin"]:
    st.title(f"✈️ {st.session_state.user['real_name']} 的销售看板")
    
    # 退出按钮
    col_logout, _ = st.columns([1, 9])
    with col_logout:
        if st.button("🚪 退出登录"):
            st.session_state.clear()
            st.rerun()
    
    # 1. 数据筛选
    st.subheader("📅 数据筛选")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("结束日期", datetime.now())
    
    # 2. 获取个人销售数据
    df_staff = get_staff_sales(st.session_state.user["id"], start_date, end_date)
    
    # 3. 个人核心统计
    if not df_staff.empty:
        total_amount = df_staff["sale_amount"].sum()
        total_target = df_staff["sale_target"].sum()
        total_rate = total_amount / total_target if total_target > 0 else 0
        
        today = datetime.now().strftime("%Y-%m-%d")
        df_today = df_staff[df_staff["sale_date"] == today]
        today_amount = df_today["sale_amount"].sum()
        today_target = df_today["sale_target"].sum()
        today_rate = today_amount / today_target if today_target > 0 else 0
    else:
        total_amount = total_target = total_rate = today_amount = today_target = today_rate = 0
    
    # 4. 核心指标看板
    st.subheader("📊 核心销售指标")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("今日销售额", format_amount(today_amount))
    with col2:
        st.metric("今日完成率", format_rate(today_rate))
    with col3:
        st.metric("筛选期总销售额", format_amount(total_amount))
    with col4:
        st.metric("筛选期完成率", format_rate(total_rate))
    
    # 5. 录入航班销售数据
    st.subheader("➕ 录入航班销售数据")
    with st.form("add_sale_form", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            sale_date = st.date_input("销售日期", datetime.now())
        with col2:
            flight_no = st.text_input("航班号", placeholder="如：MU1234、CA5678")
        with col3:
            sale_amount = st.number_input("销售额（元）", min_value=0.0, step=0.01)
        with col4:
            sale_target = st.number_input("销售指标（元）", min_value=0.0, step=0.01)
        
        submit_btn = st.form_submit_button("提交数据", type="primary")
        if submit_btn:
            success, msg = add_flight_sale(
                st.session_state.user["id"],
                st.session_state.user["real_name"],
                flight_no,
                sale_date,
                sale_amount,
                sale_target
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    
    # 6. 个人可视化图表
    st.subheader("📈 个人销售数据可视化")
    if not df_staff.empty:
        tab1, tab2, tab3, tab4 = st.tabs(["完成率趋势", "航班TOP10", "月度趋势", "销售额vs指标"])
        
        with tab1:
            fig_trend = plot_staff_completion_trend(df_staff)
            if fig_trend:
                st.pyplot(fig_trend)
        
        with tab2:
            fig_flight_top10 = plot_staff_flight_top10(df_staff)
            if fig_flight_top10:
                st.pyplot(fig_flight_top10)
        
        with tab3:
            fig_monthly = plot_monthly_sales_trend(df_staff, is_admin=False)
            if fig_monthly:
                st.pyplot(fig_monthly)
        
        with tab4:
            fig_sales_vs_target = plot_sales_vs_target(df_staff)
            if fig_sales_vs_target:
                st.pyplot(fig_sales_vs_target)
        
        # 饼图
        st.subheader("🥧 个人航班销售占比")
        fig_pie = plot_flight_sales_pie(df_staff)
        if fig_pie:
            st.pyplot(fig_pie)
    else:
        st.info("暂无销售数据，录入后即可查看所有可视化图表")
    
    # 7. 个人销售记录
    st.subheader("📋 销售记录列表")
    if not df_staff.empty:
        display_df = df_staff[["id", "sale_date", "flight_no", "sale_amount_formatted", "sale_target_formatted", "completion_rate_formatted"]]
        display_df.columns = ["ID", "销售日期", "航班号", "销售额", "销售指标", "完成率"]
        st.dataframe(display_df, use_container_width=True)
        
        # 删除功能
        st.subheader("🗑️ 删除记录")
        selected_id = st.selectbox("选择要删除的记录ID", df_staff["id"].tolist())
        if st.button("删除选中记录"):
            success, msg = delete_flight_sale(selected_id, st.session_state.user["id"])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("暂无销售记录，请先录入数据")

# ======================== 管理员后台 ========================
else:
    st.title("🔧 航班销售管理后台")
    
    # 退出按钮
    col_logout, _ = st.columns([1, 9])
    with col_logout:
        if st.button("🚪 退出登录"):
            st.session_state.clear()
            st.rerun()
    
    # 1. 全平台数据筛选
    st.subheader("📅 全平台数据筛选")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("结束日期", datetime.now())
    
    # 2. 获取全平台数据
    df_all = get_all_staff_sales(start_date, end_date)
    ranking_df = get_staff_ranking(start_date, end_date)
    
    if not df_all.empty:
        # 3. 全平台核心统计
        total_amount = df_all["sale_amount"].sum()
        total_target = df_all["sale_target"].sum()
        total_rate = total_amount / total_target if total_target > 0 else 0
        staff_count = df_all["staff_name"].nunique()
        flight_count = df_all["flight_no"].nunique()
        
        st.subheader("📊 全平台核心指标")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("总销售额", format_amount(total_amount))
        with col2:
            st.metric("总销售指标", format_amount(total_target))
        with col3:
            st.metric("整体完成率", format_rate(total_rate))
        with col4:
            st.metric("销售人员数", staff_count)
        with col5:
            st.metric("涉及航班数", flight_count)
        
        # 4. 整体完成率仪表盘
        st.subheader("🎯 整体完成率")
        fig_gauge = plot_total_completion_gauge(total_rate)
        if fig_gauge:
            st.pyplot(fig_gauge)
        
        # 5. 全平台可视化图表
        st.subheader("📈 全平台数据可视化")
        tab1, tab2, tab3 = st.tabs(["月度销售趋势", "航班占比", "销售人员对比"])
        
        with tab1:
            fig_admin_monthly = plot_monthly_sales_trend(df_all, is_admin=True)
            if fig_admin_monthly:
                st.pyplot(fig_admin_monthly)
        
        with tab2:
            fig_admin_pie = plot_flight_sales_pie(df_all)
            if fig_admin_pie:
                st.pyplot(fig_admin_pie)
        
        with tab3:
            fig_ranking = plot_staff_ranking(ranking_df)
            if fig_ranking:
                st.pyplot(fig_ranking)
        
        # 6. 排名表格
        st.subheader("🏆 销售人员完成率排名")
        display_ranking = ranking_df[["rank", "staff_name", "sale_amount_formatted", "sale_target_formatted", "completion_rate_formatted"]]
        display_ranking.columns = ["排名", "销售人员", "总销售额", "总指标", "完成率"]
        st.dataframe(display_ranking, use_container_width=True)
        
        # 7. 数据导出
        st.subheader("📥 数据导出")
        export_df = df_all[["staff_name", "flight_no", "sale_date", "sale_amount", "sale_target", "completion_rate"]]
        export_df.columns = ["销售人员", "航班号", "销售日期", "销售额", "销售指标", "完成率"]
        export_df["销售额"] = export_df["销售额"].apply(format_amount)
        export_df["销售指标"] = export_df["销售指标"].apply(format_amount)
        export_df["完成率"] = export_df["完成率"].apply(format_rate)
        
        st.download_button(
            label="导出Excel格式（CSV）",
            data=export_df.to_csv(index=False, encoding='utf-8-sig'),
            file_name=f"航班销售数据_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # 8. 全平台详细数据
        st.subheader("📋 全平台销售记录")
        display_df = df_all[["staff_name", "flight_no", "sale_date", "sale_amount", "sale_target", "completion_rate"]]
        display_df.columns = ["销售人员", "航班号", "销售日期", "销售额", "销售指标", "完成率"]
        display_df["销售额"] = display_df["销售额"].apply(format_amount)
        display_df["销售指标"] = display_df["销售指标"].apply(format_amount)
        display_df["完成率"] = display_df["完成率"].apply(format_rate)
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.info("📭 全平台暂无销售数据，请先让销售人员录入数据")

# 底部信息
st.markdown("---")
st.markdown("<div style='text-align:center; color:#666;'>航班销售管理系统 | 外网可访问 | 销售人员独立统计</div>", unsafe_allow_html=True)
