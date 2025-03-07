import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------
# Настройка подключения к Google Sheets
# ---------------------------
SHEET_ID = "1cbQtfwOR32_J7sIGuZnqmEINKrc1hqcAwAZVmOADPMA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
service = build("sheets", "v4", credentials=credentials)

# ---------------------------
# Функция для преобразования числовых колонок
# ---------------------------
def convert_numeric_columns(df, columns):
    """
    Преобразует строковые колонки в числовые, заменяя запятые на точки.
    """
    for col in columns:
        if col in df.columns:
            if df[col].dtype == object:  # Если колонка строковая
                df[col] = df[col].astype(str).str.replace(",", ".")
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ---------------------------
# Функция загрузки данных для отдела ФАСОВКА
# ---------------------------
@st.cache_data
def load_facovka_data(sheet_name):
    try:
        # Получаем данные из указанного листа
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=sheet_name
        ).execute()
        values = result.get("values", [])
        if not values:
            st.error("Помилка завантаження даних!")
            return pd.DataFrame()
        
        # Создаём DataFrame, пропуская первую строку с заголовками
        df = pd.DataFrame(values[1:], columns=values[0])
        df.columns = df.columns.str.strip()
        
        # Для листа ФАСОВКА столбцы:
        # A - Номер, B - Позиція (Entry Number), C - ПІБ, D - Тип обладнання, 
        # E - Час на операцію, F - Продуктивність за годину, G - Відсоток браку,
        # H - Кількість операторів, I - Тип продукту, J - Об'єм,
        # K - День, L - Місяць, M - Рік
    
        # Переименовываем столбец B если он есть
        if len(df.columns) > 1 and df.columns[1] not in ["ПІБ", "Позиція"]:
            df.rename(columns={df.columns[1]: "Позиція"}, inplace=True)
    
        # Создадим колонку "Дата" на основе K, L, M:
        if set(["День", "Місяць", "Рік"]).issubset(df.columns):
            try:
                df["Дата"] = pd.to_datetime(
                    df["День"].astype(str) + "." + df["Місяць"].astype(str) + "." + df["Рік"].astype(str),
                    format="%d.%m.%Y", errors="coerce"
                )
            except Exception as e:
                st.warning(f"Помилка при створенні колонки 'Дата': {str(e)}")
        
        # Преобразуем числовые колонки
        numeric_cols = ["Час на операцію", "Продуктивність за годину", "Відсоток браку", "Кількість операторів"]
        df = convert_numeric_columns(df, numeric_cols)
        
        # Конвертация объема если возможно (удалить "мл")
        if "Об'єм" in df.columns:
            try:
                # Улучшенное регулярное выражение для извлечения чисел, в том числе с десятичной точкой
                df["Об'єм_число"] = df["Об'єм"].str.extract(r'(\d+(?:\.\d+)?)').astype(float)
            except Exception:
                st.warning("Не вдалося розпізнати числові значення об'єму")
        
        return df
    except Exception as e:
        st.error(f"Помилка завантаження даних: {str(e)}")
        return pd.DataFrame()

# ---------------------------
# Функция для пресет-периода
# ---------------------------
def get_preset_dates(preset):
    today = date.today()
    if preset == "Цей тиждень":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif preset == "Минулий тиждень":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    elif preset == "Цей місяць":
        start = date(today.year, today.month, 1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = date(today.year, today.month, last_day)
    elif preset == "Минулий місяць":
        if today.month == 1:
            year = today.year - 1
            month = 12
        else:
            year = today.year
            month = today.month - 1
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)
    else:
        start, end = None, None
    return start, end

# ---------------------------
# Функция для подсчёта рабочих дней (понедельник-пятница)
# ---------------------------
def count_working_days(start, end):
    num = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            num += 1
        current += timedelta(days=1)
    return num

# ---------------------------
# Загрузка данных из листа "ФАСОВКА"
# ---------------------------
facovka_df = load_facovka_data("ФАСОВКА")

if facovka_df.empty:
    st.warning("Дані відсутні або не завантажені.")
