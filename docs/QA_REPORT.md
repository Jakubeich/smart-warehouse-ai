# Ověření Smart Warehouse AI

Aktualizace: 14. 11. 2026. Ověřena světlá česká verze s přepínáním 2D / 3D, modely z Blenderu, skutečným strojovým učením a generátorem skladů včetně úzkých průjezdů a protisměrných přeprav. Starší výsledky kontrol zůstávají níže označené po etapách.

## Automatické kontroly

| Kontrola | Výsledek | Rozsah |
|---|---|---|
| pytest | 39 passed | Algoritmy, energie, tick invarianty, determinismus, přepravy, API/DB, WebSocket, selhání a obnova perzistence |
| Nezávislý CBS oracle | 24 malých instancí v pytest | Srovnání statického SoC s joint-state Dijkstrou |
| Ruff | bez chyb | Backend aplikace a testy |
| mypy | bez chyb, 31 souborů | Strict backend typing |
| Vitest / React Testing Library | 11 passed | Protokol, sekvence, reset, souřadnice, stavy UI, česká validace, čtyři orientace 3D, bezpečné podmínky interpolace a GLB manifest |
| TypeScript + Vite build | úspěch | Produkční frontend; lazy routes a oddělené renderer/chart chunks |
| Playwright | 10 passed, 1,1 min | Skutečné browser workflow, Blender GLB, velký sklad s 32 roboty, bez console error / pageerror v hlavních 3D scénářích |
| GLB validace | 8 souborů, 0 chyb / 0 varování | glTF Transform 4.5.1 / Khronos validátor; samostatné soubory, jeden kořen, bez dekodérů |
| Blender roundtrip | 8 passed | Import optimalizovaných GLB, shoda obálek se zdrojem do 0,1 mm |
| npm audit | 0 vulnerabilities | Uzamčený frontend dependency tree při instalaci |
| Docker Compose | všechny 3 služby healthy | PostgreSQL, migrace, FastAPI, Nginx produkční frontend, API přes proxy |

pytest hlásí jednu upstream deprecation poznámku Starlette/TestClient k httpx. Nejde o selhání testu. Produkční build prošel. Vite upozorňuje na samostatný 3D chunk nad 500 kB (přibližně 1 MB před gzip); načítá se až při přepnutí na 3D. Three.js hlásí upstream deprecation `Clock` používaného React Three Fiber. Hlavní 3D průchod i načtení GLB prošly bez console error a pageerror.

## Browser workflow

1. Přehled → Malý sklad → Spustit → skutečný postup ticků → Pozastavit → ověření stabilního ticku → reload zachovávající session → robot a jeho Sheet → nový úkol → pokračování → experiment → čtyři skutečné výsledky → individual CBS optimality flag → CSV download.
2. Editor → nový sklad → umístění regálu → undo/redo → uložení do PostgreSQL → reload → načtení uloženého scénáře.
3. Mobil 390 × 844 → dosažitelné ovládání → žádné horizontální přetékání ani při tlačítku Pozastavit → otevření a zavření navigačního Sheet.
4. Nastavení simulace → změna planneru a potvrzení → Vrstvy / Teplotní mapa a Escape → jednotlivý krok → český záznam událostí → záložka Úkoly a vyhledávání „ceka“ → zamknutý planner po začátku běhu.

E2E sessions se po testu likvidují, aby opakované spuštění nevyčerpalo limit osmi sessions. Editor a experimenty zapisují označená testovací data do vývojové DB. V průběhu implementace byly staré testovací sessions a duplicitní E2E scénáře uklizeny.

Manuální ověření proběhlo nejprve v integrovaném prohlížeči. Po redesignu byl přímo ověřen start, reálný pohyb a pauza v ticku 32: dvě dokončené úlohy, 61 m a nula vykonaných kolizí. Playwright je součástí původně požadované testovací sady, nikoli náhradou za první browser kontrolu.

## Česká lokalizace

Přeložena navigace, všechny stránky a dialogy, stavy robotů/úkolů/běhů, serverové události a známé chyby. Validace Zod i číselných vstupů má české zprávy. Dokument má `lang="cs"`, čísla a data používají `cs-CZ`, data časové pásmo Europe/Prague. Vyhledávání stavu funguje i bez diakritiky. Názvy ukázkových skladů a výchozích experimentů se zobrazují česky; vlastní názvy a technické identifikátory API/exportů se nemění.

