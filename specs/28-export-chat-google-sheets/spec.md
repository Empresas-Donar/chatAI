# Spec: Exportar datos del Chat IA a Google Sheets

## Qué

Cuando el Chat IA devuelve una tabla de datos, aparece un botón "Google Sheets" junto a los botones
de Excel y PDF existentes. Al hacer clic, se crea un Google Sheet en el Drive del usuario y se abre
en una nueva pestaña.

## Criterios de aceptación

- [ ] Aparece un botón "Google Sheets" junto a los botones de Excel y PDF en la barra de descarga del chat
- [ ] Al hacer login con Google, se solicitan los scopes `drive.file` y `spreadsheets` adicionales
- [ ] El `access_token` de Google se guarda en una cookie firmada `donar_gtoken` (mismo mecanismo que `donar_session`)
- [ ] El endpoint `POST /chat/export-sheets` re-ejecuta el SQL, crea el Sheet en el Drive del usuario via `gspread` y retorna la URL
- [ ] El frontend abre la URL del Sheet en una nueva pestaña
- [ ] Si el usuario no tiene token de Google, el endpoint retorna HTTP 401

## Contexto

### Flujo técnico

1. Al hacer login con Google OAuth, se piden scopes `drive.file` y `spreadsheets` adicionales junto a `openid email profile`
2. El `access_token` se guarda en cookie firmada `donar_gtoken` usando `itsdangerous.URLSafeTimedSerializer` (mismo mecanismo que `donar_session`)
3. Al clickear "Google Sheets", el frontend llama `POST /chat/export-sheets` con el SQL y la fuente (`bigquery` o `postgres`) de la consulta
4. El backend re-ejecuta el SQL usando la función correcta según la fuente, crea el Sheet via `gspread.authorize(Credentials(token=google_token))` en el Drive del usuario, y retorna la URL
5. El frontend abre la URL en nueva pestaña

### Decisiones

- **Cookie `donar_gtoken`**: Mismo mecanismo de firma que `donar_session` — `itsdangerous` con `SECRET_KEY`. Se limpia junto a la sesión en logout.
- **`gspread>=6.0.0`**: Dependencia mínima que soporta `gspread.authorize()` con `google.oauth2.credentials.Credentials`.
- **Scopes adicionales en OAuth**: `drive.file` (crear archivos en Drive del usuario) y `spreadsheets` (leer/escribir Sheets). Se agregan al scope del login inicial para no requerir un segundo flujo OAuth.
- **Re-ejecución del SQL en backend**: El frontend envía el SQL original y la fuente de datos; el backend lo re-ejecuta en lugar de recibir los datos serializados, evitando límites de tamaño en el body de la request.

## Implementado

- `chatai/requirements.txt` — agregado `gspread>=6.0.0`
- `chatai/backend/auth.py` — funciones `set_google_token` y `get_google_token`; cookie `donar_gtoken` limpiada en logout
- `chatai/backend/controllers/google_auth_controller.py` — scopes `drive.file` y `spreadsheets` en OAuth; `set_google_token` llamado en callback
- `chatai/backend/controllers/chat_controller.py` — endpoint `POST /chat/export-sheets` y helper privado `_build_gsheet`
- `chatai/frontend/templates/chat.html` — función `makeSheetsBtn`, `triggerSheetsExport`, botón agregado en `buildDownloadBar`
- `specs/28-export-chat-google-sheets/spec.md` — este archivo

## Rutas

| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/chat/export-sheets` | Re-ejecuta el SQL y crea un Google Sheet en el Drive del usuario; retorna `{"url": "https://docs.google.com/..."}` |

## Tests

Validado manualmente — no se agregaron tests automatizados en esta iteración.

## QA Manual

1. Hacer logout y login nuevamente con Google para que los nuevos scopes (`drive.file`, `spreadsheets`) sean solicitados; aceptar los permisos en la pantalla de consentimiento de Google
2. Realizar una consulta en el Chat IA que devuelva una tabla de datos (ej: "¿Cuántas facturas hay por cliente?")
3. Verificar que aparece el botón "Google Sheets" junto a los botones "Excel" y "PDF" en la barra de descarga
4. Hacer clic en "Google Sheets" y confirmar que se abre una nueva pestaña con el Google Sheet creado en el Drive del usuario
5. Verificar que el Sheet contiene los mismos datos que la tabla en el chat, con encabezados en la primera fila
