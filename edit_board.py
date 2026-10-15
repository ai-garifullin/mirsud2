import streamlit as st
import os
import json
import time

CONFIG_FILE = "info.json"

def load_main_info():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("info_text", "Текст не задан")
        except Exception as e:
            return f"Ошибка чтения конфига: {e}"
    return "Информационный текст не найден."

def save_main_info(new_text):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"info_text": new_text}, f, ensure_ascii=False, indent=4)
        from github_sync import sync_file_and_notify
        sync_file_and_notify(CONFIG_FILE, "Обновление текста инфодоски через панель управления")
        return True
    except Exception as e:
        st.error(f"Ошибка записи: {e}")
        return False

from db_utils import verify_user_credentials

if not st.session_state.get("admin_logged_in", False):
    st.title("🔐 Редактирование информационной доски")
    st.info("Для редактирования объявлений необходимо войти с правами администратора.")
    with st.form("edit_board_auth_form"):
        login_inp = st.text_input("Логин")
        pass_inp = st.text_input("Пароль", type="password")
        submit_btn = st.form_submit_button("Войти", use_container_width=True, type="primary")
        if submit_btn:
            user_data = verify_user_credentials(login_inp, pass_inp)
            if user_data and user_data.get("role") == "admin":
                st.session_state["admin_logged_in"] = True
                st.session_state["admin_user"] = user_data["login"]
                st.success("Успешный вход!")
                st.rerun()
            elif user_data:
                st.error("Доступ запрещен: требуются права администратора.")
            else:
                st.error("Неверный логин или пароль")
    st.stop()

st.title("✏️ Редактирование информационной доски")
from github_sync import get_github_config
gh_cfg = get_github_config()
if gh_cfg["token"]:
    st.caption(f"🟢 **Автосинхронизация с GitHub активна** (репозиторий `{gh_cfg['repo']}`, ветка `{gh_cfg['branch']}`)")
else:
    st.caption("ℹ️ Синхронизация с GitHub отключена (для автокоммитов добавьте `[github]` токен в `secrets.toml`).")
st.markdown("Изменения, сохраненные здесь, сразу отображаются на главной информационной доске.")

tab_edit, tab_preview = st.tabs(["📝 Редактор объявления", "👁 Предварительный просмотр"])

with tab_edit:
    current_txt = load_main_info()
    new_txt = st.text_area(
        "Текст объявления (поддерживаются Markdown и HTML):",
        value=current_txt,
        height=280
    )
    
    col_save, col_reset = st.columns([1, 4])
    with col_save:
        if st.button("💾 Сохранить изменения", type="primary", use_container_width=True):
            if save_main_info(new_txt):
                st.success("Объявление успешно обновлено!")
                time.sleep(0.8)
                st.rerun()
    with col_reset:
        if st.button("🔄 Сбросить к текущему"):
            st.rerun()

with tab_preview:
    st.subheader("Вид для пользователей:")
    preview_content = load_main_info().strip()
    st.markdown(f'<div style="background-color: #EFF6FF; border-left: 5px solid #3B82F6; border-radius: 8px; padding: 20px; margin-bottom: 20px;">\n\n{preview_content}\n\n</div>', unsafe_allow_html=True)
