import streamlit as st
import time
from db_utils import verify_user_credentials

try:
    st.set_page_config(page_title="Админ-панель", layout="wide", page_icon="⚙️")
except Exception:
    pass

is_authenticated = st.session_state.get("admin_logged_in", False)

# Базовые общедоступные страницы
pages = [
    st.Page("croc.py", title="Генератор VBS", icon="🐊", default=True),
    st.Page("diagnostic_act.py", title="Генератор акта диагностики оборудования", icon="📝"),
]

# Закрытые страницы, доступные только после авторизации
if is_authenticated:
    pages.append(st.Page("salary.py", title="Калькулятор зарплаты", icon="💰"))

pages.append(st.Page("cloud_files.py", title="Облачные файлы", icon="☁️"))

if is_authenticated:
    pages.extend([
        st.Page("edit_board.py", title="Редактирование доски", icon="✏️"),
        st.Page("edit_kb.py", title="База знаний", icon="🧠"),
    ])

pg = st.navigation(pages)

# Блок авторизации администратора в боковой панели
with st.sidebar:
    st.divider()
    if is_authenticated:
        admin_user = st.session_state.get("admin_user", "Администратор")
        st.success(f"👤 Авторизован: **{admin_user}**")
        if st.button("Выйти", use_container_width=True, type="secondary", key="admin_logout_btn"):
            st.session_state["admin_logged_in"] = False
            st.session_state.pop("admin_user", None)
            st.session_state["cloud_files_logged_in"] = False
            st.session_state.pop("cloud_user", None)
            st.rerun()
    else:
        now = time.time()
        lockout_until = st.session_state.get("admin_lockout_until", 0)
        if now < lockout_until:
            st.warning(f"⏳ Слишком много попыток. Подождите {int(lockout_until - now)} сек.")
        else:
            with st.expander("🔐 Вход администратора", expanded=True):
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

                            if user_data and user_data.get("role") == "admin":
                                st.session_state["admin_fail_count"] = 0
                                st.session_state["admin_lockout_until"] = 0
                                st.session_state["admin_logged_in"] = True
                                st.session_state["admin_user"] = user_data.get("login", login_inp)
                                st.success("Успешный вход!")
                                st.rerun()
                            elif user_data:
                                fails = st.session_state.get("admin_fail_count", 0) + 1
                                st.session_state["admin_fail_count"] = fails
                                st.error("Доступ запрещен: требуются права администратора.")
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

