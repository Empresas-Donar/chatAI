-- Schema: appsheet
-- App: contratistas_isla_maipo
-- Column names match AppSheet EXACTLY (case-sensitive)
-- Creation order respects FK dependencies

-- 1. Empresa
CREATE TABLE "appsheet"."contratistas_isla_maipo_empresa" (
    "CC"      text NOT NULL,
    "Empresa" text,
    PRIMARY KEY ("CC")
);

-- 2. Labor
CREATE TABLE "appsheet"."contratistas_isla_maipo_labor" (
    "Codigo_Labor" text NOT NULL,
    "Labor"        text,
    PRIMARY KEY ("Codigo_Labor")
);

-- 3. Contratistas
CREATE TABLE "appsheet"."contratistas_isla_maipo_contratistas" (
    "Id_Supervisor"       text NOT NULL,
    "Campo"               text,
    "Supervisor"          text,
    "Empresa_Contratista" text,
    "Valor_Jornada"       numeric,
    "Valor_Hora_Extra"    numeric,
    "%Jornada_Bono"       numeric DEFAULT 0,
    "%Trato"              numeric DEFAULT 0,
    "Fijo_Jornada"        numeric,
    "Bono_Extra"          numeric,
    PRIMARY KEY ("Id_Supervisor")
);

-- 4. Trabajadores
CREATE TABLE "appsheet"."contratistas_isla_maipo_trabajadores" (
    "Id_Trabajador"     text NOT NULL,
    "Nombre_Trabajador" text,
    "Campo"             text DEFAULT 'Isla de Maipo',
    "Contratista"       text,
    "Ingresar_Nombre"   text,
    "Rut"               text,
    PRIMARY KEY ("Id_Trabajador")
);

-- 5. Tratos
CREATE TABLE "appsheet"."contratistas_isla_maipo_tratos" (
    "Id_Tratos"             text NOT NULL,
    "Campo"                 text DEFAULT 'Isla de Maipo',
    "Centro de Costo"       text,
    "Labor"                 text,
    "Nombre etiqueta trato" text,
    "Fecha Inicio Trato"    date DEFAULT CURRENT_DATE,
    "Fecha Termino Trato"   date,
    "Valor del Trato"       numeric,
    PRIMARY KEY ("Id_Tratos")
);

-- 6. Registro
CREATE TABLE "appsheet"."contratistas_isla_maipo_registro" (
    "ID_Registro"       text NOT NULL,
    "Campo"             text DEFAULT 'Isla de maipo',
    "Fecha"             date DEFAULT CURRENT_DATE,
    "Contratista"       text,
    "CC"                text,
    "Labor"             text,
    "Tipo de Registro"  text,
    "Trabajador"        text[],
    "Jornada"           numeric DEFAULT 1,
    "Bonificación"      numeric,
    "Bono_Especial_Piso" numeric DEFAULT 0,
    "Horas_Extras"      numeric DEFAULT 0,
    "Trato"             text,
    "Dia_Habil"         boolean,
    "Contador"          numeric,
    "dia"               text,
    PRIMARY KEY ("ID_Registro")
);

-- 7. Registro Trato
CREATE TABLE "appsheet"."contratistas_isla_maipo_registro_trato" (
    "Id_Registro_Trato" text NOT NULL,
    "Id_Registro"       text,
    "Contratista"       text,
    "Trabajador"        text,
    "Unidades Trato"    numeric,
    "Base"              numeric DEFAULT 0,
    "Id_Busqueda"       text,
    PRIMARY KEY ("Id_Registro_Trato")
);

-- 8. Resumen
CREATE TABLE "appsheet"."contratistas_isla_maipo_resumen" (
    "ID_Resumen"         text NOT NULL,
    "ID_Registro"        text,
    "Campo"              text,
    "Fecha"              date,
    "Contratista"        text,
    "CC"                 text,
    "Labor"              text,
    "Trabajador"         text,
    "Jornada"            numeric,
    "Bonificación"       numeric,
    "Bono_Especial_Piso" numeric,
    "Horas_Extras"       numeric,
    "Trato"              text,
    "Unidades Trato"     numeric,
    "Base Trato"         numeric,
    "Dia_Habil"          boolean,
    "Id_Busqueda"        text,
    "Nombre Labor"       text,
    PRIMARY KEY ("ID_Resumen")
);

