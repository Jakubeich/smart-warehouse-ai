# Algoritmy a jejich záruky

## Model MAPF

Neorientovaná čtyřsousední mřížka, jednotkové ceny pohybu/čekání, různé počátky a různé cíle. Trasa obsahuje počáteční pozici v čase 0. Po posledním prvku agent zůstává v cíli (`stay-at-goal`). Zakázán je vertex konflikt i souběžné prohození protisměrné hrany. Následování robota do právě uvolněné buňky je dovoleno. Tyto předpoklady odpovídají rozlišení variant problému v [Stern et al., 2019](https://arxiv.org/abs/1906.08291).

## A*

Manhattan heuristika je na této mřížce přípustná a konzistentní. Implementace používá `heapq`, `g_score`, implicitní `f=g+h`, rodiče a monotónní pořadové číslo pro deterministické shody. Zastaralé záznamy fronty se přeskočí. Pro jeden dosažitelný cíl vrací nejkratší cestu; neprůchozí či nedosažitelný cíl vrací `None`.

```text
g[start] = 0; open.push(h(start), start)
while open:
    u = pop smallest f, g, insertion order
    if u == goal: reconstruct parents
    for traversable neighbor v:
        if g[u]+1 improves g[v]: update parent and push g[v]+h(v)
return no path
```

Na konečném grafu s binární haldou O((V+E) log V), paměť O(V+E) včetně záznamů fronty. `A* Baseline` počítá nezávislé trasy a kontroluje celý společný plán. Konflikt znamená neúspěch bez vykonání pohybu. Jednoagentní optimalita není víceagentní koordinace.

## Space-time A* a rezervace

Stav `(position,time)`, akce čtyři sousedé + wait, g = čas od startu. Kontroluje vertex constraint v cílovém čase a orientovanou edge constraint na příjezdu. Reservation table ukládá obsazené `(cell,t)` a `(from,to,t)`; pro dalšího robota zakáže i opačnou hranu. Koncová buňka je rezervovaná trvale.

Cíl lze přijmout jen pokud neexistuje budoucí constraint/rezervace bránící trvalému setrvání. Nízká vrstva CBS nepoužívá uživatelský pevný horizont: pro poslední čas omezení L a nejvýše V buněk stačí prozkoumat do L+V. Po L už nejsou časová omezení; existující pokračování lze zkrátit na jednoduchou cestu. Tím se nezahazuje levnější větev CBS kvůli libovolnému horizontu. Při konečném horizontu H je nejvýše O(VH) stavů, čas O(VH log(VH)) pro omezený stupeň grafu, paměť O(VH).

## Prioritized Planning

```text
reservations = empty
for robot in deterministic priority order:
    path = space-time A*(start, goal, reservations, horizon)
    if no path: return NO_PLAN
    reserve vertices, directed edges and permanent goal
return paths
```

Čas O(k VH log(VH)) pro k robotů, paměť O(VH + kH). Žádná globální optimalita ani úplnost. Výsledek NO_PLAN může znamenat nevhodné pořadí nebo příliš krátký horizont, nikoli neřešitelnost MAPF. Žádný automatický CBS fallback.

## Conflict-Based Search

Implementace `algorithms/mapf.py:cbs` je dvouúrovňová CBS: conflict tree obsahuje omezení po agentech a jejich individuálně optimální trasy. High-level fronta je řazena podle součtu délek tras minus počátky. První vertex nebo edge-swap konflikt se rozdělí do dvou větví. Každá větev omezí jednoho z konfliktních agentů; přepočítá se pouze jeho cesta. Struktura vychází z [Sharon et al., 2015](https://doi.org/10.1016/j.artint.2014.11.006).

```text
root = shortest individual paths, no constraints
open.push(root, sum_of_costs)
while open:
    if budget exhausted: return TIMEOUT
    node = cheapest node
    conflict = earliest conflicting pair (extend shorter paths at goal)
    if no conflict: return SUCCESS with optimal=true
    for each of the two agents:
        child = node + vertex/edge constraint for that agent
        replan constrained agent using complete shortest low-level search
        if possible and constraint-set not visited: push child
return UNSOLVABLE
```

Úspěšné statické CBS řešení minimalizuje Sum of Costs, protože low-level je optimální, konfliktové větvení pokrývá všechna přípustná řešení a fronta nezahazuje levnější uzly. Časový/uzlový limit přeruší výpočet s TIMEOUT a `optimal=false`; nedochází k vrácení heuristického řešení jako optimálního. `UNSOLVABLE` se používá při odpojených cílech nebo vyčerpání stromu. Na obtížném neřešitelném problému může místo důkazu přijít timeout. Ve špatném případě exponenciální počet CT uzlů; každá větev volá space-time A*. Nedáváme polynomiální garanci pro MAPF.

Testy porovnávají CBS s nezávislou joint-state Dijkstra referencí: konečné dosažení cíle je explicitní stav, každý krok stojí počet dosud nedokončených agentů. Dále se testují swap/vertex konflikty, budoucí zákaz cíle, waiting a limit 1 uzlu.

## Adaptivní online koordinace

Při změně cíle, přidání úkolu či překážky, dokončení služby nebo změně dostupnosti se trasy globálně přepočítají v synchronizačním bodě před dalším tickem. Adaptivní varianta řadí pohybující se roboty podle sestupného celkového čekání, potom ID. Základní prioritizovaná varianta podle ID. Není implementováno selektivní přeplánování ani WHCA*.

Nepohybliví roboti tvoří pevné překážky; servisní čekání se nesmí změnit na uhybný pohyb CBS. Při selhání se běh zastaví; netvrdíme, že každé zablokování lze rozřešit. A* baseline bezpečně selže při konfliktní společné trase. CBS v online provozu optimalizuje jen daný aktuální MAPF podproblém, ne celý transportní provoz.

## Scheduling a stanice

Nearest řadí úkoly FIFO a vybere nejbližšího schopného robota podle skutečné BFS vzdálenosti. Priority-aware řadí podle priority, created tick, ID; skóre robota je vzdálenost + 5·(1−battery/capacity). Hungarian implementuje obdélníkovou minimální nákladovou matching metodu s transpozicí, O(min(n,m)² max(n,m)); nepřípustné přiřazení má cenu 10⁹ a výsledek se odfiltruje. Cílem je součet vzdáleností k pickup, nikoli makespan.

Před přiřazováním funguje jednotná admission policy: současně aktivní úkoly si rezervují pickup a dropoff, takže se nevytvoří shodné cíle nebo prohození stanic mezi fázemi služby. Dávka obsahuje jen úkoly s různými neobsazenými stanicemi. To omezuje paralelismus a znamená, že Hungarian optimalizuje pouze připuštěnou dávku, nikoli celý backlog. Po vyložení se robot vrací do své domovské buňky; je-li to charger, dobije do plna. Tyto konzervativní volby jsou záměrné a pro všechny plánovače stejné.

## Energie

Spotřeba: jeden pohyb `move_energy`, servisní tick `handling_energy`, neobslužné stání mimo charging `wait_energy` (výchozí 0). Nabíjení přidává `charging_rate` do kapacity, bez záporných či nadlimitních hodnot. Přiřazení vyžaduje nosnost a energii na nejkratší pickup + delivery + návrat do vlastního chargeru (nebo nejbližšího dosažitelného) + service + absolutní `critical_threshold` rezervu.

Jde o zjednodušený model, nikoli fyzikální simulaci baterie. Čekání kvůli provozu a objížďky nelze přesně předpovědět při přiřazení; při vyčerpání se celý neplatný přechod bezpečně odmítne. Chybějící dosažitelný charger znamená nepřípustné přiřazení. Frontend nastavení neslibuje proveditelnost libovolné kombinace kapacity, rezervy a mapy.

## Naučené přiřazování podle doby přepravy

Scheduler `learned` používá stejnou prioritu úkolů a admission policy jako priority-aware. Po kontrole dostupnosti, nosnosti a energie vypočte pro každého kandidáta 27 příznaků v2 a predikci: BFS cesta k nakládce + přeprava + obsluha + zpoždění z natrénovaného Random Forest (96 stromů, hloubka nejvýše 12). Jedenáct vstupů popisuje obsazenost konkrétní geometrické trasy, zúžení a překryv/směr/časové konflikty se současnými plány ostatních robotů (horizont 64 kroků). Budoucí replánování nezná. Starší modely v1 čtou jen původních 16 vstupů. Vybere minimum, shody řeší ID. Každého zvoleného robota vyřadí z dalších kandidátů v dávce. Jde o greedy přiřazování s naučenou cenou, nikoli o globální optimalizaci celé flotily.

Skutečnou cílovou hodnotu dodá až dokončení vykládky. Vstup nikdy neobsahuje budoucí výsledek. Bez natrénovaného kompatibilního modelu se ML simulace nevytvoří. Plánovače a bezpečnostní invarianty zůstávají nezávislé na modelu. [Trénink, validace a měření](machine-learning.md).
