import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import re
import os

st.set_page_config(page_title="誠品智慧排班系統", layout="wide")

SAVE_FILE = "staff_database.csv"

def load_data():
    if os.path.exists(SAVE_FILE):
        try: return pd.read_csv(SAVE_FILE, dtype={"員編": str, "分機": str})
        except: return get_default_df()
    return get_default_df()

def get_default_df():
    return pd.DataFrame([
        {"員編": "800060", "姓名": "洪麗雯", "職稱": "資深經理", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "800121", "姓名": "徐佩君", "職稱": "資深副理", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "804280", "姓名": "鄭殷潔", "職稱": "副理", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "802601", "姓名": "孫崇儀", "職稱": "主任", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "804023", "姓名": "王莉文", "職稱": "主任", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "805498", "姓名": "張語喬", "職稱": "資深組長", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "808119", "姓名": "潘宛誼", "職稱": "資深專員", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "808201", "姓名": "馬忠昀", "職稱": "資深專員", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "809029", "姓名": "蕭婧仰", "職稱": "專員", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
        {"員編": "809183", "姓名": "林迪勝", "職稱": "專員", "劃休(/)": "", "補休(補)": "", "年假(年)": ""},
    ])

if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

st.markdown("<style>html, body, [class*='css'] { font-size: 16pt !important; }[data-testid='stDataEditor'] div { font-size: 16pt !important; color: #000000 !important; }th { background-color: #f0f2f6 !important; color: #000000 !important; font-weight: bold !important; }.stButton>button { font-size: 18pt !important; font-weight: bold; width: 100%; border-radius: 10px; height: 3em; }.rule-box { background-color: #f1f8e9; border-left: 5px solid #2e7d32; padding: 15px; border-radius: 5px; margin-bottom: 20px; }</style>", unsafe_allow_html=True)

st.title("🏬 誠品智慧排班系統")

with st.container():
    st.markdown('<div class="rule-box"><h3 style="margin-top:0;">📌 排班規則說明</h3><p style="font-size:14pt;">• <b>連四休一</b>：連續上班不可超過 4 天。<br>• <b>晚不接早</b>：晚班隔天禁接早班 A。<br>• <b>人力水位</b>：平日 4早3晚 / 假日 2早2晚。<br>• <b>月休門檻</b>：每人月休至少 9 天。</p></div>', unsafe_allow_html=True)

st.sidebar.header("🗓️ 選擇月份")
target_date = st.sidebar.date_input("年份與月份", datetime(2026, 3, 1))
target_month = target_date.replace(day=1)
num_days = ((target_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day

st.subheader("👥 人員資料管理")
with st.form("staff_form"):
    edited_staff = st.data_editor(st.session_state.staff_df, num_rows="dynamic", use_container_width=True, key="main_editor")
    col1, col2 = st.columns(2)
    with col1: save_btn = st.form_submit_button("💾 儲存名單")
    with col2: clear_btn = st.form_submit_button("🧹 清空假別")

    if save_btn:
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.success("✅ 已儲存")
    if clear_btn:
        for col in ["劃休(/)", "補休(補)", "年假(年)"]: edited_staff[col] = ""
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.rerun()

def parse_days(s):
    if pd.isna(s) or str(s).strip() == "": return []
    return [int(m.group(1)) for p in str(s).replace('，',',').split(',') if (m := re.search(r'(\d+)$', p.strip()))]

def generate_schedule(staff_df, start_date, days):
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}

    fixed_offs = {}
    for _, row in staff_df.iterrows():
        n = row["姓名"]; fixed_offs[n] = {}
        for d in parse_days(row["劃休(/)"]): 
            if 1<=d<=days: model.Add(shifts[(n,d-1,0)]==1); fixed_offs[n][d-1]="/"
        for d in parse_days(row["補休(補)"]): 
            if 1<=d<=days: model.Add(shifts[(n,d-1,0)]==1); fixed_offs[n][d-1]="補"
        for d in parse_days(row["年假(年)"]): 
            if 1<=d<=days: model.Add(shifts[(n,d-1,0)]==1); fixed_offs[n][d-1]="年"

    for d in range(days):
        wk = dates[d].weekday() >= 5
        for n in names: model.Add(sum(shifts[(n,d,s)] for s in [0,1,2])==1)
        if wk:
            model.Add(sum(shifts[(n,d,1)] for n in names)>=2); model.Add(sum(shifts[(n,d,2)] for n in names)>=2)
        else:
            model.Add(sum(shifts[(n,d,1)] for n in names)>=4); model.Add(sum(shifts[(n,d,2)] for n in names)>=3)

    for n in names:
        for d in range(days-1): model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
        for d in range(days-4): model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4)
        model.Add(sum(shifts[(n,d,0)] for d in range(days)) >= 9)

    solver = cp_model.CpSolver()
    if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res = []
        for n in names:
            row = staff_df[staff_df["姓名"]==n].iloc[0].to_dict()
            for d_idx, d_obj in enumerate(dates):
                h = f"{d_obj.month}/{d_obj.day}({['一','二','三','四','五','六','日'][d_obj.weekday()]})"
                if solver.Value(shifts[(n,d_idx,1)]): v="A"
                elif solver.Value(shifts[(n,d_idx,2)]): v="B2" if d_obj.weekday() in [4,5] else "B1"
                else: v=fixed_offs[n].get(d_idx, "/")
                row[h] = v
            row["總休"] = sum(1 for d in range(days) if solver.Value(shifts[(n,d,0)]))
            row["早A"] = sum(1 for d in range(days) if solver.Value(shifts[(n,d,1)]))
            row["晚B"] = sum(1 for d in range(days) if solver.Value(shifts[(n,d,2)]))
            res.append(row)
        return pd.DataFrame(res)
    return None

st.markdown("---")
if st.button("🚀 執行 AI 自動排班"):
    final_df = generate_schedule(st.session_state.staff_df, target_month, num_days)
    if final_df is not None:
        st.success("✅ 成功！")
        st.data_editor(final_df, use_container_width=True, height=550)
        st.download_button("📥 下載 CSV", final_df.to_csv(index=False).encode('utf-8-sig'), "Schedule.csv")
    else:
        st.error("🚨 無法生成。請檢查是否有人預約假別太多，或人力不足（平日需 7 人）。")
