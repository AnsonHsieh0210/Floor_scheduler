import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import re
import os
import random

# --- 頁面配置 ---
st.set_page_config(page_title="百貨櫃位智慧排班系統", layout="wide")

# --- 本地資料庫邏輯 ---
SAVE_FILE = "staff_database.csv"

def mask_name(name):
    """將名字中間字變為 O 以保護隱私"""
    name = str(name).strip()
    if "O" in name: return name 
    if len(name) <= 2: return name[0] + "O"
    return name[0] + "O" + name[2:]

def load_data():
    """讀取人員資料，並強制執行資料清理"""
    if os.path.exists(SAVE_FILE):
        try: 
            df = pd.read_csv(SAVE_FILE, dtype={"員編": str})
            df = df.replace(["None", "nan"], "")
            return df
        except: return get_default_df()
    return get_default_df()

def get_default_df():
    """預設的人員名單 (新增指定班別欄位)"""
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
    df = pd.DataFrame(raw_data)
    # 初始化欄位：除了休假，新增指定早班/晚班
    for col in ["劃休(/)", "補休(補)", "年假(年)", "指定早班(A)", "指定晚班(B)"]:
        if col not in df.columns: df[col] = ""
    return df

if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

# --- 強制修復資料 ---
if not st.session_state.staff_df.empty:
    st.session_state.staff_df["姓名"] = st.session_state.staff_df["姓名"].apply(mask_name)
    st.session_state.staff_df = st.session_state.staff_df.replace(["None", "nan"], "")
    # 確保新欄位存在 (針對舊存檔的相容性)
    for col in ["指定早班(A)", "指定晚班(B)"]:
        if col not in st.session_state.staff_df.columns:
            st.session_state.staff_df[col] = ""

