import streamlit as st
import urllib.request
import urllib.parse
import json
from datetime import datetime
import os
from db_utils import verify_user_credentials

YANDEX_DISK_PUBLIC_URL = os.getenv("CLOUD_LINK", "https://disk.yandex.ru/d/t8813cr2Yl5DZg")
API_BASE_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"

def format_size(bytes_val):
    if bytes_val is None or bytes_val == 0:
        return "—"
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} ПБ"

def get_file_icon(name, mime_type=""):
    ext = name.lower().split('.')[-1] if '.' in name else ''
    if ext in ['zip', 'rar', '7z', 'tar', 'gz']:
        return "📦"
    elif ext in ['cmd', 'bat', 'vbs', 'ps1', 'sh', 'py', 'sql', 'js', 'json']:
        return "⚙️"
    elif ext in ['txt', 'log', 'md', 'cfg', 'ini']:
        return "📄"
    elif ext in ['doc', 'docx', 'rtf', 'odt']:
        return "📝"
    elif ext in ['xls', 'xlsx', 'csv']:
        return "📊"
    elif ext in ['pdf']:
        return "📑"
    elif ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg']:
        return "🖼️"
    elif ext in ['mp3', 'wav', 'ogg']:
        return "🎵"
    elif ext in ['mp4', 'mkv', 'avi', 'mov']:
        return "🎬"
    return "📎"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_disk_resources(public_key: str, path: str = "/"):
    params = {
        'public_key': public_key,
        'path': path,
        'limit': 1000,
        'sort': 'name'
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{API_BASE_URL}?{query_string}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode('utf-8'))
        return data

@st.cache_data(ttl=300, show_spinner=False)
def download_file_content(file_url: str):
    req = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

