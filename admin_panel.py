from __future__ import annotations
import streamlit as st
import streamlit.components.v1 as components
import time
import json
import os
import hmac
import hashlib
from typing import Optional
from urllib.parse import unquote
from dotenv import load_dotenv

from db_utils import verify_user_credentials, get_user_by_login, log_action

load_dotenv()

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "mirsud_crm_secret_session_key_2026")

def sign_auth_cookie(login_val: str) -> str:
    """Формирует криптографически подписанную строку сессии: login:timestamp:signature."""
    timestamp = str(int(time.time()))
    payload = f"{login_val}:{timestamp}"
    signature = hmac.new(SESSION_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_auth_cookie(cookie_val: str, max_age_days: int = 30) -> Optional[str]:
    """Проверяет подпись HMAC и срок действия куки. Возвращает login при успехе, иначе None."""
    if not cookie_val:
        return None
    cleaned = cookie_val.strip('"\t\r\n ')
    parts = cleaned.split(":")
    if len(parts) != 3:
        return None
    login, ts_str, signature = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None

    now = time.time()
    if now - ts > max_age_days * 86400 or ts > now + 300:
        return None

    payload = f"{login}:{ts_str}"
    expected_sig = hmac.new(SESSION_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(signature, expected_sig):
        return login
    return None

def set_auth_cookie(login_val: str):
    """Устанавливает куки авторизации на 30 дней."""
    signed_token = sign_auth_cookie(login_val)
    token_safe = json.dumps(signed_token)

    js_code = f"""
        <script>
            var d = new Date();
            d.setTime(d.getTime() + (30*24*60*60*1000)); // 30 дней
            var expires = "; expires=" + d.toUTCString() + "; path=/; SameSite=Lax";
            document.cookie = "mirsud_admin_user=" + encodeURIComponent({token_safe}) + expires;
            document.cookie = "mirsud_user=" + encodeURIComponent({token_safe}) + expires;
        </script>
    """
    components.html(js_code, height=0)

def clear_auth_cookie():
    """Сбрасывает куки авторизации."""
    js_code = """
        <script>
            document.cookie = "mirsud_admin_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            document.cookie = "mirsud_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        </script>
    """
    components.html(js_code, height=0)

try:
    st.set_page_config(page_title="Админ-панель", layout="wide", page_icon="⚙️")
except Exception:
    pass

# Флаг для подавления автоматического входа сразу после нажатия кнопки "Выйти"
if "admin_logout_submitted" not in st.session_state:
    st.session_state["admin_logout_submitted"] = False

# --- ПРОВЕРКА АВТОРИЗАЦИИ ЧЕРЕЗ КУКИ (ДО ФОРМИРОВАНИЯ СТРАНИЦ) ---
if st.session_state.get("admin_logout_submitted", False):
    st.session_state["admin_logged_in"] = False
    st.session_state.pop("admin_user", None)
    st.session_state.pop("admin_role", None)
else:
    if not st.session_state.get("admin_logged_in", False):
        if hasattr(st, "context") and hasattr(st.context, "cookies"):
            raw_cookie = st.context.cookies.get("mirsud_admin_user") or st.context.cookies.get("mirsud_user")
            if raw_cookie:
                decoded_cookie = unquote(raw_cookie)
                valid_login = verify_auth_cookie(decoded_cookie)

                if valid_login:
                    user_db = get_user_by_login(valid_login)
                    if user_db:
                        st.session_state["admin_logged_in"] = True
                        st.session_state["admin_user"] = user_db.get("login", valid_login)
                        st.session_state["admin_role"] = user_db.get("role", "")
                        st.session_state["cloud_files_logged_in"] = True
                        st.session_state["cloud_user"] = user_db

is_authenticated = st.session_state.get("admin_logged_in", False)
user_role = st.session_state.get("admin_role", "")

# Базовые общедоступные страницы (видны всем без авторизации)
pages = [
    st.Page("croc.py", title="Генератор VBS", icon="🐊", default=True),
    st.Page("diagnostic_act.py", title="Генератор акта диагностики оборудования", icon="📝"),
]

# Для авторизованных пользователей:
# - Администраторам добавляется только Облако
# - Инженеру БД отображаются ВСЕ функции
if is_authenticated:
    # Облачные файлы для всех вошедших пользователей (админов и инженера БД)
    pages.append(st.Page("cloud_files.py", title="Облачные файлы", icon="☁️"))

    # Полный доступ ко всем модулям админ-панели только для Инженера БД
    if user_role in ["engineer_bd", "Инженер_БД"]:
        pages.extend([
            st.Page("salary.py", title="Калькулятор зарплаты", icon="💰"),
            st.Page("manage_users.py", title="Управление пользователями", icon="👥"),
            st.Page("edit_board.py", title="Редактирование доски", icon="✏️"),
            st.Page("edit_kb.py", title="База знаний", icon="🧠"),
        ])

pg = st.navigation(pages)

# Блок авторизации в боковой панели (единый вход для всех)
with st.sidebar:
    st.divider()
    if is_authenticated:
        admin_user = st.session_state.get("admin_user", "Пользователь")
        if user_role in ["engineer_bd", "Инженер_БД"]:
            role_label = "🛠️ Инженер БД"

        elif user_role == "admin":
            role_label = "👑 Администратор"
        elif user_role == "dispatcher":
            role_label = "🎧 Диспетчер"
        else:
            role_label = "👤 Пользователь"
        st.success(f"{role_label}: **{admin_user}**")

        if st.button("Выйти", use_container_width=True, type="secondary", key="admin_logout_btn"):
            st.session_state["admin_logout_submitted"] = True
            st.session_state["admin_logged_in"] = False
            user_to_log = st.session_state.pop("admin_user", "Пользователь")
            st.session_state.pop("admin_role", None)
            st.session_state["cloud_files_logged_in"] = False
            st.session_state.pop("cloud_user", None)
            log_action(user_to_log, "LOGOUT", "Выход из панели")
            clear_auth_cookie()
            time.sleep(0.4)
            st.rerun()
    else:
        now = time.time()
        lockout_until = st.session_state.get("admin_lockout_until", 0)
        if now < lockout_until:
            st.warning(f"⏳ Слишком много попыток. Подождите {int(lockout_until - now)} сек.")
        else:
            with st.expander("🔐 Вход в систему", expanded=True):
                with st.form("admin_panel_auth_form"):
                    login_inp = st.text_input("Логин", key="admin_auth_login")
                    pass_inp = st.text_input("Пароль", type="password", key="admin_auth_pass")
                    submit_btn = st.form_submit_button("Войти", use_container_width=True, type="primary")
                    if submit_btn:
                        if not login_inp or not pass_inp:
                            st.warning("Введите логин и пароль")
                        else:
                            try:
                                user_data = verify_user_credentials(login_inp, pass_inp)
                            except Exception as e:
                                user_data = None
                                st.error("Ошибка проверки учетных данных")

                            if user_data:
                                st.session_state["admin_logout_submitted"] = False
                                st.session_state["admin_fail_count"] = 0
                                st.session_state["admin_lockout_until"] = 0
                                st.session_state["admin_logged_in"] = True
                                st.session_state["admin_user"] = user_data.get("login", login_inp)
                                st.session_state["admin_role"] = user_data.get("role", "")
                                st.session_state["cloud_files_logged_in"] = True
                                st.session_state["cloud_user"] = user_data
                                set_auth_cookie(user_data["login"])
                                log_action(user_data["login"], "LOGIN", f"Вход в панель ({user_data.get('role', '')})")
                                st.success("Успешный вход!")

                                time.sleep(0.5)
                                st.rerun()
                            else:
                                fails = st.session_state.get("admin_fail_count", 0) + 1
                                st.session_state["admin_fail_count"] = fails
                                if fails >= 5:
                                    st.session_state["admin_lockout_until"] = time.time() + 30
                                    st.error("Превышен лимит попыток. Вход заблокирован на 30 секунд.")
                                else:
                                    time.sleep(1)
                                    st.error(f"Неверный логин или пароль (осталось попыток: {5 - fails})")

pg.run()