Produkční build, 7 Vitest/RTL testů a všechny 4 Playwright průchody prošly. Česká simulace byla navíc vizuálně ověřena v integrovaném prohlížeči a v aktuálních snímcích desktopu, mobilu a experimentů. Backend se při této úpravě neměnil; jeho výsledky výše pocházejí z předchozího ověření.

## Ověření přepínání 2D / 3D

Tok: **Simulace → 3D → kamera/výběr → 2D → porovnání snapshotu → 3D → reload → spuštění → přepnutí při jízdě → pauza → mobil**.

- Přepínání při pauze neodeslalo žádný POST do simulačního API. Celý snapshot před/po (včetně ID, ticku, úkolů a metrik) byl shodný.
- Za běhu se robotům změnily skutečné pozice, ID session zůstalo stejné a počet vykonaných kolizí byl nulový.
- Ověřen výběr robota, pohled shora, obnova kamery, uchování volby pohledu po reloadu a katalog modelů.
- Validní samostatný GLB testovacího robota se načetl z manifestu a dokončil krok bez chyb. Fixture je pouze testovací objekt, nevydává se za Blender model.
- Chybějící GLB ukázal hlášení a základní tvar; simulaci šlo dál krokovat.
- Skutečně vyvolaná ztráta WebGL kontextu nabídla návrat do 2D, snapshot zůstal nezměněný.
- Vizuálně ověřeno 1536 × 1024 a 390 × 844; na mobilu žádné horizontální přetékání.
- Během QA opraven konflikt HTML popisků s pomocnými React kořeny a překryv popisků sousedních robotů. Popisky jsou nyní ve společném React stromu a rozmísťují se bez překrytí.

| Kontrola 3D | Výsledek |
|---|---|
| Správná stránka a obsah | PASS — Živá simulace, mapa a ovládání |
| Framework overlay / prázdná stránka | PASS — žádná chybová překryvná vrstva |
| Konzole | PASS — žádné console error ani pageerror v hlavním průchodu a validním GLB; známé upstream upozornění Clock |
| Interakce a stav | PASS — přepínání, výběr, kamera, jízda, pauza, reload |
| Chyby modelu / GPU | PASS — náhradní geometrie / návrat do 2D |
| Screenshoty | PASS — [desktop](screenshots/simulation-3d-desktop.png), [mobil](screenshots/simulation-3d-mobile.png) |

Browser plugin not available; první vizuální ověření proběhlo přes dostupný integrovaný prohlížeč CUA, automatizace používá původně požadovanou projektovou sadu Playwright. Příkazy: `npm --prefix apps/frontend run build`, `npm --prefix apps/frontend test`, `npm --prefix apps/frontend run test:e2e`. Backend ani databázové schéma se touto změnou neměnily, jejich kontroly a Docker health v tabulce pocházejí z předchozí fáze. Finální uživatelské GLB modely a jejich výkon na cílovém hardwaru je potřeba ověřit po dodání.

## Modely z Blenderu a jejich zapojení

- Modelováno v živém Blenderu 5.2.3 LTS: AMR, regál, nakládka, vykládka, nabíjení, paleta s nákladem, stěna a překážka. Editovatelný `.blend`, generátor a render jsou v `assets/blender/`.
- Každý export má jeden kořen s identickou transformací, floor pivot, správné rozměry a +Y Up. Předek robota je +X, horní plošina 0,35 m. Stanice mají volný centrální průjezd. Zpětný import všech optimalizovaných souborů zachoval rozměry v toleranci 0,1 mm.
- Dedup/prune zmenšily sadu z 527 944 B na 389 292 B. Žádné externí textury, placené assety ani vzdálené dekodéry. Rozpočet robot/regál je 6 016 / 1 196 trojúhelníků. Podrobnosti v [reportu](../assets/blender/asset-report.json).
- Skutečný manifest a skutečné modely jsou v hlavním E2E průchodu: šest použitých typů hlásí „GLB načteno“, robot veze náklad, mění pozici a přepnutí pohledu zachovává stav. Malý sklad nepoužívá stěnu ani překážku; ty se navíc načetly v testu mapy 40 × 28 s 32 roboty a čtyřmi orientacemi.
- Statické GLB se instancují po mesh částech; robotům se sdílí geometrie a mění pouze materiál barevného akcentu. Chybějící robot i instancovaný regál mají ověřený náhradní tvar.
- Manuální kontrola v integrovaném prohlížeči: nové modely, katalog načtení, krok 129 → 130, dokončené úkoly 7 → 8, nula vykonaných kolizí. Automatické screenshoty byly vizuálně prohlédnuté na desktopu, mobilu i velké mapě.