def cloud_files_page():
    # Проверка авторизации
    is_authenticated = st.session_state.get("admin_logged_in", False) or st.session_state.get("cloud_files_logged_in", False)

    if not is_authenticated:
        st.title("☁️ Облачные файлы")
        st.warning("⚠️ Для доступа к облачным файлам необходимо войти в систему. Пожалуйста, выполните вход через форму на боковой панели.")
        return

    st.title("☁️ Облачные файлы")
    st.caption(f"Источник: [Яндекс.Диск]({YANDEX_DISK_PUBLIC_URL})")

    # Инициализация состояния текущего пути
    if 'cloud_current_path' not in st.session_state:
        st.session_state.cloud_current_path = "/"
    if 'preview_file' not in st.session_state:
        st.session_state.preview_file = None

    # Верхняя панель: навигация, кнопка выхода и обновление
    user_info = st.session_state.get("cloud_user") or {}
    user_login = user_info.get("login") or user_info.get("username") or st.session_state.get("admin_user", "Пользователь")

    col_nav, col_user, col_refresh, col_open = st.columns([4.5, 2.5, 1.5, 2.5])
    
    with col_user:
        st.write(f"👤 **{user_login}**")
        if st.button("🚪 Выйти", key="btn_logout_user"):
            st.session_state["cloud_files_logged_in"] = False
            st.session_state["admin_logged_in"] = False
            st.session_state.pop("admin_user", None)
            st.session_state.pop("admin_role", None)
            st.session_state["cloud_user"] = None
            st.session_state["admin_logout_submitted"] = True
            st.rerun()


    with col_refresh:
        if st.button("🔄 Обновить", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with col_open:
        st.link_button("🌐 Открыть на Яндекс.Диске", YANDEX_DISK_PUBLIC_URL, use_container_width=True)

    # Хлебные крошки (breadcrumbs)
    current_path = st.session_state.cloud_current_path.strip("/")
    path_parts = [p for p in current_path.split("/") if p]
    
    crumbs_cols = st.columns([1] * (len(path_parts) + 2) + [10])
    with crumbs_cols[0]:
        if st.button("🏠 Корень", key="crumb_root"):
            st.session_state.cloud_current_path = "/"
            st.session_state.preview_file = None
            st.rerun()

    accumulated_path = ""
    for idx, part in enumerate(path_parts):
        accumulated_path += f"/{part}"
        part_path = accumulated_path
        with crumbs_cols[idx + 1]:
            if st.button(f"📁 {part}", key=f"crumb_{idx}_{part}"):
                st.session_state.cloud_current_path = part_path
                st.session_state.preview_file = None
                st.rerun()

    st.divider()

    # Загрузка данных
    try:
        with st.spinner("Загрузка содержимого папки..."):
            data = fetch_disk_resources(YANDEX_DISK_PUBLIC_URL, st.session_state.cloud_current_path)
    except Exception:
        st.error("Не удалось получить данные с хранилища. Попробуйте обновить страницу.")
        if st.button("⬅️ Вернуться в корень"):
            st.session_state.cloud_current_path = "/"
            st.session_state.preview_file = None
            st.rerun()
        return

    items = data.get('_embedded', {}).get('items', [])
    
    # Кнопка возврата на уровень выше (если не в корне)
    if st.session_state.cloud_current_path != "/":
        parent_path = "/" + "/".join(path_parts[:-1])
        if not parent_path.startswith("/"):
            parent_path = "/" + parent_path
        if st.button("⬅️ На уровень выше", key="btn_parent_dir"):
            st.session_state.cloud_current_path = parent_path
            st.session_state.preview_file = None
            st.rerun()

    # Поиск / фильтрация
    search_query = st.text_input("🔍 Поиск по названию в текущей папке", "").strip().lower()
    if search_query:
        items = [i for i in items if search_query in i.get('name', '').lower()]

    dirs = [i for i in items if i.get('type') == 'dir']
    files = [i for i in items if i.get('type') == 'file']

    # Метрики
    total_size = sum(f.get('size', 0) for f in files if f.get('size'))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Всего элементов", len(items))
    m2.metric("Папок", len(dirs))
    m3.metric("Файлов", len(files))
    m4.metric("Общий размер файлов", format_size(total_size))

    st.write("")

    # --- ПАПКИ ---
    if dirs:
        st.subheader("📁 Папки")
        dir_cols_count = min(3, len(dirs))
        dir_cols = st.columns(dir_cols_count)
        
        for idx, d in enumerate(dirs):
            col = dir_cols[idx % dir_cols_count]
            with col:
                d_name = d.get('name')
                d_path = d.get('path')
                if st.button(f"📁 {d_name}", key=f"dir_btn_{idx}_{d_name}", use_container_width=True):
                    st.session_state.cloud_current_path = d_path
                    st.session_state.preview_file = None
                    st.rerun()

    # --- ФАЙЛЫ ---
    if files:
        st.subheader("📄 Файлы")
        
        for idx, f in enumerate(files):
            f_name = f.get('name', 'Без имени')
            f_size = f.get('size', 0)
            f_modified = f.get('modified', '')
            f_download_url = f.get('file', '')
            icon = get_file_icon(f_name)
            
            # Форматирование даты
            mod_str = ""
            if f_modified:
                try:
                    dt = datetime.fromisoformat(f_modified.replace("Z", "+00:00"))
                    mod_str = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    mod_str = str(f_modified)[:16]

            with st.container():
                c_icon_name, c_size, c_date, c_action1, c_action2 = st.columns([5, 1.5, 2, 1.5, 1.5])
                
                with c_icon_name:
                    st.markdown(f"**{icon} {f_name}**")
                with c_size:
                    st.caption(format_size(f_size))
                with c_date:
                    st.caption(mod_str)
                with c_action1:
                    # Кнопка предпросмотра
                    ext = f_name.lower().split('.')[-1] if '.' in f_name else ''
                    previewable = ext in ['txt', 'cmd', 'bat', 'vbs', 'ps1', 'sh', 'py', 'sql', 'js', 'json', 'log', 'md', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg']
                    if previewable:
                        if st.button("👁️ Просмотр", key=f"prev_btn_{idx}_{f_name}", use_container_width=True):
                            st.session_state.preview_file = f
                            st.rerun()
                with c_action2:
                    if f_download_url:
                        st.link_button("📥 Скачать", f_download_url, use_container_width=True)
                
                st.divider()

    if not dirs and not files:
        st.info("В этой папке нет файлов или папок, соответствующих условию.")

    # --- БЛОК ПРЕДПРОСМОТРА ---
    if st.session_state.preview_file:
        selected_file = st.session_state.preview_file
        f_name = selected_file.get('name', '')
        f_url = selected_file.get('file', '')
        ext = f_name.lower().split('.')[-1] if '.' in f_name else ''

        st.subheader(f"👁️ Предпросмотр: {f_name}")
        
        col_close, _ = st.columns([2, 8])
        with col_close:
            if st.button("❌ Закрыть предпросмотр"):
                st.session_state.preview_file = None
                st.rerun()

        if f_url:
            try:
                with st.spinner("Загрузка содержимого файла..."):
                    file_bytes = download_file_content(f_url)
                
                # Текстовые файлы и скрипты
                if ext in ['txt', 'cmd', 'bat', 'vbs', 'ps1', 'sh', 'py', 'sql', 'js', 'json', 'log', 'md', 'ini', 'cfg']:
                    # Пробуем декодировать в UTF-8 или CP1251
                    try:
                        text_content = file_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            text_content = file_bytes.decode('cp1251')
                        except:
                            text_content = file_bytes.decode('utf-8', errors='replace')
                    
                    lang_map = {
                        'py': 'python',
                        'sql': 'sql',
                        'json': 'json',
                        'js': 'javascript',
                        'sh': 'bash',
                        'cmd': 'batch',
                        'bat': 'batch',
                        'vbs': 'vbscript',
                        'ps1': 'powershell',
                        'md': 'markdown'
                    }
                    lang = lang_map.get(ext, 'text')
                    st.code(text_content, language=lang)
                
                # Изображения
                elif ext in ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg']:
                    st.image(file_bytes, caption=f_name, use_container_width=True)
                
            except Exception:
                st.error("Не удалось отобразить файл.")

cloud_files_page()
