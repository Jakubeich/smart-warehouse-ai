# Experimentální metodika

Oficiální název: **Návrh a experimentální vyhodnocení inteligentního systému pro koordinaci autonomních robotů ve skladovém prostředí.**

## Výzkumné otázky a hypotézy

RQ1: Jak se mění plánovací čas a Sum of Costs při přechodu od nezávislého A* přes prioritizované plánování k CBS? H1: CBS na zvládnutelných statických případech najde minimální SoC, ale jeho čas poroste s konflikty.

RQ2: Jak ovlivní počet robotů a topologie úspěšnost? H2: Úzké průchody a vysoká obsazenost zvýší počet neúspěchů/timeoutů při stejném rozpočtu.

RQ3: Jaký vliv má scheduler na transportní propustnost při stejné admission policy? H3: Minimální součet přiřazovacích nákladů nezaručí minimální makespan celé simulace.

RQ4: Zachová synchronní globální přeplánování bezpečnost při dynamické překážce? H4: Invarianty zůstanou zachovány; úspěšné dokončení závisí na zbývající dosažitelnosti a limitech.

## Dva experimentální režimy

**Static MAPF** používá jednorázovou start/goal konfiguraci, stay-at-goal a bez manipulace/baterie. Primární prostředí pro optimalitu CBS. Každé splněné „task“ v jednotném výsledkovém schématu znamená dosažený MAPF cíl, nikoli přepravní zásilku. Neúspěšná baseline trasa se nevykoná.

**Online transport** měří celý tick engine včetně scheduleru, admission, nakládky, vykládky, návratů a nabíjení. Online přeplánování není globálně optimální. Režimy se nesmí slévat do jedné tabulky bez označení.

## Benchmarks A–F

| ID | Konstrukce | Doporučený režim |
|---|---|---|
| A Open Space | Vybraná mapa bez SHELF buněk | static MAPF |
| B Narrow Corridors | Původní uličky vybrané mapy | static MAPF |
| C High Congestion | Počátky soustředěné do sousedních volných buněk, zvýšená flotila | static MAPF |
| D Dynamic Obstacles | Pevná změna stejné buňky v ticku 5 pro každý běh | transport |
| E Increasing Fleet Size | Stejný seed při flotilách 2, 4, 8 | static MAPF |
| F Task Scheduling | Stejná dávka úkolů pro nearest/priority/Hungarian | transport |

Konfigurace jsou v `scenarios/benchmarks/`. V D je buňka deterministicky první vhodná podlahová buňka mimo okrajové řady; pokud ji v okamžiku změny obsadí robot, změna je odmítnuta a zaznamená se neúspěch. Tato intervence nemusí zasáhnout každou trasu; pro cílený stresový test vytvořte mapu s relevantním úzkým průchodem. C nezaručuje konkrétní hustotu bez volby vhodné mapy a počtu robotů. E samo nemění jinou geometrii než domovské nabíjecí buňky navíc; u všech algoritmů dané fleet size je totožná.

## Férovost a reprodukovatelnost

Pro každou kombinaci seed/fleet se z původního scénáře vytvoří čerstvá kopie. Počátky, cíle, stanice a priority jsou deterministické. Opakování r používá seed+r, tj. různé ale párované instance. Parametry, původní scénář a environment jsou součástí JSON exportu. Při výhradním měření časového šumu opakujte stejný seed v samostatných experimentech.

Neměňte limity algoritmů uvnitř porovnávané skupiny. Zaznamenejte Python, platformu, architekturu, engine version a zátěž stroje. `perf_counter()` měří výpočetní čas monotónně; simulated time je tick·tick_seconds. Rychlost UI 0.25×–16× mění jen reálné tempo publikování, nikoli kroky ani výsledky enginu. Wall-clock timeout ovšem může na přetíženém stroji změnit úspěšnost limitovaného hledání; není součástí deterministické logiky.

## Přesné metriky

Nechť T je poslední provedený tick, k počet robotů, n počet úkolů, C množina dokončených úkolů, d_i počet pohybů, w_i počet ticků čekání na trase (bez služby/nabíjení/idle), a_j tick vytvoření a f_j tick dokončení.