Evidence: [Blender studio](../assets/blender/warehouse-assets.png), [3D desktop](screenshots/simulation-3d-desktop.png), [3D mobil](screenshots/simulation-3d-mobile.png), [velký sklad / 32 robotů](screenshots/simulation-3d-large.png).

Po zapojení modelů znovu prošel produkční build, všech 10 Vitest/RTL testů a všech 9 E2E průchodů. Backend se při této změně neměnil; jeho testy výše pocházejí z předchozího ověření. Kontrola velkého skladu ověřuje vykreslení a zachování snapshotu, nikoli rychlost plánování 32 robotů nebo garantovaný FPS na cílovém hardwaru.

## Vizuální kontrola

Referenční [koncept v2](design/simulation-concept-v2.png) i finální screenshot byly otevřeny přes image viewer a přímo porovnány. Záměrné rozdíly: skutečná geometrie skladu a data, souřadnice od nuly, přidání úkolu, přístup k překážkám a stav výběru. Dekorativní data z konceptu nejsou součástí aplikace.

| Oblast | Ověření |
|---|---|
| Hierarchie a rozložení | Jedna lišta, dominantní mapa, jeden postranní seznam, tři malé souhrny. Inspektor a události nezabírají místo bez vyžádání. |
| Typografie | Jednotné 14px ovládání, 26px nadpisy, větší popisky než v původní verzi. Na mobilu minimální velikost mapových popisků; při malém měřítku jen ID vybraného robota, další po přiblížení. |
| Paleta a povrchy | Bílé/zinkové plochy, neutrální linky, jedno indigo pro hlavní akce. Odstraněny gradienty a barevné metrické karty. |
| Komponenty | shadcn/ui + Radix: jednotná tlačítka, formuláře, Dialog, Sheet, Tabs, DropdownMenu, Collapsible; Lucide ikony. |
| Obsah a odezva | Reálné snapshoty, jasné empty/error stavy, méně marketingového textu. Experimenty mají oddělené záložky. |
| Responsivita | Desktop 1536 × 1024, mobil 390 × 844. Na mobilu je mapa před flotilou a navigace v menu. |

Evidence: [desktop simulace](screenshots/simulation-desktop.png), [mobil simulace](screenshots/simulation-mobile.png), [experimenty](screenshots/experiments-desktop.png). Snímky byly vytvořeny skutečnými E2E běhy, nikoli image generátorem.

## Reálné měření a omezení

96 benchmark runů A–F, z toho 84 úspěšných; surová data a interpretace jsou v [experimentálních výsledcích](experiments/results.md). Konfliktní baseline plány se nikdy nevykonávají. Small a Medium dokončují koordinované přepravy. U Large CBS s limitem 2 s / 2 000 uzlů nastal timeout; nebyl nahrazen jiným algoritmem.

Tyto kontroly nejsou důkazem správnosti všech map ani plným auditem přístupnosti. Body robotů jsou diskrétní, prioritizované plánování není úplné, energetický odhad může selhat na dlouhých objížďkách a aktivní session nepřežije restart backendu. Platí další limity popsané v README. Animace jednotlivých částí modelů a autentizace zatím nejsou implementované. 3D vzhled nemění rovinnou diskrétní logiku simulace.

## Spuštění a opakování

`make dev` spouští lokální prostředí, `make test`, `make check` a `make e2e` kontroly. `docker compose up --build -d --wait` spustí produkční sestavení lokálně. Testovací Compose deployment byl ověřen na náhradních portech 15173/18000, aby nekolidoval s běžícím vývojem 5173/8000. Po ověření jsou duplicitní aplikační kontejnery zastaveny; PostgreSQL zůstává pro vývoj běžet.


## Strojové učení a generátor

Implementace: Random Forest se učí ze skutečných dokončených přeprav, model vstupuje do výběru robotů. Generátor používá seed, průchozí geometrii a doménovou validaci. Rozhraní odděluje trénink, validační chybu a skutečné porovnání provozu; všechny texty jsou česky a používají stávající shadcn/ui komponenty.

