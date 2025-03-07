import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------
# Налаштування підключення до Google Sheets
# ---------------------------
SHEET_ID = "1cbQtfwOR32_J7sIGuZnqmEINKrc1hqcAwAZVmOADPMA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
service = build("sheets", "v4", credentials=credentials)

# ---------------------------
# Функція для перетворення числових колонок
# ---------------------------
def convert_numeric_columns(df, columns):
    """
    Перетворює строкові колонки в числові, замінюючи коми на крапки.
    """
    for col in columns:
        if col in df.columns:
            if df[col].dtype == object:  # Якщо колонка строкова
                df[col] = df[col].apply(lambda x: str(x).replace(",", ".") if isinstance(x, str) else x)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ---------------------------
# Функція загрузки даних для відділу ФАСОВКА
# ---------------------------
@st.cache_data
def load_facovka_data(sheet_name):
    try:
        # Отримуємо дані з вказаного листа
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=sheet_name
        ).execute()
        values = result.get("values", [])
        if not values:
            st.error("Помилка завантаження даних!")
            return pd.DataFrame()
        
        # Створюємо DataFrame, пропускаючи першу строку з заголовками
        df = pd.DataFrame(values[1:], columns=values[0])
        df.columns = df.columns.str.strip()
        
        # Для листа ФАСОВКА стовпці:
        # A - Номер, B - Позиція (Entry Number), C - ПІБ, D - Тип обладнання, 
        # E - Час на операцію, F - Продуктивність за годину, G - Відсоток браку,
        # H - Кількість операторів, I - Тип продукту, J - Об'єм,
        # K - День, L - Місяць, M - Рік
    
        # Переіменуємо стовпець B якщо він є
        if len(df.columns) > 1 and df.columns[1] not in ["ПІБ", "Позиція"]:
            df.rename(columns={df.columns[1]: "Позиція"}, inplace=True)
    
        # Створюємо стовпець "Дата" на основі K, L, M:
        if set(["День", "Місяць", "Рік"]).issubset(df.columns):
            try:
                df["Дата"] = pd.to_datetime(
                    df["День"].astype(str) + "." + df["Місяць"].astype(str) + "." + df["Рік"].astype(str),
                    format="%d.%m.%Y", errors="coerce"
                )
            except Exception as e:
                st.warning(f"Помилка при створенні стовпця 'Дата': {str(e)}")
        
        # Перетворюємо числові стовпці
        numeric_cols = ["Час на операцію", "Продуктивність за годину", "Відсоток браку", "Кількість операторів"]
        df = convert_numeric_columns(df, numeric_cols)
        
        # Конвертація об'єму якщо це можливо (видалити "мл")
        if "Об'єм" in df.columns:
            try:
                # Улучшене регулярне вираз для вилучення чисел, в тому числі з десятковою точкою
                df["Об'єм_число"] = df["Об'єм"].str.extract(r'(\d+(?:\.\d+)?)').astype(float)
            except Exception:
                st.warning("Не вдалося розпізнати числові значення об'єму")
        
        return df
    except Exception as e:
        st.error(f"Помилка завантаження даних: {str(e)}")
        return pd.DataFrame()

# ---------------------------
# Функція для отримання дат за пресетами
# ---------------------------
def get_preset_dates(preset):
    today = date.today()
    
    if preset == "Цей тиждень":
        # Понеділок поточного тижня
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif preset == "Цей місяць":
        # Перший день поточного місяця
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif preset == "Минулий тиждень":
        # Понеділок минулого тижня
        start_date = today - timedelta(days=today.weekday() + 7)
        # Неділя минулого тижня
        end_date = start_date + timedelta(days=6)
    elif preset == "Минулий місяць":
        # Перший день минулого місяця
        if today.month == 1:
            start_date = date(today.year - 1, 12, 1)
            end_date = date(today.year - 1, 12, 31)
        else:
            start_date = date(today.year, today.month - 1, 1)
            # Останній день минулого місяця
            last_day = calendar.monthrange(today.year, today.month - 1)[1]
            end_date = date(today.year, today.month - 1, last_day)
    else:  # За замовчуванням - поточний тиждень
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    
    return start_date, end_date

# ---------------------------
# Функція для підрахунку робочих днів (понеділок-п'ятниця)
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
# Загрузка даних з листа "ФАСОВКА"
# ---------------------------
facovka_df = load_facovka_data("ФАСОВКА")

if facovka_df.empty:
    st.warning("Дані відсутні або не завантажені.")
