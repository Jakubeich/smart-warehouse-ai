# Neuronové řízení skladové flotily

V živé simulaci jediný vícevrstvý perceptron (MLP) vybírá práci, nabíječku, návrat domů a jednotlivé kroky robotů. V aplikaci otevřete **Strojové učení → Otevřít ukázkový sklad**. V **Podrobnostech běhu** jsou zvolené akce, skóre a počet automatických aktualizací vah. API živé simulace použije aktuální neuronový model i pro dříve uložené scénáře s nastavením klasických algoritmů.

## Jak se vybírají akce

1. Pro volné roboty vzniknou kandidáti na převzetí čekajících úkolů, dobití na dosažitelné nabíječce, návrat domů nebo čekání. Kontrola dostupnosti stanice, nosnosti a rezervy energie omezuje nabídku. Síť ohodnotí všechny kandidáty, včetně alternativních robotů pro tentýž úkol. Systém přiřadí nejlepší slučitelné akce podle skóre.
2. Pro roboty s cílem síť ohodnotí pohyb do sousedních buněk a čekání. Vstupy popisují vzdálenost k cíli, volné směry, okolní roboty a jejich cíle, protisměrný provoz, baterii a nedávno navštívené buňky. BFS dodává vzdálenost jako jeden ze vstupů. Rozhodnutí v každém kroku vychází z výstupu sítě.
3. Pokud dvě volby míří do stejné buňky nebo si roboti chtějí vyměnit pozice, vyřadí se konfliktní návrhy a vyhodnotí se další možnosti v pořadí sítě. Centrální validátor zkontroluje výsledný společný krok, průchodnost a energii. Po příjezdu na stanici simulátor vykoná obsluhu nebo nabíjení. Python posílá stejný stav do 2D i 3D zobrazení.

Klasický plánovač dodává ukázkové kroky při tréninku. V neuronovém běhu rozhoduje síť krok po kroku bez volání A*, CBS či adaptivního plánovače. Pokud flotila přestane postupovat, běh může skončit chybou. Klasické metody slouží k reprodukci výzkumných měření.

## Trénink

Model `nn-975367e33160` má 44 vstupů, dvě skryté vrstvy (48 a 32 neuronů, ReLU) a jeden výstup pro skóre kandidátní akce. Trénink s učitelem používá 240 999 příkladů kandidátních akcí z 39 simulovaných scénářů. Scénáře zahrnují 36 generovaných rozložení se seedy 810000–810035 a tři ukázkové mapy. Ukázky pohybu pocházejí z adaptivního plánovače. Ukázky výběru úkolů a nabíjení vytváří pravidla učitele z dostupných akcí ve stejném stavu. Příklady se při učení váží podle typu akce a toho, zda ji učitel zvolil.

Trénink použil scikit-learn MLPClassifier, Adam, seed 742 a pevný rozpočet 32 epoch. Optimalizace dosáhla tohoto limitu a trénink byl zopakován se shodným ID vah. Běhová inference v NumPy byla proti modelu scikit-learn ověřena na vzorku kandidátů při exportu. Síť se učí napodobováním rozhodnutí z příkladů. V provozu používá uložené váhy.

## Párové porovnání výchozího modelu

24 testovacích rozložení se seedy 920000–920023 bylo oddělených od tréninku podle hashů map. Každý scénář má 20 přeprav v obou směrech, 4, 6, 8 nebo 12 robotů a stejný počáteční stav pro obě metody. Klasické řízení kombinuje přiřazování podle priority a adaptivní plánovač. Porovnání měří celé řídicí režimy včetně volby úkolů, jízdy, čekání a návratů k nabíječce.

| Podmínka | Dokončené klasické běhy | Dokončené neuronové běhy | Klasické kroky | Neuronové kroky |
|---|---:|---:|---:|---:|
| Otevřená mapa | 8/8 | 8/8 | 259,4 | 226,4 |
| Úzké průjezdy, šířka 1 buňka | 8/8 | 6/8 | 299,8 | 298,0 |
| Širší průjezdy, šířka 2 buňky | 8/8 | 8/8 | 265,4 | 245,1 |
| Celkem | 24/24 | 22/24 | 272,6 | 252,7 |

Průměrná doba se počítá pouze z dvojic, kde dokončily obě metody. Rozdíl činí 7,3 % ve prospěch sítě v těchto 22 dvojicích. Ve všech 48 simulacích bylo nula vykonaných kolizí. Na seedech 920013 a 920016 se neuronový režim zastavil po 30 krocích bez pokroku. Dokončil 17 a 19 přeprav z 20. Bezpečnostní filtr na těchto mapách opakovaně vyřazoval konfliktní návrhy. Nižší průměrný čas ve společně dokončených bězích je potřeba posuzovat společně s těmito dvěma neúspěchy. Vzorek zahrnuje flotily nejvýše 12 robotů a simulované sklady.

[Kompletní testovací scénáře a měření](pairs.json) · [Váhy modelu](../../../apps/backend/app/neural/fleet-policy.json)

## Reprodukce

Z kořene projektu s uzamčenými závislostmi v `apps/backend/uv.lock` spusťte:

```bash
uv run --directory apps/backend python ../../scripts/train-neural-fleet.py
uv run --directory apps/backend python ../../scripts/evaluate-neural-fleet.py --output ../../docs/experiments/neural-fleet/pairs.json --publish-summary
```

## Průběžné učení při jízdě

Živé běhy začínají s poslední uloženou verzí vah. Dokončená přeprava, nabíjení a návrat dávají pozitivní zpětnou vazbu. Posun k cíli je odměněn, opakované návštěvy a odmítnuté návrhy snižují skóre. Nedokončené přiřazení při selhání dostane zápornou odměnu. Model provádí malé aktualizace vah zpětným šířením chyby. Velikost změny je omezená a váhy jsou přitaženy k původnímu modelu, aby si zachovaly dovednosti z úvodního tréninku.

Aktualizace probíhá po 64 krocích, pokud vznikly zkušenosti, a při dokončení, zastavení nebo opuštění simulace. Úspěšně uložený checkpoint v PostgreSQL obsahuje váhy, ID a počty aktualizací a zkušeností. Další krok běhu použije novou verzi. Nové běhy čtou poslední dostupnou verzi a server ji obnoví po restartu. U souběžných běhů server aktualizace ukládá po jedné. Aktuální krok každého běhu používá konkrétní verzi modelu a jeho ID je ve snapshotu.

Historické párové měření se vztahuje k výchozím vahám. Testy průběžného učení ověřují změnu vah, jejich použití při dalším kroku a obnovu po restartu. Z dlouhodobé změny výkonu zatím nemáme měření. Zkušenosti vznikají při běhu simulace. Každá aktualizace může změnit rozhodnutí, zejména ve scénářích s úzkými průjezdy.

Po natrénování nového výchozího modelu restartujte backend. Pokud se jeho ID změní, naváže průběžné učení z nových výchozích vah. Archivní měření obsahuje ID vah, pro které bylo získáno.
