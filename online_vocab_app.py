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
from gtts import gTTS
import io


# =================================================================
# MODULE 1: 設定與常數 (Config & Constants)
# =================================================================
class Config:
    HISTORY_FILE = "vocab_history.json"
    FULL_WORD_FILE = "full-word.json"

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

    @staticmethod
    def load_css():
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
# MODULE 2: 服務層 (Services) - 負責 API, Firebase, I/O
# =================================================================
class FirebaseService:
    def __init__(self):
        self.db = None
        self.api_key = None
        try:
            self.api_key = st.secrets["firebase"]["api_key"]
            if not firebase_admin._apps:
                if "firebase" in st.secrets:
                    cred = credentials.Certificate(dict(st.secrets["firebase"]))
                elif os.path.exists("firebase-key.json"):  # 假設的本地檔名
                    cred = credentials.Certificate("firebase-key.json")
                else:
                    return
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
        except Exception as e:
            st.error(f"Firebase 初始化警告: {e}")

    def auth_user(self, email, password, is_login=True):
        url_type = "signInWithPassword" if is_login else "signUp"
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:{url_type}?key={self.api_key}"
        payload = {"email": email, "password": password, "returnSecureToken": True}
        res = requests.post(url, json=payload)
        return res.json()

    def load_user_data(self, uid):
        if not self.db: return {}, None
        doc = self.db.collection("users").document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("learning_data", {}), data.get("api_key", None)
        return {}, None

    def save_data(self, uid, data):
        if self.db:
            self.db.collection("users").document(uid).set({"learning_data": data}, merge=True)

    def save_api_key(self, uid, api_key):
        if self.db:
            if api_key is None:
                self.db.collection("users").document(uid).update({"api_key": firestore.DELETE_FIELD})
            else:
                self.db.collection("users").document(uid).set({"api_key": api_key}, merge=True)


class AIService:
    @staticmethod
    def fetch_dictionary(word):
        """
        改用 Gemini 生成中文定義與例句
        """
        # 如果沒有 API Key，回傳預設值以免報錯
        if "gemini_key" not in st.session_state or not st.session_state.gemini_key:
            return {
                "phonetic": "/.../",
                "definition": "請先設定 API Key 以取得 AI 解釋",
                "example": "Please set API Key first."
            }

        try:
            genai.configure(api_key=st.session_state.gemini_key)
            model = genai.GenerativeModel('models/gemini-pro')

            # 提示詞：強制要求 JSON 格式以便程式解析
            prompt = f"""
            請作為一個英文教學字典，針對單字 "{word}" 提供以下資訊，並嚴格依照 JSON 格式回傳，不要有 markdown 標記：
            {{
                "phonetic": "KK音標",
                "definition": "繁體中文的簡潔定義 (約15字內)",
                "example": "一個實用的英文例句 (附上繁體中文翻譯)"
            }}
            """

            response = model.generate_content(prompt)
            text = response.text.strip()

            # 清理可能產生的 Markdown code block 符號
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            data = json.loads(text)
            return data

        except Exception as e:
            # 如果 AI 解析失敗，回傳錯誤訊息
            print(f"Dictionary Error: {e}")
            return {
                "phonetic": "/.../",
                "definition": "暫時無法取得解釋 (AI 連線錯誤)",
                "example": "Connection Error"
            }

    @staticmethod
    def play_audio(text):
        try:
            tts = gTTS(text=text, lang='en')
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            st.audio(fp, format='audio/mp3')
        except:
            st.warning("語音播放失敗")

    @staticmethod
    def generate_mnemonic(word):
        if "gemini_key" not in st.session_state:
            st.error("請先設定 API Key")
            return

        # === 修正點 1: 從 Session State 取得主題設定 ===
        # 如果使用者還沒選，預設為 "職場生活"
        theme_config = st.session_state.get("theme_config", ("職場生活", "辦公室趣事"))
        main_theme, sub_theme = theme_config

        # 取得目前累積的弱點單字，如果沒有就用當前單字
        target_words = st.session_state.unknown_words if st.session_state.unknown_words else [word]

        with st.spinner("AI 正在動腦筋想梗..."):
            try:
                genai.configure(api_key=st.session_state.gemini_key)
                model = genai.GenerativeModel('models/gemini-pro')

                prompt = f"""
                你是一位幽默的英文老師。請針對單字 "{word}"：
                1. 提供一個好記的「諧音記憶法」或「聯想記憶法」(繁體中文)。
                2. 結合主題「{main_theme} - {sub_theme}」寫一個簡短好笑的句子。
                """
                res = model.generate_content(prompt)
                st.info(f"💡 **記憶小撇步**：\n\n{res.text}")
            except Exception as e:
                st.error(f"AI 呼叫失敗: {e}")

    @staticmethod
    def generate_story(theme, sub_theme, words):
        if "gemini_key" not in st.session_state:
            st.error("請先設定 API Key")
            return

        prompt = f"""
            你是一位專業英文老師。請用英文寫一個關於「{theme} - {sub_theme}」的故事（約 120-150 字）。
            必須自然地包含這幾個單字：{', '.join(words)}。

            要求：
            1. 將指定單字用 Markdown 粗體 (**word**) 標示。
            2. 語意通順，劇情流暢。
            3. 在英文故事下方，附上「全文繁體中文翻譯」。
        """
        with st.spinner("AI 正在編織故事中..."):
            try:
                genai.configure(api_key=st.session_state.gemini_key)
                model = genai.GenerativeModel('models/gemini-pro')
                response = model.generate_content(prompt)
                st.markdown("### 📖 您的客製化故事")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"生成失敗: {e}")


