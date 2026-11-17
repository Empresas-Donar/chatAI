-- Ficha de los tractores habilitados.
-- El catálogo de AppSheet no traía chasis, año de fabricación ni fecha de partida.
-- `año` sigue siendo el texto que ya usaba la app (la fecha de partida).
-- `anio` es el año del tractor. `modelo` es el nombre del equipo.
-- `maquina` no se toca en las filas que ya existen: es el texto de la tarja.

ALTER TABLE appsheet.tarjas_maquina
    ADD COLUMN IF NOT EXISTS modelo TEXT,
    ADD COLUMN IF NOT EXISTS chasis TEXT,
    ADD COLUMN IF NOT EXISTS anio INTEGER,
    ADD COLUMN IF NOT EXISTS fecha_partida DATE,
    ADD COLUMN IF NOT EXISTS habilitado BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE appsheet.tarjas_maquina AS m
   SET modelo = v.modelo,
       color = v.color,
       chasis = v.chasis,
       anio = v.anio,
       fecha_partida = v.fecha_partida,
       "año" = to_char(v.fecha_partida, 'DD/MM/YYYY'),
       tractorista = v.tractorista,
       cumple = v.cumple,
       habilitado = TRUE
  FROM (VALUES
        ('VPYY10'::text, '1'::text, 'Same Frutetto 65'::text, 'ROJO'::text,
         'ZKDCK702W0RS10415'::text, 2026, DATE '2025-11-12', 'RD'::text, 'SI'::text),
        ('PTFK72', '3', 'Same Frutteto 3 75', 'ROJO',
         'ZKDCL002W0RS10521', 2021, DATE '2021-03-25', 'CYG', 'SI'),
        ('PZVS78', '3', 'Same frutteto 3 75', 'ROJO',
         'ZKDCL002W0RS10505', 2021, DATE '2021-06-15', 'CYG', 'SI'),
        ('RLXJ64', '3', 'Same Frutteto 3 75', 'ROJO',
         'ZKDCL002W0RS10557', 2022, DATE '2021-11-08', 'CYG', NULL),
        ('VDCW81', '1', 'Same frutteto 80.4', 'ROJO',
         'ZKDCL302W0RS10554', 2024, DATE '2024-01-01', 'RD', 'SI'),
        ('VDCW81', '2', 'Same frutteto 80.4', 'ROJO',
         'ZKDCL302W0RS10554', 2024, DATE '2024-01-01', 'RD', 'SI'),
        ('TZHH19', '3', 'Same frutteto 80.4', 'ROJO',
         'ZKDCL302W0RS10641', 2025, DATE '2025-02-02', 'CYG', 'SI')
       ) AS v(patente, campo, modelo, color, chasis, anio, fecha_partida, tractorista, cumple)
 WHERE upper(btrim(m.patente)) = v.patente
   AND btrim(m.campo) = v.campo;

INSERT INTO appsheet.tarjas_maquina
    (id_maquina, maquina, modelo, "año", cumple, color, patente, chasis,
     tractorista, campo, anio, fecha_partida, habilitado)
SELECT v.id_maquina, v.maquina, v.modelo, to_char(v.fecha_partida, 'DD/MM/YYYY'),
       v.cumple, v.color, v.patente, v.chasis, v.tractorista, v.campo,
       v.anio, v.fecha_partida, TRUE
  FROM (VALUES
        ('e7rxzs81'::text, 'RXZS88-Same 75'::text, 'Same Frutteto 75'::text,
         'SI'::text, 'ROJO'::text, 'RXZS88'::text, 'ZKDCL002W0RS10570'::text,
         'RD'::text, '1'::text, 2022, DATE '2022-04-19'),
        ('e7rxzs82', 'RXZS88-Same 75', 'Same Frutteto 75',
         'SI', 'ROJO', 'RXZS88', 'ZKDCL002W0RS10570',
         'RD', '2', 2022, DATE '2022-04-19')
       ) AS v(id_maquina, maquina, modelo, cumple, color, patente, chasis,
              tractorista, campo, anio, fecha_partida)
 WHERE NOT EXISTS (
       SELECT 1
         FROM appsheet.tarjas_maquina m
        WHERE upper(btrim(m.patente)) = v.patente
          AND btrim(m.campo) = v.campo
 );