-- 9. Pagos
CREATE TABLE "appsheet"."contratistas_isla_maipo_pagos" (
    "ID_Resumen"                  text NOT NULL,
    "Campo"                       text,
    "Fecha"                       date DEFAULT CURRENT_DATE,
    "Mes"                         text,
    "Contratista"                 text,
    "CC"                          text,
    "Labor"                       text,
    "Trabajador"                  text,
    "Jornada"                     numeric,
    "Bonificación"                numeric,
    "Bono_Especial_Piso"          numeric,
    "Horas_Extras"                numeric,
    "Trato"                       text,
    "Unidades Trato"              numeric,
    "Base Trato"                  numeric,
    "Dia_Habil"                   boolean,
    "Nombre Labor"                text,
    "Valor Bonificación 2"        numeric,
    "Bono Extra"                  numeric,
    "Valor Jornada"               numeric,
    "Total Unidades"              numeric,
    "Valor Trato"                 numeric,
    "Trabajador Jornal mas Bonos" numeric,
    "Trabajador Tratos"           numeric,
    "Total Trabajador"            numeric,
    "Contratista Jornada"         numeric,
    "Contratista Tratos"          numeric,
    "Total Contratista"           numeric,
    "Total a Pagar"               numeric,
    "Total Jornada"               numeric,
    "dia"                         text,
    "Empresa"                     text,
    "Cultivo"                     text,
    "Dia de Ayer"                 boolean,
    "Tipo de Pago"                text,
    PRIMARY KEY ("ID_Resumen")
);

-- 10. Cultivos
CREATE TABLE "appsheet"."contratistas_isla_maipo_cultivos" (
    "CC"         text NOT NULL,
    "Cultivo"    text,
    "Tipo"       text,
    "Id"         numeric,
    "Valor odoo" text,
    PRIMARY KEY ("CC")
);

-- 11. Cultivos Detalle
CREATE TABLE "appsheet"."contratistas_isla_maipo_cultivos_detalle" (
    "CC"         text NOT NULL,
    "Cultivo"    text,
    "Tipo"       text,
    "Id"         numeric,
    "Valor odoo" text,
    PRIMARY KEY ("CC")
);

-- 12. Usuarios
CREATE TABLE "appsheet"."contratistas_isla_maipo_usuarios" (
    "Id_Usuario"     text NOT NULL,
    "Nombre Usuario" text,
    "Correo"         text,
    "Rol"            text,
    "Contraseña"     text,
    PRIMARY KEY ("Id_Usuario")
);

-- Foreign Keys
ALTER TABLE "appsheet"."contratistas_isla_maipo_trabajadores"
    ADD FOREIGN KEY ("Contratista") REFERENCES "appsheet"."contratistas_isla_maipo_contratistas"("Id_Supervisor");

ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("Contratista") REFERENCES "appsheet"."contratistas_isla_maipo_contratistas"("Id_Supervisor");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("Labor") REFERENCES "appsheet"."contratistas_isla_maipo_labor"("Codigo_Labor");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("Trato") REFERENCES "appsheet"."contratistas_isla_maipo_tratos"("Id_Tratos");
ALTER TABLE "appsheet"."contratistas_isla_maipo_registro"
    ADD FOREIGN KEY ("CC") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("CC");

ALTER TABLE "appsheet"."contratistas_isla_maipo_tratos"
    ADD FOREIGN KEY ("Labor") REFERENCES "appsheet"."contratistas_isla_maipo_labor"("Codigo_Labor");

ALTER TABLE "appsheet"."contratistas_isla_maipo_registro_trato"
    ADD FOREIGN KEY ("Id_Registro") REFERENCES "appsheet"."contratistas_isla_maipo_registro"("ID_Registro");

ALTER TABLE "appsheet"."contratistas_isla_maipo_resumen"
    ADD FOREIGN KEY ("ID_Registro") REFERENCES "appsheet"."contratistas_isla_maipo_registro"("ID_Registro");

ALTER TABLE "appsheet"."contratistas_isla_maipo_cultivos"
    ADD FOREIGN KEY ("CC") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("CC");

ALTER TABLE "appsheet"."contratistas_isla_maipo_cultivos_detalle"
    ADD FOREIGN KEY ("CC") REFERENCES "appsheet"."contratistas_isla_maipo_empresa"("CC");
