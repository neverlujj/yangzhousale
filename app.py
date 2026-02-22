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
    page_title="销售数据管理系统",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 设置中文字体（解决图表中文乱码）
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

# ======================== 数据库配置 ========================
# 预置管理员账号（可自行修改）
ADMIN_USER = "admin"
ADMIN_PWD = "Admin123@"  # 符合密码强度要求

class DBManager:
    _conn = None
    
    @classmethod
    def get_conn(cls):
        if cls._conn is None or cls._conn.close:
            cls._conn = sqlite3.connect(
                'sales.db',
                check_same_thread=False
            )
            cls._conn.execute("PRAGMA foreign_keys = ON")
        return cls._conn

def init_db():
    conn = DBManager.get_conn()
    c = conn.cursor()
    
    # 创建用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password_hash TEXT NOT NULL,
                 is_admin INTEGER DEFAULT 0,
                 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 创建销售数据表
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 date TEXT NOT NULL,
                 flight_no TEXT NOT NULL,
                 amount REAL NOT NULL CHECK(amount >= 0),
                 target REAL NOT NULL CHECK(target >= 0),
                 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # 创建索引优化查询
    c.execute('CREATE INDEX IF NOT EXISTS idx_sales_user_date ON sales(user_id, date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sales_flight ON sales(flight_no)')
    
    # 预置管理员账号（不存在则创建）
    c.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USER,))
    if not c.fetchone():
        admin_pwd_hash = generate_password_hash(ADMIN_PWD, method='pbkdf2:sha256')
        c.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (ADMIN_USER, admin_pwd_hash)
        )
        st.success(f"✅ 管理员账号已创建：用户名={ADMIN_USER}，密码={ADMIN_PWD}")
    
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
def login(username, password):
    if "login_attempts" not in st.session_state:
        st.session_state.login_attempts = 0
    if st.session_state.login_attempts >= 5:
        return None, "登录失败次数过多，请1分钟后再试"
    
    conn = DBManager.get_conn()
    user = conn.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    
    if user and check_password_hash(user[2], password):
        st.session_state.login_attempts = 0
        return {"id": user[0], "username": user[1], "is_admin": user[3]}, "登录成功"
    else:
        st.session_state.login_attempts += 1
        return None, f"账号或密码错误（剩余尝试次数：{5 - st.session_state.login_attempts}）"

def register(username, password):
    if not username:
        return False, "用户名不能为空"
    is_strong, msg = is_strong_password(password)
    if not is_strong:
        return False, msg
    
    try:
        conn = DBManager.get_conn()
        pwd_hash = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, pwd_hash)
        )
        conn.commit()
        return True, "注册成功，请登录"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"
    except Exception as e:
        return False, f"注册失败：{str(e)}"

def add_sale(user_id, date, flight_no, amount, target):
    try:
        conn = DBManager.get_conn()
        conn.execute(
            "INSERT INTO sales (user_id, date, flight_no, amount, target) VALUES (?, ?, ?, ?, ?)",
            (user_id, str(date), flight_no, amount, target)
        )
        conn.commit()
        return True, "数据提交成功"
    except Exception as e:
        return False, f"提交失败：{str(e)}"

def delete_sale(sale_id, user_id):
    try:
        conn = DBManager.get_conn()
        conn.execute("DELETE FROM sales WHERE id = ? AND user_id = ?", (sale_id, user_id))
        conn.commit()
        return True, "删除成功"
    except Exception as e:
        return False, f"删除失败：{str(e)}"

def get_user_sales(user_id, start_date=None, end_date=None):
    conn = DBManager.get_conn()
    query = "SELECT * FROM sales WHERE user_id = ?"
    params = [user_id]
    if start_date:
        query += " AND date >= ?"
        params.append(str(start_date))
    if end_date:
        query += " AND date <= ?"
        params.append(str(end_date))
    query += " ORDER BY date DESC, id DESC"
    df = pd.read_sql(query, conn, params=params)
    if not df.empty:
        df['completion_rate'] = df['amount'] / df['target']
        df['amount_formatted'] = df['amount'].apply(format_amount)
        df['target_formatted'] = df['target'].apply(format_amount)
        df['completion_rate_formatted'] = df['completion_rate'].apply(format_rate)
    return df

def get_all_sales(start_date=None, end_date=None):
    conn = DBManager.get_conn()
    query = "SELECT s.*, u.username FROM sales s JOIN users u ON s.user_id = u.id"
    params = []
    if start_date:
        query += " AND s.date >= ?"
        params.append(str(start_date))
    if end_date:
        query += " AND s.date <= ?"
        params.append(str(end_date))
    query += " ORDER BY s.date DESC"
    df = pd.read_sql(query, conn, params=params)
    if not df.empty:
        df['completion_rate'] = df['amount'] / df['target']
    return df

