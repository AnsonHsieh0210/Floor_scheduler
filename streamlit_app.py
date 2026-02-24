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
    """將名字中間字變為 O 以保護隱私 (防止重複遮罩)"""
    name = str(name).strip()
    if "O" in name: return name # 已經遮過的就不再遮
    if len(name) <= 2: return name[0] + "O"
    return name[0] + "O" + name[2:]

def load_data():
    """讀取人員資料，並強制執行資料清理"""
    if os.path.exists(SAVE_FILE):
        try: 
            df = pd.read_csv(SAVE_FILE, dtype={"員編": str})
            # 清理可能存在的 "None" 字串
            df = df.replace(["None", "nan"], "")
            return df
        except: return get_default_df()
    return get_default_df()

def get_default_df():
    """預設的人員名單"""
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
    # 初始化欄位
    for col in ["劃休(/)", "補休(補)", "年假(年)"]:
        if col not in df.columns: df[col] = ""
    return df

# 初始化 Session State
if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

# --- 強制修復資料 (解決遮罩消失與 None 問題) ---
# 每次執行都檢查一次，確保名字被遮罩，且 None 被清除
if not st.session_state.staff_df.empty:
    # 1. 強制遮罩名字
    st.session_state.staff_df["姓名"] = st.session_state.staff_df["姓名"].apply(mask_name)
    # 2. 清除 "None" 字串
    st.session_state.staff_df = st.session_state.staff_df.replace(["None", "nan"], "")

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
        <p>• <b>人力配置</b>：每日最低門檻 2A / 2B，並<b>盡量平衡早晚班人數</b>。<br>
        • <b>休假規則</b>：每人預設排班 <b>21 天</b> (若請假過多則自動調整)。<br>
        • <b>人性化排班</b>：優先安排<b>連續班別</b>，減少 A/B 頻繁切換。<br>
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
    edited_staff = st.data_editor(st.session_state.staff_df, num_rows="dynamic", use_container_width=True, key="main_editor")
    submit_data = st.form_submit_button("💾 儲存並備份名單")
    if submit_data:
        # 儲存前再次確保格式正確
        edited_staff = edited_staff.replace(["None", "nan"], "")
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.success("✅ 資料已同步儲存 (已自動修復格式)")
        st.rerun() # 重新整理頁面以更新顯示

# --- 3. 核心邏輯函式 ---

def parse_days(input_str):
    """解析日期字串，過濾掉 None 或無效文字"""
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
    """AI 排班核心邏輯 (加入 A/B 班平衡 + 穩定度懲罰)"""
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # 變數定義：0=休假, 1=早班(A), 2=晚班(B)
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}

    priority_rewards = []    # 獎勵分數 (滿足休假/平衡)
    stability_penalties = [] # 懲罰分數 (混亂/不平衡)
    
    req_offs_record = {}
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        req_offs_record[n] = {"/": parse_days(row["劃休(/)"]), "補": parse_days(row["補休(補)"]), "年": parse_days(row["年假(年)"])}
        
        # --- 上班天數 21 天邏輯 ---
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

        # --- 休假優先權邏輯 ---
        is_p1 = ("洪O雯" in n)
        is_p2 = ("潘O誼" in n)
        for label, d_list in req_offs_record[n].items():
            for d in d_list:
                if 1 <= d <= days:
                    d_idx = d - 1
                    if is_p1:
                        model.Add(shifts[(n, d_idx, 0)] == 1)
                    elif is_p2:
                        pref = model.NewBoolVar(f'pref_p2_{n}_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        model.Add(shifts[(n, d_idx, 0)] == 0).OnlyEnforceIf(pref.Not())
                        priority_rewards.append(pref * 100)
                    else:
                        pref = model.NewBoolVar(f'pref_n_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        model.Add(shifts[(n, d_idx, 0)] == 0).OnlyEnforceIf(pref.Not())
                        priority_rewards.append(pref * 1)

    # --- 硬性限制與優化條件 ---
    for d in range(days):
        # 1. 每人每天只能一種狀態
        for n in names: 
            model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
        
        # 2. 每日人力下限 (2A 2B)
        count_a = sum(shifts[(n, d, 1)] for n in names)
        count_b = sum(shifts[(n, d, 2)] for n in names)
        model.Add(count_a >= 2) 
        model.Add(count_b >= 2) 

        # 3. [新功能] 人力平衡機制：避免早晚班人數懸殊
        # 邏輯：建立變數 diff = |count_a - count_b|，並懲罰 diff
        diff = model.NewIntVar(0, 10, f'diff_{d}')
        model.AddAbsEquality(diff, count_a - count_b)
        # 懲罰係數設為 5，讓系統盡量拉平，但不會為了拉平而違反休假需求(100)
        stability_penalties.append(diff * 5)

    for n in names:
        for d in range(days-1): 
            # 4. 絕對禁止晚接早 (B -> A)
            model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
            
            # 5. 穩定性優化：懲罰 A -> B 的切換
            switch_a_to_b = model.NewBoolVar(f'switch_ab_{n}_{d}')
            model.Add(shifts[(n, d, 1)] + shifts[(n, d+1, 2)] == 2).OnlyEnforceIf(switch_a_to_b)
            model.Add(shifts[(n, d, 1)] + shifts[(n, d+1, 2)] < 2).OnlyEnforceIf(switch_a_to_b.Not())
            stability_penalties.append(switch_a_to_b * 20)

        # 6. 連續上班限制 (不可連續上班 5 天)
        for d in range(days-4): 
            model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4)

    # --- 目標函數 ---
    # 最大化 (休假滿意度 - 班別混亂 - 人力不均)
    model.Maximize(sum(priority_rewards) - sum(stability_penalties))
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0 # 稍微增加時間讓它運算平衡
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
                    for label, d_list in req_offs_record[n].items():
                        if (d_idx + 1) in d_list: v = label; break
                row[h] = v
            res.append(row)
        return pd.DataFrame(res), None
    else:
        return None, ["排班失敗：限制過於嚴格。請嘗試檢查是否有某天可用人力過少，導致無法平衡 A/B 班。"]

# --- 4. 執行按鈕 ---
if st.button("🚀 執行 AI 智慧排班"):
    with st.spinner("正在檢查人力配置..."):
        errors = pre_check_feasibility(st.session_state.staff_df, target_month, num_days)
    
    if errors:
        st.error(f"🚨 排班前檢測失敗！共有 {len(errors)} 天人力不足，請先協調休假：")
        for e in errors:
             st.markdown(f"<div class='error-box'>❌ {e}</div>", unsafe_allow_html=True)
    else:
        with st.spinner("人力充足，正在優化班表連續性與平衡..."):
            final_df, diag = generate_schedule(st.session_state.staff_df, target_month, num_days)
            
        if final_df is not None:
            st.success("✅ 班表生成成功！(已優化：資料修復、人力平衡、減少A/B切換)")
            st.dataframe(final_df, use_container_width=True, height=500, hide_index=True)
        else:
            st.error(f"🚨 班表生成失敗：{diag[0]}")
