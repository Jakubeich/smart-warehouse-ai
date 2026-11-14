# MASTER PROMPT — Smart Warehouse AI

## Role a hlavní zadání

Jsi zkušený tým seniorních softwarových inženýrů, AI/ML specialistů, algoritmiků, systémových architektů, UX/UI designérů a QA inženýrů.

Tvým úkolem je **navrhnout, implementovat, otestovat a zdokumentovat kompletní fullstack webovou aplikaci** s názvem **Smart Warehouse AI – Intelligent Multi-Robot Coordination System**.

Jedná se o vysokoškolský projekt pro předmět zaměřený na inteligentní systémy.

Oficiální název projektu:

**Návrh a experimentální vyhodnocení inteligentního systému pro koordinaci autonomních robotů ve skladovém prostředí.**

Nechci pouze prototyp, ukázkovou aplikaci, statický dashboard ani simulaci s předem připravenými animacemi. Chci skutečně funkční softwarový systém s algoritmickým jádrem, simulací, interaktivním uživatelským rozhraním a experimentálním vyhodnocením.

Pracuj přímo v dostupném projektovém adresáři. Pokud existující projekt neobsahuje žádný kód, vytvoř aplikaci od začátku.

Než začneš implementovat, analyzuj zadání, stanov architekturu, navrhni datové modely a rozděl práci do kontrolovatelných etap. Potom postupně implementuj aplikaci. Nezůstávej pouze u plánování.

Nevytvářej falešné implementace, nefunkční tlačítka, mockované výsledky vydávané za skutečné ani simulace, jejichž chování je jen vizuální iluze.

Pokud je některá funkce náročná, nejdříve implementuj její správnou základní variantu a následně ji rozšiřuj. Každá dokončená etapa musí být funkční a ověřitelná.

---

# 1. Základní koncept

Aplikace bude představovat inteligentní sklad, ve kterém autonomní mobilní roboti přepravují zboží mezi skladovými lokacemi a předávacími stanicemi.

Roboti musí:

- přijímat přepravní úkoly,
- získávat úkoly pomocí přiřazovacího algoritmu,
- plánovat cesty,
- koordinovat pohyb s ostatními roboty,
- předcházet kolizím,
- reagovat na dynamické překážky,
- řešit konflikty a blokování,
- vykonávat přepravní operace,
- spravovat baterii,
- případně se přesouvat do nabíjecích stanic,
- reportovat vlastní stav a výkonnost.

Uživatel prostřednictvím webové aplikace může:

1. Vytvářet a upravovat sklad.
2. Přidávat a konfigurovat roboty.
3. Vytvářet přepravní úkoly.
4. Volit různé plánovací algoritmy.
5. Spouštět a zastavovat simulaci.
6. Sledovat pohyb robotů v reálném čase.
7. Zobrazovat trasy, rezervace a konflikty.
8. Vytvářet překážky za běhu simulace.
9. Porovnávat efektivitu algoritmů.
10. Spouštět automatizované experimenty.
11. Ukládat a načítat scénáře.
12. Exportovat výsledky.

Systém musí být navržen tak, aby fungoval jako simulační a experimentální platforma, nikoli pouze jako demonstrační hra.

---

# 2. Zásadní architektonické rozhodnutí: 2D nyní, 3D později

**V první implementační etapě realizuj pouze plně funkční 2D aplikaci.**

Nyní NEIMPLEMENTUJ kompletní 3D prostředí.

Architekturu ale od začátku připrav na budoucí 3D vizualizaci pomocí:

- Blenderu,
- Three.js,
- React Three Fiber,
- Drei,
- GLTF/GLB modelů.

Simulační engine nesmí být závislý na grafickém rendereru.

Backend musí být jediným autoritativním zdrojem simulačního stavu.

Frontend pouze:

- vykresluje stav,
- zobrazuje statistiky,
- přijímá uživatelské příkazy,
- umožňuje interakci,
- případně interpoluje pozice pro plynulé animace.

Definuj společný model souřadnic, entit a scén.

Doporučené souřadnice:

- Sklad používá diskrétní souřadnice `(x, y)`.
- Každá buňka má definovanou velikost v metrech.
- 2D renderer zobrazuje mřížku shora.
- Budoucí 3D renderer mapuje `(x, y)` na horizontální rovinu `(x, 0, y)`.
- Výška 3D objektů je pouze vizuální vlastností.
- Logika pohybu a kolizí zůstává v simulačním enginu.

Důležité:

Žádné rozhodování, plánování cest ani fyzika simulačních kroků nesmí být implementována pouze ve frontendových komponentách.

Vytvoř oddělené vrstvy pro:

1. Domain model.
2. Simulation engine.
3. Pathfinding algorithms.
4. Task scheduling.
5. Simulation orchestration.
6. API a WebSocket komunikaci.
7. Rendering.
8. UI.
9. Experiment management.
10. Persistence.

Díky tomu půjde později vytvořit `Warehouse3DRenderer`, aniž by bylo nutné přepisovat existující algoritmy.

---