# ======================== 可视化图表函数 ========================
# 1. 销售额vs指标趋势图（用户端）
def plot_sales_trend(df):
    df_plot = df.copy()
    df_plot["date"] = pd.to_datetime(df_plot["date"])
    df_plot = df_plot.sort_values("date")
    
    # 按日期聚合
    df_daily = df_plot.groupby("date").agg({
        "amount": "sum",
        "target": "sum"
    }).reset_index()
    
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df_daily["date"], df_daily["amount"], marker='o', linewidth=2, label='实际销售额', color='#2c8ef7')
    ax.plot(df_daily["date"], df_daily["target"], marker='s', linewidth=2, label='销售指标', color='#ff7f0e')
    
    ax.set_title("每日销售额 vs 销售指标趋势", fontsize=14, pad=20)
    ax.set_ylabel("金额（元）", fontsize=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.xticks(rotation=45)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig

# 2. 航班销售额统计（用户端）
def plot_flight_sales(df):
    if df.empty:
        return None
    
    # 按航班号聚合
    flight_stats = df.groupby("flight_no").agg({
        "amount": "sum",
        "target": "sum"
    }).reset_index()
    flight_stats = flight_stats.sort_values("amount", ascending=False).head(10)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(flight_stats["flight_no"]))
    width = 0.35
    
    ax.bar(x - width/2, flight_stats["amount"], width, label='实际销售额', color='#2c8ef7')
    ax.bar(x + width/2, flight_stats["target"], width, label='销售指标', color='#ff7f0e')
    
    ax.set_title("TOP10 航班销售额统计", fontsize=14, pad=20)
    ax.set_ylabel("金额（元）", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(flight_stats["flight_no"], rotation=45)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    return fig

# 3. 日期热力图（用户端）
def plot_date_heatmap(df):
    if df.empty:
        return None
    
    df_heat = df.copy()
    df_heat["date"] = pd.to_datetime(df_heat["date"])
    df_heat["weekday"] = df_heat["date"].dt.dayofweek  # 0=周一，6=周日
    df_heat["day"] = df_heat["date"].dt.day
    
    # 构建透视表
    heat_data = df_heat.pivot_table(
        index="weekday",
        columns="day",
        values="amount",
        aggfunc="sum",
        fill_value=0
    )
    
    # 映射星期几
    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    heat_data.index = heat_data.index.map(weekday_map)
    
    fig, ax = plt.subplots(figsize=(12, 4))
    sns.heatmap(heat_data, annot=True, fmt=".0f", cmap="YlGnBu", ax=ax, cbar_kws={'label': '销售额（元）'})
    ax.set_title("日期销售额热力图", fontsize=14, pad=20)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("星期", fontsize=12)
    plt.tight_layout()
    return fig

# 4. 管理员-用户完成率对比
def plot_admin_user_rate(df):
    user_stats = df.groupby("username").agg({
        "amount": "sum",
        "target": "sum"
    }).reset_index()
    user_stats["completion_rate"] = user_stats["amount"] / user_stats["target"]
    user_stats = user_stats.sort_values("completion_rate", ascending=False)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(user_stats["username"], user_stats["completion_rate"], color='#2c8ef7')
    
    ax.set_title("各用户销售完成率对比", fontsize=14, pad=20)
    ax.set_ylabel("完成率", fontsize=12)
    ax.set_ylim(0, 1.2)
    ax.grid(True, alpha=0.3, axis='y')
    
    # 显示数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                f'{height:.1%}', ha='center', va='bottom', fontsize=10)
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# 5. 管理员-航班销售额排行
def plot_admin_flight_ranking(df):
    flight_rank = df.groupby("flight_no").agg({
        "amount": "sum"
    }).reset_index().sort_values("amount", ascending=False).head(10)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(flight_rank["flight_no"][::-1], flight_rank["amount"][::-1], color='#2c8ef7')
    
    ax.set_title("全平台TOP10航班销售额排行", fontsize=14, pad=20)
    ax.set_xlabel("销售额（元）", fontsize=12)
    ax.grid(True, alpha=0.3, axis='x')
    
    # 显示数值标签
    for i, v in enumerate(flight_rank["amount"][::-1]):
        ax.text(v + 10, i, format_amount(v), va='center', fontsize=10)
    
    plt.tight_layout()
    return fig

# 6. 管理员-日期销售额热力图
def plot_admin_date_heatmap(df):
    df_heat = df.copy()
    df_heat["date"] = pd.to_datetime(df_heat["date"])
    df_heat["weekday"] = df_heat["date"].dt.dayofweek
    df_heat["day"] = df_heat["date"].dt.day
    
    heat_data = df_heat.pivot_table(
        index="weekday",
        columns="day",
        values="amount",
        aggfunc="sum",
        fill_value=0
    )
    
    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    heat_data.index = heat_data.index.map(weekday_map)
    
    fig, ax = plt.subplots(figsize=(12, 4))
    sns.heatmap(heat_data, annot=True, fmt=".0f", cmap="RdYlGn", ax=ax, cbar_kws={'label': '销售额（元）'})
    ax.set_title("全平台日期销售额热力图", fontsize=14, pad=20)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("星期", fontsize=12)
    plt.tight_layout()
    return fig

# ======================== 页面逻辑 ========================
init_db()

if "user" not in st.session_state:
    st.session_state.user = None

# ======================== 登录/注册页面 ========================
if st.session_state.user is None:
    st.title("🔐 销售数据管理系统")
    tab1, tab2 = st.tabs(["登录", "注册"])
    
    with tab1:
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("用户名", placeholder=f"管理员账号：{ADMIN_USER}")
            password = st.text_input("密码", type="password", placeholder=f"管理员密码：{ADMIN_PWD}")
            if st.form_submit_button("登录", type="primary"):
                user, msg = login(username, password)
                if user:
                    st.session_state.user = user
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    with tab2:
        with st.form("register_form", clear_on_submit=True):
            new_username = st.text_input("新用户名")
            new_password = st.text_input("新密码", type="password", placeholder="至少6位，含大写字母+数字")
            confirm_pwd = st.text_input("确认密码", type="password")
            if st.form_submit_button("注册"):
                if new_password != confirm_pwd:
                    st.error("两次密码不一致")
                else:
                    success, msg = register(new_username, new_password)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    st.stop()

# ======================== 普通用户页面 ========================
if not st.session_state.user["is_admin"]:
    st.title(f"📊 {st.session_state.user['username']} 的销售看板")
    
    # 退出按钮
    col_logout, _ = st.columns([1, 9])
    with col_logout:
        if st.button("🚪 退出登录"):
            st.session_state.clear()
            st.rerun()
    
    # 数据筛选
    st.subheader("📅 数据筛选")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("结束日期", datetime.now())
    
    # 获取用户数据
    df = get_user_sales(st.session_state.user["id"], start_date, end_date)
    
    # 核心指标统计
    if not df.empty:
        total_amount = df["amount"].sum()
        total_target = df["target"].sum()
        overall_rate = total_amount / total_target if total_target > 0 else 0
        today = datetime.now().strftime("%Y-%m-%d")
        df_today = df[df["date"] == today]
        today_amount = df_today["amount"].sum()
        today_target = df_today["target"].sum()
        today_rate = today_amount / today_target if today_target > 0 else 0
    else:
        total_amount = total_target = overall_rate = today_amount = today_target = today_rate = 0
    
    # 核心指标展示
    st.subheader("💰 核心指标")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("今日销售额", format_amount(today_amount))
    with col2:
        st.metric("今日完成率", format_rate(today_rate))
    with col3:
        st.metric("筛选期总销售额", format_amount(total_amount))
    with col4:
        st.metric("筛选期总完成率", format_rate(overall_rate))
    
    # 录入数据
    st.subheader("➕ 录入销售数据")
    with st.form("add_sale_form", clear_on_submit=True):
        col_date, col_flight, col_amt, col_tgt = st.columns(4)
        with col_date:
            sale_date = st.date_input("日期", datetime.now())
        with col_flight:
            flight_no = st.text_input("航班号", placeholder="如：MU1234、CA5678")
        with col_amt:
            amount = st.number_input("销售额", min_value=0.0, step=0.01)
        with col_tgt:
            target = st.number_input("销售指标", min_value=0.0, step=0.01)
        if st.form_submit_button("提交", type="primary"):
            if not flight_no:
                st.error("航班号不能为空")
            elif amount <= 0 or target <= 0:
                st.error("销售额和指标必须大于0")
            else:
                success, msg = add_sale(st.session_state.user["id"], sale_date, flight_no, amount, target)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    # 可视化图表区域
    st.subheader("📈 数据可视化")
    if not df.empty:
        # 趋势图
        st.subheader("1. 每日销售额 vs 指标趋势")
        fig_trend = plot_sales_trend(df)
        st.pyplot(fig_trend)
        
        # 航班统计
        st.subheader("2. TOP10 航班销售额统计")
        fig_flight = plot_flight_sales(df)
        st.pyplot(fig_flight)
        
        # 日期热力图
        st.subheader("3. 日期销售额热力图")
        fig_heat = plot_date_heatmap(df)
        st.pyplot(fig_heat)
    else:
        st.info("暂无销售数据，录入数据后即可查看可视化图表")
    
    # 销售记录列表
    st.subheader("📋 销售记录")
    if not df.empty:
        display_df = df[["id", "date", "flight_no", "amount_formatted", "target_formatted", "completion_rate_formatted"]]
        display_df.columns = ["ID", "日期", "航班号", "销售额", "销售指标", "完成率"]
        st.dataframe(display_df, use_container_width=True)
        
        # 删除功能
        st.subheader("🗑️ 数据删除")
        sale_ids = df["id"].tolist()
        selected_id = st.selectbox("选择要删除的记录ID", sale_ids)
        if st.button("删除选中记录"):
            success, msg = delete_sale(selected_id, st.session_state.user["id"])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("暂无销售记录")

# ======================== 管理员后台 ========================
else:
    st.title("🔧 管理员后台")
    
    # 退出按钮
    col_logout, _ = st.columns([1, 9])
    with col_logout:
        if st.button("🚪 退出登录"):
            st.session_state.clear()
            st.rerun()
    
    # 全平台数据筛选
    st.subheader("📅 全平台数据筛选")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("结束日期", datetime.now())
    
    # 获取全平台数据
    all_df = get_all_sales(start_date, end_date)
    
    if not all_df.empty:
        # 全平台核心统计
        total_amount = all_df["amount"].sum()
        total_target = all_df["target"].sum()
        overall_rate = total_amount / total_target if total_target > 0 else 0
        user_count = all_df["username"].nunique()
        flight_count = all_df["flight_no"].nunique()
        
        st.subheader("📊 全平台核心统计")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总销售额", format_amount(total_amount))
        with col2:
            st.metric("总销售指标", format_amount(total_target))
        with col3:
            st.metric("整体完成率", format_rate(overall_rate))
        with col4:
            st.metric("活跃用户数", user_count)
        
        # 数据导出
        st.subheader("📥 数据导出")
        export_df = all_df[["username", "date", "flight_no", "amount", "target", "completion_rate"]]
        export_df.columns = ["用户名", "日期", "航班号", "销售额", "销售指标", "完成率"]
        # 格式化导出数据
        export_df["销售额"] = export_df["销售额"].apply(format_amount)
        export_df["销售指标"] = export_df["销售指标"].apply(format_amount)
        export_df["完成率"] = export_df["完成率"].apply(format_rate)
        
        st.download_button(
            label="📤 导出Excel格式（CSV）",
            data=export_df.to_csv(index=False, encoding='utf-8-sig'),
            file_name=f"全平台销售数据_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # 管理员可视化图表
        st.subheader("📈 全平台数据可视化")
        
        # 1. 用户完成率对比
        st.subheader("1. 各用户销售完成率对比")
        fig_user_rate = plot_admin_user_rate(all_df)
        st.pyplot(fig_user_rate)
        
        # 2. 航班销售额排行
        st.subheader("2. TOP10 航班销售额排行")
        fig_flight_rank = plot_admin_flight_ranking(all_df)
        st.pyplot(fig_flight_rank)
        
        # 3. 日期销售额热力图
        st.subheader("3. 全平台日期销售额热力图")
        fig_admin_heat = plot_admin_date_heatmap(all_df)
        st.pyplot(fig_admin_heat)
        
        # 全平台详细数据
        st.subheader("📋 全平台销售记录")
        display_df = all_df[["username", "date", "flight_no", "amount", "target", "completion_rate"]]
        display_df.columns = ["用户名", "日期", "航班号", "销售额", "销售指标", "完成率"]
        display_df["销售额"] = display_df["销售额"].apply(format_amount)
        display_df["销售指标"] = display_df["销售指标"].apply(format_amount)
        display_df["完成率"] = display_df["完成率"].apply(format_rate)
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.info("📭 全平台暂无销售数据，请先让用户录入数据")

# 底部版权信息
st.markdown("---")
st.markdown("<div style='text-align:center; color:#666;'>销售数据管理系统 | 外网可访问 | 多用户隔离 | 数据可视化</div>", unsafe_allow_html=True)