| Metrika | Transport | Static MAPF |
|---|---|---|
| Makespan | T; pro neúspěch jde o dobu do zastavení, nikoli dobu dokončení | max_i τ_i, kde τ_i je finální příjezd |
| Sum of Costs | Σ_i(d_i+w_i), včetně návratových pohybů před koncem běhu; nejde o klasické MAPF SoC | Σ_i τ_i |
| Completed Tasks | \|C\| | k při validním společném řešení, jinak 0 |
| Task Completion Rate | \|C\|/n; pro n=0 je 1 | 1 při společném úspěchu, jinak 0 |
| Average Task Completion Time | Σ_(j∈C)(f_j−a_j)/\|C\|; 0 bez dokončených | průměr τ_i úspěšného řešení |
| Total Distance | cell_size·Σ_i d_i v metrech | stejný výpočet z validních tras |
| Total Waiting | Σ_i w_i v tick jednotkách | SoC − počet skutečných pohybů |
| Planning Computation Time | součet perf_counter intervalů všech volání plánovače, ms | čas jediného volání, ms |
| Replanning Events | počet globálních plánovacích volání, včetně prvního | 0 (jednorázové offline plánování) |
| Detected Planning Conflicts | konflikty skutečně nalezené CBS / kontrolou baseline; PP rezervace konflikty předchází a zde vykazuje 0 | totéž |
| Executed Collisions | 0 při validním běhu; neplatné přechody se odmítají před provedením | 0, validovaný plán se logicky přehraje v testech |
| Algorithm Success Rate | úspěšně dokončené běhy / všechny pokusy | společná řešení / všechny pokusy |
| Throughput | \|C\|/(T·tick_seconds), UI násobí 60 pro tasks/min | nevyhodnocuje se |
| Robot utilization | busy_ticks/T, zahrnuje dopravu, službu, návrat a charging | nevyhodnocuje se |
| Heatmap | počet robot-tick obsazení buňky po provedeném ticku, včetně stání | nevyhodnocuje se |

Nulové kolize samy o sobě nedokazují schopnost vyřešit úlohu: algoritmus, který okamžitě odmítne plán, také nezpůsobí kolizi. Vždy uvádějte úspěšnost společně s cenou a časem. Počet nalezených konfliktů není přímo srovnatelnou mírou bezpečnosti různých metod.

## Agregace a limity validity

Tabulky uvádějí průměr a populační směrodatnou odchylku σ=√(Σ(x−μ)²/N). Kvalita cest (makespan/SoC/distance) se agreguje jen z úspěšných běhů; plánovací čas a konflikty ze všech. Ve skupině bez úspěchu je cena `null`, ne falešná nula. Jednotlivé výsledky zůstávají exportované. Neúspěch/timeout se nesmí vynechat ze jmenovatele úspěšnosti.

Výchozí limity: PP horizont 128, CBS 2 000 CT uzlů, jedno hledání 2 s, transport 500 ticků; navíc 30 s wall limit na run (nastavitelné API 1–120 s), max 120 runů na experiment. Zrušení zastaví zahajování dalších runů; probíhající run může doběhnout do svého limitu. Extrémně tvrdý real-time preemption Python operace není garantován.

Jde o diskrétní bodové roboty, bez kinematiky, rozměrů, nejistoty senzorů či fyziky. Konzervativní station admission a návrat domů významně ovlivňují provoz. Vzorek dodaných malých benchmarků je demonstrační, nestačí pro obecná statistická tvrzení. Ke školní obhajobě přiložte CSV/JSON, přesné konfigurace, omezení a skutečný čas měření.

## Experiment se strojovým učením

RQ5: Přinese naučený odhad času lepší přiřazování robotů než dosavadní vzdálenostní/bateriová heuristika? Model se učí rozdíl mezi skutečnou dobou od přidělení po vykládku a vzdálenostním základem. Validace odděluje celé mapy a uvádí MAE/RMSE proti základu bez učení. Následné párové běhy na dalších mapách měří skutečný dopad scheduleru na dokončení všech úkolů, čekání, vzdálenost a úspěšnost. Přesnost regrese a provozní výkon nejsou zaměnitelné.

Stránka Strojové učení používá vlastní párovou agregaci: provozní metriky (i plánovací čas) pouze z dvojic, kde dokončily obě metody; úspěšnost ze všech pokusů. V JSON zůstávají všechny výsledky, stejné počáteční scénáře, seedy a fixovaný model. Porovnávací epizody nikdy nevstupují do tréninku. UI nepředstírá statistickou významnost z malého počtu map.

První demonstrační měření neprokázalo přínos ML. [Konkrétní čísla, metodika dělení dat, omezení a surová evidence](machine-learning.md). Pro další výzkum rozšiřujte rozmanitost a vytížení skladů, držte samostatnou testovací sadu a vyhodnocujte také neúspěchy; nevybírejte pouze běhy, ve kterých model vyšel lépe.

Následný [experiment s průjezdy a protisměrem](experiments/ml-route-study/report.md) má předem uložených šest podmínek (počet/šířka průjezdů a 4/8/12 robotů), 90 sběrových pokusů a 72 nových párových testů. Nové příznaky v2 nejsou zpětně doplňované do starých dat. Model je před testy zmrazený a hash datasetu i zdrojů ověřený. Průměr času pouze úspěšných dvojic je nutné číst současně s úspěšností: např. u 12 robotů dokončilo 11/12 původních a 9/12 ML běhů. Srovnání nepřineslo obecný přínos ML. Report uchovává i nulově dokončený sběrový běh, přesná data, model, explorační intervaly a reprodukci tréninku.
