# Strojové učení a generování skladů

Tento dokument popisuje dřívější experimenty s modelem Random Forest. Aktuální živé řízení používá síť, která se učí z vlastních jízd. [Popis současného řízení a průběžného učení](experiments/neural-fleet/report.md).

## Co se skutečně učí

Aplikace obsahuje učení s učitelem: `RandomForestRegressor` ze scikit-learn se z dokončených simulovaných jízd učí odhadnout čas od **přidělení úkolu robotovi do dokončení vykládky**. Cílová hodnota je `completed_tick − assigned_tick`. Jde o logické kroky simulace, nikoli čas výpočtu nebo čekání úkolu před přidělením.

Model odhaduje zpoždění nad jednoduchým základem:

```text
základ = BFS vzdálenost robota k nakládce
       + BFS vzdálenost nakládky k vykládce
       + doba nakládky a vykládky
cíl učení = max(0, skutečná doba − základ)
odhad ML = základ + max(0, průměr predikcí 96 naučených stromů)
```

Naučené stromy se opravdu používají při volbě robota. Scheduler `learned` řadí úkoly podle priority a pro každý připuštěný úkol vybírá dostupného přípustného robota s nejnižším předpovězeným časem. Shody řeší ID robota. Zůstávají kontroly baterie, nosnosti, dostupnosti stanic, plánování tras a centrální kontrola kolizí. Model neřídí jednotlivé pohybové kroky. Rozhodování je stejné ve 2D i 3D.

Je to naučený lokální regresní model. Není potřeba LLM, API klíč ani cloud. A*, CBS a Hungarian v projektu zůstávají samostatnými algoritmy vyhledávání a optimalizace.

## Postup v aplikaci

1. **Sklady → Generovat sklad:** nastavte rozměry, rozložení regálů, cílové pokrytí, počet robotů a úkolů a seed. Volitelně zapněte **Zúžené průjezdy**, jejich počet a šířku, a směr přeprav **Oba směry**. **Vygenerovat náhled** otevře editor. Náhled lze upravit a teprve potom uložit nebo spustit.
2. **Strojové učení → Model a trénink → Nasbírat data a natrénovat:** generátor vytvoří více různých skladů, backend je skutečně odsimuluje a natrénuje nový model. Počty map, robotů, úkolů, průjezdy, směr přeprav a seed lze měnit. Minimum je 60 dokončených přeprav z 5 rozložení. Stejné nastavení průjezdů a směru se používá v záložce Porovnání pro nové generované mapy; uložený scénář má vlastní konfiguraci.
3. **Porovnání:** zvolte referenční přiřazování a nové generované mapy, případně jeden uložený scénář. Každý scénář proběhne s oběma metodami. Výsledky i neúspěchy lze rozbalit a exportovat jako JSON.
4. **Simulace → Nastavení simulace → Způsob přiřazování → ML odhad doby přepravy:** nová simulace použije aktuální model. **Podrobnosti běhu** ukazují poslední skutečné rozhodnutí, kandidáty, jejich odhady a vybraného robota.
5. Dokončené přepravy z běžných simulací se průběžně ukládají. **Přetrénovat z uložených dat** vytvoří novou verzi z rozšířené datové sady. Učení není automatické po každém kroku: uživatel spouští přetrénování explicitně. Rozběhnutá simulace si ponechá původní verzi modelu i při resetu.

Při shodných parametrech generátoru včetně seedu vznikne shodný scénář. Opakovaný sběr stejných generovaných epizod data neduplikuje. Běžný reset simulace má vlastní ID epizody; opakované publikování snapshotů jednu epizodu pouze aktualizuje.

## Vstupní příznaky a data

Aktuální **verze 2 má 27 hodnot**. Zachovává původních 16: dvě skutečné BFS vzdálenosti, doba obsluhy, počet robotů, počet aktivních robotů, počet čekajících úkolů, podíl neprůchozích buněk, relativní baterie, využití nosnosti, počet robotů poblíž nakládky a vykládky, šířka a výška mapy, počet dostupných sousedních buněk robota a indikátory CBS/adaptivního plánovače.

Přidává 11 příznaků konkrétní kandidátní trasy:

| Příznak | Význam |
|---|---|
| `pickup_route_occupied`, `delivery_route_occupied` | Počet ostatních robotů právě stojících na geometrické cestě k nakládce / vykládce |
| `route_stationary_blockers` | Roboti na trase v klidu, offline, při nabíjení nebo obsluze |
| `route_reserved_overlap` | Součet překryvů buněk trasy se současnými plány ostatních robotů |
| `route_vertex_conflicts`, `route_head_on_conflicts` | Potenciální setkání v buňce nebo výměna protisměrné hrany při nominálním časování |
| `route_opposing_edges`, `route_same_direction_edges` | Společné hrany projeté opačně / shodně, bez požadavku stejného času |
| `route_narrow_cells`, `route_narrow_occupied` | Buňky trasy s nejvýše dvěma sousedy a roboti právě na těchto buňkách |
| `route_service_ticks` | Součet zbývající obsluhy robotů právě na trase |

