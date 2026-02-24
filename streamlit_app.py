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
    """將名字中間字變為 O 以保護隱私"""
    if len(name) <= 2: return name[0] + "O"
    return name[0] + "O" + name[2:]

def load_data():
    """讀取人員資料，若無則建立預設資料"""
    if os.path.exists(SAVE_FILE):
        try: return pd.read_csv(SAVE_FILE, dtype={"員編": str})
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
    for item in raw_data:
        # 初始化假別欄位
        item.update({"姓名": mask_name(item["姓名"]), "劃休(/)": "", "補休(補)": "", "年假(年)": ""})
    return pd.DataFrame(raw_data)

# 初始化 Session State
if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

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

# --- 1. 排班規則看板 (已移除優先權顯示) ---
with st.container():
    st.markdown("""
    <div class="rule-box">
        <h3 style='margin-top:0;'>📌 系統排班規則</h3>
        <p>• <b>人力配置</b>：每日最低門檻為 <b>2 早班 (A) / 2 晚班 (B)</b>。<br>
        • <b>休假規則</b>：每人預設排班 <b>21 天</b> (若請假過多則自動調整)。<br>
        • <b>連上限制</b>：不可連續上班 5 天 (即連上 4 天後必須休假)。<br>
        • <b>診斷系統</b>：若排班失敗，系統會自動預先檢查人力是否不足。</p>
    </div>
    """, unsafe_allow_html=True)

# --- 2. 參數與資料管理 ---
st.sidebar.header("🗓️ 設定排班月份")
target_date = st.sidebar.date_input("選擇月份", datetime(2026, 3, 1))
target_month = target_date.replace(day=1)
# 自動計算該月天數
next_month = (target_month.replace(day=28) + timedelta(days=4)).replace(day=1)
num_days = (next_month - timedelta(days=1)).day

st.subheader("👥 人員資料管理")
with st.form("staff_form"):
    edited_staff = st.data_editor(st.session_state.staff_df, num_rows="dynamic", use_container_width=True, key="main_editor")
    submit_data = st.form_submit_button("💾 儲存並備份名單")
    if submit_data:
        st.session_state.staff_df = edited_staff
        edited_staff.to_csv(SAVE_FILE, index=False)
        st.success("✅ 資料已同步儲存")

# --- 3. 核心邏輯函式 ---

def parse_days(input_str):
    """解析日期字串，例如 '1, 3, 5' -> [1, 3, 5]"""
    if pd.isna(input_str) or str(input_str).strip() == "": return []
    parts = str(input_str).replace('，', ',').split(',')
    days = []
    for p in parts:
        m = re.search(r'(\d+)$', p.strip())
        if m: days.append(int(m.group(1)))
    return days

def pre_check_feasibility(staff_df, start_date, days):
    """
    【除錯功能】預先檢查：每天的可用人數是否 < 最低需求人數 (4人)
    """
    error_logs = []
    min_staff_needed = 4  # 每日最低需求：2早 + 2晚
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # 1. 解析每個人的休假請求
    staff_leaves = {}
    for _, row in staff_df.iterrows():
        # 合併所有假別 (劃休 + 補休 + 年假)
        leaves = parse_days(row["劃休(/)"]) + parse_days(row["補休(補)"]) + parse_days(row["年假(年)"])
        staff_leaves[row["姓名"]] = leaves

    # 2. 檢查每一天
    for d_idx, d_obj in enumerate(dates):
        day_num = d_idx + 1 # 日期 (1號, 2號...)
        available_staff = 0 # 當天可用人數
        people_on_leave = [] # 當天休假名單
        
        for name, leaves in staff_leaves.items():
            if day_num in leaves:
                people_on_leave.append(name)
            else:
                available_staff += 1
        
        # 3. 如果可用人數 < 4，這天絕對排不出來，報錯！
        if available_staff < min_staff_needed:
            weekday_str = ['一','二','三','四','五','六','日'][d_obj.weekday()]
            h = f"{d_obj.month}/{d_obj.day}({weekday_str})"
            
            error_logs.append(
                f"**{h}** 人力不足！需求 {min_staff_needed} 人，僅剩 {available_staff} 人可用。 (休假: {', '.join(people_on_leave)})"
            )
            
    return error_logs