| Oblast | Ověření |
|---|---|
| Backend | 39 testů: původní invarianty plus determinismus a souvislost generátoru, dispatch příznaky a skutečné štítky, neúplné jízdy, mapový holdout, JSON inference, ML minimum a energetická omezení, párové průměry, izolace evaluace, perzistence a reset, idempotentní sběr, souběžný start a zrušení práce |
| Frontend | 11 testů; nový test zachování současného běhu při chybějícím ML modelu. Strict TS a Vite build prošly. |
| Nový E2E | Generátor → náhled → uložení/reload → reprodukce seedu → 5 skutečně simulovaných tréninkových map → nový model → 2 dosud nepoužité párové scénáře → ML přiřazování → 3D → dokončení 8 úkolů → růst datasetu přesně o 8 štítků |
| Oddělení dat | Porovnání nezměnilo dataset; model zůstal pro oba porovnávané běhy fixovaný. Opakovaný snapshot dokončené simulace data nezdvojil. |
| Stav a bezpečnost | Kandidáti z UI odpovídají serveru; zvolen minimální ML odhad. Přepnutí na 3D zachovalo celý snapshot. Živý běh dokončen s nulou vykonaných kolizí. |
| Konzole a layout | Nový E2E bez console error/pageerror, desktop 1536 × 1024, mobil 390 × 844 bez horizontálního přetečení stránky. Tabulky mají vlastní posun. |
| Regrese | Všech 10 E2E scénářů prošlo, včetně Blender GLB, fallbacku, kontextu WebGL, 32 robotů, editoru a starších experimentů. |
| Manuální kontrola | Integrovaný prohlížeč: první trénink 12 map, dokončené porovnání 6 nových map, generátor s editovatelným náhledem. Finální E2E screenshoty otevřeny a vizuálně prohlédnuty. |

Evidence: [model a trénink](screenshots/learning-desktop.png), [porovnání](screenshots/learning-comparison.png), [mobil](screenshots/learning-mobile.png), [mobilní porovnání](screenshots/learning-comparison-mobile.png), [generátor](screenshots/warehouse-generator.png), [vygenerovaný sklad](screenshots/warehouse-generated.png), [ML rozhodnutí ve 3D](screenshots/learning-dispatch-3d.png).

První model na 288 přepravách nepřekonal základ: MAE 0,1260 proti 0,0556. Šest nových testovacích map dokončilo priority i ML se stejným průměrným makespanem 480 kroků a totožným přiřazením. Nejde o doklad zlepšení ML. [Surové výsledky a interpretace](machine-learning.md). E2E přidal další skutečná tréninková data a aktivoval další model; původní report je uložen samostatně. Snímky zachycují pozdější E2E model, nikoli původní měření.

Aktuální Python/TypeScript/build/test kontroly byly spuštěny po změně ML. Schéma DB zůstává stejné. Docker/GLB/npm audit výsledky v tabulce pocházejí z předchozí fáze; při tomto doplnění se samostatně neopakovaly. Zůstává upozornění Vite na lazy 3D chunk a upstream Starlette/Three.js deprecation. Automatické přetrénování po každém ticku není součástí aplikace; data se sbírají automaticky, model se přetrénuje explicitním tlačítkem.


## Rozšířený experiment s hustším provozem

90 nových tréninkových map s flotilami 8/12/16 a 96 úkoly; 60 dalších párových porovnání se 4/8/12/16 roboty. Všech 120 testovacích simulací dokončilo všechny úkoly, nula vykonaných kolizí. Přiřazení i časy obou metod byly totožné — větší trénink zde nepřinesl provozní zrychlení. Nový model má 9 036 štítků z 109 map; na stejných nových validačních mapách klesla MAE proti předchozímu modelu o 44,5 %, ale geometrický základ má stále nižší MAE.

Ověřeno: předem uložený plán a hashe nezměněných simulačních zdrojů; oddělení všech testovacích map od tréninku/validace; shodné úkoly a konfigurace v párech i odpovídající geometrie napříč flotilami; zachování datasetu během evaluace; opakování tréninku ze zmrazeného datasetu reprodukuje přesně všech 96 stromů a metriky. Skripty prošly Ruff; orchestrace, analýza a report také strict mypy.

Drobné upřesnění UI: uložená porovnání mají počet robotů v názvu a výsledek uvádí skutečné počty a seed. 11 frontendových testů a produkční build prošly. Browser plugin not available; cílený read-only Playwright průchod vybral všechny čtyři uložené výsledky, ověřil model, rozbalení jednotlivých běhů a zobrazení 1536 × 1024 / 390 × 844 bez console error/pageerror a bez přetečení stránky. Screenshoty i graf byly vizuálně prohlédnuty. Celá starší E2E sada se znovu nespouštěla, protože obsahuje trénink a měnila by právě měřený model/dataset. Backend aplikace se neměnil; jeho dřívější testy zůstávají předchozí evidencí.

