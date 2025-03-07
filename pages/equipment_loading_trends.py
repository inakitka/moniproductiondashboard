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
# Функции для загрузки данных из Google Sheets
# ---------------------------
@st.cache_data
def load_data(sheet_name):
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SHEET_ID, range=sheet_name).execute()
        values = result.get("values", [])
        if not values:
            st.error(f"Помилка завантаження даних з листа {sheet_name}!")
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
        for col in numeric_cols:
            if col in df.columns:
                if df[col].dtype == object:  # Если колонка строковая
                    df[col] = df[col].astype(str).str.replace(",", ".")
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                else:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Обработка процентов
        percent_cols = ["Відсоток втрат", "Відсоток браку"]
        for col in percent_cols:
            if col in df.columns:
                if df[col].dtype == object:  # Если колонка строковая
                    df[col] = df[col].astype(str).str.replace(",", ".")
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                else:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df
    except Exception as e:
        st.error(f"Помилка завантаження даних: {str(e)}")
        return pd.DataFrame()

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
# Настройка страницы
# ---------------------------
st.set_page_config(
    page_title="Тренд завантаження обладнання",
    page_icon="📈",
    layout="wide",
)

# ---------------------------
# Загрузка данных
# ---------------------------
cooking_df = load_data("варка")
packaging_df = load_data("ФАСОВКА")

if cooking_df.empty and packaging_df.empty:
    st.warning("Дані відсутні або не завантажені.")
