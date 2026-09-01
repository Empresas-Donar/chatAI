-- =============================================================================
-- TARJAS: Reemplazar catálogo tarjas_maquina con columnas nuevas y una fila
-- por (id_maquina, campo) en vez de una fila por id_maquina.
-- Issue #73
--
-- Motivo: la misma máquina (id_maquina) puede estar desplegada en más de un
-- campo, cada despliegue con su propia patente/tractorista/cumple. La tabla
-- no tenía PK ni FK y no se usa en ningún endpoint del backend (verificado
-- con grep), por lo que el reemplazo completo es seguro.
--
-- Clave natural verificada: (id_maquina, campo) es única en las 18 filas
-- nuevas (ninguna máquina se repite dos veces en el mismo campo).
--
-- Inconsistencia detectada y NO corregida (se preserva tal cual la entregó
-- el usuario): id_maquina '3aa5e989' aparece como "Massey Ferguson 250" en
-- campo 1 y 2, pero como "Massey 265" en campo 3 — mismo ID, nombre
-- distinto según campo. Ver spec.md para el detalle.
-- =============================================================================

BEGIN;

ALTER TABLE appsheet.tarjas_maquina
    ADD COLUMN IF NOT EXISTS color TEXT,
    ADD COLUMN IF NOT EXISTS patente TEXT,
    ADD COLUMN IF NOT EXISTS tractorista TEXT,
    ADD COLUMN IF NOT EXISTS campo TEXT;

DELETE FROM appsheet.tarjas_maquina;

INSERT INTO appsheet.tarjas_maquina
    (id_maquina, maquina, color, patente, "año", tractorista, cumple, campo)
VALUES
    ('c520d027', 'Farmtrac',             'Azul', NULL,     '01/01/2026', 'DONAR', 'SI', '1'),
    ('3aa5e989', 'Massey Ferguson 250',  NULL,   NULL,     '01/01/2008', 'DONAR', 'SI', '1'),
    ('98677ec2', 'Same frutteto 80.4',   'ROJO', 'VDCW81', '01/01/2024', 'RD',    'SI', '1'),
    ('96088b6f', 'Same frutetto 70',     NULL,   NULL,     NULL,         'DONAR', 'NO', '1'),
    ('c520d028', 'Same Frutteto 65',     'ROJO', 'VPYY10', '12/11/2025', 'RD',    'SI', '1'),
    ('3aa5e989', 'Massey 265',           NULL,   NULL,     NULL,         'DONAR', 'NO', '3'),
    ('cbd2cea0', 'Same Frutteto 3 75',   'ROJO', 'PTFK72', '25/03/2021', 'CYG',   'SI', '3'),
    ('038c7251', 'Desbrozadora',         NULL,   NULL,     NULL,         'DONAR', 'NO', '3'),
    ('a0b7551e', 'Pala Cola',            NULL,   NULL,     NULL,         'DONAR', 'NO', '3'),
    ('92caba52', 'Otra máquina',         NULL,   NULL,     NULL,         'DONAR', 'NO', '3'),
    ('98677ec2', 'Same frutteto 3 75',   'ROJO', 'PZVS78', '15/06/2021', 'CYG',   'SI', '3'),
    ('48d46934', 'Same frutteto 80.4',   'ROJO', 'TZHH19', '02/02/2025', 'CYG',   'SI', '3'),
    ('c520d028', 'Same Fruteto 3 75',    'ROJO', 'RLXJ64', '08/11/2021', 'CYG',   NULL, '3'),
    ('3aa5e990', 'Same Frutteto 3 65',   'ROJO', 'SJWB50', '10/11/2022', 'DONAR', NULL, '3'),
    ('c520d027', 'Farmtrac',             'Azul', NULL,     '01/01/2026', 'DONAR', 'SI', '2'),
    ('3aa5e989', 'Massey Ferguson 250',  NULL,   NULL,     '01/01/2008', 'DONAR', 'SI', '2'),
    ('98677ec2', 'Same frutteto 80.4',   'ROJO', 'VDCW81', '01/01/2024', 'RD',    'SI', '2'),
    ('96088b6f', 'Same frutetto 70',     NULL,   NULL,     NULL,         'DONAR', 'NO', '2');

COMMIT;
