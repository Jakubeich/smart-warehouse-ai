# Lokální GLB modely

Složka obsahuje osm skutečných exportů z Blenderu, připojených v manifest.json. Zdroj: `assets/blender/warehouse-assets.blend` v kořeni projektu. Celá sada má 380,2 KiB, bez externích textur a dekodérů. Hodnota `null` v manifestu vrátí základní tvar. Podporované klíče: robot, shelf, pickup, dropoff, charger, pallet, wall, obstacle.

Měřítko: referenční buňka 1 m, pivot u podlahy ve středu, model robota míří +X, GLB osa Y nahoru. Textury zabalte dovnitř GLB. Pro první sadu použijte nekomprimované GLB. Podrobné zadání je v docs/blender-assets.md a docs/future-3d.md v kořeni projektu. Po změně manifestu nebo modelu obnovte stránku.
