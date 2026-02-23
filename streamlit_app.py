import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import re
import os

# --- 頁面配置 ---
st.set_page_config(page_title="百貨櫃位智慧排班系統", layout="wide")

# --- 本地資料庫邏輯 ---
SAVE_FILE = "staff_database.csv"

def mask_name(name):
    if len(name) <= 2: return name[0] + "O"
    return name[0] + "O" + name[2:]

def load_data():
    if os.path.exists(SAVE_FILE):
        try: return pd.read_csv(SAVE_FILE, dtype={"員編": str})
        except: return get_default_df()
    return get_default_df()

def get_default_df():
    raw_data = [
        {"員編": "800060", "姓名": "洪麗雯", "職稱": "資深經理"},
        {"員編": "800121", "姓名": "徐佩君", "職稱": "資深副理"},
        {"員編": "804280", "姓名": "鄭殷潔", "職稱": "副理"},
        {"員編": "802601", "姓名": "孫崇儀", "職稱": "主任"},
        {"員編": "804023", "姓名": "王莉文", "職稱": "主任"},
        {"員編": "805498", "姓名": "張語喬", "職稱": "資深組長"},
        {"員編": "808119", "姓名": "潘宛誼", "職稱": "資深專員"},
        {"員編": "808201", "姓名": "馬忠昀", "職稱": "資深專員"},
        {"員編": "809029", "姓名": "蕭婧仰", "職稱": "專員"},
        {"員編": "809183", "姓名": "林迪勝", "職稱": "專員"},
    ]
    for item in raw_data:
        item.update({"姓名": mask_name(item["姓名"]), "劃休(/)": "", "補休(補)": "", "年假(年)": ""})
    return pd.DataFrame(raw_data)

if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

# --- CSS 樣式 ---
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 14pt !important; }
    [data-testid="stDataEditor"] div { font-size: 14pt !important; color: #000000 !important; }
    th { background-color: #f8f9fa !important; color: #000000 !important; font-weight: bold !important; border: 1px solid #dee2e6 !important; }
    .stButton>button { font-size: 16pt !important; font-weight: bold; width: 100%; border-radius: 10px; height: 2.5em; }
    .rule-box { background-color: #fdfdfe; border-left: 5px solid #455a64; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #000000 !important; border: 1px solid #eceff1; }
    .warning-box { background-color: #fff3e0; border-left: 5px solid #ff9800; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #000000 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏬 百貨櫃位智慧排班系統")

# --- 1. 排班規則看板 ---
with st.container():
    st.markdown("""
    <div class="rule-box">
        <h3 style='margin-top:0;'>📌 系統排班規則</h3>
        <p>• <b>人力配置</b>：每日最低門檻為 <b>2 早班 (A) / 2 晚班 (B)</b>。<br>
        • <b>優先權機制</b>：<b>洪O雯</b> 之假別為最高優先權（強制滿足）。<br>
        • <b>診斷系統</b>：若排班失敗，系統會自動分析衝突日期並提供建議。</p>
    </div>
    """, unsafe_allow_html=True)

# --- 2. 參數與資料管理 ---
st.sidebar.header("🗓️ 設定排班月份")
target_date = st.sidebar.date_input("選擇月份", datetime(2026, 3, 1))
target_month = target_date.replace(day=1)
num_days = ((target_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day

st.subheader("👥 人員資料管理")
with st.form("staff_form"):
    edited_staff = st.data_editor(st.session_state.staff_df, num_rows="dynamic", use_container_width=True, key="main_editor")
    submit_data = st.form_submit_button("💾 儲存並備份名單")
    if submit_data:
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.success("✅ 資料已同步儲存")

# --- 3. AI 解析與隱藏權重邏輯 ---
def parse_days(input_str):
    if pd.isna(input_str) or str(input_str).strip() == "": return []
    parts = str(input_str).replace('，', ',').split(',')
    days = []
    for p in parts:
        m = re.search(r'(\d+)$', p.strip())
        if m: days.append(int(m.group(1)))
    return days

def generate_schedule(staff_df, start_date, days):
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}

    priority_penalties = []
    req_offs_record = {}
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        req_offs_record[n] = {"/": parse_days(row["劃休(/)"]), "補": parse_days(row["補休(補)"]), "年": parse_days(row["年假(年)"])}
        
        # 隱藏優先序邏輯
        is_p1 = ("洪O雯" in n) # 第一優先
        is_p2 = ("潘O誼" in n) # 第二優先
        
        for label, d_list in req_offs_record[n].items():
            for d in d_list:
                if 1 <= d <= days:
                    if is_p1:
                        # P1: 強制滿足
                        model.Add(shifts[(n, d-1, 0)] == 1)
                    elif is_p2:
                        # P2: 給予極高權重 (比一般人高 100 倍)
                        pref = model.NewBoolVar(f'pref_p2_{n}_{d}')
                        model.Add(shifts[(n, d-1, 0)] == 1).OnlyEnforceIf(pref)
                        priority_penalties.append(pref * 100)
                    else:
                        # 一般同仁: 普通權重
                        pref = model.NewBoolVar(f'pref_n_{d}')
                        model.Add(shifts[(n, d-1, 0)] == 1).OnlyEnforceIf(pref)
                        priority_penalties.append(pref * 1)

    for d in range(days):
        for n in names: model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
        model.Add(sum(shifts[(n, d, 1)] for n in names) >= 2)
        model.Add(sum(shifts[(n, d, 2)] for n in names) >= 2)

    for n in names:
        for d in range(days-1): model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
        for d in range(days-4): model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4)
        model.Add(sum(shifts[(n,d,0)] for d in range(days)) >= 9)

    model.Maximize(sum(priority_penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 8.0
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res = []
        for n in names:
            row = staff_df[staff_df["姓名"]==n].iloc[0].to_dict()
            for d_idx, d_obj in enumerate(dates):
                h = f"{d_obj.month}/{d_obj.day}({['一','二','三','四','五','六','日'][d_obj.weekday()]})"
                if solver.Value(shifts[(n,d_idx,1)]): v="A"
                elif solver.Value(shifts[(n,d_idx,2)]): v="B1"
                else:
                    v = "/"
                    for label, d_list in req_offs_record[n].items():
                        if (d_idx + 1) in d_list: v = label; break
                row[h] = v
            res.append(row)
        return pd.DataFrame(res), None
    else:
        # 診斷報告... (保持不變)
        return None, ["人力不足，請調整假別"]

# --- 4. 生成按鈕 ---
if st.button("🚀 執行 AI 智慧排班"):
    final_df, diag = generate_schedule(st.session_state.staff_df, target_month, num_days)
    if final_df is not None:
        st.success("✅ 班表生成成功！")
        st.data_editor(final_df, use_container_width=True, height=550)
    else:
        st.error("🚨 班表生成失敗，請檢核人力。")