Trasa používá jednu deterministickou nejkratší BFS cestu. Nominální čas zahrnuje nakládku a vykládku; časové konflikty a hrany používají horizont 64 kroků. Z plánů ostatních robotů se čte pouze aktuálně známý úsek; za jeho koncem se předpokládá obsazený koncový bod. Pozdější přepočet plánu není znám. Tyto příznaky jsou indikátory možného zdržení, nikoli skutečné budoucí kolize. Obsazení a geometrické zúžení se počítá přes celou cestu. V podrobnostech živého rozhodnutí jsou vidět součty obsazení obou úseků (tentýž robot může být na obou) a protisměrných hran.

Trénink používá pouze záznamy aktuální verze příznaků. Starší záznamy v1 zůstávají v databázi jako archiv a UI uvádí jejich počet; údaje o trasách se nevymýšlejí zpětně. Staré modely dál přijímají původních 16 vstupů, nové vyžadují všech 27. ID sběrové epizody obsahuje verzi příznaků, takže nový sběr nepřepisuje stará pozorování.

Vstupy se zachytí v okamžiku rozhodnutí před změnou stavu robotů. Výsledný čas se doplní až při skutečném dokončení přepravy. Nedokončené úkoly neposkytují regresní štítek; počet nedokončených přidělení a neúspěšných běhů je vykázaný zvlášť. Dokončené přepravy z později neúspěšné epizody mohou do učení vstoupit. Staré uložené běhy bez dispatch příznaků se dodatečně nevydávají za trénovací data.

Sběr na pozadí střídá nearest/priority/Hungarian a tři rozložení, rozměry a hustoty. Běžné simulace přidávají zkušenosti i z vlastních upravených map. Pozorování popisují jen skutečně vybrané roboty; neobsahují skutečný výsledek neprovedených alternativ. Odhady pro jiné kandidáty jsou generalizací modelu a mohou být nepřesné.

## Trénink a oddělení evaluace

- Random Forest: 96 stromů, maximální hloubka 12, nejméně 3 vzorky v listu, pevný seed, jeden výpočetní worker.
- `GroupShuffleSplit` oddělí přibližně 25 % **celých rozložení skladů** pro validaci. Hash rozložení zahrnuje rozměry, velikost buňky a všechny funkční/neprůchozí buňky; nezávisí na názvu mapy. Všechny epizody stejného rozložení zůstanou spolu.
- Stromy se trénují pouze na tréninkové části. Po změření MAE/RMSE se nepřeučují na validačních datech. Exportovaný model odpovídá právě měřenému modelu.
- Nové generované porovnávací mapy nesmějí být v tréninkové ani validační sadě dané verze. U vlastního uloženého scénáře se průnik nezakazuje, ale je viditelně vykázáno, kolik map bylo skutečně neznámých.
- Porovnání má fixovanou verzi modelu a identickou úplnou počáteční konfiguraci obou běhů. Výsledky porovnání se nevracejí do trénovací sady.
- MAE/RMSE měří **přesnost předpovědí** proti základu bez učení. Makespan, čekání, vzdálenost a úspěšnost měří **dopad scheduleru na sklad**. Jde o dvě různé otázky.
- Průměry provozních metrik jsou jen ze dvojic, v nichž dokončily obě metody. Úspěšnost má ve jmenovateli všechny dokončené pokusy porovnání, včetně neúspěchů. Selhání/časový limit se zachovává v jednotlivých výsledcích.