# =================================================================
# MODULE 3: 商業邏輯層 (Business Logic) - SRS 演算法
# =================================================================
class SRSEngine:
    @staticmethod
    def calculate_next_review(current_data, quality):
        """
        quality: 0=Again, 3=Hard, 4=Good, 5=Easy
        Return: Updated data dict
        """
        # 初始化
        if "mastery" not in current_data: current_data.update({"mastery": 0, "seen": 0, "interval": 0})

        data = current_data.copy()
        data["seen"] = data.get("seen", 0) + 1
        now = datetime.now()

        if quality == 0:  # Again
            data["mastery"] = 0
            data["interval"] = 1
            data["next_review"] = now.isoformat()
        else:
            if data["interval"] == 0: data["interval"] = 1

            # 簡單乘數邏輯
            multiplier = {3: 1.2, 4: 2.5, 5: 4.0}.get(quality, 2.5)
            data["interval"] = max(1, int(data["interval"] * multiplier))
            data["mastery"] += 1
            data["next_review"] = (now + timedelta(days=data["interval"])).isoformat()

        return data

    @staticmethod
    def get_review_batch(history, full_list, batch_size=5):
        now = datetime.now().isoformat()
        review_list = [w for w, d in history.items() if d.get("next_review", "") < now]
        new_list = [w for w in full_list if w not in history]

        selected = []
        # 優先複習
        if review_list:
            selected.extend(random.sample(review_list, min(len(review_list), 3)))

        # 補新單字
        needed = batch_size - len(selected)
        if needed > 0 and new_list:
            selected.extend(random.sample(new_list, min(len(new_list), needed)))

        random.shuffle(selected)
        return selected