# 3. Technologický stack

Použij moderní, stabilní a kompatibilní technologie.

## Frontend

- React
- TypeScript se strict mode
- Vite
- Tailwind CSS
- shadcn/ui
- Zustand
- TanStack Query
- React Router
- PixiJS pro 2D vykreslování
- Recharts pro analytické grafy
- Lucide Icons
- Zod pro validaci dat
- Vitest
- React Testing Library
- Playwright pro E2E testování

Používej aktuální stabilní kompatibilní verze. Před instalací ověř kompatibilitu závislostí.

Pokud by PixiJS v konkrétním prostředí komplikoval implementaci, použij čistý Canvas 2D s jasně odděleným rendererem. Nedovol, aby volba vykreslovací knihovny narušila simulační architekturu.

## Backend

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- WebSockets
- NumPy tam, kde má praktický přínos
- pytest
- Ruff
- mypy
- uv pro správu Python prostředí

## Infrastruktura

- Docker Compose
- `.env.example`
- strukturované logování
- databázové migrace
- reprodukovatelné vývojové prostředí
- jednoduché příkazy pro spuštění všech komponent

Nepřidávej Redis, Celery, Kafka, Kubernetes nebo další infrastrukturní služby, pokud pro ně není skutečný technický důvod.

První verze má běžet lokálně bez placených API a externích cloudových služeb.

---

# 4. Návrh repository

Použij přehledný monorepo přístup.

Doporučená struktura:

```text
smart-warehouse-ai/
├── apps/
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── app/
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── features/
│   │   │   │   ├── dashboard/
│   │   │   │   ├── warehouse/
│   │   │   │   ├── simulation/
│   │   │   │   ├── robots/
│   │   │   │   ├── tasks/
│   │   │   │   ├── experiments/
│   │   │   │   └── analytics/
│   │   │   ├── renderers/
│   │   │   │   ├── shared/
│   │   │   │   └── 2d/
│   │   │   ├── stores/
│   │   │   ├── hooks/
│   │   │   ├── lib/
│   │   │   └── types/
│   │   └── tests/
│   └── backend/
│       ├── app/
│       │   ├── api/
│       │   ├── core/
│       │   ├── domain/
│       │   ├── simulation/
│       │   ├── algorithms/
│       │   ├── scheduling/
│       │   ├── experiments/
│       │   ├── persistence/
│       │   └── schemas/
│       └── tests/
├── docs/
│   ├── architecture/
│   ├── algorithms/
│   ├── experiments/
│   └── presentation/
├── scenarios/
├── scripts/
├── docker-compose.yml
├── README.md
└── AGENTS.md
```

Strukturu můžeš odborně upravit, pokud to sníží duplicity nebo zlepší organizaci.

Dodržuj principy:

- Separation of Concerns
- SOLID tam, kde přináší hodnotu
- DRY
- KISS
- typová bezpečnost
- nízká provázanost komponent
- dependency injection
- testovatelnost
- čitelný kód
- žádné kruhové závislosti
- žádné zbytečné abstrakce

---

# 5. Simulační engine

Implementuj vlastní deterministický simulační engine v Pythonu.

Simulace bude diskrétní, založená na časových krocích.

Každý tick představuje definovaný časový interval.

Engine musí podporovat:

- inicializaci scénáře,
- reset,
- start,
- pause,
- resume,
- single-step,
- změnu rychlosti simulace,
- ukončení,
- detekci dokončení scénáře,
- publikování stavu,
- záznam událostí.

Základní pravidla:

1. Engine vlastní stav všech robotů.
2. Každý robot má diskrétní logickou pozici.
3. Přechod do sousední buňky je definovaný pohyb.
4. Diagonální pohyb není v základní verzi povolen.
5. Robot může v jednom kroku zůstat na místě.
6. Dva roboti nesmí ve stejném kroku obsadit stejnou buňku.
7. Dva roboti si nesmí ve stejném kroku prohodit sousední pozice.
8. Pohyb do neprůchozí buňky je zakázán.
9. Neplatná změna stavu musí být bezpečně odmítnuta.
10. Výsledek musí být reprodukovatelný pomocí random seed.

Odděl logický čas simulace od reálného času počítače.

Simulace při vyšší rychlosti nesmí měnit algoritmické výsledky pouze proto, že frontend vykresluje více nebo méně snímků.

Implementuj centrální validátor přechodů a invariantů.

Proveď jasné oddělení:

- logického stavu,
- plánovaných tras,
- časoprostorových rezervací,
- vizuálně interpolovaných pozic.

Začni s roboty, jejichž přesun mezi sousedními buňkami trvá jeden tick.

Pozdější rychlostní profily a rozdílné velikosti robotů navrhni jako rozšíření, nikoliv jako komplikaci základního MAPF modelu.

---

# 6. Datové modely

Implementuj explicitní datové modely.

## Warehouse

- ID
- název
- šířka
- výška
- cell size
- kolekce buněk
- skladové lokace
- stanice
- metadata
- verze schématu

## Cell

Možné typy:

- FLOOR
- WALL
- SHELF
- PICKUP
- DROPOFF
- CHARGER
- OBSTACLE

Rozlišuj průchodnost buňky a její funkční typ.

Například pickup station musí být pro robota dosažitelná, zatímco fyzický regál může být neprůchozí.

## Robot

- ID
- název
- pozice
- orientace
- status
- aktuální úkol
- aktuální plánovaná trasa
- index trasy
- úroveň baterie
- nosnost
- aktuální náklad
- počitadlo splněných úkolů
- celková ujetá vzdálenost
- celková doba čekání
- aktuální režim

Stavy:

- IDLE
- ASSIGNED
- MOVING_TO_PICKUP
- LOADING
- MOVING_TO_DROPOFF
- UNLOADING
- WAITING
- CHARGING
- BLOCKED
- ERROR

Definuj platné stavové přechody.

## TransportTask

- ID
- pickup position
- dropoff position
- priority
- created tick
- assigned robot
- status
- load duration
- unload duration
- completed tick
- volitelné deadline
- payload weight

Stavy:

- PENDING
- ASSIGNED
- IN_PROGRESS
- COMPLETED
- FAILED
- CANCELLED

## SimulationState

- simulation ID
- current tick
- status
- algorithm configuration
- robots
- tasks
- warehouse
- active obstacles
- events
- metrics
- random seed

Připrav verzované serializační schéma pro snapshoty.

---

# 7. Implementace plánovacích algoritmů

Tato část je akademicky nejdůležitější.

Algoritmy nesmí být pouze názvy v uživatelském rozhraní.

Každý musí obsahovat vlastní funkční implementaci, dokumentaci, testy a měření.

## 7.1 A* jako referenční algoritmus

Implementuj A* pro hledání nejkratší cesty jednoho robota.

Požadavky:

- Manhattan heuristika
- priority queue
- `gScore`
- `fScore`
- rekonstrukce cesty
- neprůchozí buňky
- detekce nedosažitelného cíle
- deterministické řešení shodných priorit

A* použij jako low-level pathfinder a samostatnou referenční metodu.

Samostatné A* neřeší koordinaci více robotů. V experimentální části proto jasně rozlišuj mezi individuálním plánováním a víceagentním řešením.

## 7.2 Prioritized Planning

Implementuj základní víceagentní plánování s prioritami.

Princip:

1. Seřaď roboty podle priority.
2. Naplánuj cestu prvnímu robotovi.
3. Zapiš jeho časoprostorové rezervace.
4. Naplánuj dalšího robota s ohledem na existující rezervace.
5. Pokračuj pro ostatní roboty.

Implementuj:

- space-time A*
- vertex reservations
- edge reservations
- wait actions
- omezený plánovací horizont
- kontrolu konfliktů
- bezpečné ošetření situací bez řešení

Prioritizované plánování nemusí nalézt řešení, i když řešení existuje. Tuto vlastnost správně dokumentuj.

## 7.3 Conflict-Based Search (CBS)

Implementuj skutečný CBS algoritmus pro klasický diskrétní MAPF problém.

Low-level:

- space-time A*
- vertex constraints
- edge constraints
- wait actions
- omezení v čase
- rekonstrukce cesty

High-level:

- conflict tree
- detekce prvního konfliktu
- rozdělení konfliktu na dvě větve
- přidání omezení jednomu z robotů
- přepočítání dotčené trasy
- prioritní fronta CBS uzlů
- optimalizace podle Sum of Costs

Pro základní statické problémy se standardními předpoklady implementuj správnou optimální variantu CBS.

Důležité:

- Názvem CBS neoznačuj pouze prioritizované plánování.
- Nepoužívej falešný CBS fallback.
- Jasně specifikuj zacházení s roboty po dosažení cíle.
- Pro standardní MAPF použij stay-at-goal semantics.
- Zajisti, aby byly počáteční a cílové konfigurace validní.
- V situacích s omezeným časem nebo počtem uzlů vrať explicitní timeout či failure.
- Neinterpretuj timeout jako důkaz neexistence řešení.

CBS musí být možné testovat na známých malých MAPF scénářích.

Pokud použiješ omezení výpočetních zdrojů, nesmíš u výsledku s omezeným výpočtem tvrdit optimálnost bez příslušné záruky.

## 7.4 Dynamické přeplánování

Implementuj adaptivní mechanismus, který reaguje na:

- novou překážku,
- změnu dostupnosti buňky,
- přidání nového úkolu,
- dokončení úkolu,
- nedostupnost robota,
- blokovanou plánovanou trasu.

Algoritmus musí bezpečně:

1. Identifikovat dotčené roboty.
2. Zastavit nebezpečné přechody.
3. Přepočítat nové trasy.
4. Aktualizovat rezervace.
5. Znovu zahájit pohyb.

Pro základní verzi používej bezpečné globální přeplánování v synchronizačním bodě.

Jako pozdější optimalizaci můžeš zavést selektivní přeplánování.

Rozlišuj:

- plně statické offline plánování,
- online adaptivní koordinaci.

Nevydávej dynamické přeplánování automaticky za optimální algoritmus.

## 7.5 Porovnávání algoritmů

V aplikaci nabídni minimálně tyto režimy:

- A* Baseline
- Prioritized Planning
- CBS
- Adaptive Prioritized Planning

Samotný A* baseline může být omezen na nezávislé trasy s následnou bezpečnostní kontrolou. Pokud není schopen vyřešit konflikty, musí být běh označen jako neúspěšný, nikoliv proveden s kolizí.

Volitelně implementuj další relevantní algoritmus, například WHCA*, pokud budou základní metody dokončené a otestované.

---

# 8. Task Scheduling

Implementuj samostatný systém přiřazování přepravních úkolů.

Musí být oddělený od algoritmu plánování tras.

## Základní metody

### Nearest Available Robot

Úkol získá dostupný robot s nejnižší odhadovanou vzdáleností k pickup stanici.

### Priority-Aware Assignment

Přiřazování zohledňuje:

- prioritu úkolu,
- dostupnost robota,
- vzdálenost,
- baterii,
- nosnost.

### Globální přiřazování

Pro dávku úkolů implementuj metodu minimalizující celkové přiřazovací náklady, například pomocí Hungarian algorithm.

Algoritmus musí zvládat různý počet robotů a úkolů.

Nevytvářej tvrzení, že minimalizace přiřazovacích nákladů automaticky minimalizuje celkový makespan. Jsou to rozdílné optimalizační cíle.

V UI musí být možné zvolit scheduling strategy nezávisle na pathfinding strategy.

---

# 9. Energetický model robotů

Implementuj rozumně zjednodušený model baterie.

Robot spotřebovává energii při:

- pohybu,
- čekání, pokud je takto model nakonfigurován,
- manipulaci s nákladem.

Definuj:

- battery capacity
- battery level
- energy consumption per move
- charging rate
- critical threshold
- charging station

Pokud robot nemá dostatek energie na dokončení úkolu a bezpečný návrat k nabíjení, scheduler by mu neměl úkol přiřadit.

Implementuj základní politiku nabíjení.

Dokumentuj zjednodušení modelu.

Pokročilá optimalizace nabíjení může být volitelným rozšířením.

---

# 10. Warehouse Editor

Vytvoř interaktivní 2D editor skladu.

Uživatel musí být schopen:

- vytvořit nový sklad,
- nastavit rozměry,
- zoomovat,
- posouvat mapu,
- vybírat nástroje,
- kreslit podlahu,
- přidávat zdi,
- přidávat regály,
- umisťovat pickup/dropoff stanice,
- umisťovat nabíjecí stanice,
- přidávat roboty,
- mazat objekty,
- upravovat vlastnosti,
- uložit mapu,
- načíst mapu,
- exportovat/importovat JSON.

Požadavky na editor:

- přehledné souřadnice,
- vizuální mřížka,
- hover informace o buňce,
- náhled umístění objektu,
- rozumný zoom,
- pan,
- minimálně základní undo/redo,
- validace neplatných konfigurací.

Nedovol umístit roboty do zdí nebo mimo mapu.

Validuj dosažitelnost stanic tam, kde je to nutné.

Připrav alespoň tři demonstrační mapy:

1. Small Warehouse
2. Medium Warehouse
3. Large Warehouse

Mapy mají mít realistické uspořádání regálů, uliček a stanic.

---

# 11. Live Simulation

Vytvoř hlavní obrazovku simulace, která bude nejdůležitější částí celé aplikace.

## Rozložení

### Horní panel

- název scénáře,
- výběr algoritmu,
- aktuální tick,
- stav simulace,
- rychlost,
- start/pause,
- reset,
- step.

### Levý panel

- přehled robotů,
- seznam úkolů,
- filtry,
- výběr robotů.

### Střed

Velká interaktivní mapa skladu.

### Pravý panel

Detail vybraného robota nebo úkolu:

- status,
- poloha,
- baterie,
- aktuální cíl,
- trasa,
- vzdálenost,
- metriky.

### Spodní část

- event log,
- přehled statistik,
- případně časová osa.

## Vizualizace

Každý robot musí být viditelný jako vlastní objekt s:

- barvou,
- identifikátorem,
- orientací,
- stavovým indikátorem,
- zvýrazněním při výběru.

Kresli:

- plánovanou trasu,
- aktuální pohyb,
- cílovou stanici,
- rezervované buňky,
- konflikty,
- překážky.

Přidej volitelné visualization layers:

- Show Grid
- Show Paths
- Show Robot IDs
- Show Reservations
- Show Conflicts
- Show Stations
- Show Heatmap

Přechod mezi logickými buňkami vizuálně interpoluj pro plynulý pohyb.

Interpolace nesmí měnit autoritativní polohu robota.

---

# 12. WebSocket komunikace

Použij WebSocket pro živý přenos simulačních událostí.

Navrhni verzovaný protokol.

Typy zpráv:

- SIMULATION_STARTED
- SIMULATION_PAUSED
- SIMULATION_RESET
- STATE_SNAPSHOT
- STATE_DELTA
- ROBOT_UPDATED
- TASK_CREATED
- TASK_ASSIGNED
- TASK_COMPLETED
- OBSTACLE_ADDED
- PATH_REPLANNED
- METRICS_UPDATED
- SIMULATION_ERROR

Není nutné odesílat všechny typy jako samostatné zprávy, pokud lze efektivně použít snapshot/delta model. Události ale musí být jednoznačně reprezentovány.

Implementuj:

- validaci payloadů,
- reconnect,
- obnovení aktuálního snapshotu,
- monotónní sequence number,
- ochranu před zastaralými zprávami,
- odpojení klienta bez pádu simulace.

UI musí korektně zobrazovat stav připojení.

---

# 13. REST API

Navrhni konzistentní API přibližně v následujícím rozsahu:

```text
GET    /api/health

GET    /api/warehouses
POST   /api/warehouses
GET    /api/warehouses/{id}
PUT    /api/warehouses/{id}
DELETE /api/warehouses/{id}

GET    /api/scenarios
POST   /api/scenarios
GET    /api/scenarios/{id}

POST   /api/simulations
GET    /api/simulations/{id}
POST   /api/simulations/{id}/start
POST   /api/simulations/{id}/pause
POST   /api/simulations/{id}/step
POST   /api/simulations/{id}/reset

GET    /api/simulations/{id}/robots
GET    /api/simulations/{id}/tasks
POST   /api/simulations/{id}/tasks
POST   /api/simulations/{id}/obstacles

GET    /api/algorithms
GET    /api/experiments
POST   /api/experiments
GET    /api/experiments/{id}
GET    /api/experiments/{id}/results

WS     /ws/simulations/{id}
```

Přesné API můžeš upravit podle architektury.

Požadavky:

- konzistentní chyby,
- odpovídající HTTP statusy,
- Pydantic validace,
- generovaná OpenAPI dokumentace,
- oddělená DTO a doménové modely,
- bezpečné zacházení s neexistujícími prostředky,
- žádné blokování event loop dlouhými výpočty.

Výpočetně náročné plánování a experimenty prováděj mimo hlavní async event loop.

---

# 14. Dashboard

Vytvoř moderní úvodní dashboard.

Zobraz:

- počet vytvořených skladů,
- počet robotů,
- počet aktivních simulací,
- dokončené úkoly,
- aktuálně dostupné scénáře,
- poslední experimenty,
- rychlé spuštění simulace.

Použij skutečná data.

Pokud databáze neobsahuje žádná data, zobraz dobře navržený empty state a nabídni vytvoření ukázkového scénáře.

---

# 15. Experimentální modul

Toto je klíčová část pro vysokoškolské hodnocení.

Implementuj experimentální framework pro systematické porovnávání algoritmů.

## Konfigurace experimentu

Uživatel nastaví:

- skladovou mapu,
- počet robotů,
- počet úkolů,
- algoritmy,
- scheduling strategies,
- random seed,
- počet opakování,
- počet simulačních kroků,
- limity výpočtů.

Experiment musí být možné spustit bez grafického rendereru.

## Metriky

Měř minimálně:

1. Makespan.
2. Sum of Costs.
3. Completed Tasks.
4. Task Completion Rate.
5. Average Task Completion Time.
6. Total Distance Traveled.
7. Total Waiting Time.
8. Planning Computation Time.
9. Number of Replanning Events.
10. Number of Detected Planning Conflicts.
11. Number of Executed Collisions.
12. Algorithm Success Rate.

Pro každou metriku definuj přesný matematický význam.

Rozlišuj mezi:

- počtem konfliktů objevených při hledání,
- počtem kolizí během vykonávání plánu.

Bezpečné plánovací algoritmy by měly mít během platného běhu nulové vykonané kolize.

Plánovací konflikty ale mohou vznikat během řešení a být následně odstraněny.

## Experimentální scénáře

Vytvoř sadu benchmarků:

### Scenario A — Open Space

Roboti se pohybují na relativně otevřené mapě.

### Scenario B — Narrow Corridors

Sklad s úzkými uličkami.

### Scenario C — High Congestion

Větší počet robotů na omezeném prostoru.

### Scenario D — Dynamic Obstacles

Během simulace vznikají překážky.

### Scenario E — Increasing Fleet Size

Postupné navyšování počtu robotů.

### Scenario F — Task Scheduling

Porovnání různých metod přiřazování úkolů.

Ne všechny algoritmy musí řešit všechny typy scénářů. Jasně definuj jejich předpoklady a použitelnost.

CBS benchmarky v první řadě zaměř na statické MAPF problémy. Dynamické scénáře vyhodnocuj odděleně.

## Férovost experimentů

Stejné algoritmy musí dostat:

- totožnou mapu,
- stejné počáteční pozice,
- stejné cíle,
- stejné úkoly,
- stejné random seed,
- srovnatelné výpočetní limity.

