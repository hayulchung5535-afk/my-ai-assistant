import streamlit as st
import json
import os
import base64
import pytz
from io import BytesIO
from PIL import Image
from datetime import datetime
from google import genai
from tavily import TavilyClient
from streamlit_paste_button import paste_image_button

# =========================================================
# 💡 [설정 및 타이틀 변경 구역]
# =========================================================
PAGE_TITLE = "내 전용 AI 비서"
PAGE_ICON = "⚡"
APP_TITLE = "⚡ 스마트 AI 어시스턴트"
# =========================================================

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")

SESSIONS_DIR = "chat_sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# 1. secrets.toml에서 API 키 로드
GEMINI_API_KEYS = st.secrets.get("GEMINI_API_KEYS", [])
if not GEMINI_API_KEYS:
    single_key = st.secrets.get("GEMINI_API_KEY", "")
    if single_key:
        GEMINI_API_KEYS = [single_key]

TAVILY_API_KEY = st.secrets.get("TAVILY_API_KEY", "")

# 2. 세션 및 파일 저장 관리 함수
def get_all_sessions():
    files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SESSIONS_DIR, x)), reverse=True)
    return files

def load_session(session_id):
    file_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
    return []

def save_session(session_id, messages):
    file_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def get_session_title(messages):
    if not isinstance(messages, list):
        return "새로운 대화"
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                clean_title = content.replace("\n", " ").strip()
                return clean_title[:20] + "..." if len(clean_title) > 20 else clean_title
    return "새로운 대화"

# 이미지 크기 조절 (최대 길이 1024px 제한)
def resize_image(pil_img, max_size=1024):
    img = pil_img.copy()
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return img

# 이미지 PIL 객체를 Base64 문자열로 변환
def image_to_base64(pil_img):
    buffered = BytesIO()
    if pil_img.mode in ("RGBA", "P"):
        pil_img = pil_img.convert("RGB")
    pil_img.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# Base64 문자열을 PIL 객체로 변환
def base64_to_image(b64_str):
    image_data = base64.b64decode(b64_str)
    return Image.open(BytesIO(image_data))

# 3. Tavily 실시간 검색 함수
def search_tavily(query):
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        response = tavily.search(query=query, search_depth="basic", max_results=5)
        results = response.get("results", [])
        
        if not results:
            return "검색 결과가 없습니다."
        
        context = "Tavily 실시간 웹 검색 결과:\n\n"
        for idx, item in enumerate(results, 1):
            title = item.get("title", "")
            snippet = item.get("content", "")
            url = item.get("url", "")
            context += f"[{idx}] {title}\n내용: {snippet}\n출처: {url}\n\n"
        return context
    except Exception as e:
        return f"[Tavily 검색 오류: {e}]"

# 4. 세션 상태 초기화
if "current_session_id" not in st.session_state:
    all_sessions = get_all_sessions()
    if all_sessions:
        st.session_state.current_session_id = all_sessions[0].replace(".json", "")
    else:
        st.session_state.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

if "messages" not in st.session_state:
    st.session_state.messages = load_session(st.session_state.current_session_id)

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# 5. 사이드바 UI (대화 세션 목록 관리)
with st.sidebar:
    if st.button("➕ 새 대화 시작", use_container_width=True, type="primary"):
        new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.session_state.uploader_key += 1
        st.rerun()

    st.markdown("### 최근 대화 목록")
    
    all_session_files = get_all_sessions()
    for s_file in all_session_files:
        s_id = s_file.replace(".json", "")
        s_messages = load_session(s_id)
        s_title = get_session_title(s_messages)
        
        is_current = (s_id == st.session_state.current_session_id)
        button_label = f"💬 {s_title}" if not is_current else f"👉 {s_title}"
        
        if st.button(button_label, key=s_id, use_container_width=True):
            st.session_state.current_session_id = s_id
            st.session_state.messages = load_session(s_id)
            st.session_state.uploader_key += 1
            st.rerun()

    st.divider()
    
    if st.button("🗑️ 현재 대화 삭제", use_container_width=True):
        file_path = os.path.join(SESSIONS_DIR, f"{st.session_state.current_session_id}.json")
        if os.path.exists(file_path):
            os.remove(file_path)
        
        remaining = get_all_sessions()
        if remaining:
            st.session_state.current_session_id = remaining[0].replace(".json", "")
            st.session_state.messages = load_session(st.session_state.current_session_id)
        else:
            new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.session_state.current_session_id = new_id
            st.session_state.messages = []
        st.session_state.uploader_key += 1
        st.rerun()

# 6. 메인 화면 메시지 출력
st.title(APP_TITLE)

for msg in st.session_state.messages:
    if isinstance(msg, dict) and "role" in msg and "content" in msg:
        with st.chat_message(msg["role"]):
            if "image" in msg and msg["image"]:
                try:
                    img_obj = base64_to_image(msg["image"])
                    st.image(img_obj, width=350)
                except Exception:
                    pass
            st.markdown(msg["content"])

# 7. 답변 생성 필요 여부 확인
is_generating = (
    bool(st.session_state.messages) and 
    st.session_state.messages[-1]["role"] == "user"
)

current_img = None

