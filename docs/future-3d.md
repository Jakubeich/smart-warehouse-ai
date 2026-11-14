# 2D / 3D zobrazení a Blender workflow

Simulace má přepínač **2D / 3D** v záhlaví mapy. 2D používá PixiJS, 3D používá React Three Fiber, Three.js a kameru OrbitControls. Přepínání mění pouze vykreslování; stejný běh, úkoly, baterie a plánovač zůstávají na backendu. Volba pohledu se pamatuje v prohlížeči. Editor skladu zatím používá 2D; živé dynamické překážky lze upravovat v obou pohledech.

## Co je nyní funkční

- Prostorová podlaha, regály, stěny, nakládka, vykládka, nabíjení, překážky a roboti. Náklad se objeví na robotovi podle skutečného `load`.
- Stejné pozice a orientace jako ve 2D; vyhlazení sousedních ticků, okamžitá změna při resetu, ztracených aktualizacích nebo přepnutí pohledu.
- Orbit / posun / zoom, pohled shora a obnova kamery, výběr robota do společného detailu.
- Mřížka, ID, trasy, rezervace nejbližších tří kroků, konflikty, stanice a teplotní mapa.
- Lazy loading 3D knihoven, instancované GLB regály/stěny/stanice i náhradní tvary a vykreslování na vyžádání. Klidová scéna neběží v trvalé animační smyčce.
- Lokální GLB manifest, hlášený náhradní základní tvar při chybě modelu a návrat do 2D po ztrátě WebGL kontextu.

**V aplikaci je zapojená kompletní sada osmi modelů z Blenderu.** Původní editovatelný zdroj, rozměry a postup úprav jsou v [blender-assets.md](blender-assets.md). Barevné detaily robotů odpovídají flotile; náklad se zobrazuje podle stavu enginu. Celá sada GLB má 380,2 KiB.

## Připojení modelu

1. Exportujte samostatný GLB podle zadání modelování.
2. Uložte ho například do `apps/frontend/public/models/robots/amr.glb`.
3. V `apps/frontend/public/models/manifest.json` nastavte cestu od kořene webu. Dodaná konfigurace:

```json
{
  "version": 1,
  "models": {
    "robot": "/models/robots/amr.glb",
    "shelf": "/models/warehouse/shelf.glb",
    "pickup": "/models/warehouse/pickup.glb",
    "dropoff": "/models/warehouse/dropoff.glb",
    "charger": "/models/warehouse/charger.glb",
    "pallet": "/models/warehouse/pallet.glb",
    "wall": "/models/warehouse/wall.glb",
    "obstacle": "/models/warehouse/obstacle.glb"
  }
}
```

4. Obnovte stránku nebo přepněte 2D → 3D. Nenahrané druhy dál používají základní tvary. V produkčním Docker obrazu je po změně souborů potřeba znovu sestavit frontend.

Manifest načítáme až při otevření 3D, kontrolujeme jeho verzi i lokální cesty `.glb`. Neodkazujte na `.blend` soubor ani na neexistující model. Loader používá sdílenou cache; po přepsání existujícího GLB obnovte stránku, případně soubor verzujte novým názvem. Neplatný manifest má viditelné upozornění. Po chybě GLB zůstává příslušná základní geometrie i výběr robota funkční.

## Datová smlouva

`renderers/shared/scene.ts` obsahuje společný `SceneFrame`, callbacky `WarehouseViewProps`, převod `worldPosition`, `worldYaw` a podmínku `canInterpolate`. `WarehouseViewport` pouze vybírá renderer. Neposílá start, step ani reset a neotevírá druhou simulační session.

Souřadnice středu buňky `(x,y)` se mapují na `((x + 0,5) * cell_size, 0, (y + 0,5) * cell_size)`. V Three.js je **Y nahoru**, gridová osa y se mapuje na **Z**. Model robota míří podél +X; rotace kolem Y je `−orientation × π / 180`. Směry 0°, 90°, 180°, −90° jsou pokryté testem.

Základní modely jsou autorské šablony pro buňku **1 m**. Renderer je rovnoměrně násobí `cell_size`, včetně výšky. Robot i jeho náklad jsou potomky téže transformační skupiny. Jméno/ID, výběr a trasa pocházejí ze stejného snímku jako v 2D. HTML popisky jsou ve standardním React stromu; jejich pozici promítá kamera bez změn simulačního stavu.

Interpolace nastává jen pro stejnou session, následující tick a přesun nejvýše o jednu buňku. Používá skutečnou minulou a novou polohu, nikoli predikci. `prefers-reduced-motion` vyhlazení vypíná. Zobrazení může při pozastavení dokončit krátký přechod posledního potvrzeného kroku.

## Hranice této fáze

Logika zůstává diskrétní a rovinná. 3D výška je vlastnost vzhledu; nevznikají vícepatrové trasy, fyzikální kolize meshů ani simulace zdvihu. GLB animace kol, zdviže, dopravníku a signálních světel jsou příští fáze. Aktuálně se přenáší a otáčí celý robot a náklad se podle stavu ukazuje nebo skrývá.

Výchozí GLB loader neaktivuje Draco, Meshopt ani KTX2 dekodéry. Začněte nekomprimovaným GLB s PNG/JPEG texturami. Lokální dekodéry a kompresi přidejte společně, až bude základní export ověřený. Fyziku Rapier nepřidávat pouze kvůli vzhledu: autoritou pohybu zůstává existující engine.

Statické GLB používají instancing po jednotlivých mesh částech: například všechny regály sdílejí tři vykreslovací volání na render pass. Roboti a palety používají klony se sdílenou geometrií; robotovi se kopíruje pouze materiál barevného akcentu. Vykreslení bylo ověřeno i na mapě 40 × 28 s 32 roboty. To není záruka konkrétního FPS na každém zařízení. 3D knihovny mají větší samostatný chunk (přibližně 1 MB před gzip); načítá se až při prvním přepnutí na 3D.

## Odkazy k použitým knihovnám

- [React Three Fiber: Canvas, rendering a chybové stavy](https://r3f.docs.pmnd.rs/api/canvas)
- [Drei: GLTF loader a volitelné dekodéry](https://drei.docs.pmnd.rs/loaders/gltf-use-gltf)
- [Drei: OrbitControls](https://drei.docs.pmnd.rs/controls/introduction)
