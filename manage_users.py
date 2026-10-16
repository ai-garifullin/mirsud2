import hashlib
import getpass
import re
import time
import pandas as pd
import streamlit as st
import os
from dotenv import load_dotenv

from db_utils import (
    get_db_connection,
    get_all_system_users,
    create_system_user,
    update_system_user_role_and_tg,
    update_system_user_password,
    delete_system_user,
    get_recent_user_logs,
    verify_user_credentials,
    log_action,
)

load_dotenv()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БЕЗОПАСНОСТИ И ХЭШИРОВАНИЯ ---

def hash_password(password: str) -> str:
    """Хэширует пароль с использованием SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def is_streamlit_context() -> bool:
    """Определяет, выполняется ли скрипт в контексте Streamlit runtime."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False

# Справочник ролей с описанием и визуальным оформлением
ROLE_METADATA = {
    "engineer_bd": {
        "title": "🛠️ Инженер БД",
        "badge_color": "#8B5CF6",
        "description": "Полный доступ ко всей системе и исключительное право входа в скрытую админ-панель (управление пользователями, доской, базой знаний, калькулятором)."
    },
    "Инженер_БД": {
        "title": "🛠️ Инженер БД",
        "badge_color": "#8B5CF6",
        "description": "Полный доступ ко всей системе и исключительное право входа в скрытую админ-панель (управление пользователями, доской, базой знаний, калькулятором)."
    },
    "admin": {
        "title": "👑 Администратор",
        "badge_color": "#EF4444",
        "description": "Административный доступ к CRM (просмотр и редактирование любых заявок, аналитика, диспетчеризация). Без доступа к скрытой админ-панели."
    },
    "dispatcher": {
        "title": "🎧 Диспетчер",
        "badge_color": "#F59E0B",
        "description": "Диспетчерский доступ: распределение заявок, назначение исполнителей, мониторинг очередей."
    },
    "user": {
        "title": "👤 Пользователь",
        "badge_color": "#3B82F6",
        "description": "Стандартный доступ: просмотр и выполнение назначенных заявок, работа с базой знаний."
    }
}


def get_role_badge(role: str) -> str:
    """Возвращает форматированный бейдж роли с иконкой."""
    meta = ROLE_METADATA.get(role)
    if meta:
        return meta["title"]
    return f"❓ {role}"

# --- ИНТЕРАКТИВНЫЙ КОНСОЛЬНЫЙ РЕЖИМ (CLI) ---

def add_user_cli():
    """Интерактивная консольная утилита для создания пользователя через терминал."""
    print("--- Создание нового пользователя CRM ---")
    login = input("Введите логин: ").strip()
    if not login:
        print("❌ Логин не может быть пустым!")
        return

    password = getpass.getpass("Введите пароль: ")
    password_confirm = getpass.getpass("Повторите пароль: ")

    if password != password_confirm:
        print("❌ Пароли не совпадают!")
        return

    print("Доступные роли: Инженер_БД, admin, dispatcher, user")
    role = input("Введите роль (например, dispatcher): ").strip()
    if role not in ROLE_METADATA:
        print("❌ Неверная роль!")
        return

    telegram_id = input("Введите Telegram ID (необязательно, Enter для пропуска): ").strip() or None
    password_hash = hash_password(password)

    success, msg = create_system_user(login, password_hash, role, telegram_id)
    if success:
        print(f"✅ Пользователь '{login}' с ролью '{role}' успешно создан!")
    else:
        print(f"❌ Ошибка: {msg}")

def add_user():
    """Алиас для обратной совместимости с оригинальным скриптом."""
    add_user_cli()

# --- ВЕБ-ИНТЕРФЕЙС STREAMLIT ---

