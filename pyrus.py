import streamlit as st
import streamlit.components.v1 as components
import os

st.title("Страница с виджетом Pyrus")

widget_id = os.getenv("PYRUS_WIDGET_ID", "6aozIb7GzbJAVi-e4OjrH4hc4~T5vr3n476RGxvjwYYxk4mSt6bEr1Rb79lDvE0IWBSE5MkXR8Ec3mRyiovIO0jeIvC7dM8zt-j3rIMBxXeBc3Nebo~h0mQs8CqXQElBOirtog%3D%3D")

widget_html = f"""
<style>
    body {{ margin: 0; padding: 0; background-color: transparent; }}
</style>
<script
    type="text/javascript"
    src="https://pyrus.com/js/webwidget?id={widget_id}"
    async="true">
</script>
"""

# Отрисовываем виджет. 
# ВАЖНО: Укажите высоту и ширину, если кнопка должна быть видна.
# Если виджет должен быть в углу, лучше поместить его в st.sidebar или дать большой height.
components.html(widget_html, height=500)