Dokumentace použitých metod: [RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html), [GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html), [prevence úniku dat](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## První skutečně změřený výsledek

Dne 13. 11. 2026: 12 map, počáteční seed 2026, 4 roboti a 24 úkolů na mapě. Všech 288 přeprav dokončeno. Trénink: 216 přeprav / 9 map; validace: 72 přeprav / 3 jiné mapy. Model `47accc59-d559-4892-823d-23edc9a78674`.

| Validační metrika (kroky) | ML | Základ bez učení |
|---|---:|---:|
| MAE | 0,1260 | 0,0556 |
| RMSE | 0,2946 | 0,2887 |

Následné porovnání 6 dalších map se seedy 9026–9031 proti priority scheduleru: obě metody dokončily 6/6 běhů, průměrný makespan obou byl 480 kroků, všechna přiřazení byla shodná. **Tento vzorek nepřinesl zlepšení; ML měl mírně horší chybu předpovědi.** Na těchto mapách vzniká minimum zpoždění nad nejkratší cestou. Široké uličky a konzervativní rezervace stanic omezují příležitost k přínosu modelu. To je omezení prostředí a výsledek experimentu, nikoli důvod upravovat výsledky.

Surová evidence: [párové běhy včetně scénářů](experiments/ml-comparison-initial.json) a [trénink, oddělené mapy a predikce](experiments/ml-training-initial.json). Další E2E kontroly mohou přidat data a aktivovat novou verzi; historické porovnání si stále ponechává původní model.

## Generátor a provozní limity

Generátor je procedurální, sám se neučí. Staví oddělené bloky regálů, vytváří nakládky, vykládky, domovské nabíječky a různorodé přepravní úkoly. Otevřený sklad má příčné a obvodové průchody. Režim zúžení přidá středovou stěnu tloušťky 2 buněk od horního po spodní okraj, s 1–3 průjezdy šířky 1–3 buňky; obvodem ji nelze objet. Volné uličky podél stěny zachovávají souvislost. Příliš mnoho širokých průjezdů pro nízkou mapu se odmítne. Režim Oba směry střídá úkoly zleva doprava a zprava doleva a rozmístí domovy na obě strany. Jde o směr přeprav, ne jednosměrné dopravní pravidlo pro jednotlivé buňky. BFS ověřuje souvislost všech průchozích buněk; doménová validace ověřuje scénář. Požadované hustoty nemusí dosáhnout kvůli chráněným uličkám — skutečné pokrytí je vidět v editoru.

Rozměry generátoru 12–64 × 10–64, 1–32 robotů, 1–200 úkolů; počet robotů musí odpovídat prostoru pro domovské stanice. Souvislost mapy a základní energetická proveditelnost nezaručují úspěšné víceagentní plánování.

Jedna ML úloha běží na pozadí v samostatném procesu; maximálně 30 map, výchozí limit 1 800 kroků na simulaci, nejvýše 4 000, plus 30 s kontrolovaných mezi kroky. Jedno plánování může tento čas mírně přesáhnout do vlastního limitu. Zrušení dokončí aktuální simulaci nebo dvojici a zastaví další práci. Nasbíraná data zůstanou uložená. Restart označí přerušené úlohy, neobnoví jejich výpočet.

Model, dataset a práce se ukládají jako JSON v existující PostgreSQL tabulce `documents` (`ml_model`, `ml_episode`, `ml_job`, `ml_settings`). Stromy mají přenosný JSON formát; při načítání se nespouští pickle. Test kontroluje shodu exportované inference se scikit-learn. API je zdokumentované v `/docs`: `/api/generator`, `/api/learning`, `/api/learning/jobs`, `/api/learning/jobs/{id}`, `/api/learning/jobs/{id}/cancel`, `/api/learning/models/{id}`.

Model se učí pouze ze zjednodušené simulace, nemá ověřenou platnost pro fyzické roboty ani pro jinou distribuci map, provozu či plánovačů. Není reinforcement learning a negarantuje globální optimum ani zlepšování po každém přetrénování. Validační mapy se při dalším přetrénování mohou přesunout mezi oddíly; pro srovnání verzí je vhodné navíc držet samostatnou neměnnou testovací sadu mimo sběr dat.


## Rozšířené měření na 90 mapách

Následný experiment s příznaky v1 přidal 8 640 přeprav z 90 nových skladů s 8/12/16 roboty a 96 úkoly. Tehdejší model používal 9 036 štítků z 109 map. Na stejných nových validačních mapách měl o 44,5 % nižší MAE než předchozí ML model; proti geometrickému odhadu zůstala MAE horší, RMSE celého holdoutu byla mírně lepší.

V 60 párových testech se 4/8/12/16 roboty měly obě metody stejná přiřazení a časy. Ve všech případech dokončily a nevykonaly kolizi. Přínos ML pro řízení skladu se tedy ani v tomto experimentu neprokázal. [Úplný report, limity, grafy a data](experiments/ml-traffic-study/report.md).

## Průjezdy, protisměr a příznaky tras v2

Další měření zahrnulo 90 sběrových map (87 dokončených, 3 neúspěšné) a 72 nových párových scénářů. Nový aktivovaný model `cea34362` má 5 690 štítků z 95 rozložení, z toho 5 602 nových přeprav. Provozní výsledek: původní řešení dokončilo 69/72 scénářů, ML 68/72; v 67 společně dokončených dvojicích ML 5× vyhrálo, 54× remizovalo a 8× prohrálo. Malé průměrné zrychlení u 8 robotů v úzkých průjezdech doprovází zhoršení u 12 robotů. Obecná převaha se neprokázala.

MAE nového holdoutu: 1,9991 proti geometrickému základu 1,7876; RMSE 2,9852 proti 3,5848. Výsledky jsou z jiné distribuce než starší studie a nejde o přímé porovnání kvality verzí. Model nebyl upravován podle nových testovacích výsledků. [Úplný report podle průjezdů, všechna selhání, zmrazený model a data](experiments/ml-route-study/report.md).