def render_user_management_page():
    """Основной интерфейс управления пользователями в Streamlit."""

    # Проверка прав доступа: только для Инженера БД
    if not st.session_state.get("admin_logged_in", False) or st.session_state.get("admin_role") not in ["engineer_bd", "Инженер_БД"]:
        st.title("👥 Управление пользователями CRM")
        st.warning("⚠️ Доступ к этому разделу разрешен только Инженеру БД. Пожалуйста, выполните вход через форму на боковой панели.")
        st.stop()



    current_admin = st.session_state.get("admin_user", "admin")

    # Верхний колонтитул страницы
    col_title, col_user = st.columns([3, 1])
    with col_title:
        st.title("👥 Управление пользователями CRM")
        st.caption("Учетные записи сотрудников, назначение ролей и безопасность доступа")
    with col_user:
        st.write("")
        st.markdown(
            f"""
            <div style="background-color: #F3F4F6; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 14px; text-align: center;">
                <div style="font-size: 11px; color: #6B7280; text-transform: uppercase; font-weight: bold;">Текущий сеанс</div>
                <div style="font-size: 14px; font-weight: 600; color: #111827;">👤 {current_admin}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Загрузка пользователей из базы
    try:
        users = get_all_system_users()
    except Exception as e:
        users = []
        st.error(f"Ошибка при получении списка пользователей: {e}")

    total_count = len(users)
    db_eng_count = sum(1 for u in users if u.get("role") in ["engineer_bd", "Инженер_БД"])
    admin_count = sum(1 for u in users if u.get("role") == "admin")
    dispatcher_count = sum(1 for u in users if u.get("role") == "dispatcher")
    user_count = sum(1 for u in users if u.get("role") == "user")

    # Панель ключевых метрик
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Всего", total_count)
    m2.metric("🛠️ Инженеры БД", db_eng_count)
    m3.metric("👑 Администраторы", admin_count)
    m4.metric("🎧 Диспетчеры", dispatcher_count)
    m5.metric("👤 Пользователи", user_count)

    st.markdown("---")

    # Навигационные вкладки интерфейса
    tab_list, tab_create, tab_edit, tab_audit = st.tabs([
        "📋 Список пользователей",
        "➕ Добавить пользователя",
        "✏️ Редактирование и пароли",
        "📜 Журнал действий"
    ])

    # ==========================================
    # ВКЛАДКА 1: СПИСОК ПОЛЬЗОВАТЕЛЕЙ
    # ==========================================
    with tab_list:
        c_search, c_filter, c_refresh = st.columns([3, 2, 1])
        with c_search:
            search_query = st.text_input(
                "🔍 Поиск пользователя:",
                placeholder="Поиск по логину или Telegram ID...",
                key="mu_search_inp"
            ).strip().lower()
        with c_filter:
            role_filter = st.selectbox(
                "Фильтр по роли:",
                ["Все роли", "🛠️ Инженер БД", "👑 Администраторы (admin)", "🎧 Диспетчеры (dispatcher)", "👤 Пользователи (user)"],
                key="mu_role_filter"
            )
        with c_refresh:
            st.write("")
            st.write("")
            if st.button("🔄 Обновить", use_container_width=True, key="mu_refresh_btn"):
                st.rerun()

        # Фильтрация данных
        filtered_users = []
        for u in users:
            u_login = str(u.get("login") or "").lower()
            u_tg = str(u.get("telegram_id") or "").lower()
            u_role = str(u.get("role") or "").lower()

            # Фильтр по строке
            if search_query and (search_query not in u_login and search_query not in u_tg):
                continue

            # Фильтр по роли
            if role_filter == "🛠️ Инженер БД" and u_role not in ["engineer_bd", "инженер_бд"]:
                continue
            elif role_filter == "👑 Администраторы (admin)" and u_role != "admin":
                continue
            elif role_filter == "🎧 Диспетчеры (dispatcher)" and u_role != "dispatcher":
                continue
            elif role_filter == "👤 Пользователи (user)" and u_role != "user":
                continue

            filtered_users.append(u)


        if not filtered_users:
            if not users:
                st.warning("⚠️ В базе данных пока нет пользователей либо отсутствует связь с MySQL.")
            else:
                st.info("По заданным критериям поиска пользователи не найдены.")
        else:
            # Таблица пользователей
            table_data = []
            for u in filtered_users:
                role_val = u.get("role", "")
                is_curr = " (Вы)" if u.get("login") == current_admin else ""
                table_data.append({
                    "ID": u.get("user_id"),
                    "Логин": f"{u.get('login')}{is_curr}",
                    "Роль": get_role_badge(role_val),
                    "Telegram ID": u.get("telegram_id") or "—"
                })

            df_display = pd.DataFrame(table_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Экспорт в CSV (без паролей)
            csv_data = df_display.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 Скачать список пользователей (CSV)",
                data=csv_data,
                file_name=f"crm_system_users_{int(time.time())}.csv",
                mime="text/csv"
            )

    # ==========================================
    # ВКЛАДКА 2: СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ
    # ==========================================
    with tab_create:
        st.subheader("➕ Создание нового пользователя CRM")
        st.caption("Заполните форму для регистрации нового сотрудника в системе")

        with st.container(border=True):
            with st.form("create_new_user_form"):
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    new_login = st.text_input(
                        "Логин пользователя *",
                        placeholder="Например: ivanov_ii",
                        help="Латинские буквы, цифры, дефис и подчеркивание (от 3 до 50 символов)"
                    ).strip()

                    new_role = st.selectbox(
                        "Роль в системе *",
                        options=["user", "dispatcher", "admin", "engineer_bd"],
                        format_func=lambda r: f"{ROLE_METADATA[r]['title']} — {r}",
                        help="Определяет права доступа в CRM и панелях"
                    )

                with col_c2:
                    new_password = st.text_input(
                        "Пароль *",
                        type="password",
                        help="Минимум 4 символа"
                    )

                    new_password_confirm = st.text_input(
                        "Повторите пароль *",
                        type="password"
                    )

                new_telegram_id = st.text_input(
                    "Telegram ID (необязательно)",
                    placeholder="Например: 7299417632",
                    help="Числовой ID для отправки уведомлений ботом в Telegram"
                ).strip()

                st.markdown(
                    f"""
                    <div style="background-color: #F8FAFC; border-left: 4px solid #3B82F6; padding: 10px 14px; border-radius: 4px; font-size: 13px; margin: 10px 0 15px 0;">
                        <b>Описание выбранной роли:</b> {ROLE_METADATA[new_role]['description']}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                submit_create = st.form_submit_button(
                    "➕ Создать пользователя",
                    type="primary",
                    use_container_width=True
                )

                if submit_create:
                    # Валидация логина
                    if not new_login:
                        st.error("Пожалуйста, укажите логин!")
                    elif len(new_login) < 3:
                        st.error("Логин должен содержать не менее 3 символов!")
                    elif not re.match(r"^[a-zA-Z0-9_\.\-]+$", new_login):
                        st.error("Логин может содержать только латинские буквы, цифры, дефис и подчеркивание!")
                    elif any(str(u.get("login")).lower() == new_login.lower() for u in users):
                        st.error(f"Пользователь с логином '{new_login}' уже существует!")
                    # Валидация пароля
                    elif not new_password:
                        st.error("Пожалуйста, введите пароль!")
                    elif len(new_password) < 4:
                        st.error("Пароль должен содержать минимум 4 символа!")
                    elif new_password != new_password_confirm:
                        st.error("Пароли не совпадают!")
                    # Валидация Telegram ID
                    elif new_telegram_id and not new_telegram_id.lstrip("-").isdigit():
                        st.error("Telegram ID должен состоять только из цифр!")
                    else:
                        pwd_hash = hash_password(new_password)
                        tg_val = new_telegram_id if new_telegram_id else None
                        success, message = create_system_user(new_login, pwd_hash, new_role, tg_val)

                        if success:
                            log_action(
                                current_admin,
                                "USER_CREATE",
                                f"Создан пользователь '{new_login}' (роль: {new_role}, tg: {tg_val or 'нет'})"
                            )
                            st.success(f"✅ Пользователь '{new_login}' успешно создан!")
                            time.sleep(0.6)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")

    # ==========================================
    # ВКЛАДКА 3: РЕДАКТИРОВАНИЕ И ПАРОЛИ
    # ==========================================
    with tab_edit:
        st.subheader("✏️ Редактирование учетной записи")

        if not users:
            st.warning("В базе нет пользователей для редактирования.")
        else:
            # Выбор пользователя
            user_options = {u["user_id"]: u for u in users}

            def format_user_label(uid):
                u = user_options[uid]
                is_self = " (Вы)" if u["login"] == current_admin else ""
                return f"[ID: {uid}] {u['login']} ({u['role']}){is_self}"

            # Сохранение выбранного пользователя в session_state
            selected_uid = st.selectbox(
                "Выберите пользователя для управления:",
                options=list(user_options.keys()),
                format_func=format_user_label,
                key="mu_selected_user_box"
            )

            target_user = user_options[selected_uid]
            target_login = target_user["login"]
            target_role = target_user["role"]
            target_tg = str(target_user.get("telegram_id") or "")

            is_editing_self = (target_login == current_admin)

            col_edit_data, col_edit_pwd = st.columns(2)

            # БЛОК 1: Изменение роли и Telegram ID
            with col_edit_data:
                with st.container(border=True):
                    st.markdown("#### 👤 Основные параметры")

                    st.text_input("Логин (не изменяется)", value=target_login, disabled=True)

                    role_keys = ["user", "dispatcher", "admin", "engineer_bd"]
                    role_idx = role_keys.index(target_role) if target_role in role_keys else (role_keys.index("engineer_bd") if target_role == "Инженер_БД" else 0)

                    new_role_val = st.selectbox(
                        "Роль пользователя:",
                        options=role_keys,
                        index=role_idx,
                        format_func=lambda r: f"{ROLE_METADATA[r]['title']}",
                        key=f"edit_role_{selected_uid}"
                    )

                    new_tg_val = st.text_input(
                        "Telegram ID:",
                        value=target_tg,
                        placeholder="Например: 7299417632",
                        key=f"edit_tg_{selected_uid}"
                    ).strip()

                    if st.button("💾 Сохранить параметры", type="primary", use_container_width=True, key=f"btn_save_data_{selected_uid}"):
                        # Защита от снятия прав Инженера БД с себя
                        if is_editing_self and target_role in ["engineer_bd", "Инженер_БД"] and new_role_val not in ["engineer_bd", "Инженер_БД"]:
                            st.error("Вы не можете снять с себя роль Инженера БД!")
                        # Защита от удаления/понижения последнего Инженера БД
                        elif target_role in ["engineer_bd", "Инженер_БД"] and new_role_val not in ["engineer_bd", "Инженер_БД"] and db_eng_count <= 1:
                            st.error("Нельзя понизить роль последнего Инженера БД в системе!")
                        elif new_tg_val and not new_tg_val.lstrip("-").isdigit():
                            st.error("Telegram ID должен состоять только из цифр!")
                        else:
                            tg_to_save = new_tg_val if new_tg_val else None
                            success, msg = update_system_user_role_and_tg(selected_uid, new_role_val, tg_to_save)
                            if success:
                                log_action(
                                    current_admin,
                                    "USER_UPDATE",
                                    f"Обновлен пользователь '{target_login}' (ID {selected_uid}): роль '{new_role_val}', tg: {tg_to_save or 'нет'}"
                                )
                                st.success("✅ Параметры пользователя успешно обновлены!")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")

            # БЛОК 2: Смена пароля
            with col_edit_pwd:
                with st.container(border=True):
                    st.markdown("#### 🔑 Смена пароля")
                    new_pwd_1 = st.text_input(
                        "Новый пароль:",
                        type="password",
                        key=f"new_pwd_1_{selected_uid}"
                    )
                    new_pwd_2 = st.text_input(
                        "Повторите новый пароль:",
                        type="password",
                        key=f"new_pwd_2_{selected_uid}"
                    )

                    if st.button("🔑 Обновить пароль", use_container_width=True, key=f"btn_save_pwd_{selected_uid}"):
                        if not new_pwd_1:
                            st.error("Введите новый пароль!")
                        elif len(new_pwd_1) < 4:
                            st.error("Пароль должен содержать минимум 4 символа!")
                        elif new_pwd_1 != new_pwd_2:
                            st.error("Введенные пароли не совпадают!")
                        else:
                            new_hash = hash_password(new_pwd_1)
                            success, msg = update_system_user_password(selected_uid, new_hash)
                            if success:
                                log_action(
                                    current_admin,
                                    "USER_PASSWORD_CHANGE",
                                    f"Изменен пароль для пользователя '{target_login}' (ID {selected_uid})"
                                )
                                st.success(f"✅ Пароль для '{target_login}' успешно изменен!")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")

            # БЛОК 3: Удаление пользователя (Опасная зона)
            st.markdown("---")
            with st.container(border=True):
                st.markdown("#### 🗑️ Опасная зона: Удаление пользователя")
                st.caption(
                    "Удаление учетной записи приведет к безвозвратной потере доступа сотрудника к системе."
                )

                if is_editing_self:
                    st.warning("🔒 Вы не можете удалить собственную учетную запись, под которой сейчас авторизованы.")
                elif target_role in ["engineer_bd", "Инженер_БД"] and db_eng_count <= 1:
                    st.warning("🔒 Нельзя удалить единственного Инженера БД в системе.")
                else:
                    confirm_del = st.checkbox(
                        f"Я подтверждаю, что хочу безвозвратно удалить учетную запись '{target_login}' (ID: {selected_uid})",
                        key=f"chk_confirm_del_{selected_uid}"
                    )

                    col_del_btn, _ = st.columns([2, 3])
                    with col_del_btn:
                        if st.button("🗑️ Удалить пользователя", type="secondary", disabled=not confirm_del, use_container_width=True, key=f"btn_del_{selected_uid}"):
                            success, msg = delete_system_user(selected_uid)
                            if success:
                                log_action(
                                    current_admin,
                                    "USER_DELETE",
                                    f"Удален пользователь '{target_login}' (ID {selected_uid})"
                                )
                                st.success(f"✅ Пользователь '{target_login}' успешно удален!")
                                time.sleep(0.6)
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")

    # ==========================================
    # ВКЛАДКА 4: ЖУРНАЛ АУДИТА ДЕЙСТВИЙ
    # ==========================================
    with tab_audit:
        st.subheader("📜 Журнал действий с пользователями")
        st.caption("История создания, изменения ролей, смены паролей и удаления учетных записей")

        try:
            logs = get_recent_user_logs(limit=50)
        except Exception as e:
            logs = []
            st.error(f"Ошибка загрузки журнала: {e}")

        if not logs:
            st.info("В журнале пока нет записей о действиях с пользователями.")
        else:
            log_rows = []
            for item in logs:
                ts = item.get("timestamp")
                ts_str = ts.strftime("%d.%m.%Y %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "—")
                log_rows.append({
                    "ID": item.get("log_id"),
                    "Дата и время": ts_str,
                    "Инициатор": item.get("user_login") or "System",
                    "Действие": item.get("action_type") or "—",
                    "Подробности": item.get("details") or "—"
                })

            df_logs = pd.DataFrame(log_rows)
            st.dataframe(df_logs, use_container_width=True, hide_index=True)

# Точка входа: определяет запуск в Streamlit, из терминала или импорт как модуль
if is_streamlit_context():
    render_user_management_page()
elif __name__ == "__main__":
    add_user_cli()