# AI가 대화 중(답변 생성 중)이 아닐 때만 업로드 창 출력
if not is_generating:
    upload_container = st.container()
    with upload_container:
        st.write("---")
        col1, col2 = st.columns([1, 1])

        with col1:
            paste_result = paste_image_button(
                label="📋 클립보드 이미지 붙여넣기 (캡처 후 클릭)",
                background_color="#2b2b2b",
                hover_background_color="#3b3b3b",
                key=f"paste_{st.session_state.uploader_key}"
            )
            if paste_result.image_data is not None:
                current_img = paste_result.image_data

        with col2:
            uploaded_file = st.file_uploader(
                "📁 파일 직접 선택", 
                type=["png", "jpg", "jpeg"],
                key=f"upload_{st.session_state.uploader_key}"
            )
            if uploaded_file is not None:
                current_img = Image.open(uploaded_file)

        if current_img is not None:
            current_img = resize_image(current_img)
            st.image(current_img, caption="전송할 이미지 (자동 리사이즈 적용됨)", width=250)

# 8. 사용자 입력 처리
if user_input := st.chat_input("질문이나 지시사항을 입력하세요..."):
    if not GEMINI_API_KEYS:
        st.error("GEMINI_API_KEYS 설정이 필요합니다. .streamlit/secrets.toml 파일을 확인해 주세요.")
        st.stop()

    user_msg_data = {"role": "user", "content": user_input, "image": None}

    if current_img is not None:
        user_msg_data["image"] = image_to_base64(current_img)

    st.session_state.messages.append(user_msg_data)
    save_session(st.session_state.current_session_id, st.session_state.messages)
    
    # 전송 후 키 변경 (업로드 영역 초기화)
    st.session_state.uploader_key += 1
    st.rerun()



# 9. 답변 생성 로직
if is_generating:
    last_user_msg = st.session_state.messages[-1]
    last_user_input = last_user_msg["content"]
    last_user_image_b64 = last_user_msg.get("image")

    with st.chat_message("assistant"):
        # 1. KST 시각을 구한 뒤 무조건 문자열 변수에 담음
        kst = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분 (%A)")

        search_keywords = [
            "검색", "최신", "찾아", "뉴스", "정보", "알려", "구글",
            "몇", "개", "얼마", "언제", "누구", "어디", "현재", "오늘", "어제",
            "순위", "기록", "성적", "결과", "일정", "홈런", "경기", "날씨", "KBO"
        ]
        need_search = any(kw in last_user_input for kw in search_keywords)

        search_data = ""
        if need_search:
            if not TAVILY_API_KEY:
                st.warning("⚠️ TAVILY_API_KEY가 설정되지 않아 웹 검색을 건너뜁니다.")
            else:
                with st.spinner("웹 정보 실시간 검색 중..."):
                    search_query = f"{now_str} 기준 {last_user_input}"
                    search_data = search_tavily(search_query)

        # 2. 이전 대화 내역 구성
        recent_history = ""
        if len(st.session_state.messages) > 1:
            recent_history = "--- [이전 대화 기록] ---\n"
            for msg in st.session_state.messages[:-1]:
                if isinstance(msg, dict):
                    role_name = "사용자" if msg.get("role") == "user" else "AI"
                    recent_history += f"{role_name}: {msg.get('content', '')}\n"
            recent_history += "-----------------------\n\n"

        # 3. [핵심 수정] contents_payload 내부에 KST 시각을 직접 강제로 주입
        final_user_prompt = (
            f"📌 [현재 실제 대한민국 KST 시각]: {now_str}\n"
            f"📌 [시간 기준 지침]: 시간, 날짜, 오늘, 지금 관련 모든 판단은 반드시 위 '현재 실제 대한민국 KST 시각'({now_str})을 기준으로만 답변하세요.\n\n"
            f"{recent_history}"
        )

        if search_data:
            final_user_prompt += f"[웹 검색 결과]\n{search_data}\n\n"

        final_user_prompt += f"[사용자 질문]\n{last_user_input}"

        contents_payload = [final_user_prompt]
        if last_user_image_b64:
            img_to_send = base64_to_image(last_user_image_b64)
            contents_payload.append(img_to_send)

        # 4. system_instruction에도 한번 더 시간 기준 및 환각 방지 강제
        system_instruction_text = (
            f"너는 친절하고 정확한 AI 어시스턴트이다.\n"
            f"현재 시각은 대한민국 표준시(KST)로 [{now_str}] 이다.\n"
            f"이전 대화 기록의 시각에 얽매이지 말고, 무조건 위에 명시된 현재 시각[{now_str}]을 기준으로 답변해라.\n"
            f"검색 결과에 없는 사실관계나 스포츠 결과는 절대 지어내지 말 것."
        )

        answer_text = None
        
        with st.spinner("분석 및 답변을 생성하는 중..."):
            for idx, key in enumerate(GEMINI_API_KEYS):
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=contents_payload,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction_text
                        )
                    )
                    answer_text = response.text
                    break

                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        if idx < len(GEMINI_API_KEYS) - 1:
                            continue
                        else:
                            st.error("⚠️ 등록된 모든 Gemini API 키의 한도가 초과되었습니다.")
                    else:
                        st.error(f"Gemini API 호출 중 오류가 발생했습니다: {e}")
                        break

        if answer_text:
            st.session_state.messages.append({"role": "assistant", "content": answer_text, "image": None})
            save_session(st.session_state.current_session_id, st.session_state.messages)
            st.rerun()