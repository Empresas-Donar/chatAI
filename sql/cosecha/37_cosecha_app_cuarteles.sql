-- =============================================================================
-- Cosecha app: cuarteles de Isla de Maipo
--
-- Reemplaza el catálogo copiado de Zúñiga. Cultivo sigue siendo cereza o
-- ciruela: ciruela en los tres cuarteles D'Agen (C09, C10, C14).
-- No hay registros ni tratos apuntando a los id anteriores.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

DELETE FROM cosecha_app_cuarteles;

INSERT INTO cosecha_app_cuarteles (id_cuartel, nombre_cuartel, variedad, cultivo) VALUES
  ('C03', '422-Sweet Aryana 2023', 'Swet Aryana', 'cereza'),
  ('C04', '432-Lapins 2023', 'Lapins', 'cereza'),
  ('C05', '431-Rainier 2023', 'Rainier', 'cereza'),
  ('C06', '424-Santina 2023', 'Santina', 'cereza'),
  ('C07', '426-Glow 2023', 'Glow', 'cereza'),
  ('C08', '427-Treat/Lapins 2023', 'Treat/Lapins', 'cereza'),
  ('C09', '451-CIRUELAS D`AGEN ORIENTE', 'D''AGEN', 'ciruela'),
  ('C10', '452-CIRUELAS D`AGEN PONIENTE', 'D''AGEN', 'ciruela'),
  ('C11', '429-CEREZOS RED PACIFIC 2023-ORIENTE', 'Red Pacific', 'cereza'),
  ('C12', '430-CEREZOS RED PACIFIC 2023-PONIENTE', 'Red Pacific', 'cereza'),
  ('C13', '428-CEREZOS RED PACIFIC 2023', 'Red Pacific', 'cereza'),
  ('C14', '453-CIRUELAS D`AGEN', 'D''AGEN', 'ciruela');

COMMENT ON COLUMN cosecha_app_cuarteles.cultivo IS
  'cereza o ciruela. Ciruela en C09, C10 y C14 (D''Agen).';

COMMIT;
