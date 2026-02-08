import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
import json
import os
import random
import requests
import time
from datetime import datetime, timedelta

# =================================================================
# 1. 配置與全域變數 (Configuration & Global Variables)
# =================================================================

# Firebase Web API Key (用於 Firebase Auth REST API)
FIREBASE_WEB_API_KEY = st.secrets["firebase"]["api_key"]

# 本地檔案路徑
HISTORY_FILE = "vocab_history.json"
FULL_WORD_FILE = "full-word.json"

# AI 故事生成主題清單
THEME_DATA = {
    "職場生活": ["辦公室趣事", "職涯規劃", "人際互動"],
    "科幻冒險": ["外星探索", "未來科技", "平行世界"],
    "日常美食": ["料理分享", "街頭小吃", "飲食文化"],
    "旅行見聞": ["異國文化", "自然景觀", "城市探索"],
    "偵探解謎": ["懸疑案件", "推理挑戰", "心理戰術"],
    "個人成長與心靈探索": ["自我提升", "心靈療癒", "人生反思"],
    "藝術與創意": ["創作分享", "文化觀察", "靈感來源"],
    "社會與人文": ["歷史故事", "社會觀察", "人物傳記"],
    "科技與未來": ["AI與新科技", "未來生活", "數位文化"],
    "自然與動物": ["動物趣聞", "環境議題", "自然探索"],
    "趣味與娛樂": ["遊戲人生", "影視分享", "幽默段子"],
    "運動與健康": ["健身技巧", "運動賽事", "健康生活"],
    "教育與學習": ["學習方法", "知識分享", "語言探索"],
    "財經與理財": ["投資理財", "商業趨勢", "消費文化"],
    "人際與情感": ["友情故事", "愛情觀察", "家庭互動"],
    "文化與傳統": ["節慶習俗", "民間故事", "宗教文化"],
    "創業與挑戰": ["商業點子", "創業心路", "成功案例"],
    "幽默與搞笑": ["生活尷尬", "冷笑話", "趣味段子"],
    "奇幻世界": ["魔法冒險", "神話傳說", "異世界旅程"],
    "心理與思考": ["認知偏差", "心理測驗", "思維模式"]
}

# =================================================================
# 2. 初始化 Firebase Admin SDK
# =================================================================

if not firebase_admin._apps:
    try:
        # 混合模式讀取：優先嘗試 Streamlit Secrets，否則讀取本地 JSON
        if "firebase" in st.secrets:
            cred_info = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_info)
            firebase_admin.initialize_app(cred)
        elif os.path.exists("studyenglish-a0c15-firebase-adminsdk-fbsvc-86412d005d.json"):
            cred = credentials.Certificate("studyenglish-a0c15-firebase-adminsdk-fbsvc-86412d005d.json")
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase 初始化失敗: {e}")

try:
    db = firestore.client()
except:
    db = None

# =================================================================
# 3. 自定義介面樣式 (CSS)
# =================================================================

