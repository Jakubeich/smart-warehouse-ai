# Další učení neuronové sítě pro rychlejší přepravu

Na 64 nových mapách s jednobuněčnými průjezdy dokončil aktivní model `nn-17a7071a6ab3` **61 běhů**, kandidát po dalším učení `nn-f2ea4c6f5dcc` **59 běhů**. Kandidát ukončil čtyři běhy bez pokroku v oblasti průjezdu oproti dvěma u aktivního modelu. Ve společně dokončených dvojicích byl průměrně o **1,5 % pomalejší**. Aplikace dál používá `nn-17a7071a6ab3`.

## Trénink a výběr kandidáta

Obě větve začaly ze stejného uloženého modelu, který už měl 500 aktualizací vah. Každá absolvovala stejných 96 tréninkových scénářů. První použila dosavadní zpětnou vazbu. Druhá posílila odměnu za rychlé vyzvednutí a doručení s malým zpožděním. Dostatečně nabitý robot, který zvolil dobití, ač mohl převzít práci, dostal zápornou odměnu. Dávka učení přikládala vyšší váhu pozorovaným výsledkům přeprav a nabíjení. Pohyb a přidělování při každé jízdě řídila neuronová síť.

Na samostatných 24 validačních mapách se porovnaly modely po 32, 64 a 96 jízdách z obou větví. Rozhodoval postupně počet nových nedokončených scénářů oproti výchozímu modelu, případný nárůst počtu zastavení, nárůst počtu map s dlouhým čekáním, počet dokončených scénářů a průměrný čas ve společně dokončených dvojicích.

Vybraný kandidát pochází z prvních 32 jízd větve s upravenou zpětnou vazbou. Po nich měl o 171 aktualizací vah a o 41 871 započtených zkušeností v tréninkových dávkách více. Počet zahrnuje opakovaně vážené příklady. Na validaci kandidát dokončil 24/24 oproti 23/24 a ve společně dokončených dvojicích zrychlil o 2,4 %. Map s dlouhým čekáním ale přibylo z 6 na 9.

## Závěrečné měření

Testovací sada měla 64 předem připravených map. Každá obsahovala jeden nebo dva průjezdy široké jednu buňku a obousměrné přepravy. Ve flotilách 4, 6, 8 a 12 robotů bylo po 16 mapách. Geometrie překážek se nepřekrývala s úvodními tréninky, dřívějšími měřeními této sítě, novým tréninkem ani validací. Obě verze dostaly totožné scénáře a během 128 testovacích jízd používaly pevné váhy. Limit byl 1 600 kroků na běh.

| Metrika | Aktivní model | Kandidát |
|---|---:|---:|
| Dokončené mapy | 61/64 | 59/64 |
| Ukončeno po 30 krocích bez pokroku v oblasti průjezdu | 2 | 4 |
| Ukončeno po dosažení limitu kroků | 1 | 1 |
| Mapy s alespoň jedním čekáním 10 nebo více kroků v kuse u průjezdu | 15/64 | 29/64 |
| Průměrná doba dokončení v 58 společně dokončených dvojicích | 273,6 kroku | 277,8 kroku |
| Průměrný součet čekání robotů u průjezdů v těchto dvojicích | 34,8 kroku | 52,8 kroku |
| Vykonané kolize | 0 | 0 |

Kandidát byl ve společně dokončených dvojicích 24× rychlejší, 4× stejně rychlý a 30× pomalejší. Průměrný rozdíl je +4,2 kroku. Orientační 95% interval z 10 000 párových bootstrap výběrů je −3,1 až +11,5 kroku. Zahrnuje nulu, takže samotná doba nedává přesvědčivý důkaz o změně rychlosti. Úspěšnost a čekání v tomto vzorku neposkytují důvod kandidáta nasadit. Kandidát dokončil jednu mapu, kde se aktivní model zastavil. Tři mapy, které aktivní model dokončil, kandidát nedokončil.

Čekání v průjezdu se měří u jedoucího robota, který po sobě zůstává stát v průjezdu nebo těsně u jeho vchodu. Zastavení označuje ukončení celého běhu po 30 krocích bez pohybu, obsluhy či nabíjení, kdy v oblasti průjezdu čekal alespoň jeden robot. Dosažení limitu kroků zůstává samostatným výsledkem.

[Scénáře](plan.json) · [Výběr modelu na validaci](validation-summary.json) · [Párové výsledky](pairs.json) · [Souhrn](summary.json) · [Vstupní váhy](before-checkpoint.json) · [Váhy kandidáta](after-checkpoint.json) · [Hashe zdrojů](source-hashes.json)

Reprodukce z kořene projektu:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/study-neural-speed.py --output ../../.run/neural-speed-repeat \
  --start-checkpoint ../../docs/experiments/neural-speed-study/before-checkpoint.json
```
