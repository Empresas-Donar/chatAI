-- Schema: appsheet
-- App: contratistas_isla_maipo
-- Orden de creación respeta dependencias (FK)

-- 1. empresa
CREATE TABLE "appsheet"."contratistas_isla_maipo_empresa" (
    "cc" text NOT NULL,
    "empresa" text,
    PRIMARY KEY ("cc")
);

-- 2. labor
CREATE TABLE "appsheet"."contratistas_isla_maipo_labor" (
    "codigo_labor" text NOT NULL,
    "labor" text,
    PRIMARY KEY ("codigo_labor")
);

-- 3. contratistas
CREATE TABLE "appsheet"."contratistas_isla_maipo_contratistas" (
    "id_supervisor" text NOT NULL,
    "campo" text,
    "supervisor" text,
    "empresa_contratista" text,
    "valor_jornada" numeric,
    "valor_hora_extra" numeric,
    "porcentaje_jornada_bono" numeric DEFAULT 0,
    "porcentaje_trato" numeric DEFAULT 0,
    "fijo_jornada" numeric,
    "bono_extra" numeric,
    PRIMARY KEY ("id_supervisor")
);

-- 4. trabajadores
CREATE TABLE "appsheet"."contratistas_isla_maipo_trabajadores" (
    "id_trabajador" text NOT NULL,
    "nombre_trabajador" text,
    "campo" text DEFAULT 'Isla de Maipo'::text,
    "contratista" text,
    "ingresar_nombre" text,
    "rut" text,
    PRIMARY KEY ("id_trabajador")
);

-- 5. tratos
CREATE TABLE "appsheet"."contratistas_isla_maipo_tratos" (
    "id_tratos" text NOT NULL,
    "campo" text DEFAULT 'Isla de Maipo'::text,
    "centro_de_costo" text,
    "labor" text,
    "nombre_etiqueta_trato" text,
    "fecha_inicio_trato" date DEFAULT CURRENT_DATE,
    "fecha_termino_trato" date,
    "valor_del_trato" numeric,
    PRIMARY KEY ("id_tratos")
);

-- 6. registro
CREATE TABLE "appsheet"."contratistas_isla_maipo_registro" (
    "id_registro" text NOT NULL,
    "campo" text DEFAULT 'Isla de Maipo'::text,
    "fecha" date DEFAULT CURRENT_DATE,
    "contratista" text,
    "cc" text,
    "labor" text,
    "tipo_de_registro" text,
    "trabajador" text[],
    "jornada" numeric DEFAULT 1,
    "bonificacion" numeric,
    "bono_especial_piso" numeric DEFAULT 0,
    "horas_extras" numeric DEFAULT 0,
    "trato" text,
    "dia_habil" bool,
    "contador" numeric,
    "dia" text,
    PRIMARY KEY ("id_registro")
);

-- 7. registro_trato
CREATE TABLE "appsheet"."contratistas_isla_maipo_registro_trato" (
    "id_registro_trato" text NOT NULL,
    "id_registro" text,
    "contratista" text,
    "trabajador" text,
    "unidades_trato" numeric,
    "base" numeric DEFAULT 0,
    "id_busqueda" text,
    PRIMARY KEY ("id_registro_trato")
);

-- 8. resumen
CREATE TABLE "appsheet"."contratistas_isla_maipo_resumen" (
    "id_resumen" text NOT NULL,
    "id_registro" text,
    "campo" text,
    "fecha" date,
    "contratista" text,
    "cc" text,
    "labor" text,
    "trabajador" text,
    "jornada" numeric,
    "bonificacion" numeric,
    "bono_especial_piso" numeric,
    "horas_extras" numeric,
    "trato" text,
    "unidades_trato" numeric,
    "base_trato" numeric,
    "dia_habil" bool,
    "id_busqueda" text,
    "nombre_labor" text,
    PRIMARY KEY ("id_resumen")
);

-- 9. pagos
CREATE TABLE "appsheet"."contratistas_isla_maipo_pagos" (
    "id_resumen" text NOT NULL,
    "campo" text,
    "fecha" date DEFAULT CURRENT_DATE,
    "mes" text,
    "contratista" text,
    "cc" text,
    "labor" text,
    "trabajador" text,
    "jornada" numeric,
    "bonificacion" numeric,
    "bono_especial_piso" numeric,
    "horas_extras" numeric,
    "trato" text,
    "unidades_trato" numeric,
    "base_trato" numeric,
    "dia_habil" bool,
    "nombre_labor" text,
    "valor_bonificacion_2" numeric,
    "bono_extra" numeric,
    "valor_jornada" numeric,
    "total_unidades" numeric,
    "valor_trato" numeric,
    "trabajador_jornal_mas_bonos" numeric,
    "trabajador_tratos" numeric,
    "total_trabajador" numeric,
    "contratista_jornada" numeric,
    "contratista_tratos" numeric,
    "total_contratista" numeric,
    "total_a_pagar" numeric,
    "total_jornada" numeric,
    "dia" text,
    "empresa" text,
    "cultivo" text,
    "dia_de_ayer" bool,
    "tipo_de_pago" text,
    PRIMARY KEY ("id_resumen")
);

-- 10. cultivos
CREATE TABLE "appsheet"."contratistas_isla_maipo_cultivos" (
    "cc" text NOT NULL,
    "cultivo" text,
    "tipo" text,
    "id" numeric,
    "valor_odoo" text,
    PRIMARY KEY ("cc")
);

-- 11. cultivos_detalle
CREATE TABLE "appsheet"."contratistas_isla_maipo_cultivos_detalle" (
    "cc" text NOT NULL,
    "cultivo" text,
    "tipo" text,
    "id" numeric,
    "valor_odoo" text,
    PRIMARY KEY ("cc")
);

-- 12. usuarios
CREATE TABLE "appsheet"."contratistas_isla_maipo_usuarios" (
    "id_usuario" text NOT NULL,
    "nombre_usuario" text,
    "correo" text,
    "rol" text,
    "contrasena" text,
    PRIMARY KEY ("id_usuario")
);

-- Foreign Keys
ALTER TABLE "appsheet"."contratistas_isla_maipo_trabajadores"
    ADD FOREIGN KEY ("contratista") REFERENCES "appsheet"."contratistas_isla_maipo_contratistas"("id_supervisor");

ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("contratista") REFERENCES "appsheet"."contratistas_isla_maipo_contratistas"("id_supervisor");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("labor") REFERENCES "appsheet"."contratistas_isla_maipo_labor"("codigo_labor");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("trato") REFERENCES "appsheet"."contratistas_isla_maipo_tratos"("id_tratos");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("cc") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("cc");

ALTER TABLE "appsheet"."contratistas_isla_maipo_tratos"
    ADD FOREIGN KEY ("labor") REFERENCES "appsheet"."contratistas_isla_maipo_labor"("codigo_labor");

ALTER TABLE "appsheet"."contratistas_isla_maipo_registro_trato"
    ADD FOREIGN KEY ("id_registro") REFERENCES "appsheet"."contratistas_isla_maipo_registro"("id_registro");

ALTER TABLE "appsheet"."contratistas_isla_maipo_resumen"
    ADD FOREIGN KEY ("id_registro") REFERENCES "appsheet"."contratistas_isla_maipo_registro"("id_registro");

ALTER TABLE "appsheet"."contratistas_isla_maipo_cultivos"
    ADD FOREIGN KEY ("cc") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("cc");

ALTER TABLE "appsheet"."contratistas_isla_maipo_cultivos_detalle"
    ADD FOREIGN KEY ("cc") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("cc");