Pro měření plánovacího času použij monotónní high-resolution timer.

U měření výpočetního výkonu zaznamenej také informace o prostředí.

Použij více opakování, pokud jsou výsledky ovlivněny náhodností.

Nedovol zaměňovat wall-clock runtime a simulated time.

## Výsledky

Umožni:

- tabulkové porovnání,
- čárové grafy,
- sloupcové grafy,
- průměr,
- směrodatnou odchylku,
- úspěšnost,
- export CSV,
- export JSON.

U každého výsledku musí být jasně uvedeno:

- který algoritmus byl použit,
- která konfigurace byla použita,
- zda běh úspěšně skončil,
- zda došlo k timeoutu,
- zda byl problém neřešitelný,
- zda výsledek pochází ze skutečného běhu.

Nevytvářej syntetické výsledky vydávané za empirická měření.

---

# 16. Analytics

Vytvoř analytickou obrazovku s grafy.

Zobraz:

- dokončené úkoly v čase,
- průměrnou čekací dobu,
- vytížení jednotlivých robotů,
- stav baterií,
- průchodnost skladu,
- efektivitu jednotlivých algoritmů,
- čas strávený plánováním.

Přidej heatmapu využití jednotlivých buněk skladu.

Heatmapa má vycházet ze skutečných zaznamenaných trajektorií robotů.

---

# 17. Vizuální design

Vytvoř profesionální UI připomínající průmyslovou simulační platformu nebo moderní SaaS produkt.

Nechci výchozí vzhled HTML formulářů.

## Design direction

- Dark-first design.
- Moderní industriální styl.
- Čistá typografie.
- Přehledné dashboardy.
- Konzistentní mezery.
- Jemné okraje a oddělovače.
- Kvalitní ikony.
- Barevné rozlišení stavů.
- Elegantní animace.
- Vizuální hierarchie.
- Přehledná datová tabulka.
- Responzivní layout.

Inspirace:

- průmyslové digital-twin dashboardy,
- moderní fleet-management software,
- simulační a analytické nástroje.

Doporučené barevné směřování:

- tmavé pozadí,
- neutrální povrchy,
- modrá/cyan pro aktivní operace,
- zelená pro dokončení,
- oranžová pro varování,
- červená pro chyby.

Používej barvy konzistentně a s dostatečným kontrastem.

Nedělej neonový design, který zhoršuje čitelnost.

## Navigace

Hlavní sekce:

- Dashboard
- Warehouses
- Simulation
- Robots
- Tasks
- Experiments
- Analytics
- Settings

Názvy navigace mohou být anglicky, ale architekturu připrav na lokalizaci.

Primární UI může být anglické, protože jde o technickou aplikaci. Dokumentace projektu však musí obsahovat i české akademické materiály.

---

# 18. Persistence

Použij PostgreSQL pro perzistentní data.

Ukládej:

- skladové mapy,
- scénáře,
- konfigurace robotů,
- konfigurace experimentů,
- výsledky experimentů,
- metadata běhů.

Není nutné ukládat každý simulační tick do databáze.

Preferuj:

- in-memory stav aktivní simulace,
- události/snapshoty pro export,
- trvalé uložení scénářů a dokončených výsledků.

Definuj jasný lifecycle aktivní simulace.

Při restartu backendu nesmí aplikace předstírat, že ztracená simulace stále běží.

---

# 19. Testování

Implementuj automatizované testy.

## Unit tests

Testuj:

- A*,
- Manhattan heuristiku,
- průchodnost buněk,
- vertex conflicts,
- edge swap conflicts,
- reservation table,
- space-time A*,
- prioritized planning,
- CBS conflict detection,
- CBS branching,
- assignment algorithms,
- validaci stavů,
- energetický model.

## Property-based nebo invariant tests

Ověř:

- žádní dva roboti nesdílejí jednu buňku,
- žádné dva roboty si neprohodí pozice v jednom kroku,
- robot nevstoupí do zdi,
- dokončený úkol má platnou historii,
- baterie nepřekročí povolené hranice,
- opakování deterministického scénáře dává stejný výsledek.

## Integration tests

Testuj:

- vytvoření skladu,
- uložení scénáře,
- vytvoření simulace,
- spuštění,
- přidání úkolu,
- dokončení úkolu,
- uložení výsledků,
- WebSocket komunikaci.

## E2E tests

Minimálně:

1. Uživatel otevře dashboard.
2. Vybere demonstrační sklad.
3. Spustí simulaci.
4. Pozoruje pohyb robotů.
5. Pozastaví simulaci.
6. Přidá nový úkol.
7. Znovu spustí simulaci.
8. Otevře experimenty.
9. Spustí jednoduchý experiment.
10. Zobrazí skutečné výsledky.

Testy musí být spustitelné lokálně.

---

# 20. Dokumentace pro vysokoškolský projekt

Vytvoř soubor dokumentace v `/docs`.

## README.md

Musí obsahovat:

