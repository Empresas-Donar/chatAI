-- =============================================================================
-- TARJAS: Corregir base_trato duplicada el mismo día en labores de trato
-- Issue #46
--
-- 60 registros tenían base_trato asignada más de una vez el mismo día cuando
-- el trabajador realizó varias labores de tipo trato en la misma jornada —
-- la base solo corresponde a la primera labor del día.
--
-- Corrección: base_trato=0 en las labores duplicadas, total_trato recalculado
-- como rendimiento*valor_trato (sin la base duplicada), y total_trabajado /
-- total_contratista (~45% markup) / total_pagar recalculados en consecuencia.
--
-- Verificado antes de aplicar: las 60 filas tenían base_trato=15000,
-- tipo_pago='trato', y total_trato actual = base_trato + rendimiento*valor_trato
-- en las 60 (fórmula conocida, confirmada issue #42). Los nuevos valores de
-- este script fueron validados contra esa misma fórmula antes de ejecutar.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='9ce21206';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='3b2e75ac';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='f339c06d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='95630a0d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='efa2c06d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='f3a36a08';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='14dfc372';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='428d110b';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='0662dece';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='e3dba9f2';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='f8985f05';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='922e6cf1';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='5cdf15d6';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='7ddf2705';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='59f14f1d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='2a9fec5d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='fb4d8a70';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='6038d8ca';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='3683cfbc';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='4ff5e122';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='6b1d7735';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='6ab164f8';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='93993452';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='a94c801d';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='6c004cec';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='9e72623e';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=3000, total_trabajado=3000, total_contratista=1350, total_pagar=4350 WHERE "id_Resumen"='499432df';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10500, total_trabajado=10500, total_contratista=4725, total_pagar=15225 WHERE "id_Resumen"='c9243a96';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10000, total_trabajado=10000, total_contratista=4500, total_pagar=14500 WHERE "id_Resumen"='820b8552';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10500, total_trabajado=10500, total_contratista=4725, total_pagar=15225 WHERE "id_Resumen"='e5b6a269';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=15000, total_trabajado=15000, total_contratista=6750, total_pagar=21750 WHERE "id_Resumen"='fff23482';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10000, total_trabajado=10000, total_contratista=4500, total_pagar=14500 WHERE "id_Resumen"='b95899e9';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10000, total_trabajado=10000, total_contratista=4500, total_pagar=14500 WHERE "id_Resumen"='d34b22a8';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='9d198a66';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='09c88c90';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='91824755';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='8bbe432e';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9000, total_trabajado=9000, total_contratista=4050, total_pagar=13050 WHERE "id_Resumen"='32758f8e';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9000, total_trabajado=9000, total_contratista=4050, total_pagar=13050 WHERE "id_Resumen"='64bef651';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9750, total_trabajado=9750, total_contratista=4388, total_pagar=14138 WHERE "id_Resumen"='9c1e18fa';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9750, total_trabajado=9750, total_contratista=4388, total_pagar=14138 WHERE "id_Resumen"='2fc8adb6';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9000, total_trabajado=9000, total_contratista=4050, total_pagar=13050 WHERE "id_Resumen"='03c039d6';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=45, total_trabajado=45, total_contratista=20, total_pagar=45 WHERE "id_Resumen"='a16f13fc';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='bb6b8559';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='c869af22';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='9d6ad59e';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='a691281c';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=7500, total_trabajado=7500, total_contratista=3375, total_pagar=10875 WHERE "id_Resumen"='01bc8a64';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=16500, total_trabajado=16500, total_contratista=7425, total_pagar=23925 WHERE "id_Resumen"='36e7ec80';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=2500, total_trabajado=2500, total_contratista=1125, total_pagar=3625 WHERE "id_Resumen"='10350369';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='2ec25728';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='6a302cc1';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='2d96a5d3';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=20000, total_trabajado=20000, total_contratista=9000, total_pagar=29000 WHERE "id_Resumen"='8e010fa9';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9000, total_trabajado=9000, total_contratista=4050, total_pagar=13050 WHERE "id_Resumen"='a131b6c7';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=9000, total_trabajado=9000, total_contratista=4050, total_pagar=13050 WHERE "id_Resumen"='6fc97b4b';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=12500, total_trabajado=12500, total_contratista=5625, total_pagar=18125 WHERE "id_Resumen"='3391b76a';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=12500, total_trabajado=12500, total_contratista=5625, total_pagar=18125 WHERE "id_Resumen"='0a24acfe';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10000, total_trabajado=10000, total_contratista=4500, total_pagar=14500 WHERE "id_Resumen"='10419f26';
UPDATE appsheet.tarjas_pagos SET base_trato=0, total_trato=10000, total_trabajado=10000, total_contratista=4500, total_pagar=14500 WHERE "id_Resumen"='c0ca9d8a';

-- Las 60 UPDATE de arriba fijan total_contratista pero no contratista_trato,
-- dejando ambos campos desincronizados (contratista_jornada=0 en las 60,
-- confirmado antes de aplicar). Se sincroniza aquí para no reintroducir el
-- bug corregido en el issue #42.
UPDATE appsheet.tarjas_pagos
SET contratista_trato = total_contratista
WHERE "id_Resumen" IN (
    '9ce21206','3b2e75ac','f339c06d','95630a0d','efa2c06d','f3a36a08','14dfc372','428d110b','0662dece','e3dba9f2',
    'f8985f05','922e6cf1','5cdf15d6','7ddf2705','59f14f1d','2a9fec5d','fb4d8a70','6038d8ca','3683cfbc','4ff5e122',
    '6b1d7735','6ab164f8','93993452','a94c801d','6c004cec','9e72623e','499432df','c9243a96','820b8552','e5b6a269',
    'fff23482','b95899e9','d34b22a8','9d198a66','09c88c90','91824755','8bbe432e','32758f8e','64bef651','9c1e18fa',
    '2fc8adb6','03c039d6','a16f13fc','bb6b8559','c869af22','9d6ad59e','a691281c','01bc8a64','36e7ec80','10350369',
    '2ec25728','6a302cc1','2d96a5d3','8e010fa9','a131b6c7','6fc97b4b','3391b76a','0a24acfe','10419f26','c0ca9d8a'
) AND contratista_trato != total_contratista;

COMMIT;