# --- CSS 樣式優化 ---
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 14pt !important; }
    [data-testid="stDataEditor"] div { font-size: 14pt !important; color: #000000 !important; }
    th { background-color: #f8f9fa !important; color: #000000 !important; font-weight: bold !important; border: 1px solid #dee2e6 !important; }
    .stButton>button { font-size: 16pt !important; font-weight: bold; width: 100%; border-radius: 10px; height: 2.5em; }
    .rule-box { background-color: #fdfdfe; border-left: 5px solid #455a64; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #000000 !important; border: 1px solid #eceff1; }
    .error-box { background-color: #ffebee; border-left: 5px solid #d32f2f; padding: 10px; border-radius: 5px; margin-bottom: 10px; color: #b71c1c !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏬 百貨櫃位智慧排班系統")

# --- 1. 排班規則看板 ---
with st.container():
    st.markdown("""
    <div class="rule-box">
        <h3 style='margin-top:0;'>📌 系統排班規則</h3>
        <p>• <b>指定班別</b>：可於表格右側指定某日上 <b>早班(A)</b> 或 <b>晚班(B)</b>。<br>
        • <b>休假規則</b>：每人預設排班 <b>21 天</b> (若請假過多則自動調整)。<br>
        • <b>人性化排班</b>：優先安排連續班別，並加入<b>隨機洗牌</b>。<br>
        • <b>連上限制</b>：不可連續上班 5 天 (即連上 4 天後必須休假)。</p>
    </div>
    """, unsafe_allow_html=True)

# --- 2. 參數與資料管理 ---
st.sidebar.header("🗓️ 設定排班月份")
target_date = st.sidebar.date_input("選擇月份", datetime(2026, 3, 1))
target_month = target_date.replace(day=1)
next_month = (target_month.replace(day=28) + timedelta(days=4)).replace(day=1)
num_days = (next_month - timedelta(days=1)).day

st.subheader("👥 人員資料管理")
with st.form("staff_form"):
    # 調整欄位順序，方便閱讀
    cols = ["員編", "姓名", "職稱", "劃休(/)", "補休(補)", "年假(年)", "指定早班(A)", "指定晚班(B)"]
    # 確保只顯示存在的欄位
    display_cols = [c for c in cols if c in st.session_state.staff_df.columns]
    
    edited_staff = st.data_editor(
        st.session_state.staff_df[display_cols], 
        num_rows="dynamic", 
        use_container_width=True, 
        key="main_editor"
    )
    submit_data = st.form_submit_button("💾 儲存並備份名單")
    if submit_data:
        edited_staff = edited_staff.replace(["None", "nan"], "")
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.success("✅ 資料已同步儲存")
        st.rerun()

# --- 3. 核心邏輯函式 ---

def parse_days(input_str):
    s = str(input_str).lower().strip()
    if s in ["none", "nan", "", "nat"]: return []
    parts = s.replace('，', ',').split(',')
    days = []
    for p in parts:
        m = re.search(r'(\d+)$', p.strip())
        if m: days.append(int(m.group(1)))
    return days

def pre_check_feasibility(staff_df, start_date, days):
    error_logs = []
    min_staff_needed = 4 
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    staff_leaves = {}
    for _, row in staff_df.iterrows():
        leaves = parse_days(row["劃休(/)"]) + parse_days(row["補休(補)"]) + parse_days(row["年假(年)"])
        staff_leaves[row["姓名"]] = leaves

    for d_idx, d_obj in enumerate(dates):
        day_num = d_idx + 1
        available_staff = 0
        people_on_leave = []
        for name, leaves in staff_leaves.items():
            if day_num in leaves:
                people_on_leave.append(name)
            else:
                available_staff += 1
        
        if available_staff < min_staff_needed:
            weekday_str = ['一','二','三','四','五','六','日'][d_obj.weekday()]
            h = f"{d_obj.month}/{d_obj.day}({weekday_str})"
            error_logs.append(
                f"**{h}** 人力不足！需求 {min_staff_needed} 人，僅剩 {available_staff} 人可用。 (休假: {', '.join(people_on_leave)})"
            )
    return error_logs

def generate_schedule(staff_df, start_date, days):
    """AI 排班核心邏輯 (新增指定班別功能)"""
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}

    priority_rewards = []    # 獎勵分數
    stability_penalties = [] # 懲罰分數
    random_noise = []        # 隨機擾動
    
    req_offs_record = {}
    req_shifts_record = {} # [新增] 記錄指定班別
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        req_offs_record[n] = {"/": parse_days(row["劃休(/)"]), "補": parse_days(row["補休(補)"]), "年": parse_days(row["年假(年)"])}
        req_shifts_record[n] = {"A": parse_days(row["指定早班(A)"]), "B": parse_days(row["指定晚班(B)"])}

        # 1. 上班天數 21 天邏輯
        total_leaves = set(req_offs_record[n]["/"] + req_offs_record[n]["補"] + req_offs_record[n]["年"])
        valid_leaves = len([d for d in total_leaves if 1 <= d <= days])
        work_days_var = sum(shifts[(n,d,1)] + shifts[(n,d,2)] for d in range(days))
        
        target = 21
        max_possible = days - valid_leaves
        if max_possible < target:
            model.Add(work_days_var == max_possible)
        else:
            model.Add(work_days_var >= target)
            model.Add(work_days_var <= target + 2)

        # 2. 休假優先權 (最高優先)
        is_p1 = ("洪O雯" in n)
        is_p2 = ("潘O誼" in n)
        
        # 為了避免衝突，先收集該員所有的休假日期
        my_leave_days = []
        for label, d_list in req_offs_record[n].items():
            for d in d_list:
                if 1 <= d <= days:
                    d_idx = d - 1
                    my_leave_days.append(d)
                    if is_p1:
                        model.Add(shifts[(n, d_idx, 0)] == 1)
                    elif is_p2:
                        pref = model.NewBoolVar(f'pref_p2_{n}_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        priority_rewards.append(pref * 100)
                    else:
                        pref = model.NewBoolVar(f'pref_n_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        priority_rewards.append(pref * 1)

        # 3. [新功能] 指定班別優先權 (A班/B班)
        # 規則：如果那天已經劃休，則忽略指定班別 (休假 > 上班)
        # 指定 A 班
        for d in req_shifts_record[n]["A"]:
            if 1 <= d <= days and d not in my_leave_days:
                d_idx = d - 1
                # 強制那天必須是早班 (1)
                model.Add(shifts[(n, d_idx, 1)] == 1)
        
        # 指定 B 班
        for d in req_shifts_record[n]["B"]:
            if 1 <= d <= days and d not in my_leave_days:
                d_idx = d - 1
                # 強制那天必須是晚班 (2)
                model.Add(shifts[(n, d_idx, 2)] == 1)

        # 4. 隨機洗牌
        for d in range(days):
            for s in [1, 2]:
                rand_weight = random.randint(-2, 2) 
                random_noise.append(shifts[(n, d, s)] * rand_weight)

    # --- 限制與優化 ---
    for d in range(days):
        for n in names: 
            model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
        
        count_a = sum(shifts[(n, d, 1)] for n in names)
        count_b = sum(shifts[(n, d, 2)] for n in names)
        model.Add(count_a >= 2) 
        model.Add(count_b >= 2) 

        # 平衡早晚班
        diff = model.NewIntVar(0, 10, f'diff_{d}')
        model.AddAbsEquality(diff, count_a - count_b)
        stability_penalties.append(diff * 5)

    for n in names:
        for d in range(days-1): 
            # 禁止 B -> A
            model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
            
            # 連續性優化
            switch_a_to_b = model.NewBoolVar(f'switch_ab_{n}_{d}')
            model.Add(shifts[(n, d, 1)] + shifts[(n, d+1, 2)] == 2).OnlyEnforceIf(switch_a_to_b)
            model.Add(shifts[(n, d, 1)] + shifts[(n, d+1, 2)] < 2).OnlyEnforceIf(switch_a_to_b.Not())
            stability_penalties.append(switch_a_to_b * 20)

        # 連續上班限制 (不可連 5)
        for d in range(days-4): 
            model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4)

    # --- 目標函數 ---
    model.Maximize(sum(priority_rewards) - sum(stability_penalties) + sum(random_noise))
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res = []
        for n in names:
            row = staff_df[staff_df["姓名"]==n].iloc[0].to_dict()
            for d_idx, d_obj in enumerate(dates):
                h = f"{d_obj.month}/{d_obj.day}({['一','二','三','四','五','六','日'][d_obj.weekday()]})"
                if solver.Value(shifts[(n,d_idx,1)]): v = "A"
                elif solver.Value(shifts[(n,d_idx,2)]): v = "B"
                else:
                    v = "/"
                    # 顯示假別
                    for label, d_list in req_offs_record[n].items():
                        if (d_idx + 1) in d_list: v = label; break
                row[h] = v
            res.append(row)
        return pd.DataFrame(res), None
    else:
        return None, ["排班失敗：限制過於嚴格。請檢查「指定班別」是否導致某天 A/B 班人數不足，或與休假衝突。"]

# --- 4. 執行按鈕 ---
if st.button("🚀 執行 AI 智慧排班 (每次點擊結果不同)"):
    with st.spinner("正在檢查人力配置..."):
        errors = pre_check_feasibility(st.session_state.staff_df, target_month, num_days)
    
    if errors:
        st.error(f"🚨 排班前檢測失敗！共有 {len(errors)} 天人力不足，請先協調休假：")
        for e in errors:
             st.markdown(f"<div class='error-box'>❌ {e}</div>", unsafe_allow_html=True)
    else:
        with st.spinner("正在進行運算 (加入隨機洗牌)..."):
            final_df, diag = generate_schedule(st.session_state.staff_df, target_month, num_days)
            
        if final_df is not None:
            st.success("✅ 班表生成成功！(已套用指定班別)")
            st.dataframe(final_df, use_container_width=True, height=500, hide_index=True)
            st.info("💡 如果覺得這版的人員搭配不滿意，可以再按一次按鈕重新洗牌。")
        else:
            st.error(f"🚨 班表生成失敗：{diag[0]}")
