import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, time
import pandas as pd
import json

# --- 定数設定 ---
CREDENTIAL_FILE = "nice-virtue-467105-v3-8aa4dd80c645.json"  
SHEET_ID = "1D4j2Jyx4tigJ2OipiGNUAQ8hTZPYG8QbKOVCXy_E5Po"
IN_PROGRESS_SHEET_NAME = "作業中"
COMPLETED_SHEET_NAME = "完了記録"
PROCESS_OPTIONS = ["", "断裁", "折", "中綴じ", "無線綴じ", "ミシン・スジ", "綴じ（カレンダー）", "丁合（カレンダー）", "梱包", "区分け"]
FOLD_OPTIONS = ["", "4p", "6p", "8p", "16p", "その他"]
IN_PROGRESS_HEADER = ["記録ID", "製品名", "工程名", "詳細", "開始時間", "終了時間", "作業時間_分", "出来数", "作業人数", "ステータス"]

# --- 認証とデータ操作関数 ---
@st.cache_resource
def authorize_gspread():
    """Google Sheets APIへの認証を行い、クライアントオブジェクトを返す"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # ▼▼▼ 変更点：新しいSecretsの形式に合わせて認証情報を組み立てる ▼▼▼
        creds_dict = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": st.secrets["private_key"],
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"],
            "universe_domain": st.secrets["universe_domain"]
        }
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(credentials)
    except (KeyError, FileNotFoundError):
        # Secretsがない場合（ローカルでの実行時）は、ファイルから読み込む
        try:
            credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIAL_FILE, scope)
            return gspread.authorize(credentials)
        except Exception as e:
            st.error(f"❌ ローカルでのGoogle認証に失敗: {e}")
            return None

def load_in_progress_data(sheet):
    """「作業中」シートから全データを読み込み、DataFrameとして返す"""
    try:
        data = sheet.get_all_records(expected_headers=IN_PROGRESS_HEADER)
        df = pd.DataFrame(data)
        if not df.empty and '記録ID' in df.columns:
            df['記録ID'] = df['記録ID'].astype(str)
        return df
    except gspread.exceptions.GSpreadException:
        return pd.DataFrame()

# --- Streamlit UIの初期設定 ---
st.set_page_config(layout="wide")
st.title("📘 製本作業記録アプリ Final")

if 'view' not in st.session_state:
    st.session_state.view = 'SELECT_PROCESS'

client = authorize_gspread()
if not client: st.stop()
try:
    spreadsheet = client.open_by_key(SHEET_ID)
    in_progress_sheet = spreadsheet.worksheet(IN_PROGRESS_SHEET_NAME)
    completed_sheet = spreadsheet.worksheet(COMPLETED_SHEET_NAME)
except Exception as e:
    st.error(f"❌ スプレッドシート接続中にエラーが発生: {e}")
    st.stop()

# =======================================================================
#  画面①：工程選択画面
# =======================================================================
if st.session_state.view == 'SELECT_PROCESS':
    in_progress_df = load_in_progress_data(in_progress_sheet)
    col_form, col_list = st.columns(2)

    with col_form:
        st.header("Step 1: 製品と工程を選択")
        in_progress_products = [""] 
        if not in_progress_df.empty:
            in_progress_products.extend(sorted(in_progress_df['製品名'].unique()))
        product_choice_options = ["（新規登録）"] + in_progress_products
        selected_choice = st.selectbox("作業対象の製品を選択", product_choice_options, key="product_choice")
        
        product_name = ""
        if selected_choice == "（新規登録）":
            product_name = st.text_input("新しい製品名を入力", key="new_product_name_input")
        else:
            product_name = selected_choice
        process_name = st.selectbox("記録する工程名", PROCESS_OPTIONS, key="process_name_input")

        if st.button("この工程の入力を開始する", type="primary", disabled=(not product_name or not process_name)):
            st.session_state.selected_product = product_name
            st.session_state.selected_process = process_name
            st.session_state.view = 'INPUT_FORM'
            st.rerun()

    with col_list:
        st.header("進行中の作業一覧（削除可能）")
        if in_progress_df.empty:
            st.info("現在、作業中の製品はありません。")
        else:
            for index, row in in_progress_df.iterrows():
                with st.container():
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(f"**{row['製品名']}** / {row['工程名']} ({row['詳細']}) - {row['出来数']}個")
                    with c2:
                        if st.button("削除", key=f"delete_{row['記録ID']}", type="secondary"):
                            try:
                                cell_to_find = in_progress_sheet.find(row['記録ID'])
                                if cell_to_find:
                                    in_progress_sheet.delete_rows(cell_to_find.row)
                                    st.success(f"記録ID: {row['記録ID']} を削除しました。")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"削除中にエラーが発生しました: {e}")
                    st.divider()

# =======================================================================
#  画面②：各工程の入力フォーム画面
# =======================================================================
elif st.session_state.view == 'INPUT_FORM':
    st.header(f"Step 2: 「{st.session_state.selected_product}」の作業内容を記録")
    st.subheader(f"工程: **{st.session_state.selected_process}**")

    with st.form("process_details_form"):
        quantity = st.number_input("出来数", min_value=0, step=1)
        workers = st.number_input("作業人数", min_value=1, step=1)
        
        detail_value, start_time_obj, end_time_obj, work_time_minutes = "", None, None, 0
        if st.session_state.selected_process == "断裁":
            time_options = [f"{i*10}" for i in range(1, 12 * 6 + 1)] 
            work_time_minutes = st.selectbox("作業時間（分）", time_options)
            detail_value = f"{work_time_minutes}分"
        elif st.session_state.selected_process == "折":
            detail_value = st.selectbox("ページ数", FOLD_OPTIONS)
            start_time_obj = st.time_input("開始時間")
            end_time_obj = st.time_input("終了時間")
        else:
            start_time_obj = st.time_input("開始時間")
            end_time_obj = st.time_input("終了時間")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            add_in_progress_button = st.form_submit_button("作業中として追加", use_container_width=True)
        with col_btn2:
            complete_button = st.form_submit_button("この工程で作業完了", type="primary", use_container_width=True)
        
        def run_process(is_complete):
            if start_time_obj and end_time_obj and end_time_obj <= start_time_obj:
                st.error("❌ 終了時間は開始時間よりも後の時刻を選択してください。")
                return
            status = "完了" if is_complete else "作業中"
            start_time_str = start_time_obj.strftime('%H:%M') if start_time_obj else ""
            end_time_str = end_time_obj.strftime('%H:%M') if end_time_obj else ""
            
            final_row_list = [datetime.now().strftime("%Y%m%d%H%M%S%f"), st.session_state.selected_product, st.session_state.selected_process, detail_value, start_time_str, end_time_str, int(work_time_minutes), int(quantity), int(workers), status]
            
            if is_complete:
                with st.spinner("完了処理を実行中..."):
                    try:
                        current_in_progress_df = load_in_progress_data(in_progress_sheet)
                        records_to_complete = []
                        rows_to_delete_ids = []
                        if not current_in_progress_df.empty:
                            product_specific_df = current_in_progress_df[current_in_progress_df['製品名'] == st.session_state.selected_product]
                            if not product_specific_df.empty:
                                existing_records = [row.tolist() for index, row in product_specific_df.iterrows()]
                                for record in existing_records: record[-1] = "完了"
                                records_to_complete.extend(existing_records)
                                rows_to_delete_ids = product_specific_df['記録ID'].tolist()
                        records_to_complete.append(final_row_list)
                        if records_to_complete: completed_sheet.append_rows(records_to_complete, value_input_option='USER_ENTERED')
                        if rows_to_delete_ids:
                            rows_to_delete = sorted([in_progress_sheet.find(entry_id).row for entry_id in rows_to_delete_ids], reverse=True)
                            for row_num in rows_to_delete: in_progress_sheet.delete_rows(row_num)
                        st.success(f"✅ 「{st.session_state.selected_product}」の記録を確定しました。")
                    except Exception as e:
                        st.error(f"完了処理中にエラーが発生しました: {e}")
            else:
                in_progress_sheet.append_row(final_row_list, value_input_option='USER_ENTERED')
                st.success(f"工程「{st.session_state.selected_process}」を追加しました。")
            st.session_state.view = 'SELECT_PROCESS'

        if add_in_progress_button: run_process(is_complete=False)
        if complete_button: run_process(is_complete=True)

    if st.button("工程の選択に戻る"):
        st.session_state.view = 'SELECT_PROCESS'
        st.rerun()