- popis projektu,
- cíle,
- screenshoty nebo připravená místa pro skutečné screenshoty,
- technologický stack,
- požadavky,
- instalaci,
- spuštění,
- testování,
- přístup k API,
- popis scénářů,
- experimentální workflow.

## architecture.md

Popiš:

- architektonické vrstvy,
- komponentový diagram,
- datový tok,
- backend/frontend komunikaci,
- simulační lifecycle,
- oddělení algoritmů od rendereru.

## algorithms.md

Pro každý algoritmus:

- princip,
- pseudokód,
- časová/paměťová složitost tam, kde ji lze korektně vyjádřit,
- předpoklady,
- výhody,
- nevýhody,
- optimálnost/úplnost podle skutečné implementace.

## methodology.md

Definuj:

- výzkumné otázky,
- hypotézy,
- experimentální podmínky,
- metriky,
- metodiku měření,
- omezení validity.

## future-3d.md

Podrobně popiš, jak přidat 3D frontend.

Včetně:

- Blender workflow,
- exportu GLB,
- mapování souřadnic,
- hierarchie objektů,
- instancování regálů,
- animace robotů,
- optimalizace vykreslování,
- propojení se simulačními snapshoty.

## presentation-outline.md

Připrav osnovu prezentace na 10–15 minut:

1. Motivace.
2. Definice problému.
3. MAPF.
4. Navržená architektura.
5. Implementované algoritmy.
6. Simulační prostředí.
7. Experimenty.
8. Porovnání výsledků.
9. Živá ukázka.
10. Závěr.

Nevymýšlej si naměřené výsledky před provedením skutečných experimentů.

---

# 21. Připravenost na 3D a Blender

Ačkoli první verze bude pouze 2D, navrhni datové kontrakty pro pozdější 3D.

Definuj budoucí typy vizuálních entit:

- RobotVisual
- ShelfVisual
- WallVisual
- FloorVisual
- PickupStationVisual
- DropoffStationVisual
- ChargingStationVisual
- PalletVisual

Každá entita má:

- stabilní ID,
- typ,
- logickou pozici,
- orientaci,
- případné metadata,
- identifikátor vizuálního assetu.

Nevkládej odkazy na Blender modely do doménové logiky.

Počítej s budoucí adresářovou strukturou:

```text
assets/
└── models/
    ├── robots/
    │   ├── amr-basic.glb
    │   └── amr-industrial.glb
    ├── warehouse/
    │   ├── shelf.glb
    │   ├── pallet.glb
    │   ├── conveyor.glb
    │   ├── charger.glb
    │   └── station.glb
    └── environment/
        ├── walls.glb
        └── floor.glb
```

Tyto soubory nyní nevytvářej jako prázdné/falešné modely.

Pouze připrav dokumentaci a abstrahované datové rozhraní.

Budoucí 3D renderer musí být schopen:

- zobrazit sklad ve 3D,
- umístit modely podle souřadnic,
- animovat pohyb robotů,
- otáčet roboty podle směru pohybu,
- zobrazit stav baterie,
- zvýraznit vybraného robota,
- zobrazit trasu ve 3D,
- přepínat kameru,
- přibližovat a oddalovat,
- zobrazovat více robotů současně.

Simulační backend se při přidání 3D nesmí zásadně změnit.

---

# 22. Bezpečnost a robustnost

Aplikace musí správně zvládat:

- neplatné mapy,
- nemožné cíle,
- kolizní počáteční konfigurace,
- odpojení WebSocketu,
- přerušení experimentu,
- příliš velký scénář,
- timeout plánování,
- neřešitelné problémy,
- chyby databáze,
- nevalidní API vstupy.

Omez velikost vstupních scénářů.

Zajisti, aby výpočetně extrémně obtížný CBS scénář nezablokoval celý backend.

Používej rozumné limity.

V případě problému zobraz srozumitelnou chybu, nikoliv nekonečné načítání.

---

# 23. Implementační etapy

Implementuj projekt v následujícím pořadí.

## PHASE 1 — Foundation

- vytvoření monorepa,
- frontend,
- backend,
- databáze,
- Docker Compose,
- základní konfigurace,
- základní layout,
- health endpoint.

Výsledek: aplikace se spustí a komunikuje s backendem.

## PHASE 2 — Domain + Simulation Core

- datové modely,
- skladová mřížka,
- roboti,
- úkoly,
- deterministický tick engine,
- stavové automaty,
- invarianty.

Výsledek: simulační engine lze testovat nezávisle na UI.

## PHASE 3 — Pathfinding

- A*,
- space-time A*,
- reservation table,
- prioritized planning,
- CBS,
- testy algoritmů.

Výsledek: systém řeší malé i středně velké definované MAPF scénáře.

## PHASE 4 — 2D Warehouse Visualization

- interaktivní mapa,
- roboti,
- trasy,
- pan/zoom,
- výběr entit,
- animace.

Výsledek: funkční 2D vizualizace skutečné simulace.

## PHASE 5 — Simulation Control

- REST API,
- WebSocket,
- start/pause/reset,
- jednotlivé kroky,
- přidávání úkolů,
- stavové panely.