[Report včetně všech dat](experiments/ml-traffic-study/report.md), [desktop](experiments/ml-traffic-study/app-16-robots.png), [mobil](experiments/ml-traffic-study/app-mobile.png), [reprodukce modelu](experiments/ml-traffic-study/reproducibility.json). Běžící uživatelská simulace zůstala zachovaná; během sběru poskytla dalších 20 skutečných dokončených přeprav.

## Průjezdy a protisměrné přepravy — v2

Ověření dokončeno 14. 11. 2026. Generátor přidává skutečnou stěnu s volitelnými průjezdy a přepravy v obou směrech. Model má 27 příznaků včetně obsazení konkrétní kandidátní trasy a známých plánů ostatních robotů; starší data jsou oddělená podle verze.

| Kontrola | Výsledek |
|---|---|
| Backend | 47 testů prošlo; Ruff čistý, strict mypy bez chyb v 31 zdrojových souborech |
| Nové regresní testy | Čtyři kombinace počtu/šířky průjezdů: žádné objetí, souvislost, polovina úkolů opačně, proveditelná energie; odmítnutí nevejdoucích se průjezdů; skutečná obsazenost a protisměrné hrany; nezávislost příznaků na budoucích výsledcích a plánech za horizontem; BFS cesta; kompatibilní v1 inference a vyloučení v1 štítků z nového tréninku |
| Frontend | 11 testů, strict TypeScript a produkční build prošly |
| E2E | V úplné sadě prošlo 9 ostatních workflow. ML test nejprve narazil na dvě uložené mapy se stejným názvem po změně verze generátoru. Dostává samostatný název `E2E průjezdy ML v2`; následný celý ML průchod prošel. Všech 10 workflow je ověřeno napříč těmito běhy, nikoli jedním souvislým během. |
| ML E2E | Úzké průjezdy a oba směry → uložený scénář → 5 reálných tréninkových map → model v2 → 2 neznámé párové mapy → živé ML rozhodování ve 3D → dokončení 8 úkolů bez kolizí; přesný přírůstek štítků a zachování stavu při změně rendereru |
| Závěrečné UI | Read-only Playwright vybral všech 6 výsledků hlavního měření, ověřil model, počty/seed a rozbalené neúspěchy; desktop 1536 × 1024 a mobil 390 × 844 bez přetečení stránky a bez console error/pageerror. Screenshoty mapy, 3D rozhodnutí, výsledků a grafu vizuálně zkontrolovány. |
| Reprodukce | Zmrazená vstupní data přesně reprodukují 96 stromů, metriky, train/holdout, importance a hash. Zkontrolované zdrojové hashe, izolace testovacích map a neměnný dataset při evaluaci. Ruff prošel na pěti skriptech; orchestrace, analýza, zmrazení a report prošly strict mypy. |

Hlavní měření: 90 sběrových pokusů, 87 dokončených a 3 `NO_PLAN`, 5 602 nových přeprav. Model `cea34362` používá celkem 5 690 štítků / 95 rozložení; 9 036 původních v1 štítků zůstává archivovaných. Jedna mapa bez dokončené přepravy není mezi mapami modelu, ale je zachovaná v archivu všech pokusů.

V 72 párových testech dokončilo priority 69 a ML 68 scénářů; ve všech 144 bězích nula vykonaných kolizí. ML vyhrálo 5, remizovalo 54 a prohrálo 8 z 67 společně dokončených dvojic. Menší zrychlení u 8 robotů v úzkých průjezdech neprokazuje celkovou výhodu: u 12 robotů byly dva další neúspěchy ML. Všechny výsledky zůstávají zachované; žádné přepnutí plánovače při selhání ani ladění na testovacích mapách.

Evidence: [report a všechna data](experiments/ml-route-study/report.md), [desktop](experiments/ml-route-study/app-two-narrow-12.png), [mobil](experiments/ml-route-study/app-mobile.png), [graf](experiments/ml-route-study/comparison.png), [reprodukce](experiments/ml-route-study/reproducibility.json), [browser log](experiments/ml-route-study/browser-verification.json). Generátor a 3D rozhodnutí jsou také v aktualizovaných snímcích `screenshots/warehouse-generated.png` a `screenshots/learning-dispatch-3d.png`.

Při nasazení backendu v2 byl předchozí dokončený snapshot zálohován do `.run/pre-route-learning-sessions.json`; restart aktivní paměťové session neobnovuje. Databázové schéma i Blender assety se neměnily. Vite upozornění na velikost lazy 3D chunku a dřívější upstream deprecations zůstávají známým omezením.
