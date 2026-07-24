# Favicon con el logo de Donar
# Path: specs/36-favicon-donar-logo/spec.md
issue: #36 · branch: 36-favicon-donar-logo · date: 2026-07-24

## What
La intranet muestra el emblema circular del logo de Empresas Donar como favicon en la pestaña del navegador, en vez del ícono genérico por defecto.

## Acceptance
- [x] La pestaña del navegador muestra el emblema circular del logo de Donar (el ícono, no el wordmark completo) en todas las páginas de la intranet.
- [x] El ícono se ve nítido en tamaños pequeños (16px/32px de pestaña).
- [x] Se reutiliza el logo existente en `chatai/frontend/static/img/donar_logo.png`, recortado al emblema circular.

## Context
- `chatai/frontend/templates/base.html` es la plantilla padre de la que heredan casi todas las páginas (dashboard, tarjas, chat, reportes, etc.) vía `{% extends "base.html" %}`.
- `chatai/frontend/templates/login.html` es standalone (no extiende `base.html`), así que necesita su propio `<link>` de favicon.
- El asset fuente `donar_logo.png` (1288×539) es el logotipo completo (wordmark + emblema circular), no apto como favicon por su relación de aspecto ancha.
- Estático servido vía `app.mount("/static", StaticFiles(directory=STATIC_DIR))` en `chatai/backend/main.py:87`, con `STATIC_DIR = frontend/static`.

## Decisions
- Se recortó únicamente el emblema circular (sol, cerezo, surcos) del logo original — el wordmark "EMPRESAS DONAR" no es legible ni útil a tamaño de ícono de pestaña.
- Se generaron 3 tamaños PNG (16×16, 32×32, 180×180 para `apple-touch-icon`) en vez de un único `.ico`, ya que todos los navegadores modernos soportan `<link rel="icon" type="image/png">` directamente.
- No se tocó `donar_logo.png` original — los favicons son archivos nuevos derivados, para no afectar otros usos del logo completo.

## Implemented
### Assets
- `chatai/frontend/static/img/favicon-16x16.png` — nuevo, recorte del emblema circular
- `chatai/frontend/static/img/favicon-32x32.png` — nuevo, recorte del emblema circular
- `chatai/frontend/static/img/apple-touch-icon.png` — nuevo, 180×180 para iOS/bookmarks

### Templates
- `chatai/frontend/templates/base.html` — agregados 3 `<link rel="icon"/apple-touch-icon">` en `<head>`
- `chatai/frontend/templates/login.html` — mismos 3 `<link>` agregados (no hereda de base.html)

## Routes
N/A — cambio puramente de frontend estático, sin endpoints nuevos.

## Tests
N/A — no hay lógica de negocio ni backend involucrado; se verifica con QA manual (ver abajo).

## Manual QA
1. Levantar la app (`uvicorn` o el comando de desarrollo habitual) y abrir `/login` — la pestaña debe mostrar el emblema circular de Donar.
2. Iniciar sesión y navegar a `/dashboard`, `/chat`, cualquier reporte de tarjas — la pestaña mantiene el mismo ícono en todas.
3. Verificar en DevTools → Network que `/static/img/favicon-32x32.png` y `favicon-16x16.png` responden 200.
4. Agregar la página a marcadores/pantalla de inicio (móvil) y confirmar que usa `apple-touch-icon.png` (180×180) en vez de recortar el ícono pequeño.

## Deferred
- No se generó `favicon.ico` clásico (formato multi-resolución binario) — los PNG declarados cubren el 100% de navegadores modernos (Chrome, Firefox, Edge, Safari).
