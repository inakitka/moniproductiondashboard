# moniproductiondashboard

# Cosmetic Dashboard

Дашборд для отображения производственной отчетности косметической компании. Приложение разработано с использованием Streamlit и получает данные из Google Sheets.

## Функциональность

- Визуализация производственных данных
- Анализ потерь и эффективности производства
- Фильтрация по датам и категориям
- Интерактивные графики с использованием Plotly

## Установка и запуск

1. Клонировать репозиторий:
   ```
   git clone https://github.com/inakitka/moniproductiondashboard.git
   cd moniproductiondashboard
   ```

2. Установить зависимости:
   ```
   pip install -r requirements.txt
   ```

3. Настроить доступ к Google Sheets:
   - Создайте файл `.streamlit/secrets.toml` с учетными данными сервисного аккаунта Google
   - Формат файла:
     ```
     [gcp_service_account]
     type = "service_account"
     project_id = "ваш-project-id"
     private_key_id = "ваш-private-key-id"
     private_key = "ваш-private-key"
     client_email = "ваш-client-email"
     client_id = "ваш-client-id"
     auth_uri = "https://accounts.google.com/o/oauth2/auth"
     token_uri = "https://oauth2.googleapis.com/token"
     auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
     client_x509_cert_url = "ваш-client-x509-cert-url"
     ```

4. Запустить приложение:
   ```
   streamlit run app.py
   ```

## Онлайн-доступ

Статическая версия приложения доступна по адресу: https://inakitka.github.io/moniproductiondashboard/

Для полноценной работы с данными рекомендуется запускать приложение локально, следуя инструкциям выше. 