else:
    # ---------------------------
    # Боковая панель: выбор типа отчета и фильтры
    # ---------------------------
    st.sidebar.title("Фільтри")
    
    report_type = st.sidebar.selectbox(
        "Тип звіту",
        options=[
            "Загальний огляд",
            "Аналіз ефективності операторів",
            "Завантаження обладнання",
            "Продуктивність виробництва",
            "Аналіз якості та браку"
        ]
    )
    
    # Фильтр по периоду - пресеты или пользовательский выбор
    preset_options = ["Цей тиждень", "Цей місяць", "Минулий тиждень", "Минулий місяць", "Користувацький"]
    selected_preset = st.sidebar.radio("Виберіть період", preset_options, index=0)
    
    if selected_preset != "Користувацький":
        start_date, end_date = get_preset_dates(selected_preset)
        st.sidebar.write(f"Період: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
    else:
        if pd.notnull(facovka_df["Дата"].min()) and pd.notnull(facovka_df["Дата"].max()):
            min_date = facovka_df["Дата"].min().date()
            max_date = facovka_df["Дата"].max().date()
        else:
            min_date = max_date = date.today()
        date_cols = st.sidebar.columns(2)
        start_date = date_cols[0].date_input("Начало періоду", min_date, min_value=min_date, max_value=max_date)
        end_date = date_cols[1].date_input("Кінець періоду", max_date, min_value=min_date, max_value=max_date)
    
    if start_date > end_date:
        st.sidebar.error("Начало періоду не може бути пізніше, ніж кінець.")
        filtered_df = pd.DataFrame()
    else:
        filtered_df = facovka_df[(facovka_df["Дата"] >= pd.to_datetime(start_date)) & 
                                (facovka_df["Дата"] <= pd.to_datetime(end_date))]
    
    # Дополнительные фильтры
    st.sidebar.markdown("---")
    
    # Фильтр по продукту (если имеются данные)
    unique_products = sorted(filtered_df["Тип продукту"].dropna().unique().tolist())
    if unique_products:
        all_products = ["Усі"] + unique_products
        selected_products = st.sidebar.multiselect(
            "Оберіть продукт", 
            options=all_products, 
            default=["Усі"]
        )
        if "Усі" not in selected_products:
            filtered_df = filtered_df[filtered_df["Тип продукту"].isin(selected_products)]
    else:
        st.sidebar.info("Немає доступних продуктів за вибраний період.")
    
    # Фильтр по оборудованию
    unique_equipments = sorted(filtered_df["Тип обладнання"].dropna().unique().tolist())
    if unique_equipments:
        all_equipments = ["Усі"] + unique_equipments
        selected_equipments = st.sidebar.multiselect(
            "Оберіть обладнання", 
            options=all_equipments, 
            default=["Усі"]
        )
        if "Усі" not in selected_equipments:
            filtered_df = filtered_df[filtered_df["Тип обладнання"].isin(selected_equipments)]
    else:
        st.sidebar.info("Немає доступного обладнання за вибраний період.")
    
    # Фильтр по сотруднику
    unique_employees = sorted(filtered_df["ПІБ"].dropna().unique().tolist())
    if unique_employees:
        selected_employee = st.sidebar.selectbox(
            "Оберіть співробітника", 
            options=["Усі"] + unique_employees
        )
        if selected_employee != "Усі":
            filtered_df = filtered_df[filtered_df["ПІБ"] == selected_employee]
    else:
        st.sidebar.info("Немає даних про співробітників за вибраний період.")
        
    # ---------------------------
    # Контент в зависимости от выбранного отчета
    # ---------------------------
    
    # Заголовок страницы
    st.title("📊 Виробнича звітність - Фасовка")
    st.markdown("---")
    
    # Общие KPI для всех отчетов
    total_operations = len(filtered_df)
    avg_time = filtered_df["Час на операцію"].mean() if "Час на операцію" in filtered_df.columns and total_operations > 0 else 0
    avg_productivity = filtered_df["Продуктивність за годину"].mean() if "Продуктивність за годину" in filtered_df.columns and total_operations > 0 else 0
    avg_defect = filtered_df["Відсоток браку"].mean() if "Відсоток браку" in filtered_df.columns and total_operations > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Кількість операцій", total_operations)
    col2.metric("Середній час операції", f"{avg_time:.2f} хв")
    col3.metric("Середня продуктивність", f"{avg_productivity:.0f} од/год")
    col4.metric("Середній % браку", f"{avg_defect:.2f}%")
    
    st.markdown("---")
    
    # Отчет - Общий обзор
    if report_type == "Загальний огляд":
        st.subheader("Огляд ключових показників")
        
        # График трендов по дням
        if not filtered_df.empty:
            # Формируем словарь агрегаций только для колонок, которые существуют
            agg_dict = {}
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Відсоток браку" in filtered_df.columns:
                agg_dict["Відсоток браку"] = "mean"
            
            # Для подсчета количества операций используем size()
            trend_count = filtered_df.groupby("Дата").size().reset_index(name="Кількість операцій")
            
            # Если есть другие метрики, добавляем их
            if agg_dict:
                trend_metrics = filtered_df.groupby("Дата", as_index=False).agg(agg_dict)
                # Объединяем результаты
                trend_data = pd.merge(trend_count, trend_metrics, on="Дата", how="left")
            else:
                trend_data = trend_count
            
            tabs = st.tabs(["Кількість операцій", "Час на операцію", "Продуктивність", "Брак"])
            
            with tabs[0]:
                fig1 = px.bar(
                    trend_data,
                    x="Дата",
                    y="Кількість операцій",
                    title="Динаміка кількості операцій",
                    color_discrete_sequence=["#3498DB"]
                )
                fig1.update_layout(
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with tabs[1]:
                fig2 = px.line(
                    trend_data,
                    x="Дата",
                    y="Час на операцію",
                    title="Динаміка часу операцій",
                    markers=True
                )
                fig2.update_traces(line=dict(width=3, color="#2E86C1"), marker=dict(size=8))
                fig2.update_layout(
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            with tabs[2]:
                fig3 = px.line(
                    trend_data,
                    x="Дата",
                    y="Продуктивність за годину",
                    title="Динаміка продуктивності",
                    markers=True
                )
                fig3.update_traces(line=dict(width=3, color="#27AE60"), marker=dict(size=8))
                fig3.update_layout(
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig3, use_container_width=True)
            
            with tabs[3]:
                fig4 = px.line(
                    trend_data,
                    x="Дата",
                    y="Відсоток браку",
                    title="Динаміка відсотку браку",
                    markers=True
                )
                fig4.update_traces(line=dict(width=3, color="#E74C3C"), marker=dict(size=8))
                fig4.update_layout(
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig4, use_container_width=True)
        else:
            st.warning("Немає даних для відображення трендів.")
        
        # Распределение по продуктам и оборудованию
        cols = st.columns(2)
        
        with cols[0]:
            st.subheader("Розподіл по типу продукту")
            if "Тип продукту" in filtered_df.columns:
                prod_count = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість")
                fig_prod = px.pie(
                    prod_count,
                    names="Тип продукту",
                    values="Кількість",
                    title="Розподіл операцій за типом продукту",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    hole=0.4
                )
                fig_prod.update_traces(textposition='inside', textinfo='percent+label')
                fig_prod.update_layout(legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_prod, use_container_width=True)
            else:
                st.warning("Немає даних про типи продуктів.")
        
        with cols[1]:
            st.subheader("Розподіл по обладнанню")
            if "Тип обладнання" in filtered_df.columns:
                eq_count = filtered_df.groupby("Тип обладнання").size().reset_index(name="Кількість")
                fig_eq = px.pie(
                    eq_count,
                    names="Тип обладнання",
                    values="Кількість",
                    title="Розподіл операцій за типом обладнання",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    hole=0.4
                )
                fig_eq.update_traces(textposition='inside', textinfo='percent+label')
                fig_eq.update_layout(legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_eq, use_container_width=True)
            else:
                st.warning("Немає даних про типи обладнання.")
    
    # Отчет - Анализ эффективности операторов
    elif report_type == "Аналіз ефективності операторів":
        st.subheader("Аналіз ефективності операторів")
        
        if not filtered_df.empty and "ПІБ" in filtered_df.columns:
            # Агрегация данных по операторам
            # Проверяем наличие колонок перед агрегацией
            agg_dict = {}
            
            # Используем size() для подсчета количества записей
            operator_count = filtered_df.groupby("ПІБ").size().reset_index(name="Кількість операцій")
            
            # Агрегируем остальные числовые показатели, если они есть
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Відсоток браку" in filtered_df.columns:
                agg_dict["Відсоток браку"] = "mean"
            
            if agg_dict:
                operator_metrics = filtered_df.groupby("ПІБ", as_index=False).agg(agg_dict)
                # Объединяем результаты
                operator_stats = pd.merge(operator_count, operator_metrics, on="ПІБ", how="left")
            else:
                operator_stats = operator_count
            
            # Сортировка по продуктивности (если колонка есть)
            if "Продуктивність за годину" in operator_stats.columns:
                operator_stats_prod = operator_stats.sort_values("Продуктивність за годину", ascending=False)
                
                # График производительности
                fig_prod = px.bar(
                    operator_stats_prod,
                    x="ПІБ",
                    y="Продуктивність за годину",
                    title="Середня продуктивність операторів (од/год)",
                    color="ПІБ",
                    text=round(operator_stats_prod["Продуктивність за годину"], 0)
                )
            else:
                # Если нет данных о продуктивности, используем количество операций
                operator_stats_prod = operator_stats.sort_values("Кількість операцій", ascending=False)
                
                # График количества операций вместо продуктивности
                fig_prod = px.bar(
                    operator_stats_prod,
                    x="ПІБ",
                    y="Кількість операцій",
                    title="Кількість операцій по операторам",
                    color="ПІБ",
                    text=operator_stats_prod["Кількість операцій"]
                )
            fig_prod.update_traces(texttemplate='%{text}', textposition='outside')
            fig_prod.update_layout(
                uniformtext_minsize=8,
                uniformtext_mode='hide',
                xaxis_title="Оператор",
                yaxis_title="Продуктивність (од/год)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_prod, use_container_width=True)
            
            # Время на операцию
            operator_stats_time = operator_stats.sort_values("Час на операцію")
            fig_time = px.bar(
                operator_stats_time,
                x="ПІБ",
                y="Час на операцію",
                title="Середній час операції (хв)",
                color="ПІБ",
                text=round(operator_stats_time["Час на операцію"], 1),
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_time.update_traces(texttemplate='%{text}', textposition='outside')
            fig_time.update_layout(
                uniformtext_minsize=8,
                uniformtext_mode='hide',
                xaxis_title="Оператор",
                yaxis_title="Час (хв)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_time, use_container_width=True)
            
            # Процент брака
            operator_stats_defect = operator_stats.sort_values("Відсоток браку")
            fig_defect = px.bar(
                operator_stats_defect,
                x="ПІБ",
                y="Відсоток браку",
                title="Середній відсоток браку (%)",
                color="ПІБ",
                text=round(operator_stats_defect["Відсоток браку"], 2),
                color_discrete_sequence=px.colors.sequential.Reds
            )
            fig_defect.update_traces(texttemplate='%{text}', textposition='outside')
            fig_defect.update_layout(
                uniformtext_minsize=8,
                uniformtext_mode='hide',
                xaxis_title="Оператор",
                yaxis_title="Брак (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_defect, use_container_width=True)
            
            # Таблица для сводки
            st.subheader("Зведена таблиця показників операторів")
            st.dataframe(operator_stats.style.highlight_max(subset=["Продуктивність за годину"], color='lightgreen')
                        .highlight_min(subset=["Час на операцію"], color='lightgreen')
                        .highlight_min(subset=["Відсоток браку"], color='lightgreen'))
            
            # Анализ лучших операторов
            st.subheader("Аналіз найефективніших операторів")
            best_productivity = operator_stats.loc[operator_stats["Продуктивність за годину"].idxmax()]
            best_time = operator_stats.loc[operator_stats["Час на операцію"].idxmin()]
            best_quality = operator_stats.loc[operator_stats["Відсоток браку"].idxmin()]
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Найкраща продуктивність", f"{best_productivity['ПІБ']}: {best_productivity['Продуктивність за годину']:.0f} од/год")
            col2.metric("Найшвидший час операції", f"{best_time['ПІБ']}: {best_time['Час на операцію']:.1f} хв")
            col3.metric("Найменший % браку", f"{best_quality['ПІБ']}: {best_quality['Відсоток браку']:.2f}%")
        else:
            st.warning("Немає даних для аналізу ефективності операторів.")
    
    # Отчет - Загрузка оборудования
    elif report_type == "Завантаження обладнання":
        st.subheader("Аналіз завантаження обладнання")
        
        if "Тип обладнання" in filtered_df.columns and not filtered_df.empty:
            # Расчет ожидаемых рабочих дней
            working_days = count_working_days(start_date, end_date)
            expected_minutes = working_days * 480  # 8 часов * 60 минут
            
            # Общая статистика по оборудованию
            equipment_stats = []
            
            for equip, group in filtered_df.groupby("Тип обладнання"):
                distinct_days = group["Дата"].dt.date.nunique()
                total_minutes = group["Час на операцію"].sum()
                operations_count = len(group)
                
                day_util_pct = (distinct_days / working_days) * 100 if working_days > 0 else 0
                minutes_util_pct = (total_minutes / expected_minutes) * 100 if expected_minutes > 0 else 0
                
                equipment_stats.append({
                    "Тип обладнання": equip,
                    "Реальні дні роботи": distinct_days,
                    "Планові дні роботи": working_days,
                    "Завантаженість (дні), %": f"{day_util_pct:.1f}%",
                    "Фактичні години": total_minutes / 60,
                    "Планові години": expected_minutes / 60,
                    "Завантаженість (години), %": f"{minutes_util_pct:.1f}%",
                    "Кількість операцій": operations_count,
                    "Операцій на день": operations_count / distinct_days if distinct_days > 0 else 0
                })
            
            equipment_df = pd.DataFrame(equipment_stats)
            
            # Отображение полной таблицы
            st.dataframe(equipment_df)
            
            # Визуализация загрузки оборудования по дням
            equipment_df_sorted = equipment_df.copy()
            try:
                equipment_df_sorted["Завантаженість (дні), %"] = equipment_df_sorted["Завантаженість (дні), %"].str.rstrip("%").astype(float)
            except Exception:
                # Если преобразование не удалось, используем оригинальные значения
                st.warning("Помилка при перетворенні відсотків завантаженості в числа")
                # Создаем числовую колонку напрямую из day_util_pct
                equipment_df_sorted["Завантаженість (дні), %"] = [float(e["Завантаженість (дні), %"].rstrip("%") if isinstance(e["Завантаженість (дні), %"], str) else e["Завантаженість (дні), %"]) for _, e in equipment_df.iterrows()]
            
            equipment_df_sorted = equipment_df_sorted.sort_values("Завантаженість (дні), %", ascending=False)
            
            fig_days = px.bar(
                equipment_df_sorted,
                x="Тип обладнання",
                y="Завантаженість (дні), %",
                title=f"Завантаженість обладнання (дні), % за період {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
                color="Тип обладнання",
                text="Завантаженість (дні), %"
            )
            fig_days.update_traces(texttemplate='%{text}', textposition='outside')
            fig_days.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="Макс. завантаженість")
            fig_days.update_layout(
                xaxis_title="Обладнання",
                yaxis_title="Завантаженість (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)', range=[0, 110])
            )
            st.plotly_chart(fig_days, use_container_width=True)
            
            # Анализ производительности по типам оборудования
            equip_perf = filtered_df.groupby("Тип обладнання", as_index=False).agg({
                "Продуктивність за годину": "mean",
                "Час на операцію": "mean",
                "Відсоток браку": "mean"
            })
            
            equip_perf_sorted = equip_perf.sort_values("Продуктивність за годину", ascending=False)
            fig_perf = px.bar(
                equip_perf_sorted,
                x="Тип обладнання",
                y="Продуктивність за годину",
                title="Середня продуктивність за типами обладнання",
                color="Тип обладнання",
                text=round(equip_perf_sorted["Продуктивність за годину"], 0)
            )
            fig_perf.update_traces(texttemplate='%{text}', textposition='outside')
            fig_perf.update_layout(
                xaxis_title="Обладнання",
                yaxis_title="Продуктивність (од/год)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_perf, use_container_width=True)
            
            # Тепловая карта оборудования по дням
            if not filtered_df.empty:
                eq_daily = filtered_df.groupby([filtered_df["Дата"].dt.date, "Тип обладнання"]).size().reset_index(name="Операцій")
                eq_daily_pivot = eq_daily.pivot(index="Дата", columns="Тип обладнання", values="Операцій").fillna(0)

                # Преобразование в формат для heatmap
                dates = eq_daily_pivot.index.tolist()
                equipment_types = eq_daily_pivot.columns.tolist()
                heatmap_data = eq_daily_pivot.values

                fig_heatmap = go.Figure(data=go.Heatmap(
                    z=heatmap_data,
                    x=equipment_types,
                    y=[d.strftime("%d.%m.%Y") for d in dates],
                    colorscale="YlGnBu",
                    hoverongaps=False,
                    text=heatmap_data.round(1),
                    texttemplate="%{text}",
                    colorbar=dict(title="Операцій")
                ))
                
                fig_heatmap.update_layout(
                    title="Щоденне завантаження обладнання (кількість операцій)",
                    xaxis_title="Обладнання",
                    yaxis_title="Дата",
                    plot_bgcolor='rgba(240,240,240,0.8)',
                )
                
                st.plotly_chart(fig_heatmap, use_container_width=True)
        else:
            st.warning("Немає даних для аналізу завантаження обладнання.")
    
    # Отчет - Продуктивность производства
    elif report_type == "Продуктивність виробництва":
        st.subheader("Аналіз продуктивності виробництва")
        
        if not filtered_df.empty:
            # KPI для производительности
            total_volume = filtered_df["Об'єм_число"].sum() if "Об'єм_число" in filtered_df.columns else 0
            avg_operators = filtered_df["Кількість операторів"].mean() if "Кількість операторів" in filtered_df.columns else 0
            
            # Расчет временных показателей
            days_in_period = (end_date - start_date).days + 1
            working_days = count_working_days(start_date, end_date)
            
            # Расчет производительности
            daily_prod = total_volume / days_in_period if days_in_period > 0 else 0
            working_day_prod = total_volume / working_days if working_days > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Загальний об'єм виробництва", f"{total_volume:.0f} одиниць")
            col2.metric("Середня денна продуктивність", f"{daily_prod:.1f} од/день")
            col3.metric("Продуктивність у робочі дні", f"{working_day_prod:.1f} од/день")
            
            # Анализ производительности по дням
            # Формируем словарь агрегаций только для колонок, которые существуют
            agg_dict = {}
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "sum"
            if "Об'єм_число" in filtered_df.columns:
                agg_dict["Об'єм_число"] = "sum"
            
            # Для подсчета количества операций используем size()
            daily_count = filtered_df.groupby(filtered_df["Дата"].dt.date).size().reset_index(name="Кількість операцій")
            
            # Если есть другие метрики, добавляем их
            if agg_dict:
                daily_metrics = filtered_df.groupby(filtered_df["Дата"].dt.date).agg(agg_dict).reset_index()
                # Объединяем результаты
                daily_data = pd.merge(daily_count, daily_metrics, on="Дата", how="left")
            else:
                daily_data = daily_count
            
            # Визуализация продуктивности по дням
            fig_daily = px.bar(
                daily_data,
                x="Дата",
                y="Об'єм_число",
                title="Денна продуктивність (об'єм виробництва)",
                labels={"Об'єм_число": "Об'єм виробництва", "Дата": "Дата"},
                text=daily_data["Об'єм_число"].round(0)
            )
            fig_daily.update_traces(texttemplate='%{text}', textposition='outside')
            
            # Добавляем среднюю линию
            mean_volume = daily_data["Об'єм_число"].mean()
            fig_daily.add_hline(
                y=mean_volume,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Середня: {mean_volume:.1f}",
                annotation_position="top right"
            )
            
            fig_daily.update_layout(
                xaxis_title="Дата",
                yaxis_title="Об'єм виробництва",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_daily, use_container_width=True)
            
            # Анализ продуктивности по типам продукции
            # Формируем словарь агрегаций только для колонок, которые существуют
            agg_dict = {}
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Об'єм_число" in filtered_df.columns:
                agg_dict["Об'єм_число"] = "sum"
            
            # Для подсчета количества операций используем size()
            product_count = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість операцій")
            
            # Если есть другие метрики, добавляем их
            if agg_dict:
                product_metrics = filtered_df.groupby("Тип продукту", as_index=False).agg(agg_dict)
                # Объединяем результаты
                product_perf = pd.merge(product_count, product_metrics, on="Тип продукту", how="left")
            else:
                product_perf = product_count
            
            # Сортировка по продуктивности
            product_perf_sorted = product_perf.sort_values("Продуктивність за годину", ascending=False)
            
            fig_prod_eff = px.bar(
                product_perf_sorted,
                x="Тип продукту",
                y="Продуктивність за годину",
                title="Середня продуктивність за типами продукції",
                color="Тип продукту",
                text=round(product_perf_sorted["Продуктивність за годину"], 0)
            )
            fig_prod_eff.update_traces(texttemplate='%{text}', textposition='outside')
            # Улучшаем отображение длинных названий продуктов
            max_label_length = 15  # Максимальная длина метки
            product_labels = {}
            for i, product in enumerate(product_perf_sorted["Тип продукту"].unique()):
                if len(product) > max_label_length:
                    short_name = product[:max_label_length] + "..."
                    product_labels[product] = short_name
            
            fig_prod_eff.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Продуктивність (од/год)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(
                    showgrid=False,
                    tickmode='array',
                    tickvals=list(range(len(product_perf_sorted["Тип продукту"].unique()))),
                    ticktext=[product_labels.get(p, p) for p in product_perf_sorted["Тип продукту"].unique()],
                ),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                height=500,  # Увеличиваем высоту для лучшей читаемости
                margin=dict(b=100)  # Увеличиваем нижний отступ для меток
            )
            st.plotly_chart(fig_prod_eff, use_container_width=True)
            
            # Таблица продуктивности по типам продукции
            st.subheader("Продуктивність за типами продукції")
            st.dataframe(product_perf.style.highlight_max(subset=["Продуктивність за годину"], color='lightgreen')
                         .highlight_min(subset=["Час на операцію"], color='lightgreen'))
            
            # Новый отчет: Самые быстрые и медленные фасовки по типам продукта
            if "Час на операцію" in filtered_df.columns:
                st.subheader("Найшвидші та найповільніші фасовки за типами продукту")
                
                # Создаем DataFrame для хранения минимального и максимального времени операции
                product_time_minmax = pd.DataFrame()
                
                # Для каждого типа продукта находим минимальное и максимальное время
                for product_type in filtered_df["Тип продукту"].unique():
                    product_data = filtered_df[filtered_df["Тип продукту"] == product_type]
                    if len(product_data) > 0:
                        # Получаем данные для самой быстрой и самой медленной фасовки
                        fastest = product_data.loc[product_data["Час на операцію"].idxmin()]
                        slowest = product_data.loc[product_data["Час на операцію"].idxmax()]
                        
                        # Добавляем данные в DataFrame
                        product_time_minmax = pd.concat([product_time_minmax, pd.DataFrame({
                            "Тип продукту": [product_type, product_type],
                            "Категорія": ["Найшвидша", "Найповільніша"],
                            "Час на операцію": [fastest["Час на операцію"], slowest["Час на операцію"]],
                            "Дата": [fastest["Дата"], slowest["Дата"]],
                            "ПІБ": [fastest["ПІБ"], slowest["ПІБ"]] if "ПІБ" in fastest else ["", ""],
                            "Тип обладнання": [fastest["Тип обладнання"], slowest["Тип обладнання"]] if "Тип обладнання" in fastest else ["", ""],
                            "Продуктивність за годину": [fastest["Продуктивність за годину"], slowest["Продуктивність за годину"]] if "Продуктивність за годину" in fastest else [0, 0]
                        })])
                
                # Если есть данные, строим визуализацию
                if len(product_time_minmax) > 0:
                    # Создаем столбиковую диаграмму со сгруппированными столбцами
                    fig_minmax = px.bar(
                        product_time_minmax,
                        x="Тип продукту",
                        y="Час на операцію",
                        color="Категорія",
                        barmode="group",
                        title="Час найшвидших та найповільніших фасовок за типами продукту",
                        hover_data=["Дата", "ПІБ", "Тип обладнання", "Продуктивність за годину"],
                        color_discrete_map={"Найшвидша": "#2ECC71", "Найповільніша": "#E74C3C"}
                    )
                    
                    # Добавляем метки со значениями
                    fig_minmax.update_traces(texttemplate='%{y:.1f}', textposition='outside')
                    
                    # Улучшаем отображение длинных названий продуктов
                    # Вместо наклона текста используем сокращения с полной информацией при наведении
                    max_label_length = 15  # Максимальная длина метки на оси X
                    product_labels = {}
                    for i, product in enumerate(product_time_minmax["Тип продукту"].unique()):
                        if len(product) > max_label_length:
                            short_name = product[:max_label_length] + "..."
                            product_labels[product] = short_name
                    
                    fig_minmax.update_layout(
                        xaxis_title="Тип продукту",
                        yaxis_title="Час на операцію (хв)",
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(
                            showgrid=False,
                            tickmode='array',
                            tickvals=list(range(len(product_time_minmax["Тип продукту"].unique()))),
                            ticktext=[product_labels.get(p, p) for p in product_time_minmax["Тип продукту"].unique()],
                        ),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        legend=dict(title="", orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        height=500,  # Увеличиваем высоту для лучшей читаемости
                        margin=dict(b=100)  # Увеличиваем нижний отступ для меток
                    )
                    st.plotly_chart(fig_minmax, use_container_width=True)
                    
                    # Таблица с деталями
                    st.subheader("Деталі найшвидших та найповільніших фасовок")
                    st.dataframe(product_time_minmax)
            
            # Соотношение времени операции к производительности
            st.subheader("Співвідношення часу операції до продуктивності")
            fig_scatter = px.scatter(
                filtered_df,
                x="Час на операцію",
                y="Продуктивність за годину",
                color="Тип продукту", 
                size="Кількість операторів",
                hover_data=["ПІБ", "Тип обладнання"],
                title="Залежність продуктивності від часу операції"
            )
            
            # Добавляем линию тренда
            fig_scatter.update_layout(
                xaxis_title="Час на операцію (хв)",
                yaxis_title="Продуктивність (од/год)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("Немає даних для аналізу продуктивності виробництва.")
    
    # Отчет - Анализ качества и брака
    elif report_type == "Аналіз якості та браку":
        st.subheader("Аналіз якості та браку")
        
        if "Відсоток браку" in filtered_df.columns and not filtered_df.empty:
            # Статистика по браку
            total_operations = len(filtered_df)
            avg_defect = filtered_df["Відсоток браку"].mean()
            max_defect = filtered_df["Відсоток браку"].max()
            min_defect = filtered_df["Відсоток браку"].min()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Середній відсоток браку", f"{avg_defect:.2f}%")
            col2.metric("Максимальний відсоток браку", f"{max_defect:.2f}%")
            col3.metric("Мінімальний відсоток браку", f"{min_defect:.2f}%")
            
            # Анализ брака по дням
            daily_defect = filtered_df.groupby(filtered_df["Дата"].dt.date)["Відсоток браку"].mean().reset_index()
            
            fig_daily = px.line(
                daily_defect,
                x="Дата",
                y="Відсоток браку",
                title="Динаміка відсотка браку по днях",
                markers=True
            )
            fig_daily.update_traces(line=dict(width=3, color="#E74C3C"), marker=dict(size=8))
            
            # Добавляем среднюю линию
            fig_daily.add_hline(
                y=avg_defect,
                line_dash="dash",
                line_color="blue",
                annotation_text=f"Середня: {avg_defect:.2f}%",
                annotation_position="top right"
            )
            
            fig_daily.update_layout(
                xaxis_title="Дата",
                yaxis_title="Відсоток браку (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_daily, use_container_width=True)
            
            # Анализ брака по продуктам
            # Подсчет операций с использованием size()
            product_count = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість операцій")
            
            # Агрегируем средний процент брака
            product_defect_mean = filtered_df.groupby("Тип продукту", as_index=False)["Відсоток браку"].mean()
            
            # Соединяем результаты
            product_defect = pd.merge(product_count, product_defect_mean, on="Тип продукту", how="left")
            product_defect_sorted = product_defect.sort_values("Відсоток браку", ascending=False)
            
            fig_prod = px.bar(
                product_defect_sorted,
                x="Тип продукту",
                y="Відсоток браку",
                title="Середній відсоток браку за типами продукції",
                color="Тип продукту",
                text=round(product_defect_sorted["Відсоток браку"], 2)
            )
            fig_prod.update_traces(texttemplate='%{text}', textposition='outside')
            fig_prod.add_hline(
                y=avg_defect,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Загальний середній: {avg_defect:.2f}%",
                annotation_position="top right"
            )
            fig_prod.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Відсоток браку (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False, tickangle=45),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_prod, use_container_width=True)
            
            # Анализ брака по оборудованию
            # Подсчет операций с использованием size()
            equip_count = filtered_df.groupby("Тип обладнання").size().reset_index(name="Кількість операцій")
            
            # Агрегируем средний процент брака
            equip_defect_mean = filtered_df.groupby("Тип обладнання", as_index=False)["Відсоток браку"].mean()
            
            # Соединяем результаты
            equip_defect = pd.merge(equip_count, equip_defect_mean, on="Тип обладнання", how="left")
            equip_defect_sorted = equip_defect.sort_values("Відсоток браку", ascending=False)
            
            fig_equip = px.bar(
                equip_defect_sorted,
                x="Тип обладнання",
                y="Відсоток браку",
                title="Середній відсоток браку за типами обладнання",
                color="Тип обладнання",
                text=round(equip_defect_sorted["Відсоток браку"], 2)
            )
            fig_equip.update_traces(texttemplate='%{text}', textposition='outside')
            fig_equip.add_hline(
                y=avg_defect,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Загальний середній: {avg_defect:.2f}%",
                annotation_position="top right"
            )
            fig_equip.update_layout(
                xaxis_title="Тип обладнання",
                yaxis_title="Відсоток браку (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_equip, use_container_width=True)
            
            # Анализ брака по операторам
            # Подсчет операций с использованием size()
            operator_count = filtered_df.groupby("ПІБ").size().reset_index(name="Кількість операцій")
            
            # Агрегируем средний процент брака
            operator_defect_mean = filtered_df.groupby("ПІБ", as_index=False)["Відсоток браку"].mean()
            
            # Соединяем результаты
            operator_defect = pd.merge(operator_count, operator_defect_mean, on="ПІБ", how="left")
            operator_defect_sorted = operator_defect.sort_values("Відсоток браку", ascending=False)
            
            # Диаграмма брака по операторам
            fig_operator = px.bar(
                operator_defect_sorted,
                x="ПІБ",
                y="Відсоток браку",
                title="Середній відсоток браку за операторами",
                color="ПІБ",
                text=round(operator_defect_sorted["Відсоток браку"], 2)
            )
            fig_operator.update_traces(texttemplate='%{text}', textposition='outside')
            fig_operator.add_hline(
                y=avg_defect,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Загальний середній: {avg_defect:.2f}%",
                annotation_position="top right"
            )
            fig_operator.update_layout(
                xaxis_title="Оператор",
                yaxis_title="Відсоток браку (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_operator, use_container_width=True)
            
            # Боксплот распределения брака по типам продукции
            fig_box = px.box(
                filtered_df,
                x="Тип продукту",
                y="Відсоток браку",
                color="Тип продукту",
                title="Розподіл відсотка браку за типами продукції",
                points="all"
            )
            fig_box.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Відсоток браку (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False, tickangle=45),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.warning("Немає даних для аналізу якості та браку.")