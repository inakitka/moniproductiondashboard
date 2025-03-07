import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import calendar
from datetime import datetime, date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------
# Настройка страницы
# ---------------------------
st.set_page_config(
    page_title="Виробнича звітність",
    page_icon="📊",
    layout="wide",
)

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
# Функция для поиска колонки с процентами ошибок
# ---------------------------
def find_percentage_column(columns, target_type="втрат"):
    """
    Ищет колонку с именем "Відсоток втрат" или "Відсоток браку" (игнорируя пробелы и регистр).
    """
    target_map = {
        "втрат": ["відсотоквтрат", "втрат", "відсотоквтрат%", "втрат%"],
        "браку": ["відсотокбраку", "браку", "відсотокбраку%", "браку%"]
    }
    
    targets = target_map.get(target_type, target_map["втрат"])
    
    for col in columns:
        col_normalized = col.strip().lower().replace(" ", "").replace("%", "")
        if col_normalized in targets:
            return col
    return None

# ---------------------------
# Общая функция для преобразования числовых колонок
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
# Функция загрузки данных из Google Sheets по указанному листу
# ---------------------------
@st.cache_data
def load_data(sheet_name):
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SHEET_ID, range=sheet_name).execute()
        values = result.get("values", [])
        if not values:
            st.error("Помилка завантаження даних з Google Sheets!")
            return pd.DataFrame()
        
        # Создаем DataFrame
        df = pd.DataFrame(values[1:], columns=values[0])
        df.columns = df.columns.str.strip()
        
        # Применяем переименование колонок, чтобы унифицировать имена
        column_mapping = {
            "Тип оборудования": "Тип обладнання",
            "Тип продукта": "Тип продукту",
            "Номер заказа": "Номер замовлення",
            "Время на операцию": "Час на операцію",
            "Процент брака": "Відсоток браку"
        }
        
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        # Обработка даты
        if "Дата" in df.columns:
            df["Дата"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y", errors="coerce")
        elif all(col in df.columns for col in ["День", "Місяць", "Рік"]):
            # Если в данных дата разбита на составляющие части, создаем колонку Дата
            df["Дата"] = pd.to_datetime(
                df["День"].astype(str) + "." + df["Місяць"].astype(str) + "." + df["Рік"].astype(str),
                format="%d.%m.%Y", errors="coerce"
            )
        
        # Обработка числовых колонок
        numeric_cols = ["Час на операцію", "Продуктивність за годину", "Кількість операторів"]
        df = convert_numeric_columns(df, numeric_cols)
        
        # Поиск и обработка колонки с процентами ошибок (может называться "Відсоток втрат" или "Відсоток браку")
        loss_col = find_percentage_column(df.columns, "втрат")
        if loss_col:
            df = convert_numeric_columns(df, [loss_col])
            if "Відсоток втрат" not in df.columns:
                df["Відсоток втрат"] = df[loss_col]
        
        defect_col = find_percentage_column(df.columns, "браку")
        if defect_col:
            df = convert_numeric_columns(df, [defect_col])
            if "Відсоток браку" not in df.columns:
                df["Відсоток браку"] = df[defect_col]
        
        # Обработка объема (если есть)
        if "Об'єм" in df.columns:
            # Извлекаем числовое значение из строки (например, "50мл" -> 50)
            df["Об'єм_число"] = df["Об'єм"].str.extract(r'(\d+(?:\.\d+)?)').astype(float)
        
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
# Загрузка данных
# ---------------------------
sheet_name = "варка"
df = load_data(sheet_name)

if df.empty:
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
            "Аналіз якості та втрат",
            "Тренд завантаження обладнання"
        ]
    )
    
    # Фильтр по периоду - пресеты или пользовательский выбор
    preset_options = ["Цей тиждень", "Цей місяць", "Минулий тиждень", "Минулий місяць", "Користувацький"]
    selected_preset = st.sidebar.radio("Виберіть період", preset_options, index=0)
    
    if selected_preset != "Користувацький":
        start_date, end_date = get_preset_dates(selected_preset)
        st.sidebar.write(f"Період: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
    else:
        if pd.notnull(df["Дата"].min()) and pd.notnull(df["Дата"].max()):
            min_date = df["Дата"].min().date()
            max_date = df["Дата"].max().date()
        else:
            min_date = max_date = date.today()
        date_cols = st.sidebar.columns(2)
        start_date = date_cols[0].date_input("Начало періоду", min_date, min_value=min_date, max_value=max_date)
        end_date = date_cols[1].date_input("Кінець періоду", max_date, min_value=min_date, max_value=max_date)
    
    if start_date > end_date:
        st.sidebar.error("Начало періоду не може бути пізніше, ніж кінець.")
        filtered_df = pd.DataFrame()
    else:
        filtered_df = df[(df["Дата"] >= pd.to_datetime(start_date)) & (df["Дата"] <= pd.to_datetime(end_date))]
    
    # Дополнительные фильтры
    st.sidebar.markdown("---")
    
    # Фильтр по продукту (если имеются данные)
    unique_products = sorted(filtered_df["Тип продукту"].dropna().unique().tolist())
    if unique_products:
        all_products = ["Усі"] + unique_products
        selected_products = st.sidebar.multiselect("Оберіть продукт", options=all_products, default=["Усі"])
        if "Усі" not in selected_products:
            filtered_df = filtered_df[filtered_df["Тип продукту"].isin(selected_products)]
    else:
        st.sidebar.info("Немає доступних продуктів за вибраний період.")
    
    # Фильтр по оборудованию (если имеются данные)
    unique_equipments = sorted(filtered_df["Тип обладнання"].dropna().unique().tolist())
    if unique_equipments:
        all_equipments = ["Усі"] + unique_equipments
        selected_equipments = st.sidebar.multiselect("Оберіть обладнання", options=all_equipments, default=["Усі"])
        if "Усі" not in selected_equipments:
            filtered_df = filtered_df[filtered_df["Тип обладнання"].isin(selected_equipments)]
    else:
        st.sidebar.info("Немає доступного обладнання за вибраний період.")
    
    # Фильтр по співробітнику (если имеются данные)
    unique_employees = sorted(filtered_df["ПІБ"].dropna().unique().tolist())
    if unique_employees:
        selected_employee = st.sidebar.selectbox("Оберіть співробітника", options=["Усі"] + unique_employees)
        if selected_employee != "Усі":
            filtered_df = filtered_df[filtered_df["ПІБ"] == selected_employee]
    else:
        st.sidebar.info("Немає даних про співробітників за вибраний період.")
    
    # ---------------------------
    # Контент в зависимости от выбранного отчета
    # ---------------------------
    
    # Заголовок страницы
    st.title("📊 Виробнича звітність - Варка")
    st.markdown("---")
    
    # Общие KPI для всех отчетов
    total_batches = len(filtered_df)
    avg_loss = filtered_df["Відсоток втрат"].mean() if total_batches > 0 and "Відсоток втрат" in filtered_df.columns else 0
    avg_time = filtered_df["Час на операцію"].mean() if total_batches > 0 and "Час на операцію" in filtered_df.columns else 0
    unique_emp_count = filtered_df["ПІБ"].nunique() if total_batches > 0 and "ПІБ" in filtered_df.columns else 0
    avg_ops_per_employee = total_batches / unique_emp_count if unique_emp_count > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Кількість операцій", total_batches)
    col2.metric("Середній % втрат", f"{avg_loss:.2f}%" if total_batches > 0 else "0%")
    col3.metric("Середній час операції", f"{avg_time:.2f} хв")
    col4.metric("Операцій на співробітника", f"{avg_ops_per_employee:.2f}" if total_batches > 0 else "0")
    
    # Отчеты по выбранному типу
    if report_type == "Загальний огляд":
        st.subheader("Загальний огляд виробництва")
        
        # График трендов по дням
        if not filtered_df.empty:
            # Формируем словарь агрегаций только для колонок, которые существуют
            agg_dict = {}
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Відсоток втрат" in filtered_df.columns:
                agg_dict["Відсоток втрат"] = "mean"
            
            # Для подсчета количества операций используем size()
            trend_count = filtered_df.groupby("Дата").size().reset_index(name="Кількість операцій")
            
            # Если есть другие метрики, добавляем их
            if agg_dict:
                trend_metrics = filtered_df.groupby("Дата", as_index=False).agg(agg_dict)
                # Объединяем результаты
                trend_data = pd.merge(trend_count, trend_metrics, on="Дата", how="left")
            else:
                trend_data = trend_count
                
            tabs = st.tabs(["Кількість операцій", "Час на операцію", "Втрати"])
            
            with tabs[0]:
                fig1 = px.bar(
                    trend_data,
                    x="Дата",
                    y="Кількість операцій",
                    title="Динаміка кількості операцій",
                    color_discrete_sequence=["#3498DB"]
                )
                # Добавляем среднюю линию
                avg_ops = trend_data["Кількість операцій"].mean()
                fig1.add_hline(
                    y=avg_ops, 
                    line_dash="dash", 
                    line_color="red",
                    annotation_text=f"Середня: {avg_ops:.1f}",
                    annotation_position="top right"
                )
                fig1.update_layout(
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with tabs[1]:
                if "Час на операцію" in trend_data.columns:
                    fig2 = px.line(
                        trend_data,
                        x="Дата",
                        y="Час на операцію",
                        title="Динаміка часу операцій",
                        markers=True
                    )
                    fig2.update_traces(line=dict(width=3, color="#2E86C1"), marker=dict(size=10))
                    fig2.update_layout(
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.warning("Немає даних про час операцій.")
            
            with tabs[2]:
                if "Відсоток втрат" in trend_data.columns:
                    fig3 = px.line(
                        trend_data,
                        x="Дата",
                        y="Відсоток втрат",
                        title="Динаміка відсотку втрат",
                        markers=True
                    )
                    fig3.update_traces(line=dict(width=3, color="#E74C3C"), marker=dict(size=10))
                    fig3.update_layout(
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                    )
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.warning("Немає даних про відсоток втрат.")
        else:
            st.warning("Немає даних для відображення трендів.")
            
        # Распределение по продуктам и оборудованию
        cols = st.columns(2)
        
        with cols[0]:
            st.subheader("Розподіл по типу продукту")
            if "Тип продукту" in filtered_df.columns and not filtered_df.empty:
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
            if "Тип обладнання" in filtered_df.columns and not filtered_df.empty:
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
            if "Відсоток втрат" in filtered_df.columns:
                agg_dict["Відсоток втрат"] = "mean"
            
            if agg_dict:
                operator_metrics = filtered_df.groupby("ПІБ", as_index=False).agg(agg_dict)
                # Объединяем результаты
                operator_stats = pd.merge(operator_count, operator_metrics, on="ПІБ", how="left")
            else:
                operator_stats = operator_count
            
            # Визуализация эффективности операторов
            st.subheader("Кількість операцій по операторам")
            operator_stats_count = operator_stats.sort_values("Кількість операцій", ascending=False)
            
            fig_count = px.bar(
                operator_stats_count,
                x="ПІБ",
                y="Кількість операцій",
                title="Кількість операцій по операторам",
                color="ПІБ",
                text=operator_stats_count["Кількість операцій"]
            )
            fig_count.update_traces(texttemplate='%{text}', textposition='outside')
            fig_count.update_layout(
                uniformtext_minsize=8,
                uniformtext_mode='hide',
                xaxis_title="Оператор",
                yaxis_title="Кількість операцій",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_count, use_container_width=True)
            
            # Время на операцию
            if "Час на операцію" in operator_stats.columns:
                st.subheader("Середній час операції по операторам")
                operator_stats_time = operator_stats.sort_values("Час на операцію")
                
                fig_time = px.bar(
                    operator_stats_time,
                    x="ПІБ",
                    y="Час на операцію",
                    title="Середній час операції (хв)",
                    color="ПІБ",
                    text=round(operator_stats_time["Час на операцію"], 1),
                    color_discrete_sequence=px.colors.sequential.Viridis
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
            
            # Процент потерь
            if "Відсоток втрат" in operator_stats.columns:
                st.subheader("Середній відсоток втрат по операторам")
                operator_stats_loss = operator_stats.sort_values("Відсоток втрат")
                
                fig_loss = px.bar(
                    operator_stats_loss,
                    x="ПІБ",
                    y="Відсоток втрат",
                    title="Середній відсоток втрат (%)",
                    color="ПІБ",
                    text=round(operator_stats_loss["Відсоток втрат"], 2),
                    color_discrete_sequence=px.colors.sequential.Reds
                )
                fig_loss.update_traces(texttemplate='%{text}', textposition='outside')
                fig_loss.update_layout(
                    uniformtext_minsize=8,
                    uniformtext_mode='hide',
                    xaxis_title="Оператор",
                    yaxis_title="Втрати (%)",
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig_loss, use_container_width=True)
            
            # Таблица для сводки
            st.subheader("Зведена таблиця показників операторів")
            if "Час на операцію" in operator_stats.columns and "Відсоток втрат" in operator_stats.columns:
                st.dataframe(operator_stats.style
                       .highlight_max(subset=["Кількість операцій"], color='lightgreen')
                       .highlight_min(subset=["Час на операцію"], color='lightgreen')
                       .highlight_min(subset=["Відсоток втрат"], color='lightgreen'))
            else:
                st.dataframe(operator_stats)
            
            # Выделение лучших операторов
            st.subheader("Аналіз найефективніших операторів")
            
            cols = st.columns(3)
            best_count = operator_stats.loc[operator_stats["Кількість операцій"].idxmax()]
            cols[0].metric("Найбільше операцій", f"{best_count['ПІБ']}: {best_count['Кількість операцій']}")
            
            if "Час на операцію" in operator_stats.columns:
                best_time = operator_stats.loc[operator_stats["Час на операцію"].idxmin()]
                cols[1].metric("Найшвидший час операції", f"{best_time['ПІБ']}: {best_time['Час на операцію']:.1f} хв")
            
            if "Відсоток втрат" in operator_stats.columns:
                best_quality = operator_stats.loc[operator_stats["Відсоток втрат"].idxmin()]
                cols[2].metric("Найменший % втрат", f"{best_quality['ПІБ']}: {best_quality['Відсоток втрат']:.2f}%")
        else:
            st.warning("Немає даних для аналізу ефективності операторів.")
            
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
                total_minutes = group["Час на операцію"].sum() if "Час на операцію" in group.columns else 0
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
                equipment_df_sorted["Завантаженість (дні), %_num"] = [float(str(e).rstrip("%")) if isinstance(e, str) else e for e in equipment_df_sorted["Завантаженість (дні), %"]]
                equipment_df_sorted = equipment_df_sorted.sort_values("Завантаженість (дні), %_num", ascending=False)
            else:
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
            
    elif report_type == "Продуктивність виробництва":
        st.subheader("Аналіз продуктивності виробництва")
        
        if not filtered_df.empty:
            # Расчет временных показателей
            days_in_period = (end_date - start_date).days + 1
            working_days = count_working_days(start_date, end_date)
            
            # Расчет производительности
            productivity_per_day = total_batches / days_in_period if days_in_period > 0 else 0
            productivity_per_working_day = total_batches / working_days if working_days > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Загальна кількість операцій", f"{total_batches} операцій")
            col2.metric("Середня денна продуктивність", f"{productivity_per_day:.1f} операцій/день")
            col3.metric("Продуктивність у робочі дні", f"{productivity_per_working_day:.1f} операцій/день")
            
            # Анализ производительности по дням
            daily_data = filtered_df.groupby(filtered_df["Дата"].dt.date).size().reset_index(name="Кількість операцій")
            
            # Визуализация продуктивности по дням
            fig_daily = px.bar(
                daily_data,
                x="Дата",
                y="Кількість операцій",
                title="Денна продуктивність (кількість операцій)",
                labels={"Дата": "Дата", "Кількість операцій": "Кількість операцій"},
                color_discrete_sequence=["#5DADE2"]
            )
            
            # Добавляем среднюю линию
            fig_daily.add_hline(
                y=daily_data["Кількість операцій"].mean(),
                line_dash="dash",
                line_color="red",
                annotation_text=f"Середня: {daily_data['Кількість операцій'].mean():.1f}",
                annotation_position="top right"
            )
            
            fig_daily.update_layout(
                xaxis_title="Дата",
                yaxis_title="Кількість операцій",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_daily, use_container_width=True)
            
            # Анализ продуктивности по продуктам
            product_ops = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість операцій")
            product_ops_sorted = product_ops.sort_values("Кількість операцій", ascending=False)
            
            fig_prod = px.bar(
                product_ops_sorted,
                x="Тип продукту",
                y="Кількість операцій",
                title="Кількість операцій за типами продукції",
                color="Тип продукту",
                text=product_ops_sorted["Кількість операцій"]
            )
            fig_prod.update_traces(texttemplate='%{text}', textposition='outside')
            # Улучшаем отображение длинных названий продуктов
            max_label_length = 15  # Максимальная длина метки
            product_labels = {}
            for i, product in enumerate(product_ops_sorted["Тип продукту"].unique()):
                if len(product) > max_label_length:
                    short_name = product[:max_label_length] + "..."
                    product_labels[product] = short_name
            
            fig_prod.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Кількість операцій",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(
                    showgrid=False,
                    tickmode='array',
                    tickvals=list(range(len(product_ops_sorted["Тип продукту"].unique()))),
                    ticktext=[product_labels.get(p, p) for p in product_ops_sorted["Тип продукту"].unique()],
                ),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                height=500,  # Увеличиваем высоту для лучшей читаемости
                margin=dict(b=100)  # Увеличиваем нижний отступ для меток
            )
            st.plotly_chart(fig_prod, use_container_width=True)
            
            # Время операций - если доступно
            if "Час на операцію" in filtered_df.columns:
                st.subheader("Аналіз часу операцій")
                
                product_time = filtered_df.groupby("Тип продукту", as_index=False)["Час на операцію"].mean()
                product_time_sorted = product_time.sort_values("Час на операцію")
                
                fig_time = px.bar(
                    product_time_sorted,
                    x="Тип продукту",
                    y="Час на операцію",
                    title="Середній час операції за типами продукції",
                    color="Тип продукту",
                    text=round(product_time_sorted["Час на операцію"], 1)
                )
                fig_time.update_traces(texttemplate='%{text}', textposition='outside')
                # Улучшаем отображение длинных названий продуктов
                max_label_length = 15  # Максимальная длина метки
                product_labels = {}
                for i, product in enumerate(product_time_sorted["Тип продукту"].unique()):
                    if len(product) > max_label_length:
                        short_name = product[:max_label_length] + "..."
                        product_labels[product] = short_name
                
                fig_time.update_layout(
                    xaxis_title="Тип продукту",
                    yaxis_title="Час (хв)",
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(
                        showgrid=False,
                        tickmode='array',
                        tickvals=list(range(len(product_time_sorted["Тип продукту"].unique()))),
                        ticktext=[product_labels.get(p, p) for p in product_time_sorted["Тип продукту"].unique()],
                    ),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    height=500,  # Увеличиваем высоту для лучшей читаемости
                    margin=dict(b=100)  # Увеличиваем нижний отступ для меток
                )
                st.plotly_chart(fig_time, use_container_width=True)
                
                # Гистограмма распределения времени операций
                fig_hist = px.histogram(
                    filtered_df,
                    x="Час на операцію",
                    nbins=20,
                    title="Розподіл часу операцій",
                    color_discrete_sequence=["#3498DB"]
                )
                fig_hist.update_layout(
                    xaxis_title="Час операції (хв)",
                    yaxis_title="Кількість операцій",
                    plot_bgcolor='rgba(240,240,240,0.8)',
                    xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                    yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                )
                st.plotly_chart(fig_hist, use_container_width=True)
                
                # Новый отчет: Самые быстрые и медленные варки по типам продукта
                st.subheader("Найшвидші та найповільніші варки за типами продукту")
                
                # Создаем DataFrame для хранения минимального и максимального времени операции
                product_time_minmax = pd.DataFrame()
                
                # Для каждого типа продукта находим минимальное и максимальное время
                for product_type in filtered_df["Тип продукту"].unique():
                    product_data = filtered_df[filtered_df["Тип продукту"] == product_type]
                    if len(product_data) > 0:
                        # Получаем данные для самой быстрой и самой медленной варки
                        fastest = product_data.loc[product_data["Час на операцію"].idxmin()]
                        slowest = product_data.loc[product_data["Час на операцію"].idxmax()]
                        
                        # Добавляем данные в DataFrame
                        product_time_minmax = pd.concat([product_time_minmax, pd.DataFrame({
                            "Тип продукту": [product_type, product_type],
                            "Категорія": ["Найшвидша", "Найповільніша"],
                            "Час на операцію": [fastest["Час на операцію"], slowest["Час на операцію"]],
                            "Дата": [fastest["Дата"], slowest["Дата"]],
                            "ПІБ": [fastest["ПІБ"], slowest["ПІБ"]] if "ПІБ" in fastest else ["", ""],
                            "Тип обладнання": [fastest["Тип обладнання"], slowest["Тип обладнання"]] if "Тип обладнання" in fastest else ["", ""]
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
                        title="Час найшвидших та найповільніших варок за типами продукту",
                        hover_data=["Дата", "ПІБ", "Тип обладнання"],
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
                    st.subheader("Деталі найшвидших та найповільніших варок")
                    st.dataframe(product_time_minmax)
        else:
            st.warning("Немає даних для аналізу продуктивності виробництва.")
            
    elif report_type == "Аналіз якості та втрат":
        st.subheader("Аналіз якості та втрат")
        
        if "Відсоток втрат" in filtered_df.columns and not filtered_df.empty:
            # Статистика по потерям
            avg_loss = filtered_df["Відсоток втрат"].mean()
            max_loss = filtered_df["Відсоток втрат"].max()
            min_loss = filtered_df["Відсоток втрат"].min()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Середній відсоток втрат", f"{avg_loss:.2f}%")
            col2.metric("Максимальний відсоток втрат", f"{max_loss:.2f}%")
            col3.metric("Мінімальний відсоток втрат", f"{min_loss:.2f}%")
            
            # Анализ потерь по дням
            daily_loss = filtered_df.groupby(filtered_df["Дата"].dt.date)["Відсоток втрат"].mean().reset_index()
            
            fig_daily = px.line(
                daily_loss,
                x="Дата",
                y="Відсоток втрат",
                title="Динаміка відсотка втрат по днях",
                markers=True
            )
            fig_daily.update_traces(line=dict(width=3, color="#E74C3C"), marker=dict(size=8))
            
            # Добавляем среднюю линию
            fig_daily.add_hline(
                y=avg_loss,
                line_dash="dash",
                line_color="blue",
                annotation_text=f"Середня: {avg_loss:.2f}%",
                annotation_position="top right"
            )
            
            fig_daily.update_layout(
                xaxis_title="Дата",
                yaxis_title="Відсоток втрат (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
            )
            st.plotly_chart(fig_daily, use_container_width=True)
            
            # Анализ втрат по продуктам
            product_loss = filtered_df.groupby("Тип продукту", as_index=False)["Відсоток втрат"].mean()
            product_loss_sorted = product_loss.sort_values("Відсоток втрат", ascending=False)
            
            fig_prod = px.bar(
                product_loss_sorted,
                x="Тип продукту",
                y="Відсоток втрат",
                title="Середній відсоток втрат за типами продукції",
                color="Тип продукту",
                text=round(product_loss_sorted["Відсоток втрат"], 2)
            )
            fig_prod.update_traces(texttemplate='%{text}', textposition='outside')
            fig_prod.add_hline(
                y=avg_loss,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Загальний середній: {avg_loss:.2f}%",
                annotation_position="top right"
            )
            
            # Улучшаем отображение длинных названий продуктов
            max_label_length = 15  # Максимальная длина метки
            product_labels = {}
            for i, product in enumerate(product_loss_sorted["Тип продукту"].unique()):
                if len(product) > max_label_length:
                    short_name = product[:max_label_length] + "..."
                    product_labels[product] = short_name
            
            fig_prod.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Відсоток втрат (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(
                    showgrid=False,
                    tickmode='array',
                    tickvals=list(range(len(product_loss_sorted["Тип продукту"].unique()))),
                    ticktext=[product_labels.get(p, p) for p in product_loss_sorted["Тип продукту"].unique()],
                ),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                height=500,  # Увеличиваем высоту для лучшей читаемости
                margin=dict(b=100)  # Увеличиваем нижний отступ для меток
            )
            st.plotly_chart(fig_prod, use_container_width=True)
            
            # Анализ втрат по оборудованию
            equip_loss = filtered_df.groupby("Тип обладнання", as_index=False)["Відсоток втрат"].mean()
            equip_loss_sorted = equip_loss.sort_values("Відсоток втрат", ascending=False)
            
            fig_equip = px.bar(
                equip_loss_sorted,
                x="Тип обладнання",
                y="Відсоток втрат",
                title="Середній відсоток втрат за типами обладнання",
                color="Тип обладнання",
                text=round(equip_loss_sorted["Відсоток втрат"], 2)
            )
            fig_equip.update_traces(texttemplate='%{text}', textposition='outside')
            fig_equip.add_hline(
                y=avg_loss,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Загальний середній: {avg_loss:.2f}%",
                annotation_position="top right"
            )
            
            # Улучшаем отображение длинных названий оборудования
            max_label_length = 15  # Максимальная длина метки
            equipment_labels = {}
            for i, equipment in enumerate(equip_loss_sorted["Тип обладнання"].unique()):
                if len(equipment) > max_label_length:
                    short_name = equipment[:max_label_length] + "..."
                    equipment_labels[equipment] = short_name
            
            fig_equip.update_layout(
                xaxis_title="Тип обладнання",
                yaxis_title="Відсоток втрат (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(
                    showgrid=False,
                    tickmode='array',
                    tickvals=list(range(len(equip_loss_sorted["Тип обладнання"].unique()))),
                    ticktext=[equipment_labels.get(p, p) for p in equip_loss_sorted["Тип обладнання"].unique()],
                ),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                height=500,  # Увеличиваем высоту для лучшей читаемости
                margin=dict(b=100)  # Увеличиваем нижний отступ для меток
            )
            st.plotly_chart(fig_equip, use_container_width=True)
            
            # Боксплот распределения втрат по типам продукции
            fig_box = px.box(
                filtered_df,
                x="Тип продукту",
                y="Відсоток втрат",
                color="Тип продукту",
                title="Розподіл відсотка втрат за типами продукції",
                points="all"
            )
            
            # Улучшаем отображение длинных названий продуктов
            max_label_length = 15  # Максимальная длина метки
            product_labels = {}
            for i, product in enumerate(filtered_df["Тип продукту"].unique()):
                if len(product) > max_label_length:
                    short_name = product[:max_label_length] + "..."
                    product_labels[product] = short_name
            
            fig_box.update_layout(
                xaxis_title="Тип продукту",
                yaxis_title="Відсоток втрат (%)",
                plot_bgcolor='rgba(240,240,240,0.8)',
                xaxis=dict(
                    showgrid=False,
                    tickmode='array',
                    tickvals=list(range(len(filtered_df["Тип продукту"].unique()))),
                    ticktext=[product_labels.get(p, p) for p in filtered_df["Тип продукту"].unique()],
                ),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                height=500,  # Увеличиваем высоту для лучшей читаемости
                margin=dict(b=100)  # Увеличиваем нижний отступ для меток
            )
            st.plotly_chart(fig_box, use_container_width=True)
            
            # Дивіантність варок для конкретного продукта (если выбран)
            if "Усі" not in selected_products and len(selected_products) == 1:
                product_deviant = selected_products[0]
                st.subheader(f"Дивіантність варок для продукту: {product_deviant}")
                
                product_df = filtered_df[filtered_df["Тип продукту"] == product_deviant]
                if not product_df.empty and "Час на операцію" in product_df.columns:
                    fastest = product_df.loc[product_df["Час на операцію"].idxmin()]
                    slowest = product_df.loc[product_df["Час на операцію"].idxmax()]
                    # Расчет средней и стандартного отклонения
                    mean_time = product_df["Час на операцію"].mean()
                    std_time = product_df["Час на операцію"].std()
                    upper_limit = mean_time + 2 * std_time
                    lower_limit = max(mean_time - 2 * std_time, 0)  # Не меньше нуля
                
                    fig_scatter = px.scatter(
                        product_df,
                        x="Дата",
                        y="Час на операцію",
                        hover_data=["ПІБ", "Тип обладнання"],
                        title=f"Порівняння варок за часом для продукту: {product_deviant}",
                        labels={"Час на операцію": "Час операції (хв)"},
                        color_discrete_sequence=["#3498DB"]
                    )
                
                    # Добавляем полосы для стандартных отклонений
                    fig_scatter.add_hline(
                        y=mean_time, 
                        line_dash="solid", 
                        line_color="#2C3E50",
                        line_width=2,
                        annotation_text=f"Середній час: {mean_time:.1f} хв",
                        annotation_position="top right"
                    )
                    fig_scatter.add_hline(
                        y=upper_limit, 
                        line_dash="dot", 
                        line_color="#E74C3C",
                        annotation_text="+2σ",
                        annotation_position="top right"
                    )
                    fig_scatter.add_hline(
                        y=lower_limit, 
                        line_dash="dot", 
                        line_color="#2ECC71",
                        annotation_text="-2σ",
                        annotation_position="top right"
                    )
                    
                    fig_scatter.add_scatter(
                        x=[fastest["Дата"]],
                        y=[fastest["Час на операцію"]],
                        mode="markers",
                        marker=dict(size=15, color="#2ECC71", symbol="star-triangle-up"),
                        name="Найшвидша варка"
                    )
                    
                    fig_scatter.add_scatter(
                        x=[slowest["Дата"]],
                        y=[slowest["Час на операцію"]],
                        mode="markers",
                        marker=dict(size=15, color="#E74C3C", symbol="star-triangle-down"),
                        name="Найповільніша варка"
                    )
                    
                    fig_scatter.update_layout(
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("Немає даних для аналізу якості та втрат.")
