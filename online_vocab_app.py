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
import re


# =================================================================
# MODULE 1: 設定與常數 (Config & Constants)
# =================================================================
class Config:
    # 檔案路徑
    HISTORY_FILE = "vocab_history.json"
    FULL_WORD_FILE = "full-word.json"

    # 模型設定 (使用 Flash 模型以獲得最快速度)
    MODEL_NAME = 'models/gemini-3-flash-preview'

    # 主題設定
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

    # 集中管理提示詞 (Prompts)
    PROMPTS = {
        "dictionary": """
        你是一個專業的 JSON 格式化工具。請解釋英文單字 "{word}"。
        嚴格遵守以下規則：
        1. 只回傳純 JSON 字串，不要使用 Markdown (不要有 ```json ... ```)。
        2. JSON 格式如下：
        {{
            "phonetic": "KK音標",
            "definition": "英文簡潔定義(繁體中文翻譯)",
            "example": "英文例句 (繁體中文翻譯)"
        }}
        """,
        "mnemonic": """
        你是一位幽默的英文老師。請針對單字 "{word}"：
        1. 提供一個好記的「諧音記憶法」或「聯想記憶法」(繁體中文)。
        2. 結合主題「{theme}」寫一個簡短好笑的句子。
        """,
        "story": """
        你是一位專業英文老師。請用英文寫一個關於「{theme}」的故事（約 100-120 字）。
        必須自然地包含這幾個單字：{words}。
        要求：
        1. 將指定單字用 Markdown 粗體 (**word**) 標示。
        2. 在英文故事下方，附上「全文繁體中文翻譯」。
        """
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
            </style>
        """, unsafe_allow_html=True)


# =================================================================
# MODULE 2: 獨立快取函式 (Cached Functions)
# 說明：將耗時操作移出類別，改為獨立函式以便 Streamlit 快取
# =================================================================

@st.cache_resource
def get_firebase_db():
    """快取 Firebase 連線，避免重複初始化"""
    try:
        if not firebase_admin._apps:
            # 優先嘗試讀取 Streamlit Secrets
            if "firebase" in st.secrets:
                cred = credentials.Certificate(dict(st.secrets["firebase"]))
            # 其次嘗試讀取本地檔案
            elif os.path.exists("firebase-key.json"):
                cred = credentials.Certificate("firebase-key.json")
            else:
                return None
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase 連線錯誤: {e}")
        return None


@st.cache_data(ttl=86400)  # 快取 24 小時
def load_static_word_list(filepath):
    """快取本地單字檔讀取"""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                word_list = []
                if isinstance(data, list):
                    for item in data:
                        # 支援不同的 JSON 結構
                        if isinstance(item, str):
                            word_list.append(item)
                        else:
                            val = item.get("value", {}).get("word") or item.get("word")
                            if val: word_list.append(val)
                return word_list
        except Exception as e:
            st.error(f"讀取單字檔失敗: {e}")
            return []
    return []


@st.cache_data(ttl=3600, show_spinner=False)  # 快取 1 小時
def fetch_ai_definition(word, api_key):
    """快取 API 查詢結果 (这是加速的關鍵)"""
    if not api_key: return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(Config.MODEL_NAME)
        prompt = Config.PROMPTS["dictionary"].format(word=word)

        # 設定 response_mime_type 為 application/json (Gemini 新功能，更穩)
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )

        text = response.text.strip()
        return json.loads(text)
    except Exception as e:
        # 如果解析失敗，回傳一個安全值
        return {
            "phonetic": "/Error/",
            "definition": "查詢失敗，請重試",
            "example": f"System Error: {str(e)}"
        }


# =================================================================
# MODULE 3: 服務層 (Services)
# =================================================================
class FirebaseService:
    def __init__(self):
        self.db = get_firebase_db()
        self.api_key = None
        # 嘗試從 secrets 讀取預設 key (如果有的話)
        if "firebase" in st.secrets and "api_key" in st.secrets["firebase"]:
            self.api_key = st.secrets["firebase"]["api_key"]

    def auth_user(self, email, password, is_login=True):
        if not self.api_key:
            return {"error": {"message": "Firebase API Key not configured"}}

        url_type = "signInWithPassword" if is_login else "signUp"
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:{url_type}?key={self.api_key}"
        payload = {"email": email, "password": password, "returnSecureToken": True}
        try:
            res = requests.post(url, json=payload, timeout=10)  # 加上 timeout
            return res.json()
        except Exception as e:
            return {"error": {"message": str(e)}}

    def load_user_data(self, uid):
        if not self.db: return {}, None
        try:
            doc = self.db.collection("users").document(uid).get()
            if doc.exists:
                data = doc.to_dict()
                return data.get("learning_data", {}), data.get("api_key", None)
        except Exception:
            pass
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
        api_key = st.session_state.get("gemini_key")
        if not api_key:
            return {
                "phonetic": "/.../",
                "definition": "請先設定 API Key",
                "example": "Please set API Key first."
            }

        # 呼叫全域快取函式
        result = fetch_ai_definition(word, api_key)
        if result:
            return result
        else:
            return {"phonetic": "/?/", "definition": "AI 連線錯誤", "example": "Error"}

    @staticmethod
    def play_audio(text):
        # gTTS 本身較慢，且 Streamlit 重繪會中斷，這是目前架構的限制
        # 若要優化需改用前端 JavaScript TTS，但代碼複雜度會大增。
        try:
            tts = gTTS(text=text, lang='en')
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            st.audio(fp, format='audio/mp3')
        except:
            st.warning("語音暫時無法播放")

    @staticmethod
    def generate_mnemonic(word):
        api_key = st.session_state.get("gemini_key")
        if not api_key:
            st.error("請先設定 API Key")
            return

        theme_config = st.session_state.get("theme_config", ("職場生活", "辦公室趣事"))
        theme_str = f"{theme_config[0]} - {theme_config[1]}"

        with st.spinner("🧠 AI 腦力激盪中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(Config.MODEL_NAME)
                prompt = Config.PROMPTS["mnemonic"].format(word=word, theme=theme_str)
                res = model.generate_content(prompt)
                st.info(f"💡 **記憶小撇步**：\n\n{res.text}")
            except Exception as e:
                st.error(f"AI 呼叫失敗: {e}")

    @staticmethod
    def generate_story(theme, sub_theme, words):
        api_key = st.session_state.get("gemini_key")
        if not api_key: return

        theme_str = f"{theme} - {sub_theme}"
        words_str = ", ".join(words)

        with st.spinner("📖 AI 正在編織故事..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(Config.MODEL_NAME)
                prompt = Config.PROMPTS["story"].format(theme=theme_str, words=words_str)
                response = model.generate_content(prompt)
                st.markdown("### 📖 您的客製化故事")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"生成失敗: {e}")


# =================================================================
# MODULE 4: 商業邏輯 (SRS Engine) - 保持原樣，邏輯無問題
# =================================================================
class SRSEngine:
    @staticmethod
    def calculate_next_review(current_data, quality):
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
        if review_list:
            selected.extend(random.sample(review_list, min(len(review_list), 3)))
        needed = batch_size - len(selected)
        if needed > 0 and new_list:
            selected.extend(random.sample(new_list, min(len(new_list), needed)))
        random.shuffle(selected)
        return selected


# =================================================================
# MODULE 5: UI 管理層
# =================================================================
class UIManager:
    def __init__(self, app):
        self.app = app

    def render_login(self):
        st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🔐 會員中心</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            tab1, tab2 = st.tabs(["登入", "註冊"])
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
            st.write(f"👤 {st.session_state.user_info.get('email', 'User')}")
            st.divider()

            st.subheader("🔑 API Key 設定")
            if "gemini_key" in st.session_state and st.session_state.gemini_key:
                st.success("✅ API Key 已載入")
                if st.button("🗑️ 更換 Key"):
                    st.session_state.gemini_key = None
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
            st.session_state.theme_config = (main_theme, sub_theme)

            st.divider()
            total = len(st.session_state.full_word_list)
            learned = len(st.session_state.learning_data)
            st.caption(f"📚 總單字: {total} | 📖 已學: {learned}")

    def render_main_stage(self):
        stage = st.session_state.stage

        if stage == "setup":
            st.markdown("<h1 style='text-align: center; color: #BB86FC;'>🧠 AI 智慧記憶 (Pro)</h1>",
                        unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 開始智慧抽詞 (5 Words)", use_container_width=True):
                    self.app.start_session()

        elif stage == "learning":
            self._render_learning_card()

        elif stage == "story":
            self._render_story_mode()

    def _render_learning_card(self):
        word = st.session_state.current_word
        dict_data = st.session_state.dict_info

        # 進度條
        total_session = len(st.session_state.session_queue) + (1 if word else 0)  # 簡易估算
        # 這裡為了簡單，直接用 queue 長度反推
        st.progress(max(0.0, min(1.0, (5 - len(st.session_state.session_queue)) / 5)))

        st.markdown(f"""
        <div class="word-card">
            <div class="big-word">{word}</div>
            <div class="phonetic">{dict_data.get('phonetic', '')}</div>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.show_answer:
            col_show, col_audio = st.columns([4, 1])
            with col_show:
                if st.button("👁️ 顯示答案與意思", type="primary", use_container_width=True):
                    st.session_state.show_answer = True
                    st.rerun()
            with col_audio:
                if st.button("🔊"): AIService.play_audio(word)
        else:
            AIService.play_audio(word)
            st.markdown(f"""
            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <div style="color: #B0B0B0;">📚 Definition：{dict_data.get('definition', '')}</div>
                <div style="color: #BB86FC; margin-top: 10px; font-style: italic;">📝 Example："{dict_data.get('example', '')}"</div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🧠 AI 幫我想個諧音/記憶法", use_container_width=True):
                AIService.generate_mnemonic(word)

            st.markdown("---")
            cols = st.columns(4)
            labels = [("❌ 忘記", 0), ("😓 困難", 3), ("😊 剛好", 4), ("⚡ 秒殺", 5)]
            for col, (label, score) in zip(cols, labels):
                with col:
                    if st.button(label, use_container_width=True):
                        self.app.process_review(word, score)

    def _render_story_mode(self):
        st.markdown("<h2 style='text-align: center; color: #BB86FC;'>🎉 練習完成！</h2>", unsafe_allow_html=True)
        unknowns = st.session_state.unknown_words
        st.info(f"本次弱點單字: {', '.join(unknowns) if unknowns else '無'}")

        if st.button("🪄 生成 AI 情境故事", use_container_width=True):
            theme, sub = st.session_state.get("theme_config", ("職場生活", "辦公室趣事"))
            target_words = unknowns if unknowns else st.session_state.session_queue_history
            AIService.generate_story(theme, sub, target_words)

        if st.button("🏠 回首頁"):
            st.session_state.stage = "setup"
            st.rerun()


# =================================================================
# MODULE 6: 主程式 (Controller)
# =================================================================
class VocabularyApp:
    def __init__(self):
        Config.load_css()
        self.fb_service = FirebaseService()
        self.ui = UIManager(self)
        self.init_state()

    def init_state(self):
        defaults = {
            "user_info": None,
            "learning_data": {},
            "full_word_list": [],
            "session_queue": [],
            "session_queue_history": [],
            "current_word": None,
            "unknown_words": [],
            "stage": "setup",
            "dict_info": {},
            "show_answer": False,
            "gemini_key": None
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

        # 使用快取載入單字
        if not st.session_state.full_word_list:
            st.session_state.full_word_list = load_static_word_list(Config.FULL_WORD_FILE)

    def handle_auth(self, email, password, is_login):
        with st.spinner("連線中..."):
            res = self.fb_service.auth_user(email, password, is_login)
            if "error" in res:
                st.error(f"❌ {res['error']['message']}")
            else:
                uid = res["localId"]
                st.session_state.user_info = {"email": res["email"], "uid": uid, "token": res["idToken"]}

                # 載入用戶資料
                data, key = self.fb_service.load_user_data(uid)
                st.session_state.learning_data = data or {}
                if key: st.session_state.gemini_key = key
                st.rerun()

    def start_session(self):
        if not st.session_state.full_word_list:
            st.error("單字庫未載入 (full-word.json)")
            return

        selected = SRSEngine.get_review_batch(st.session_state.learning_data, st.session_state.full_word_list)
        if not selected:
            st.warning("沒有單字可供學習")
            return

        st.session_state.session_queue = selected
        st.session_state.session_queue_history = selected.copy()
        st.session_state.unknown_words = []
        self.next_card()

    def next_card(self):
        st.session_state.show_answer = False
        if st.session_state.session_queue:
            word = st.session_state.session_queue.pop(0)
            st.session_state.current_word = word

            # 這裡呼叫 Service，Service 會呼叫 Cached Function，速度極快
            with st.spinner("載入中..."):
                st.session_state.dict_info = AIService.fetch_dictionary(word)

            st.session_state.stage = "learning"
        else:
            st.session_state.stage = "story"
        st.rerun()

    def process_review(self, word, score):
        # 1. 更新資料
        current_data = st.session_state.learning_data.get(word, {})
        new_data = SRSEngine.calculate_next_review(current_data, score)
        st.session_state.learning_data[word] = new_data

        # 2. 紀錄弱點
        if score == 0 and word not in st.session_state.unknown_words:
            st.session_state.unknown_words.append(word)

        # 3. 雲端同步 (若擔心頻繁寫入，也可改為結束 Session 才存)
        if st.session_state.user_info:
            self.fb_service.save_data(st.session_state.user_info['uid'], st.session_state.learning_data)

        # 4. 下一張
        self.next_card()

    def run(self):
        if not st.session_state.user_info:
            self.ui.render_login()
        else:
            self.ui.render_sidebar()
            self.ui.render_main_stage()


if __name__ == "__main__":
    app = VocabularyApp()
    app.run()