# =================================================================
# MODULE 4: UI 管理層 (View Managers)
# =================================================================
class UIManager:
    def __init__(self, app):
        self.app = app  # 讓 UI 可以呼叫 App 的方法

    def render_login(self):
        st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🔐 會員中心</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            tab1, tab2 = st.tabs(["登入", "註冊新帳號"])
            with tab1:
                email = st.text_input("Email", key="login_email")
                pwd = st.text_input("密碼", type="password", key="login_pass")
                if st.button("登入", type="primary"):
                    self.app.handle_auth(email, pwd, True)
            with tab2:
                email = st.text_input("Email", key="signup_email")
                pwd = st.text_input("設定密碼", type="password", key="signup_pass")
                if st.button("建立帳號"):
                    self.app.handle_auth(email, pwd, False)

    def render_sidebar(self):
        with st.sidebar:
            st.write(f"👤 {st.session_state.user_info['email']}")
            st.divider()

            # API Key 區塊
            st.subheader("🔑 API Key 設定")
            if "gemini_key" in st.session_state:
                st.success("✅ API Key 已載入")
                if st.button("🗑️ 更換 Key"):
                    del st.session_state.gemini_key
                    self.app.fb_service.save_api_key(st.session_state.user_info['uid'], None)
                    st.rerun()
            else:
                input_key = st.text_input("Gemini API Key", type="password")
                if st.button("💾 儲存 Key"):
                    st.session_state.gemini_key = input_key
                    self.app.fb_service.save_api_key(st.session_state.user_info['uid'], input_key)
                    st.rerun()

            st.divider()
            st.subheader("🤖 故事風格")
            main_theme = st.selectbox("主題", list(Config.THEME_DATA.keys()))
            sub_theme = st.selectbox("情境", Config.THEME_DATA[main_theme])
            st.session_state.theme_config = (main_theme, sub_theme)  # 存入 session 供 Story 階段使用

            st.divider()
            st.caption(
                f"📚 總單字: {len(st.session_state.full_word_list)} | 📖 已學: {len(st.session_state.learning_data)}")

    def render_setup(self):
        st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🧠 AI 智慧記憶 (Pro)</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🚀 開始智慧抽詞 (5 Words)", use_container_width=True):
                self.app.start_session()

    def render_learning(self):
        word = st.session_state.current_word
        dict_data = st.session_state.dict_info

        st.progress((5 - len(st.session_state.session_queue)) / 5)

        # 卡片正面
        st.markdown(f"""
        <div class="word-card">
            <div class="big-word">{word}</div>
            <div class="phonetic">{dict_data.get('phonetic', '')}</div>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.show_answer:
            # 尚未翻牌
            col_show, col_audio = st.columns([4, 1])
            with col_show:
                if st.button("👁️ 顯示答案與意思", type="primary", use_container_width=True):
                    st.session_state.show_answer = True
                    st.rerun()
            with col_audio:
                if st.button("🔊"): AIService.play_audio(word)
        else:
            # 已經翻牌 (背面)
            AIService.play_audio(word)

            st.markdown(f"""
            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <div style="color: #B0B0B0;">📚 定義：{dict_data.get('definition', '')}</div>
                <div style="color: #BB86FC; margin-top: 10px; font-style: italic;">📝 例句："{dict_data.get('example', '')}"</div>
            </div>
            """, unsafe_allow_html=True)

            # AI 記憶掛鉤按鈕
            if st.button("🧠 AI 幫我想個諧音/記憶法", use_container_width=True):
                AIService.generate_mnemonic(word)

            st.markdown("---")

            # SRS 評分
            cols = st.columns(4)
            labels = [("❌ 忘記", 0), ("😓 困難", 3), ("😊 剛好", 4), ("⚡ 秒殺", 5)]
            for col, (label, score) in zip(cols, labels):
                with col:
                    if st.button(label, use_container_width=True):
                        self.app.process_review(word, score)

    def render_story(self):
        st.markdown("<h2 style='text-align: center; color: #BB86FC;'>🎉 練習完成！</h2>", unsafe_allow_html=True)
        unknowns = st.session_state.unknown_words
        st.info(f"本次弱點單字: {', '.join(unknowns) if unknowns else '無'}")

        if st.button("🪄 生成 AI 情境故事", use_container_width=True):
            theme, sub = st.session_state.get("theme_config", ("職場生活", "辦公室趣事"))
            # 如果沒有弱點單字，就隨機挑幾個剛複習的
            target_words = unknowns if unknowns else st.session_state.session_queue_history
            AIService.generate_story(theme, sub, target_words)

        if st.button("🏠 回首頁"):
            st.session_state.stage = "setup"
            st.rerun()


# =================================================================
# MODULE 5: 主程式控制器 (Main Controller)
# =================================================================
class VocabularyApp:
    def __init__(self):
        Config.load_css()
        self.fb_service = FirebaseService()
        self.ui = UIManager(self)
        self.init_state()

    def init_state(self):
        # 確保基本變數存在
        defaults = {
            "user_info": None,
            "learning_data": {},
            "full_word_list": [],
            "session_queue": [],
            "session_queue_history": [],  # 紀錄本次學了哪些字(給故事用)
            "current_word": None,
            "unknown_words": [],
            "stage": "setup",
            "dict_info": {},
            "show_answer": False
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

        # 載入單字庫 (只做一次)
        if not st.session_state.full_word_list:
            data = load_local_json(Config.FULL_WORD_FILE)
            word_list = []
            if isinstance(data, list):
                for item in data:
                    word = item.get("value", {}).get("word")
                    if word: word_list.append(word)
            st.session_state.full_word_list = word_list

    def handle_auth(self, email, password, is_login):
        with st.spinner("連線中..."):
            res = self.fb_service.auth_user(email, password, is_login)
            if "error" in res:
                st.error(f"❌ {res['error']['message']}")
            else:
                uid = res["localId"]
                st.session_state.user_info = {"email": res["email"], "uid": uid, "token": res["idToken"]}

                # 登入後載入資料
                data, key = self.fb_service.load_user_data(uid)
                st.session_state.learning_data = data
                if key: st.session_state.gemini_key = key
                st.rerun()

    def start_session(self):
        selected = SRSEngine.get_review_batch(st.session_state.learning_data, st.session_state.full_word_list)
        if not selected:
            st.warning("單字庫為空！")
            return

        st.session_state.session_queue = selected
        st.session_state.session_queue_history = selected.copy()  # 備份給故事用
        st.session_state.unknown_words = []
        self.next_card()

    def next_card(self):
        st.session_state.show_answer = False
        if st.session_state.session_queue:
            word = st.session_state.session_queue.pop(0)
            st.session_state.current_word = word
            st.session_state.dict_info = AIService.fetch_dictionary(word)
            st.session_state.stage = "learning"
        else:
            st.session_state.stage = "story"
        st.rerun()

    def process_review(self, word, score):
        # 1. 更新數據
        current_data = st.session_state.learning_data.get(word, {})
        new_data = SRSEngine.calculate_next_review(current_data, score)
        st.session_state.learning_data[word] = new_data

        # 2. 紀錄弱點
        if score == 0 and word not in st.session_state.unknown_words:
            st.session_state.unknown_words.append(word)

        # 3. 雲端存檔
        if st.session_state.user_info:
            self.fb_service.save_data(st.session_state.user_info['uid'], st.session_state.learning_data)

        # 4. 下一張
        self.next_card()

    def run(self):
        if not st.session_state.user_info:
            self.ui.render_login()
        else:
            self.ui.render_sidebar()
            if st.session_state.stage == "setup":
                self.ui.render_setup()
            elif st.session_state.stage == "learning":
                self.ui.render_learning()
            elif st.session_state.stage == "story":
                self.ui.render_story()


# 輔助函式 (為了相容舊的 load 邏輯，保留獨立函式)
def load_local_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


# =================================================================
# MAIN ENTRY POINT
# =================================================================
if __name__ == "__main__":
    app = VocabularyApp()
    app.run()
