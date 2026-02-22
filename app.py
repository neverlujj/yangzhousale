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

# ======================== 全局配置 ========================
st.set_page_config(
    page_title="航班销售管理系统",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 解决中文乱码
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

# 预置管理员账号
ADMIN_USER = "admin"
ADMIN_PWD = "Admin123@"

# ======================== 数据库管理 ========================
class DBManager:
    _conn = None
    
    @classmethod
    def get_conn(cls):
        if cls._conn is None or cls._conn.close:
            cls._conn = sqlite3.connect(
                'flight_sales.db',
                check_same_thread=False
            )
            cls._conn.execute("PRAGMA foreign_keys = ON")
        return cls._conn

def init_db():
    conn = DBManager.get_conn()
    c = conn.cursor()
    
    # 1. 用户表（销售人员）
    c.execute('''CREATE TABLE IF NOT EXISTS sales_staff
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password_hash TEXT NOT NULL,
                 real_name TEXT NOT NULL,  # 销售人员真实姓名
                 is_admin INTEGER DEFAULT 0,
                 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 2. 航班销售数据表
    c.execute('''CREATE TABLE IF NOT EXISTS flight_sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 staff_id INTEGER NOT NULL,  # 关联销售人员ID
                 staff_name TEXT NOT NULL,  # 销售人员姓名（冗余，方便查询）
                 flight_no TEXT NOT NULL,   # 航班号
                 sale_date TEXT NOT NULL,   # 销售日期
                 sale_amount REAL NOT NULL CHECK(sale_amount >= 0),  # 航班销售额
                 sale_target REAL NOT NULL CHECK(sale_target >= 0),  # 销售指标
                 completion_rate REAL DEFAULT 0,  # 完成率（自动计算）
                 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY (staff_id) REFERENCES sales_staff(id))''')
    
    # 创建索引优化查询
    c.execute('CREATE INDEX IF NOT EXISTS idx_flight_staff ON flight_sales(staff_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_flight_no ON flight_sales(flight_no)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_flight_date ON flight_sales(sale_date)')
    
    # 初始化管理员账号
    c.execute("SELECT id FROM sales_staff WHERE username = ?", (ADMIN_USER,))
    if not c.fetchone():
        admin_pwd_hash = generate_password_hash(ADMIN_PWD, method='pbkdf2:sha256')
        c.execute(
            "INSERT INTO sales_staff (username, password_hash, real_name, is_admin) VALUES (?, ?, ?, 1)",
            (ADMIN_USER, admin_pwd_hash, "系统管理员")
        )
        st.success(f"✅ 管理员账号已创建：{ADMIN_USER} / {ADMIN_PWD}")
    
    conn.commit()

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

# ======================== 业务逻辑 ========================
# 登录
def login(username, password):
    if "login_attempts" not in st.session_state:
        st.session_state.login_attempts = 0
    if st.session_state.login_attempts >= 5:
        return None, "登录失败次数过多，请1分钟后再试"
    
    conn = DBManager.get_conn()
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

# 注册（销售人员）
def register(username, password, real_name):
    if not username or not real_name:
        return False, "用户名和真实姓名不能为空"
    is_strong, msg = is_strong_password(password)
    if not is_strong:
        return False, msg
    
    try:
        conn = DBManager.get_conn()
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
        return False, f"注册失败：{str(e)}"

# 新增航班销售数据
def add_flight_sale(staff_id, staff_name, flight_no, sale_date, sale_amount, sale_target):
    try:
        completion_rate = sale_amount / sale_target if sale_target > 0 else 0
        conn = DBManager.get_conn()
        conn.execute(
            "INSERT INTO flight_sales (staff_id, staff_name, flight_no, sale_date, sale_amount, sale_target, completion_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (staff_id, staff_name, flight_no, str(sale_date), sale_amount, sale_target, completion_rate)
        )
        conn.commit()
        return True, "航班销售数据提交成功"
    except Exception as e:
        return False, f"提交失败：{str(e)}"

# 删除销售数据
def delete_flight_sale(sale_id, staff_id):
    try:
        conn = DBManager.get_conn()
        conn.execute("DELETE FROM flight_sales WHERE id = ? AND staff_id = ?", (sale_id, staff_id))
        conn.commit()
        return True, "删除成功"
    except Exception as e:
        return False, f"删除失败：{str(e)}"

# 获取单个销售人员数据
def get_staff_sales(staff_id, start_date=None, end_date=None):
    conn = DBManager.get_conn()
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

# 获取所有销售人员数据（管理员）
def get_all_staff_sales(start_date=None, end_date=None):
    conn = DBManager.get_conn()
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

# ======================== 可视化函数 ========================
# 个人销售完成率趋势
def plot_staff_completion_trend(df):
    if df.empty:
        return None
    
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

# 销售人员排名柱状图
def plot_staff_ranking(ranking_df):
    if ranking_df.empty:
        return None
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(ranking_df["staff_name"], ranking_df["completion_rate"], color='#2c8ef7')
    
    ax.set_title("销售人员完成率排名", fontsize=14, pad=20)
    ax.set_ylabel("完成率", fontsize=12)
    ax.set_ylim(0, max(ranking_df["completion_rate"].max() * 1.2, 1.2))
    ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.7, label='100%完成线')
    
    # 显示排名和数值
    for i, (bar, rank, rate) in enumerate(zip(bars, ranking_df["rank"], ranking_df["completion_rate"])):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                f'第{rank}名\n{rate:.1%}', ha='center', va='bottom', fontsize=10)
    
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# 总完成率仪表盘
def plot_total_completion_gauge(total_rate):
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # 绘制仪表盘
    theta = np.linspace(0, np.pi, 100)
    r = np.ones_like(theta)
    
    # 背景圆弧
    ax.plot(theta, r, color='#e0e0e0', linewidth=20)
    
    # 完成率圆弧
    end_theta = np.pi * min(total_rate, 1.0)
    theta_rate = np.linspace(0, end_theta, 100)
    r_rate = np.ones_like(theta_rate)
    color = '#2c8ef7' if total_rate >= 1.0 else '#ff7f0e'
    ax.plot(theta_rate, r_rate, color=color, linewidth=20)
    
    # 中心文字
    ax.text(np.pi/2, 0, f'{total_rate:.1%}', ha='center', va='center', fontsize=30, fontweight='bold')
    ax.text(np.pi/2, -0.2, "整体完成率", ha='center', va='center', fontsize=16)
    
    ax.set_xlim(0, np.pi)
    ax.set_ylim(0, 1.2)
    ax.axis('off')
    plt.tight_layout()
    return fig

# ======================== 页面逻辑 ========================
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
        
        # 今日数据
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
            if not flight_no:
                st.error("航班号不能为空")
            elif sale_amount <= 0 or sale_target <= 0:
                st.error("销售额和销售指标必须大于0")
            else:
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
    st.subheader("📈 个人销售趋势")
    if not df_staff.empty:
        fig_trend = plot_staff_completion_trend(df_staff)
        st.pyplot(fig_trend)
    else:
        st.info("暂无销售数据，录入后即可查看趋势图")
    
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
        st.pyplot(fig_gauge)
        
        # 5. 销售人员排名
        st.subheader("🏆 销售人员完成率排名")
        fig_ranking = plot_staff_ranking(ranking_df)
        st.pyplot(fig_ranking)
        
        # 排名表格
        display_ranking = ranking_df[["rank", "staff_name", "sale_amount_formatted", "sale_target_formatted", "completion_rate_formatted"]]
        display_ranking.columns = ["排名", "销售人员", "总销售额", "总指标", "完成率"]
        st.dataframe(display_ranking, use_container_width=True)
        
        # 6. 数据导出
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
        
        # 7. 全平台详细数据
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
