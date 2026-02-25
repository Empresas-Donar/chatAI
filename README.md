# AppSheet → PostgreSQL Migration Toolkit

Framework de migración para múltiples aplicaciones AppSheet hacia PostgreSQL.

Diseñado para soportar varias apps como:

- contratistas_isla_maipo
- medicion_pozos
- futuras apps agrícolas
- futuras apps operativas

---

## Objetivo

Permitir:

- Migración estructurada desde Google Sheets (AppSheet) a PostgreSQL
- Limpieza automática de datos (moneda, porcentaje, fechas)
- Respeto de claves primarias
- Respeto de relaciones (Ref)
- Soporte multi-app
- Reutilización de código

---

## Estructura del Proyecto

```
appsheet-migration/
│
├── README.md
├── requirements.txt
├── .env
│
├── config/
│   └── settings.py
│
├── sql/
│   ├── contratistas_isla_maipo/
│   │   ├── 01_schema.sql
│   │   └── 02_tables.sql
│   │
│   ├── medicion_pozos/
│   │   ├── 01_schema.sql
│   │   └── 02_tables.sql
│   │
│   └── templates/
│
├── data/
│   ├── contratistas_isla_maipo/
│   │   ├── raw/
│   │   └── processed/
│   │
│   ├── medicion_pozos/
│   │   ├── raw/
│   │   └── processed/
│   │
│   └── ...
│
├── apps/
│   ├── contratistas_isla_maipo/
│   │   ├── migrar_contratistas.py
│   │   ├── migrar_trabajadores.py
│   │   ├── migrar_tratos.py
│   │   ├── migrar_registro.py
│   │   └── migrar_all.py
│   │
│   ├── medicion_pozos/
│   │   ├── migrar_pozos.py
│   │   └── migrar_all.py
│   │
│   └── ...
│
├── core/
│   ├── db.py
│   ├── cleaners.py
│   ├── loader.py
│   └── utils.py
│
└── logs/
```

---

## Configuración

Crear archivo `.env`:

```env
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
```

---

## Requisitos

Python 3.10+

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Contenido de `requirements.txt`:

```
psycopg2-binary
pandas
python-dotenv
```

---

## Convención de Base de Datos

Todas las tablas siguen el patrón:

```
appsheet.<nombre_app>_<nombre_tabla>
```

Ejemplo:

```
appsheet.contratistas_isla_maipo_contratistas
appsheet.medicion_pozos_ingresos
```

---

## Flujo de Migración

1. Exportar CSV desde AppSheet.
2. Guardar archivos en `data/<app>/raw/`
3. Ejecutar script de migración.
4. Validar conteos en PostgreSQL.
5. Conectar AppSheet a PostgreSQL.
6. Ejecutar "Regenerate Structure".
7. Probar app en preview.

---

## Limpieza Automática

El sistema normaliza:

| Entrada       | Salida         |
|---------------|----------------|
| `$18.000`     | `18000`        |
| `45,00%`      | `0.45`         |
| Boolean       | `TRUE`/`FALSE` |
| Fechas        | `YYYY-MM-DD`   |
| EnumList      | `TEXT[]`       |

---

## Seguridad

- No subir `.env` al repositorio.
- Usar variables de entorno.
- Usar `ON CONFLICT` para evitar duplicados.
- No almacenar contraseñas en texto plano.

---

## Orden Correcto de Migración

1. empresa
2. labor
3. contratistas
4. trabajadores
5. tratos
6. registro
7. registro_trato
8. resumen
9. pagos
10. usuarios

---

## Proyecto

Migración técnica AppSheet → PostgreSQL
Arquitectura multi-app escalable
