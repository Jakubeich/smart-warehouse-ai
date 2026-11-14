# Osnova obhajoby (12–15 minut)

1. **Motivace (1 min):** autonomní doprava a sdílené uličky. Oficiální název projektu, smysl reprodukovatelné experimentální platformy.
2. **Definice problému (1 min):** čtyřsousední mřížka, body místo fyzických robotů, vertex a edge swap, stay-at-goal. Jasně vymezit statické MAPF proti online přepravě.
3. **Architektura (1 min):** diagram z architecture.md; autoritativní backend, bezrendererový engine, UI přes snapshoty, PostgreSQL pro scénáře a výsledky.
4. **Algoritmy (2–3 min):** A* a jeho limit; reservation table prioritizovaného plánování; skutečné CBS větvení na malém swap příkladu. Přiblížit Sum of Costs a výpočetní cenu.
5. **Provozní inteligence (1 min):** čtyři schedulery včetně naučeného odhadu, station admission, nakládka/vykládka, energie a nabíjení. Hungarian ≠ globální makespan optimum.
6. **Živá ukázka (2 min):** otevřít Small Warehouse → Start → Pause → označit robota → Step → přidat task → přidat překážku do volné podlahy → pokračovat. Ukázat trasy a skutečné změny ticků. Při selhání plánovače ukázat důvod, nikoli skrýt výsledek.
7. **Experimenty (2 min):** static MAPF A, seed 42, 4 roboti, 3 opakování, stejné limity. Ukázat exportované skutečné výsledky z docs/experiments. Druhá ukázka F pro schedulery.
8. **Interpretace (1 min):** souběžně úspěšnost, cena a čas. Rozlišit plánovací konflikty od vykonaných kolizí; timeout od neřešitelnosti. Grafy nevydávat za důkaz obecné převahy z malého vzorku.
9. **Ověření (1 min):** invarianty, deterministické běhy, nezávislý oracle pro CBS, integrační WebSocket test, Playwright celého workflow.
10. **Omezení a další práce (1 min):** konzervativní station admission, fixed speed, GIL u live plánování, konečné rozpočty. 3D pouze renderer, nikoli přepis algoritmů. Selektivní replanning, robustnější deadlock recovery, větší benchmarky.

Před prezentací: `make dev`, načíst demo scénáře, zkontrolovat API health a prohlížeč. JSON/CSV uložit lokálně jako zálohu. Nepoužívat čísla z návrhu obrazovky jako výsledky. Při nedostatku času ukázat již skutečně provedené experimenty a přiložit jejich konfiguraci.

## Varianta ukázky zaměřená na AI / ML

Zařaďte místo části obecné ukázky 3 minuty ke strojovému učení:

1. Sklady → Generovat sklad: změna seedu a rozložení, průchodná mapa, vlastní scénář.
2. Strojové učení: ukázat skutečný počet dokončených přeprav a model. Vysvětlit vstup (vzdálenosti, provoz, baterie…) a učitelský signál (naměřená doba do vykládky). Zmínit oddělení celých map pro validaci.
3. Porovnání: stejný scénář se současnou metodou a s ML, úspěšnost i časy. Výslovně uvést, že první malý experiment zlepšení neprokázal; to je platný experimentální výsledek.
4. Simulace s ML → Podrobnosti běhu: kandidáti, predikce a zvolený robot. Přepnout na 3D, logika zůstává stejná. Nové jízdy doplní data, přetrénování vytvoří další verzi.

Věta k obhajobě: „Vedle klasického plánování cest používám učení s učitelem. Random Forest se z reálných výstupů simulace učí předpovídat dobu přepravy a tyto předpovědi řídí výběr robota. Přínos testuji proti původní heuristice na totožných scénářích, které nepoužívám pro trénink.“