def generate_schedule(staff_df, start_date, days):
    """AI 排班核心邏輯"""
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # 變數定義：0=休假, 1=早班(A), 2=晚班(B)
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}

    priority_penalties = []
    req_offs_record = {}
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        req_offs_record[n] = {"/": parse_days(row["劃休(/)"]), "補": parse_days(row["補休(補)"]), "年": parse_days(row["年假(年)"])}
        
        # --- 1. 上班天數設定 (目標 21 天) ---
        total_leaves = set(req_offs_record[n]["/"] + req_offs_record[n]["補"] + req_offs_record[n]["年"])
        # 過濾掉超出當月範圍的日期
        valid_leaves = len([d for d in total_leaves if 1 <= d <= days])
        
        work_days_var = sum(shifts[(n,d,1)] + shifts[(n,d,2)] for d in range(days))
        
        target = 21
        max_possible = days - valid_leaves
        
        if max_possible < target:
            # 若請假太多無法上滿 21 天，則強制設定為「能上的天數」
            model.Add(work_days_var == max_possible)
        else:
            # 正常情況：至少上 21 天，最多給一點彈性到 23 天 (避免勞逸不均)
            model.Add(work_days_var >= target)
            model.Add(work_days_var <= target + 2)

        # --- 2. 隱藏的優先權邏輯 (不顯示在介面上) ---
        is_p1 = ("洪O雯" in n) # 第一優先
        is_p2 = ("潘O誼" in n) # 第二優先
        
        for label, d_list in req_offs_record[n].items():
            for d in d_list:
                if 1 <= d <= days:
                    d_idx = d - 1
                    if is_p1:
                        # P1: 強制滿足
                        model.Add(shifts[(n, d_idx, 0)] == 1)
                    elif is_p2:
                        # P2: 給予極高權重 (Soft Constraint)
                        pref = model.NewBoolVar(f'pref_p2_{n}_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        model.Add(shifts[(n, d_idx, 0)] == 0).OnlyEnforceIf(pref.Not())
                        priority_penalties.append(pref * 100)
                    else:
                        # 一般: 普通權重
                        pref = model.NewBoolVar(f'pref_n_{d}')
                        model.Add(shifts[(n, d_idx, 0)] == 1).OnlyEnforceIf(pref)
                        model.Add(shifts[(n, d_idx, 0)] == 0).OnlyEnforceIf(pref.Not())
                        priority_penalties.append(pref * 1)

    # --- 硬性限制條件 ---
    for d in range(days):
        # 每日每人只能一種狀態
        for n in names: 
            model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
        
        # 每日人力需求 (2早 2晚)
        model.Add(sum(shifts[(n, d, 1)] for n in names) >= 2) 
        model.Add(sum(shifts[(n, d, 2)] for n in names) >= 2) 

    for n in names:
        # 禁止「晚接早」
        for d in range(days-1): 
            model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
        
        # --- 3. 連續上班限制 (修正版) ---
        # 規則：不強制一定要做四休一，但「不可連續上班 5 天」
        # 邏輯：任意連續 5 天的區間內，上班天數總和 <= 4
        # 結果：允許 11110 (四休一), 11101 (三休一上一), 但禁止 11111 (連五)
        for d in range(days-4): 
            model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4)

    # --- 求解 ---
    model.Maximize(sum(priority_penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res = []
        for n in names:
            row = staff_df[staff_df["姓名"]==n].iloc[0].to_dict()
            for d_idx, d_obj in enumerate(dates):
                h = f"{d_obj.month}/{d_obj.day}({['一','二','三','四','五','六','日'][d_obj.weekday()]})"
                
                if solver.Value(shifts[(n,d_idx,1)]): 
                    v = "A"
                elif solver.Value(shifts[(n,d_idx,2)]): 
                    v = "B"
                else:
                    v = "/"
                    for label, d_list in req_offs_record[n].items():
                        if (d_idx + 1) in d_list: 
                            v = label; break
                row[h] = v
            res.append(row)
        return pd.DataFrame(res), None
    else:
        return None, ["排班失敗：無法滿足限制 (可能原因：指定上班21天與人力需求衝突，或連續上班限制導致)。"]

# --- 4. 執行按鈕 (包含除錯邏輯) ---
if st.button("🚀 執行 AI 智慧排班"):
    # 1. 先執行【預先檢查】
    with st.spinner("正在檢查人力配置..."):
        errors = pre_check_feasibility(st.session_state.staff_df, target_month, num_days)
    
    # 2. 如果有錯誤，直接顯示並停止，不跑 AI
    if errors:
        st.error(f"🚨 排班前檢測失敗！共有 {len(errors)} 天人力不足，請先協調休假：")
        for e in errors:
             st.markdown(f"<div class='error-box'>❌ {e}</div>", unsafe_allow_html=True)
            
    else:
        # 3. 檢查通過，才執行 AI 排班
        with st.spinner("人力充足，正在進行 AI 運算 (約需 5-10 秒)..."):
            final_df, diag = generate_schedule(st.session_state.staff_df, target_month, num_days)
            
        if final_df is not None:
            st.success("✅ 班表生成成功！")
            st.dataframe(final_df, use_container_width=True, height=500, hide_index=True)
        else:
            st.error(f"🚨 班表生成失敗：{diag[0]}")
            st.warning("💡 提示：若人力數量足夠但仍失敗，請檢查是否「連續上班限制」太嚴格。")
