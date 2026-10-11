from typing import Any
import streamlit as st
import os
import json
import shutil
import time
from db_utils import verify_user_credentials

KB_FILE = "knowledge_base.json"
KB_BAK_FILE = "knowledge_base.json.bak"
IMAGES_DIR = "form_images"

os.makedirs(IMAGES_DIR, exist_ok=True)


def load_kb_data() -> dict[str, Any]:
    """Загружает базу знаний из файла JSON."""
    if os.path.exists(KB_FILE):
        try:
            with open(KB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            st.error(f"Ошибка чтения файла базы знаний: {e}")
            return {}
    return {}


def save_kb_data(data: dict[str, Any]) -> bool:
    """Сохраняет базу знаний в файл с созданием резервной копии."""
    try:
        if os.path.exists(KB_FILE):
            shutil.copy2(KB_FILE, KB_BAK_FILE)
        with open(KB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        from github_sync import sync_file_and_notify
        sync_file_and_notify(KB_FILE, "Обновление базы знаний через веб-панель")
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения базы знаний: {e}")
        return False


def get_available_images() -> list[str]:
    """Возвращает список доступных изображений в папке IMAGES_DIR."""
    if not os.path.exists(IMAGES_DIR):
        return []
    valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    files = [
        f"{IMAGES_DIR}/{f}"
        for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith(valid_exts)
    ]
    return sorted(files)


def analyze_kb(kb: dict[str, Any]) -> dict[str, Any]:
    """Анализирует целостность графа базы знаний."""
    all_nodes = set(kb.keys())
    broken_links: list[tuple[str, str, str]] = []
    referenced_nodes: set[str] = set()
    questions_count = 0
    solutions_count = 0
    empty_questions: list[str] = []
    missing_images: list[tuple[str, str]] = []

    for node_id, node_data in kb.items():
        if not isinstance(node_data, dict):
            continue
        if "solution" in node_data:
            solutions_count += 1
            img = node_data.get("image")
            if isinstance(img, str) and img and not os.path.exists(img):
                missing_images.append((node_id, img))
        else:
            questions_count += 1
            opts = node_data.get("options", {})
            if not isinstance(opts, dict) or not opts:
                empty_questions.append(node_id)
            else:
                for opt_text, target in opts.items():
                    referenced_nodes.add(str(target))
                    if str(target) not in all_nodes:
                        broken_links.append((node_id, str(opt_text), str(target)))

    # Поиск недостижимых узлов от 'start'
    reachable: set[str] = set()
    if "start" in all_nodes:
        queue = ["start"]
        reachable.add("start")
        while queue:
            curr = queue.pop(0)
            curr_node = kb.get(curr)
            if isinstance(curr_node, dict):
                curr_opts = curr_node.get("options", {})
                if isinstance(curr_opts, dict):
                    for target in curr_opts.values():
                        target_str = str(target)
                        if target_str in all_nodes and target_str not in reachable:
                            reachable.add(target_str)
                            queue.append(target_str)

    unreachable_nodes = list(all_nodes - reachable)

    return {
        "total": len(all_nodes),
        "questions": questions_count,
        "solutions": solutions_count,
        "broken_links": broken_links,
        "unreachable": unreachable_nodes,
        "empty_questions": empty_questions,
        "missing_images": missing_images,
    }


# --- ПРОВЕРКА АВТОРИЗАЦИИ ---
if not st.session_state.get("admin_logged_in", False):
    st.title("🔐 Редактирование базы знаний")
    st.info("Для управления экспертной системой необходимо войти с правами администратора.")
    with st.form("kb_auth_form"):
        login_inp = st.text_input("Логин")
        pass_inp = st.text_input("Пароль", type="password")
        if st.form_submit_button("Войти", use_container_width=True, type="primary"):
            user_data = verify_user_credentials(login_inp, pass_inp)
            if user_data:
                st.session_state["admin_logged_in"] = True
                st.session_state["admin_user"] = user_data["login"]
                st.success("Успешный вход!")
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
    st.stop()


# --- ОСНОВНОЙ ИНТЕРФЕЙС РЕДАКТОРА ---
st.title("🧠 База знаний экспертной системы")
from github_sync import get_github_config
gh_cfg = get_github_config()
if gh_cfg["token"]:
    st.caption(f"🟢 **Автосинхронизация с GitHub активна** (репозиторий `{gh_cfg['repo']}`, ветка `{gh_cfg['branch']}`)")
else:
    st.caption("ℹ️ Синхронизация с GitHub отключена (для автокоммитов добавьте `[github]` токен в `secrets.toml`).")
st.caption("Удобное управление деревом вопросов и рекомендаций поддержки Мировых судей РТ")

kb_data = load_kb_data()
if not kb_data:
    st.warning("База знаний пуста или повреждена. Инициализируем стартовый узел.")
    kb_data = {
        "start": {
            "question": "Какого рода проблема возникла?",
            "options": {}
        }
    }
    save_kb_data(kb_data)

tab_editor, tab_analysis, tab_simulator, tab_backup = st.tabs([
    "✏️ Редактор шагов",
    "🔍 Диагностика и карта",
    "🧪 Интерактивный тест",
    "💾 Резервные копии и JSON"
])


# ==========================================
# ВКЛАДКА 1: РЕДАКТОР ШАГОВ
# ==========================================
with tab_editor:
    all_node_keys = list(kb_data.keys())

    def get_node_label(k: str) -> str:
        item = kb_data.get(k, {})
        if isinstance(item, dict) and "solution" in item:
            sol_raw = item.get("solution")
            preview = str(sol_raw or "").replace("\n", " ")[:45]
            return f"💡 [Решение] {k}: {preview}..."
        elif isinstance(item, dict):
            q_raw = item.get("question")
            q_text = str(q_raw or "")[:45]
            return f"❓ [Вопрос] {k}: {q_text}..."
        return k

    # Панель выбора/создания
    col_act1, col_act2 = st.columns([3, 1])
    with col_act1:
        selected_node = st.selectbox(
            "Выберите шаг для редактирования:",
            options=all_node_keys,
            format_func=get_node_label,
            key="kb_selected_node_selector"
        )
    with col_act2:
        st.write("")
        st.write("")
        create_new_btn = st.button("➕ Новый шаг", use_container_width=True, type="secondary")

    if "creating_new_node" not in st.session_state:
        st.session_state["creating_new_node"] = False

    if create_new_btn:
        st.session_state["creating_new_node"] = True

    # Блок создания нового шага
    if st.session_state.get("creating_new_node", False):
        with st.container(border=True):
            st.subheader("➕ Создание нового шага")
            col_id, col_type = st.columns([2, 2])
            with col_id:
                new_id = st.text_input(
                    "Уникальный идентификатор (ID на латинице, например: internet_error):",
                    key="new_node_id_inp"
                ).strip()
            with col_type:
                new_type = st.radio(
                    "Тип шага:",
                    ["❓ Вопрос с вариантами", "💡 Конечное решение"],
                    horizontal=True,
                    key="new_node_type_rad"
                )

            col_btn_create, col_btn_cancel = st.columns([1, 1])
            with col_btn_create:
                if st.button("Создать шаг", type="primary", use_container_width=True):
                    if not new_id:
                        st.error("Укажите идентификатор шага (ID)!")
                    elif new_id in kb_data:
                        st.error(f"Шаг с ID '{new_id}' уже существует!")
                    else:
                        if new_type.startswith("❓"):
                            kb_data[new_id] = {
                                "question": "Новый вопрос?",
                                "options": {}
                            }
                        else:
                            kb_data[new_id] = {
                                "solution": "Описание решения проблемы..."
                            }
                        if save_kb_data(kb_data):
                            st.session_state["creating_new_node"] = False
                            st.success(f"Шаг '{new_id}' успешно создан!")
                            time.sleep(0.5)
                            st.rerun()
            with col_btn_cancel:
                if st.button("Отмена", use_container_width=True):
                    st.session_state["creating_new_node"] = False
                    st.rerun()

    # Редактирование выбранного узла
    if selected_node and selected_node in kb_data:
        node_info = kb_data[selected_node]
        if isinstance(node_info, dict):
            is_solution = "solution" in node_info

            st.markdown("---")
            header_col, del_col = st.columns([3, 1])
            with header_col:
                st.subheader(f"Настройка шага: `{selected_node}`")
            with del_col:
                if selected_node == "start":
                    st.caption("🔒 Корневой узел 'start' нельзя удалить")
                else:
                    if st.button("🗑 Удалить шаг", type="secondary", use_container_width=True):
                        # Проверяем, ссылается ли кто-то на этот шаг
                        referrers: list[str] = []
                        for k, v in kb_data.items():
                            if isinstance(v, dict):
                                opts = v.get("options")
                                if isinstance(opts, dict) and selected_node in opts.values():
                                    referrers.append(k)

                        if referrers:
                            st.error(f"Нельзя удалить! На этот шаг ссылаются следующие узлы: {', '.join(referrers)}. Сначала измените переходы в них.")
                        else:
                            del kb_data[selected_node]
                            if save_kb_data(kb_data):
                                st.success(f"Шаг '{selected_node}' удален!")
                                time.sleep(0.6)
                                st.rerun()

            # Переключатель типа узла
            current_type_idx = 1 if is_solution else 0
            node_type_selected = st.radio(
                "Тип данного шага:",
                ["❓ Вопрос с вариантами ответа (разветвление)", "💡 Конечное решение (рекомендация)"],
                index=current_type_idx,
                key=f"type_toggle_{selected_node}"
            )
            should_be_solution = node_type_selected.startswith("💡")

            if should_be_solution != is_solution:
                if st.button("🔄 Применить смену типа узла"):
                    if should_be_solution:
                        # Преобразуем вопрос в решение
                        kb_data[selected_node] = {
                            "solution": node_info.get("question", "Инструкция по решению проблемы.")
                        }
                    else:
                        # Преобразуем решение в вопрос
                        kb_data[selected_node] = {
                            "question": node_info.get("solution", "Выберите вариант проблемы:")[:100],
                            "options": {}
                        }
                    if save_kb_data(kb_data):
                        st.success("Тип шага изменен!")
                        st.rerun()

            st.markdown("")

            # 1. Форма для узла-ВОПРОСА
            if not should_be_solution:
                q_val = str(node_info.get("question") or "")
                new_question = st.text_input("Текст вопроса пользователю:", value=q_val, key=f"q_text_{selected_node}")

                st.markdown("#### Варианты ответов (кнопки перехода):")
                options = node_info.get("options", {})

                # Редактирование существующих вариантов
                updated_options: dict[str, str] = {}
                deleted_opt = None

                if isinstance(options, dict) and options:
                    for idx, (opt_text, target_node) in enumerate(options.items()):
                        with st.container(border=True):
                            c_opt_text, c_opt_target, c_opt_del = st.columns([3, 2, 1])
                            with c_opt_text:
                                new_opt_text = st.text_input(
                                    "Текст кнопки:",
                                    value=str(opt_text),
                                    key=f"opt_txt_{selected_node}_{idx}"
                                )
                            with c_opt_target:
                                # Список доступных целевых узлов
                                target_options = [k for k in all_node_keys if k != selected_node]
                                target_index = target_options.index(target_node) if target_node in target_options else 0
                                new_target = st.selectbox(
                                    "Переход к шагу:",
                                    options=target_options,
                                    index=target_index,
                                    format_func=lambda k: f"{k} ({'💡' if 'solution' in kb_data.get(k, {}) else '❓'})",
                                    key=f"opt_tgt_{selected_node}_{idx}"
                                )
                            with c_opt_del:
                                st.write("")
                                st.write("")
                                if st.button("❌", key=f"del_opt_{selected_node}_{idx}", help="Удалить вариант"):
                                    deleted_opt = opt_text

                            if deleted_opt != opt_text and new_opt_text:
                                updated_options[new_opt_text] = new_target
                else:
                    st.info("Пока нет ни одного варианта ответа. Добавьте хотя бы один вариант ниже.")

                # Добавление нового варианта ответа
                st.markdown("##### ➕ Добавить новый вариант:")
                c_add_txt, c_add_tgt, c_add_btn = st.columns([3, 2, 1])
                with c_add_txt:
                    add_btn_txt = st.text_input("Название кнопки", placeholder="Например: Да / Ошибка пароля", key=f"add_txt_{selected_node}")
                with c_add_tgt:
                    avail_targets = [k for k in all_node_keys if k != selected_node]
                    add_btn_tgt = st.selectbox(
                        "Куда ведет:",
                        options=avail_targets,
                        format_func=lambda k: f"{k} ({'💡' if 'solution' in kb_data.get(k, {}) else '❓'})",
                        key=f"add_tgt_{selected_node}"
                    )
                with c_add_btn:
                    st.write("")
                    st.write("")
                    if st.button("Добавить", key=f"btn_add_opt_{selected_node}", use_container_width=True):
                        if add_btn_txt:
                            updated_options[add_btn_txt] = add_btn_tgt
                            node_info["question"] = new_question
                            node_info["options"] = updated_options
                            kb_data[selected_node] = node_info
                            if save_kb_data(kb_data):
                                st.success(f"Вариант '{add_btn_txt}' добавлен!")
                                time.sleep(0.4)
                                st.rerun()
                        else:
                            st.warning("Введите текст кнопки")

                # Кнопка сохранения изменений вопроса
                st.markdown("---")
                if st.button("💾 Сохранить изменения вопроса", type="primary", use_container_width=True, key=f"save_q_{selected_node}"):
                    node_info["question"] = new_question
                    if not deleted_opt:
                        node_info["options"] = updated_options
                    kb_data[selected_node] = node_info
                    if save_kb_data(kb_data):
                        st.success("Шаг успешно обновлен!")
                        time.sleep(0.5)
                        st.rerun()

            # 2. Форма для узла-РЕШЕНИЯ
            else:
                sol_val = str(node_info.get("solution") or "")
                new_solution = st.text_area(
                    "Текст инструкции / решения (поддерживается Markdown форматирование):",
                    value=sol_val,
                    height=220,
                    key=f"sol_text_{selected_node}"
                )

                st.markdown("#### Прикрепленное изображение:")
                col_img_select, col_img_upload = st.columns([1, 1])

                current_img = str(node_info.get("image") or "")
                available_images = ["(Без изображения)"] + get_available_images()

                cur_img_idx = 0
                if current_img and current_img in available_images:
                    cur_img_idx = available_images.index(current_img)

                with col_img_select:
                    selected_img = st.selectbox(
                        "Выбрать из доступных файлов:",
                        options=available_images,
                        index=cur_img_idx,
                        key=f"img_select_{selected_node}"
                    )

                with col_img_upload:
                    uploaded_img = st.file_uploader(
                        "Загрузить новую картинку:",
                        type=["png", "jpg", "jpeg", "webp"],
                        key=f"uploader_{selected_node}"
                    )
                    if uploaded_img is not None:
                        dest_path = f"{IMAGES_DIR}/{uploaded_img.name}"
                        with open(dest_path, "wb") as f:
                            f.write(uploaded_img.getbuffer())
                        from github_sync import sync_file_and_notify
                        sync_file_and_notify(dest_path, f"Загрузка изображения {uploaded_img.name}")
                        st.success(f"Файл сохранен: {dest_path}")
                        selected_img = dest_path

                # Предварительный просмотр карточки решения
                st.markdown("#### 👁 Предварительный просмотр решения:")
                with st.container(border=True):
                    st.success("### 💡 Рекомендация:")
                    st.markdown(new_solution)
                    preview_img_path = selected_img if selected_img != "(Без изображения)" else None
                    if preview_img_path and os.path.exists(preview_img_path):
                        st.image(preview_img_path, use_container_width=True)

                st.markdown("---")
                if st.button("💾 Сохранить решение", type="primary", use_container_width=True, key=f"save_sol_{selected_node}"):
                    node_info["solution"] = new_solution
                    if selected_img and selected_img != "(Без изображения)":
                        node_info["image"] = selected_img
                    else:
                        node_info.pop("image", None)

                    kb_data[selected_node] = node_info
                    if save_kb_data(kb_data):
                        st.success("Решение успешно сохранено!")
                        time.sleep(0.5)
                        st.rerun()


# ==========================================
# ВКЛАДКА 2: ДИАГНОСТИКА И КАРТА
# ==========================================
with tab_analysis:
    analysis = analyze_kb(kb_data)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Всего узлов", analysis["total"])
    m2.metric("❓ Вопросов", analysis["questions"])
    m3.metric("💡 Решений", analysis["solutions"])
    issues_total = (
        len(analysis["broken_links"])
        + len(analysis["unreachable"])
        + len(analysis["empty_questions"])
        + len(analysis["missing_images"])
    )
    m4.metric("⚠️ Замечаний", issues_total, delta=None if issues_total == 0 else f"-{issues_total}")

    st.markdown("---")
    st.subheader("🛠 Проверка целостности")

    if issues_total == 0:
        st.success("✅ База знаний в отличном состоянии! Все ссылки валидны, изолированных шагов нет.")
    else:
        if analysis["broken_links"]:
            st.error("🚨 **Обнаружены битые переходы (ссылки на несуществующие узлы):**")
            for src, btn_text, tgt in analysis["broken_links"]:
                st.write(f"- В узле `{src}` кнопка **'{btn_text}'** ссылается на несуществующий узел `{tgt}`")

        if analysis["unreachable"]:
            st.warning("⚠️ **Изолированные узлы (невозможно попасть из 'start'):**")
            st.write(", ".join([f"`{n}`" for n in analysis["unreachable"]]))

        if analysis["empty_questions"]:
            st.warning("⚠️ **Вопросы без вариантов ответов:**")
            st.write(", ".join([f"`{n}`" for n in analysis["empty_questions"]]))

        if analysis["missing_images"]:
            st.warning("⚠️ **Отсутствующие файлы картинок:**")
            for n_id, img_p in analysis["missing_images"]:
                st.write(f"- В узле `{n_id}` указан файл `{img_p}`, но он не найден на диске")

    st.markdown("---")
    st.subheader("📋 Полный перечень шагов базы")

    search_query = st.text_input("Поиск по ID или тексту:", placeholder="Введите слово для фильтрации...")
    filter_type = st.radio("Фильтр по типу:", ["Все", "Только вопросы ❓", "Только решения 💡"], horizontal=True)

    for n_id, n_data in kb_data.items():
        if not isinstance(n_data, dict):
            continue
        is_sol = "solution" in n_data
        if filter_type == "Только вопросы ❓" and is_sol:
            continue
        if filter_type == "Только решения 💡" and not is_sol:
            continue

        item_repr = f"{n_id} {n_data.get('question', '')} {n_data.get('solution', '')}".lower()
        if search_query and search_query.lower() not in item_repr:
            continue

        label_prefix = '💡 [Решение]' if is_sol else '❓ [Вопрос]'
        label_text = str(n_data.get('question', n_data.get('solution', '')) or '')[:65]
        with st.expander(f"{label_prefix} `{n_id}`: {label_text}..."):
            st.caption(f"ID узла: `{n_id}`")
            if is_sol:
                cur_sol = str(n_data.get("solution") or "")
                inline_sol = st.text_area(
                    "Текст рекомендации / решения:",
                    value=cur_sol,
                    height=140,
                    key=f"inline_sol_{n_id}"
                )
                img_path = n_data.get("image")
                if isinstance(img_path, str) and img_path:
                    st.caption(f"🖼 Картинка: `{img_path}`")
                    if os.path.exists(img_path):
                        st.image(img_path, width=240)

                col_s1, col_s2 = st.columns([1, 2])
                with col_s1:
                    if st.button("💾 Сохранить решение", key=f"btn_inline_save_sol_{n_id}", type="primary", use_container_width=True):
                        n_data["solution"] = inline_sol
                        kb_data[n_id] = n_data
                        if save_kb_data(kb_data):
                            st.success("Решение успешно обновлено!")
                            time.sleep(0.4)
                            st.rerun()
                with col_s2:
                    st.caption("Для изменения картинок или удаления шага используйте вкладку «✏️ Редактор шагов».")

            else:
                cur_q = str(n_data.get("question") or "")
                inline_q = st.text_input(
                    "Текст вопроса:",
                    value=cur_q,
                    key=f"inline_q_{n_id}"
                )

                # Показ и быстрое редактирование текстов вариантов ответов
                opts = n_data.get("options", {})
                inline_opts: dict[str, str] = {}
                if isinstance(opts, dict) and opts:
                    st.markdown("**Варианты ответов:**")
                    for o_idx, (opt_text, target_id) in enumerate(opts.items()):
                        c_otxt, c_otgt = st.columns([3, 2])
                        with c_otxt:
                            new_o_text = st.text_input(
                                f"Кнопка #{o_idx+1}:",
                                value=opt_text,
                                key=f"inline_opt_txt_{n_id}_{o_idx}"
                            )
                        with c_otgt:
                            st.text_input(
                                f"Переход к:",
                                value=target_id,
                                disabled=True,
                                key=f"inline_opt_tgt_disp_{n_id}_{o_idx}"
                            )
                        if new_o_text:
                            inline_opts[new_o_text] = target_id

                col_q1, col_q2 = st.columns([1, 2])
                with col_q1:
                    if st.button("💾 Сохранить вопрос", key=f"btn_inline_save_q_{n_id}", type="primary", use_container_width=True):
                        n_data["question"] = inline_q
                        if isinstance(opts, dict) and opts:
                            n_data["options"] = inline_opts
                        kb_data[n_id] = n_data
                        if save_kb_data(kb_data):
                            st.success("Вопрос успешно обновлен!")
                            time.sleep(0.4)
                            st.rerun()
                with col_q2:
                    st.caption("Для добавления новых веток или изменения целевых шагов используйте вкладку «✏️ Редактор шагов».")


# ==========================================
# ВКЛАДКА 3: ИНТЕРАКТИВНЫЙ ТЕСТ (СИМУЛЯТОР)
# ==========================================
with tab_simulator:
    st.subheader("🧪 Тестирование цепочки экспертной системы")
    st.caption("Пройдите по шагам базы знаний так же, как это видит пользователь.")

    if "sim_history" not in st.session_state:
        st.session_state.sim_history = []
    if "sim_current" not in st.session_state:
        st.session_state.sim_current = "start"

    col_sim_back, col_sim_reset = st.columns([1, 1])
    with col_sim_back:
        if st.button("⬅️ Шаг назад", use_container_width=True, key="sim_back_btn"):
            if st.session_state.sim_history:
                st.session_state.sim_current = st.session_state.sim_history.pop()
                st.rerun()
            else:
                st.warning("Вы в начальной точке.")
    with col_sim_reset:
        if st.button("🔄 Сбросить к началу ('start')", use_container_width=True, key="sim_reset_btn"):
            st.session_state.sim_history = []
            st.session_state.sim_current = "start"
            st.rerun()

    sim_node_id = str(st.session_state.sim_current)
    sim_node = kb_data.get(sim_node_id)

    st.markdown(f"**Текущий шаг:** `{sim_node_id}`")

    if not isinstance(sim_node, dict):
        st.error(f"Узел `{sim_node_id}` не найден в базе!")
    else:
        with st.container(border=True):
            if "solution" in sim_node:
                st.success("### 💡 Рекомендация:")
                st.markdown(str(sim_node.get("solution") or ""))
                sim_img = sim_node.get("image")
                if isinstance(sim_img, str) and sim_img and os.path.exists(sim_img):
                    st.image(sim_img, use_container_width=True)
                st.info("Это конечное решение (тупик ветки).")
            else:
                st.markdown(f"### {sim_node.get('question', 'Выберите вариант:')}")
                options = sim_node.get("options", {})
                if isinstance(options, dict) and options:
                    for opt_text, next_id in options.items():
                        if st.button(f"{opt_text} ➔ [{next_id}]", key=f"sim_opt_{opt_text}", use_container_width=True):
                            st.session_state.sim_history.append(sim_node_id)
                            st.session_state.sim_current = next_id
                            st.rerun()
                else:
                    st.warning("У этого вопроса нет вариантов выбора!")


# ==========================================
# ВКЛАДКА 4: РЕЗЕРВНЫЕ КОПИИ И JSON
# ==========================================
with tab_backup:
    st.subheader("💾 Экспорт и импорт базы знаний")

    col_exp, col_imp = st.columns([1, 1])
    with col_exp:
        st.markdown("#### Скачать текущую базу:")
        kb_json_str = json.dumps(kb_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 Скачать knowledge_base.json",
            data=kb_json_str.encode("utf-8"),
            file_name="knowledge_base.json",
            mime="application/json",
            use_container_width=True
        )

        if os.path.exists(KB_BAK_FILE):
            st.markdown("#### Восстановление из авто-бэкапа:")
            st.caption(f"Файл бэкапа `{KB_BAK_FILE}` существует.")
            if st.button("⏪ Восстановить предыдущую версию (.bak)", use_container_width=True):
                try:
                    shutil.copy2(KB_BAK_FILE, KB_FILE)
                    st.success("База успешно восстановлена из бэкапа!")
                    time.sleep(0.6)
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка восстановления: {e}")

    with col_imp:
        st.markdown("#### Загрузить базу из файла:")
        uploaded_kb = st.file_uploader("Выберите JSON-файл базы:", type=["json"], key="upload_kb_file")
        if uploaded_kb is not None:
            try:
                content = json.load(uploaded_kb)
                if isinstance(content, dict) and "start" in content:
                    if st.button("Применить загруженную базу", type="primary", use_container_width=True):
                        if save_kb_data(content):
                            st.success("База знаний успешно обновлена из файла!")
                            time.sleep(0.6)
                            st.rerun()
                else:
                    st.error("Неверная структура JSON: должен быть словарь с обязательным узлом 'start'.")
            except Exception as e:
                st.error(f"Ошибка синтаксиса JSON: {e}")

    st.markdown("---")
    st.subheader("🌐 Синхронизация с GitHub")
    from github_sync import get_github_config
    cfg = get_github_config()
    if cfg["token"]:
        st.success(f"Токен GitHub подключен. Репозиторий: `{cfg['repo']}`, ветка: `{cfg['branch']}`.")
        if st.button("🔍 Проверить подключение к GitHub API", key="btn_test_gh_conn"):
            import requests
            test_url = f"https://api.github.com/repos/{cfg['repo']}"
            t_headers = {
                "Authorization": f"Bearer {cfg['token']}",
                "Accept": "application/vnd.github+json"
            }
            try:
                t_resp = requests.get(test_url, headers=t_headers, timeout=8)
                if t_resp.status_code == 200:
                    st.success("✅ Связь с репозиторием GitHub установлена! Автокоммиты работают.")
                elif t_resp.status_code == 401:
                    st.error("❌ Ошибка 401: Токен недействителен или просрочен.")
                elif t_resp.status_code == 404:
                    st.error(f"❌ Ошибка 404: Репозиторий `{cfg['repo']}` не найден или у токена нет прав доступа.")
                else:
                    st.warning(f"Код ответа GitHub: {t_resp.status_code} - {t_resp.text}")
            except Exception as e:
                st.error(f"Ошибка подключения: {e}")
    else:
        st.info("💡 **Как включить автоматическое сохранение изменений в GitHub:**")
        st.markdown("""
        В файле `.streamlit/secrets.toml` (на компьютере) или в **Settings → Secrets** (на Streamlit Cloud) добавьте:
        ```toml
        [github]
        token = "ghp_ваш_токен"
        repo = "ai-garifullin/mirsudfree"
        branch = "main"
        ```
        """)