st.markdown("""
    <style>
    .stApp { background-color: #121212; color: #E0E0E0; }
    .word-card {
        background-color: #1E1E1E;
        border: 1px solid #333333;
        border-radius: 10px;
        padding: 30px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .big-word { font-size: 3.5em; font-weight: bold; color: #BB86FC; margin: 10px 0; }
    .phonetic { color: #03DAC6; font-style: italic; font-size: 1.1em; }
    .definition { color: #B0B0B0; margin-top: 10px; font-size: 1em; }
    div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; }
    .login-container { padding: 2rem; background-color: #1E1E1E; border-radius: 10px; border: 1px solid #333; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 4. 資料庫與雲端同步功能
# =================================================================

def load_data_from_cloud(uid):
    """從 Firestore 讀取使用者學習進度"""
    if db is None: return {}
    doc_ref = db.collection("users").document(uid)
    doc = doc_ref.get()
    return doc.to_dict().get("learning_data", {}) if doc.exists else {}

def load_local_json(filepath):
    """讀取本地靜態單字庫檔案"""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history():
    """將當前進度保存至本地 JSON (備援用)"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.learning_data, f, ensure_ascii=False, indent=4)

def save_data_to_cloud(uid, data):
    """將使用者進度同步至 Firestore"""
    if db is None: return
    doc_ref = db.collection("users").document(uid)
    doc_ref.set({"learning_data": data}, merge=True)

# =================================================================
# 5. Firebase Auth 驗證邏輯
# =================================================================

if "user_info" not in st.session_state:
    st.session_state.user_info = None

def auth_user(email, password, is_login=True):
    """使用 Firebase REST API 進行登入或註冊"""
    url_type = "signInWithPassword" if is_login else "signUp"
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{url_type}?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()
    else:
        try:
            error_msg = res.json().get('error', {}).get('message', 'Unknown Error')
        except:
            error_msg = "連線錯誤"
        return {"error": error_msg}

def login_ui():
    """顯示登入與註冊介面"""
    st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🔐 會員登入</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container():
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            auth_mode = st.radio("模式", ["登入", "註冊新帳號"], horizontal=True)
            email = st.text_input("Email")
            password = st.text_input("密碼", type="password")
            if st.button("送出", type="primary"):
                if not email or not password:
                    st.error("請輸入 Email 和密碼")
                else:
                    with st.spinner("驗證中..."):
                        result = auth_user(email, password, is_login=(auth_mode == "登入"))
                        if "error" in result:
                            st.error(f"❌ {result['error']}")
                        else:
                            st.success(f"🎉 {auth_mode}成功！")
                            st.session_state.user_info = {
                                "email": result["email"],
                                "uid": result["localId"],
                                "token": result["idToken"]
                            }
                            time.sleep(1)
                            st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# 權限檢查：未登入則停止執行
if not st.session_state.user_info:
    login_ui()
    st.stop()

# =================================================================
# 6. 單字練習核心邏輯
# =================================================================

# 初始化 Session State
if "learning_data" not in st.session_state:
    uid = st.session_state.user_info['uid']
    st.session_state.learning_data = load_data_from_cloud(uid)

if "full_word_list" not in st.session_state:
    data = load_local_json(FULL_WORD_FILE)
    word_map = {}
    word_list = []
    if isinstance(data, list):
        for item in data:
            val = item.get("value", {})
            word = val.get("word")
            if word:
                word_map[word] = val
                word_list.append(word)
    st.session_state.full_word_db = word_map
    st.session_state.full_word_list = word_list

# 初始化狀態機變數
for key, default in [("session_queue", []), ("current_word", None),
                    ("unknown_words", []), ("stage", "setup"), ("dict_info", {})]:
    if key not in st.session_state:
        st.session_state[key] = default

def get_word_tag(word):
    """獲取單字掌握度標籤"""
    data = st.session_state.learning_data.get(word, {})
    mastery = data.get("mastery", 0)
    if word not in st.session_state.learning_data:
        return "🆕 新單字", "#757575"
    elif mastery < 3:
        return f"⏳ 掌握度 {mastery}", "#FBC02D"
    else:
        return "💎 長期記憶", "#03DAC6"
@st.cache_data(ttl=3600)
def fetch_dictionary_data(word):
    """獲取外部字典 API 資料"""
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            data = res.json()[0]
            phonetic = data.get("phonetic", "")
            definition = data["meanings"][0]["definitions"][0]["definition"]
            return {"phonetic": phonetic, "definition": definition}
    except:
        pass
    return {"phonetic": "/.../", "definition": "暫無詳細定義 (請參考下方 AI 故事)"}

def smart_sampling():
    """SRS 智慧抽詞演算法"""
    history = st.session_state.learning_data
    full_list = st.session_state.full_word_list
    now = datetime.now().isoformat()
    review_list = [w for w, d in history.items() if d.get("next_review", "") < now]
    new_list = [w for w in full_list if w not in history]
    selected = random.sample(review_list, min(len(review_list), 3)) if review_list else []
    needed = 5 - len(selected)
    if needed > 0 and new_list:
        selected.extend(random.sample(new_list, min(len(new_list), needed)))
    random.shuffle(selected)
    st.session_state.session_queue = selected
    st.session_state.unknown_words = []

def update_srs(word, is_known):
    """更新單字的間隔重複 (SRS) 數據"""
    if word not in st.session_state.learning_data:
        st.session_state.learning_data[word] = {"mastery": 0, "seen": 0, "interval": 0}
    data = st.session_state.learning_data[word]
    now = datetime.now()
    if is_known:
        data["mastery"] += 1
        days = 2 ** data["mastery"]
        data["interval"] = days
        data["next_review"] = (now + timedelta(days=days)).isoformat()
    else:
        data["mastery"] = 0
        data["interval"] = 1
        data["next_review"] = now.isoformat()
        if word not in st.session_state.unknown_words:
            st.session_state.unknown_words.append(word)
    data["seen"] += 1
    if st.session_state.user_info:
        save_data_to_cloud(st.session_state.user_info['uid'], st.session_state.learning_data)

# =================================================================
# 7. 使用者介面流程 (Sidebar & Content Stages)
# =================================================================

with st.sidebar:
    st.write(f"👤 Hi, {st.session_state.user_info['email']}")
    if st.button("🚪 登出"):
        st.session_state.user_info = None
        st.rerun()
    st.divider()
    st.title("⚙️ 設定")
    api_key = st.text_input("Gemini API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.divider()
    st.subheader("🤖 故事風格")
    main_theme = st.selectbox("主題", list(THEME_DATA.keys()))
    sub_theme = st.selectbox("情境", THEME_DATA[main_theme])
    st.divider()
    st.caption(f"📚 總單字庫: {len(st.session_state.full_word_list)} | 📖 已學: {len(st.session_state.learning_data)}")

# 階段 1：準備畫面
if st.session_state.stage == "setup":
    st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🧠 AI 智慧記憶 (Pro)</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 開始智慧抽詞 (5 Words)", use_container_width=True):
            smart_sampling()
            if not st.session_state.session_queue:
                st.warning("單字庫為空或沒有需要複習的單字！")
            else:
                st.session_state.current_word = st.session_state.session_queue.pop(0)
                st.session_state.dict_info = fetch_dictionary_data(st.session_state.current_word)
                st.session_state.stage = "learning"
                st.rerun()

# 階段 2：學習卡片
elif st.session_state.stage == "learning":
    word = st.session_state.current_word
    tag_text, tag_color = get_word_tag(word)
    dict_data = st.session_state.dict_info
    st.progress((5 - len(st.session_state.session_queue)) / 5)
    st.markdown(f"""
    <div class="word-card">
        <div style="background-color: {tag_color}; color: #121212; display: inline-block; padding: 2px 10px; border-radius: 4px; font-weight: bold; font-size: 0.8em; margin-bottom: 10px;">
            {tag_text}
        </div>
        <div class="big-word">{word}</div>
        <div class="phonetic">{dict_data.get('phonetic', '')}</div>
        <div class="definition">{dict_data.get('definition', '')}</div>
        <br>
        <a href="https://dictionary.cambridge.org/zht/詞典/英語-漢語-繁體/{word}" target="_blank" style="color: #03DAC6; text-decoration: none;">
            🔗 查看劍橋字典詳解
        </a>
    </div>
    """, unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("❌ 不認識 (強化)", type="primary"):
            update_srs(word, False)
            if st.session_state.session_queue:
                st.session_state.current_word = st.session_state.session_queue.pop(0)
                st.session_state.dict_info = fetch_dictionary_data(st.session_state.current_word)
                st.rerun()
            else:
                st.session_state.stage = "story"
                st.rerun()
    with col2:
        if st.button("✅ 認識 (Next)"):
            update_srs(word, True)
            if st.session_state.session_queue:
                st.session_state.current_word = st.session_state.session_queue.pop(0)
                st.session_state.dict_info = fetch_dictionary_data(st.session_state.current_word)
                st.rerun()
            else:
                st.session_state.stage = "story"
                st.rerun()

# 階段 3：AI 故事生成
elif st.session_state.stage == "story":
    st.markdown("<h2 style='text-align: center; color: #BB86FC;'>🎉 練習完成！</h2>", unsafe_allow_html=True)
    st.info(f"本次弱點單字: {', '.join(st.session_state.unknown_words) if st.session_state.unknown_words else '無'}")
    if st.button("🪄 生成 AI 情境故事", use_container_width=True):
        if not api_key:
            st.error("請先在左側設定 API Key")
        else:
            prompt = f"""
                        你是一位專業英文老師。請用英文寫一個關於「{main_theme} - {sub_theme}」的故事（約 120-150 字）。
                        必須自然地包含這 5 個單字：{', '.join(st.session_state.unknown_words)}。

                        要求：
                        1. 將指定單字用 Markdown 粗體 (**word**) 標示。
                        2. 針對我不熟的字（ {', '.join(st.session_state.unknown_words)}），在語境中提供更多線索輔助理解。
                        3. 語意通順，劇情流暢
                        4. 附上全文繁體中文翻譯。
                        """
            with st.spinner("AI 正在編織故事中..."):
                try:
                    model = genai.GenerativeModel('models/gemini-3-flash-preview')
                    response = model.generate_content(prompt)
                    st.markdown("### 📖 您的客製化故事")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"生成失敗: {e}")
    if st.button("🏠 回首頁"):
        st.session_state.stage = "setup"
        st.rerun()