Výsledek: uživatel ovládá skutečnou simulaci ve webové aplikaci.

## PHASE 6 — Warehouse Editor

- kreslení skladu,
- umisťování robotů,
- validace,
- ukládání scénářů,
- import/export.

Výsledek: uživatel vytváří vlastní simulační prostředí.

## PHASE 7 — Intelligent Coordination

- scheduling strategies,
- dynamické přeplánování,
- překážky,
- energetický model,
- bezpečné řešení blokování.

Výsledek: roboti plní úkoly v měnících se podmínkách.

## PHASE 8 — Experiments and Analytics

- experiment runner,
- benchmark scenarios,
- měření,
- grafy,
- exporty.

Výsledek: projekt poskytuje skutečné empirické výsledky.

## PHASE 9 — UI/UX Polish

- finální design,
- responzivita,
- onboarding,
- empty states,
- loading states,
- error handling,
- optimalizace výkonu.

Výsledek: aplikace je připravená na živou prezentaci.

## PHASE 10 — Quality and Documentation

- kompletní testy,
- oprava chyb,
- dokumentace,
- instalační návod,
- akademická metodika,
- scénář prezentace.

Výsledek: reprodukovatelný a obhajitelný vysokoškolský projekt.

---

# 24. Akceptační kritéria

Projekt považuj za dokončený pouze tehdy, když platí:

- Frontend i backend lze lokálně spustit.
- Databázové migrace fungují.
- Aplikace obsahuje použitelné demonstrační scénáře.
- Uživatel vidí skutečně se pohybující roboty.
- Pohyb vychází z backendové simulace.
- Roboti vykonávají skutečné přepravní úkoly.
- A* je správně implementován.
- Prioritized Planning funguje.
- CBS funguje na testovaných MAPF scénářích.
- Dynamické přeplánování funguje v definovaném rozsahu.
- Bezpečnostní invarianty jsou ověřeny testy.
- Editor skladu funguje.
- Ukládání a načítání scénářů funguje.
- WebSocket poskytuje aktuální stav.
- Experimenty generují skutečné výsledky.
- Grafy používají skutečná data.
- Testy procházejí.
- Dokumentace odpovídá implementaci.
- Žádné klíčové tlačítko není pouze dekorativní.
- Aplikace je použitelná bez externích AI API.
- Architektura umožňuje přidat 3D renderer.

Pokud některé kritérium není splněno, uveď to v závěrečném reportu.

---

# 25. Pravidla pro práci implementačního agenta

Dodržuj následující pravidla.

1. Nejprve prozkoumej repository.
2. Vytvoř technický plán a seznam etap.
3. Udržuj `IMPLEMENTATION_PLAN.md`.
4. Zaznamenávej dokončené a nedokončené úkoly.
5. Implementuj funkční software, nejen návrh.
6. Nezaváděj duplicity.
7. Nezapouzdřuj chyby do prázdných `catch` bloků.
8. Nepoužívej `any` v TypeScriptu bez nezbytného důvodu.
9. Nepřidávej závislosti bez opodstatnění.
10. Nevytvářej falešná testovací data v produkčním dashboardu.
11. Neskrývej chyby algoritmů automatickým úspěšným fallbackem.
12. Dokumentuj každé algoritmické zjednodušení.
13. Po každé etapě spusť dostupné testy a build.
14. Oprav chyby před pokračováním.
15. Udržuj konzistentní veřejná rozhraní.
16. Nedovol logice frontendových animací měnit simulační stav.
17. Nepředstírej optimalitu nebo úplnost, pokud ji implementace negarantuje.
18. Při dlouhé práci průběžně aktualizuj plán, aby šlo navázat v nové relaci.
19. Nevyžaduj potvrzení každého drobného technického rozhodnutí.
20. Pokud narazíš na omezení prostředí, jasně ho zaznamenej a pokračuj v ostatních proveditelných úkolech.

---

# 26. Požadovaný výstup

Chci skutečný, běžící, testovaný projekt.

Po dokončení každé etapy stručně uveď:

- co bylo implementováno,
- které soubory byly vytvořeny nebo upraveny,
- jaké testy byly spuštěny,
- jejich výsledky,
- co zbývá,
- jak spustit aktuální verzi.

Nakonec připrav:

- kompletní README,
- architektonickou dokumentaci,
- dokumentaci algoritmů,
- experimentální metodiku,
- ukázkové scénáře,
- testovací sadu,
- návod pro budoucí 3D implementaci.

**Začni analýzou, návrhem architektury a implementací PHASE 1. Následně pokračuj dalšími etapami podle plánu, dokud to dovolují dostupné nástroje a kontext. Nepovažuj pouhé vytvoření kostry aplikace za dokončení projektu.**

Prioritou je technická správnost, kvalitní algoritmická implementace, reprodukovatelné experimenty a dobře použitelná aplikace.

Cílem je vytvořit projekt, který obstojí při odborné vysokoškolské prezentaci a ukáže skutečnou implementaci metod inteligentního plánování a multi-agent koordinace.