else:
    # ---------------------------
    # Бокова панель: вибір типу звіту та фільтри
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
    
    # Фільтр за періодом - пресети або користувацький вибір
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
        start_date = date_cols[0].date_input("Початок періоду", min_date, min_value=min_date, max_value=max_date)
        end_date = date_cols[1].date_input("Кінець періоду", max_date, min_value=min_date, max_value=max_date)
    
    if start_date > end_date:
        st.sidebar.error("Початок періоду не може бути пізніше, ніж кінець.")
        filtered_df = pd.DataFrame()
    else:
        filtered_df = facovka_df[(facovka_df["Дата"] >= pd.to_datetime(start_date)) & 
                                (facovka_df["Дата"] <= pd.to_datetime(end_date))]
    
    # Додаткові фільтри
    st.sidebar.markdown("---")
    
    # Фільтр по продукту (якщо є дані)
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
    
    # Фільтр по обладнанню
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
    
    # Фільтр по співробітнику
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
    # Контент в залежності від вибраного звіту
    # ---------------------------
    
    # Заголовок сторінки
    st.title("📊 Виробнича звітність - Фасовка")
    st.markdown("---")
    
    # Загальні KPI для всіх звітів
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
    
    # Звіт - Загальний огляд
    if report_type == "Загальний огляд":
        st.subheader("Огляд ключових показників")
        
        # Графік трендів по днях
        if not filtered_df.empty:
            # Формуємо словника агрегацій тільки для стовпців, які існують
            agg_dict = {}
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Відсоток браку" in filtered_df.columns:
                agg_dict["Відсоток браку"] = "mean"
            
            # Для підрахунку кількості операцій використовуємо size()
            trend_count = filtered_df.groupby("Дата").size().reset_index(name="Кількість операцій")
            
            # Якщо є інші метрики, додаємо їх
            if agg_dict:
                trend_metrics = filtered_df.groupby("Дата", as_index=False).agg(agg_dict)
                # Об'єднуємо результати
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
        
        # Розподіл по продуктам та обладнанню
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
    
    # Звіт - Аналіз ефективності операторів
    elif report_type == "Аналіз ефективності операторів":
        st.subheader("Аналіз ефективності операторів")
        
        if not filtered_df.empty and "ПІБ" in filtered_df.columns:
            # Агрегація даних по операторам
            # Перевіряємо наявність стовпців перед агрегацією
            agg_dict = {}
            
            # Використовуємо size() для підрахунку кількості записів
            operator_count = filtered_df.groupby("ПІБ").size().reset_index(name="Кількість операцій")
            
            # Агрегуємо інші числові показники, якщо вони є
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Відсоток браку" in filtered_df.columns:
                agg_dict["Відсоток браку"] = "mean"
            
            if agg_dict:
                operator_metrics = filtered_df.groupby("ПІБ", as_index=False).agg(agg_dict)
                # Об'єднуємо результати
                operator_stats = pd.merge(operator_count, operator_metrics, on="ПІБ", how="left")
            else:
                operator_stats = operator_count
            
            # Сортування по продуктивності (якщо колонка є)
            if "Продуктивність за годину" in operator_stats.columns:
                operator_stats_prod = operator_stats.sort_values("Продуктивність за годину", ascending=False)
                
                # Графік продуктивності
                fig_prod = px.bar(
                    operator_stats_prod,
                    x="ПІБ",
                    y="Продуктивність за годину",
                    title="Середня продуктивність операторів (од/год)",
                    color="ПІБ",
                    text=round(operator_stats_prod["Продуктивність за годину"], 0)
                )
            else:
                # Якщо немає даних про продуктивність, використовуємо кількість операцій
                operator_stats_prod = operator_stats.sort_values("Кількість операцій", ascending=False)
                
                # Графік кількості операцій замість продуктивності
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
            
            # Час на операцію
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
            
            # Таблиця для сводки
            st.subheader("Зведена таблиця показників операторів")
            st.dataframe(operator_stats.style.highlight_max(subset=["Продуктивність за годину"], color='lightgreen')
                        .highlight_min(subset=["Час на операцію"], color='lightgreen')
                        .highlight_min(subset=["Відсоток браку"], color='lightgreen'))
            
            # Аналіз найкращих операторів
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
    
    # Звіт - Завантаження обладнання
    elif report_type == "Завантаження обладнання":
        st.subheader("Аналіз завантаження обладнання")
        
        if "Тип обладнання" in filtered_df.columns and not filtered_df.empty:
            # Розрахунок очікуваних робочих днів
            working_days = count_working_days(start_date, end_date)
            expected_minutes = working_days * 480  # 8 годин * 60 хвилин
            
            # Загальна статистика по обладнанню
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
            
            # Відображення повної таблиці
            st.dataframe(equipment_df)
            
            # Візуалізація завантаження обладнання по днях
            equipment_df_sorted = equipment_df.copy()
            try:
                equipment_df_sorted["Завантаженість (дні), %"] = equipment_df_sorted["Завантаженість (дні), %"].str.rstrip("%").astype(float)
            except Exception:
                # Якщо перетворення не вдалося, використовуємо оригінальні значення
                st.warning("Помилка при перетворенні відсотків завантаженості в числа")
                # Створюємо числову колонку напрямую з day_util_pct
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
            
            # Аналіз продуктивності по типам обладнання
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
            
            # Теплова карта обладнання по днях
            if not filtered_df.empty:
                eq_daily = filtered_df.groupby([filtered_df["Дата"].dt.date, "Тип обладнання"]).size().reset_index(name="Операцій")
                eq_daily_pivot = eq_daily.pivot(index="Дата", columns="Тип обладнання", values="Операцій").fillna(0)

                # Перетворення в формат для heatmap
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
    
    # Звіт - Продуктивність виробництва
    elif report_type == "Продуктивність виробництва":
        st.subheader("Аналіз продуктивності виробництва")
        
        if not filtered_df.empty:
            # KPI для продуктивності
            total_volume = filtered_df["Об'єм_число"].sum() if "Об'єм_число" in filtered_df.columns else 0
            avg_operators = filtered_df["Кількість операторів"].mean() if "Кількість операторів" in filtered_df.columns else 0
            
            # Розрахунок часових показників
            days_in_period = (end_date - start_date).days + 1
            working_days = count_working_days(start_date, end_date)
            
            # Розрахунок продуктивності
            daily_prod = total_volume / days_in_period if days_in_period > 0 else 0
            working_day_prod = total_volume / working_days if working_days > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Загальний об'єм виробництва", f"{total_volume:.0f} одиниць")
            col2.metric("Середня денна продуктивність", f"{daily_prod:.1f} од/день")
            col3.metric("Продуктивність у робочі дні", f"{working_day_prod:.1f} од/день")
            
            # Аналіз продуктивності по днях
            # Формуємо словника агрегацій тільки для стовпців, які існують
            agg_dict = {}
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "sum"
            if "Об'єм_число" in filtered_df.columns:
                agg_dict["Об'єм_число"] = "sum"
            
            # Для підрахунку кількості операцій використовуємо size()
            daily_count = filtered_df.groupby(filtered_df["Дата"].dt.date).size().reset_index(name="Кількість операцій")
            
            # Якщо є інші метрики, додаємо їх
            if agg_dict:
                daily_metrics = filtered_df.groupby(filtered_df["Дата"].dt.date).agg(agg_dict).reset_index()
                # Об'єднуємо результати
                daily_data = pd.merge(daily_count, daily_metrics, on="Дата", how="left")
            else:
                daily_data = daily_count
            
            # Візуалізація продуктивності по днях
            fig_daily = px.bar(
                daily_data,
                x="Дата",
                y="Об'єм_число",
                title="Денна продуктивність (об'єм виробництва)",
                labels={"Об'єм_число": "Об'єм виробництва", "Дата": "Дата"},
                text=daily_data["Об'єм_число"].round(0)
            )
            fig_daily.update_traces(texttemplate='%{text}', textposition='outside')
            
            # Додаємо середню лінію
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
            
            # Аналіз продуктивності по типам продукції
            # Формуємо словника агрегацій тільки для стовпців, які існують
            agg_dict = {}
            if "Продуктивність за годину" in filtered_df.columns:
                agg_dict["Продуктивність за годину"] = "mean"
            if "Час на операцію" in filtered_df.columns:
                agg_dict["Час на операцію"] = "mean"
            if "Об'єм_число" in filtered_df.columns:
                agg_dict["Об'єм_число"] = "sum"
            
            # Для підрахунку кількості операцій використовуємо size()
            product_count = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість операцій")
            
            # Якщо є інші метрики, додаємо їх
            if agg_dict:
                product_metrics = filtered_df.groupby("Тип продукту", as_index=False).agg(agg_dict)
                # Об'єднуємо результати
                product_perf = pd.merge(product_count, product_metrics, on="Тип продукту", how="left")
            else:
                product_perf = product_count
            
            # Сортування по продуктивності
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
            # Улучшаємо відображення довгих назв продуктів
            max_label_length = 15  # Максимальна довжина мітки
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
                height=500,  # Увеличуємо висоту для кращої читаності
                margin=dict(b=100)  # Увеличуємо нижній відступ для міток
            )
            st.plotly_chart(fig_prod_eff, use_container_width=True)
            
            # Таблиця продуктивності по типам продукції
            st.subheader("Продуктивність за типами продукції")
            st.dataframe(product_perf.style.highlight_max(subset=["Продуктивність за годину"], color='lightgreen')
                         .highlight_min(subset=["Час на операцію"], color='lightgreen'))
            
            # Новий звіт: Найшвидші та найповільніші фасовки по типам продукта
            if "Час на операцію" in filtered_df.columns:
                st.subheader("Найшвидші та найповільніші фасовки за типами продукту")
                
                # Створюємо DataFrame для зберігання мінімального та максимального часу операції
                product_time_minmax = pd.DataFrame()
                
                # Для кожного типу продукта знаходимо мінімальне та максимальне час
                for product_type in filtered_df["Тип продукту"].unique():
                    product_data = filtered_df[filtered_df["Тип продукту"] == product_type]
                    if len(product_data) > 0:
                        # Отримуємо дані для найшвидшої та найповільнішої фасовки
                        fastest = product_data.loc[product_data["Час на операцію"].idxmin()]
                        slowest = product_data.loc[product_data["Час на операцію"].idxmax()]
                        
                        # Додаємо дані в DataFrame
                        product_time_minmax = pd.concat([product_time_minmax, pd.DataFrame({
                            "Тип продукту": [product_type, product_type],
                            "Категорія": ["Найшвидша", "Найповільніша"],
                            "Час на операцію": [fastest["Час на операцію"], slowest["Час на операцію"]],
                            "Дата": [fastest["Дата"], slowest["Дата"]],
                            "ПІБ": [fastest["ПІБ"], slowest["ПІБ"]] if "ПІБ" in fastest else ["", ""],
                            "Тип обладнання": [fastest["Тип обладнання"], slowest["Тип обладнання"]] if "Тип обладнання" in fastest else ["", ""],
                            "Продуктивність за годину": [fastest["Продуктивність за годину"], slowest["Продуктивність за годину"]] if "Продуктивність за годину" in fastest else [0, 0]
                        })])
                
                # Якщо є дані, будуємо візуалізацію
                if len(product_time_minmax) > 0:
                    # Створюємо стовпчикову діаграму зі сгрупованими стовпцями
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
                    
                    # Додаємо мітки зі значеннями
                    fig_minmax.update_traces(texttemplate='%{y:.1f}', textposition='outside')
                    
                    # Улучшаємо відображення довгих назв продуктів
                    # Замість нахилу тексту використовуємо скорочення з повною інформацією при наведенні
                    max_label_length = 15  # Максимальна довжина мітки на осі X
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
                        height=500,  # Увеличуємо висоту для кращої читаності
                        margin=dict(b=100)  # Увеличуємо нижній відступ для міток
                    )
                    st.plotly_chart(fig_minmax, use_container_width=True)
                    
                    # Таблиця з деталями
                    st.subheader("Деталі найшвидших та найповільніших фасовок")
                    st.dataframe(product_time_minmax)
            
            # Співвідношення часу операції до продуктивності
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
            
            # Додаємо лінію тренда
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
    
    # Звіт - Аналіз якості та браку
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
            
            # Аналіз браку по днях
            daily_defect = filtered_df.groupby(filtered_df["Дата"].dt.date)["Відсоток браку"].mean().reset_index()
            
            fig_daily = px.line(
                daily_defect,
                x="Дата",
                y="Відсоток браку",
                title="Динаміка відсотка браку по днях",
                markers=True
            )
            fig_daily.update_traces(line=dict(width=3, color="#E74C3C"), marker=dict(size=8))
            
            # Додаємо середню лінію
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
            
            # Аналіз браку по продуктам
            # Підрахунок операцій з використанням size()
            product_count = filtered_df.groupby("Тип продукту").size().reset_index(name="Кількість операцій")
            
            # Агрегуємо середній відсоток браку
            product_defect_mean = filtered_df.groupby("Тип продукту", as_index=False)["Відсоток браку"].mean()
            
            # З'єднуємо результати
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
            
            # Аналіз браку по обладнанню
            # Підрахунок операцій з використанням size()
            equip_count = filtered_df.groupby("Тип обладнання").size().reset_index(name="Кількість операцій")
            
            # Агрегуємо середній відсоток браку
            equip_defect_mean = filtered_df.groupby("Тип обладнання", as_index=False)["Відсоток браку"].mean()
            
            # З'єднуємо результати
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
            
            # Аналіз браку по операторам
            # Підрахунок операцій з використанням size()
            operator_count = filtered_df.groupby("ПІБ").size().reset_index(name="Кількість операцій")
            
            # Агрегуємо середній відсоток браку
            operator_defect_mean = filtered_df.groupby("ПІБ", as_index=False)["Відсоток браку"].mean()
            
            # З'єднуємо результати
            operator_defect = pd.merge(operator_count, operator_defect_mean, on="ПІБ", how="left")
            operator_defect_sorted = operator_defect.sort_values("Відсоток браку", ascending=False)
            
            # Діаграма браку по операторам
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
            
            # Боксплот розподілу браку по типам продукції
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