else:
    # ---------------------------
    # Заголовок страницы
    # ---------------------------
    st.title("📈 Тренд завантаження обладнання")
    st.markdown("---")
    
    # ---------------------------
    # Выбор отдела и периода
    # ---------------------------
    dept_options = []
    if not cooking_df.empty:
        dept_options.append("Варка")
    if not packaging_df.empty:
        dept_options.append("Фасовка")
    if not dept_options:
        st.warning("Немає доступних відділів з даними")
    else:
        col1, col2 = st.columns([1, 3])
        
        with col1:
            # Выбор отдела
            selected_dept = st.radio("Оберіть відділ:", dept_options)
            
            # Выбор временного интервала
            interval_options = ["День", "Тиждень", "Місяць"]
            selected_interval = st.radio("Часовий інтервал:", interval_options)
            
            # Выбор периода дат
            min_date = date.today() - timedelta(days=365)  # 1 год назад по умолчанию
            max_date = date.today()
            
            df = cooking_df if selected_dept == "Варка" else packaging_df
            
            if not df.empty and "Дата" in df.columns:
                if pd.notnull(df["Дата"].min()) and pd.notnull(df["Дата"].max()):
                    min_date = max(min_date, df["Дата"].min().date())
                    max_date = min(max_date, df["Дата"].max().date())
            
            date_range = st.date_input(
                "Виберіть період:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                if start_date > end_date:
                    st.error("Дата початку не може бути пізніше дати кінця")
            else:
                start_date = min_date
                end_date = max_date
            
            # Фильтр для оборудования
            if selected_dept == "Варка":
                df = cooking_df
                dept_name = "варка"
            else:
                df = packaging_df
                dept_name = "фасовка"
            
            filtered_df = df[(df["Дата"] >= pd.to_datetime(start_date)) & 
                            (df["Дата"] <= pd.to_datetime(end_date))]
            
            unique_equipment = sorted(filtered_df["Тип обладнання"].dropna().unique().tolist())
            if unique_equipment:
                all_equipment = ["Усі"] + unique_equipment
                selected_equipment = st.multiselect(
                    "Оберіть обладнання:", 
                    options=all_equipment, 
                    default=["Усі"]
                )
                if "Усі" not in selected_equipment:
                    filtered_df = filtered_df[filtered_df["Тип обладнання"].isin(selected_equipment)]
            else:
                st.warning(f"Немає доступного обладнання для відділу {selected_dept} за вибраний період")
        
        with col2:
            if not filtered_df.empty:
                # Подготовка данных в зависимости от выбранного интервала
                if selected_interval == "День":
                    # Группировка данных по дням
                    time_unit = 'D'
                    date_format = '%d.%m.%Y'
                    label = "за днями"
                elif selected_interval == "Тиждень":
                    # Группировка данных по неделям
                    time_unit = 'W-MON'  # Начало недели с понедельника
                    date_format = '%d.%m.%Y'
                    label = "за тижнями"
                else:  # Месяц
                    # Группировка данных по месяцам
                    time_unit = 'M'
                    date_format = '%m.%Y'
                    label = "за місяцями"
                
                # Группировка данных по интервалу для подсчета количества операций
                filtered_df['Період'] = filtered_df['Дата'].dt.to_period(time_unit)
                operations_by_period = filtered_df.groupby(['Період', 'Тип обладнання']).size().reset_index(name='Кількість операцій')
                
                # Преобразуем период в datetime для графика
                operations_by_period['Дата'] = operations_by_period['Період'].dt.to_timestamp()
                
                # ---------------------------
                # Анализ загрузки оборудования
                # ---------------------------
                st.subheader(f"Тренд завантаження обладнання: {selected_dept} {label}")
                
                # Расчет рабочих дней и часов для каждого периода
                period_stats = []
                
                for period in operations_by_period['Період'].unique():
                    if selected_interval == "День":
                        # Для дневного интервала - один день
                        period_start = period.start_time.date()
                        period_end = period.start_time.date()
                    elif selected_interval == "Тиждень":
                        # Для недельного интервала - с понедельника по воскресенье
                        period_start = period.start_time.date()
                        period_end = (period.start_time + timedelta(days=6)).date()
                    else:  # Месяц
                        # Для месячного интервала - с первого по последнее число месяца
                        period_start = period.start_time.date()
                        last_day = calendar.monthrange(period_start.year, period_start.month)[1]
                        period_end = date(period_start.year, period_start.month, last_day)
                    
                    # Подсчет рабочих дней в периоде
                    working_days = count_working_days(period_start, period_end)
                    expected_minutes = working_days * 480  # 8 часов * 60 минут
                    
                    # Фильтрация данных для текущего периода
                    period_data = filtered_df[filtered_df['Період'] == period]
                    
                    # Расчет по оборудованию
                    for equip, group in period_data.groupby('Тип обладнання'):
                        # Подсчет уникальных дней работы оборудования
                        distinct_days = group['Дата'].dt.date.nunique()
                        operations_count = len(group)
                        total_minutes = group['Час на операцію'].sum() if 'Час на операцію' in group.columns else 0
                        
                        # Расчет загрузки
                        day_util_pct = (distinct_days / working_days) * 100 if working_days > 0 else 0
                        minutes_util_pct = (total_minutes / expected_minutes) * 100 if expected_minutes > 0 else 0
                        
                        period_stats.append({
                            'Період': period,
                            'Дата': period.start_time,
                            'Тип обладнання': equip,
                            'Робочі дні у періоді': working_days,
                            'Дні роботи обладнання': distinct_days,
                            'Завантаженість (дні), %': day_util_pct,
                            'Загальний час роботи (хв)': total_minutes,
                            'Плановий час роботи (хв)': expected_minutes,
                            'Завантаженість (час), %': minutes_util_pct,
                            'Кількість операцій': operations_count
                        })
                
                period_stats_df = pd.DataFrame(period_stats)
                
                # Расчет выработки (количество произведенных штук)
                # Выработка = средняя продуктивность за заказ * количество часов работы
                has_productivity_data = 'Продуктивність за годину' in filtered_df.columns
                
                if has_productivity_data:
                    # Для каждого периода и типа оборудования рассчитываем выработку
                    for index, row in period_stats_df.iterrows():
                        period = row['Період']
                        equipment = row['Тип обладнання']
                        total_minutes = row['Загальний час роботи (хв)']
                        
                        # Фильтруем данные для текущего периода и оборудования
                        equipment_data = filtered_df[
                            (filtered_df['Період'] == period) & 
                            (filtered_df['Тип обладнання'] == equipment)
                        ]
                        
                        # Средняя продуктивность в час
                        avg_productivity = equipment_data['Продуктивність за годину'].mean()
                        
                        # Выработка = продуктивность в час * время работы в часах
                        production_units = avg_productivity * (total_minutes / 60)
                        
                        # Обновляем DataFrame
                        period_stats_df.at[index, 'Виробіток (шт)'] = production_units
                
                # ---------------------------
                # Создание графиков
                # ---------------------------
                # Вкладки для разных графиков
                tab_options = ["Кількість операцій", "Завантаженість (дні), %", "Завантаженість (час), %"]
                if has_productivity_data:
                    tab_options.append("Виробіток (шт)")
                tabs = st.tabs(tab_options)
                
                with tabs[0]:
                    # График количества операций
                    fig_ops = px.line(
                        operations_by_period,
                        x='Дата',
                        y='Кількість операцій',
                        color='Тип обладнання',
                        title=f"Кількість операцій на обладнанні ({selected_dept}) {label}",
                        markers=True
                    )
                    fig_ops.update_layout(
                        xaxis_title="Період",
                        yaxis_title="Кількість операцій",
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                    )
                    st.plotly_chart(fig_ops, use_container_width=True)
                
                with tabs[1]:
                    # График загрузки по дням
                    fig_days = px.line(
                        period_stats_df,
                        x='Дата',
                        y='Завантаженість (дні), %',
                        color='Тип обладнання',
                        title=f"Завантаженість обладнання (дні) ({selected_dept}) {label}",
                        markers=True
                    )
                    fig_days.add_hline(
                        y=100, 
                        line_dash="dash", 
                        line_color="red", 
                        annotation_text="Макс. завантаженість"
                    )
                    fig_days.update_layout(
                        xaxis_title="Період",
                        yaxis_title="Завантаженість (%)",
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)', range=[0, 110])
                    )
                    st.plotly_chart(fig_days, use_container_width=True)
                
                with tabs[2]:
                    # График загрузки по времени
                    fig_time = px.line(
                        period_stats_df,
                        x='Дата',
                        y='Завантаженість (час), %',
                        color='Тип обладнання',
                        title=f"Завантаженість обладнання (час) ({selected_dept}) {label}",
                        markers=True
                    )
                    fig_time.add_hline(
                        y=100, 
                        line_dash="dash", 
                        line_color="red", 
                        annotation_text="Макс. завантаженість"
                    )
                    fig_time.update_layout(
                        xaxis_title="Період",
                        yaxis_title="Завантаженість (%)",
                        plot_bgcolor='rgba(240,240,240,0.8)',
                        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)', range=[0, 110])
                    )
                    st.plotly_chart(fig_time, use_container_width=True)
                
                # Вкладка выработки отображается только если есть данные о продуктивности
                if has_productivity_data and len(tabs) > 3:
                    with tabs[3]:
                        if 'Виробіток (шт)' in period_stats_df.columns:
                            # Округляем выработку для отображения
                            period_stats_df['Виробіток (шт)'] = period_stats_df['Виробіток (шт)'].round(0)
                            
                            # График выработки (произведенных штук)
                            fig_prod = px.line(
                                period_stats_df,
                                x='Дата',
                                y='Виробіток (шт)',
                                color='Тип обладнання',
                                title=f"Виробіток (шт) на обладнанні ({selected_dept}) {label}",
                                markers=True
                            )
                            fig_prod.update_layout(
                                xaxis_title="Період",
                                yaxis_title="Виробіток (шт)",
                                plot_bgcolor='rgba(240,240,240,0.8)',
                                xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)'),
                                yaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(220,220,220,0.8)')
                            )
                            
                            # Добавляем аннотации со значениями точек
                            for i, row in period_stats_df.iterrows():
                                fig_prod.add_annotation(
                                    x=row['Дата'],
                                    y=row['Виробіток (шт)'],
                                    text=f"{int(row['Виробіток (шт)'])}",
                                    showarrow=False,
                                    yshift=10,
                                    font=dict(size=10)
                                )
                            
                            st.plotly_chart(fig_prod, use_container_width=True)
                        else:
                            st.warning("Немає даних про продуктивність для розрахунку виробітку")
                
                # ---------------------------
                # Таблица с детальными данными
                # ---------------------------
                st.subheader("Детальні дані по завантаженості обладнання")
                detailed_df = period_stats_df.copy()
                
                # Форматирование данных для отображения
                detailed_df['Дата'] = detailed_df['Дата'].dt.strftime(date_format)
                detailed_df['Завантаженість (дні), %'] = detailed_df['Завантаженість (дні), %'].round(1)
                detailed_df['Завантаженість (час), %'] = detailed_df['Завантаженість (час), %'].round(1)
                
                # Выбор и сортировка колонок для отображения
                display_cols = [
                    'Дата', 'Тип обладнання', 'Кількість операцій', 
                    'Дні роботи обладнання', 'Робочі дні у періоді', 'Завантаженість (дні), %',
                    'Загальний час роботи (хв)', 'Плановий час роботи (хв)', 'Завантаженість (час), %'
                ]
                
                # Добавляем колонку выработки, если она есть
                if has_productivity_data and 'Виробіток (шт)' in period_stats_df.columns:
                    # Округляем выработку для отображения в таблице
                    detailed_df['Виробіток (шт)'] = detailed_df['Виробіток (шт)'].round(0).astype(int)
                    display_cols.append('Виробіток (шт)')
                detailed_df = detailed_df[display_cols].sort_values(['Дата', 'Тип обладнання'])
                
                # Показываем таблицу с данными
                st.dataframe(detailed_df)
            else:
                st.warning(f"Немає даних для відділу {selected_dept} за вибраний період")