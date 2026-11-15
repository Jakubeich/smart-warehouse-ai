# Pokrok neuronové sítě na skladu 64 × 64

Testovaná mapa „zkouška generování složitého skladu“ má 17 robotů, 200 přeprav, dva jednobuněčné průjezdy a obousměrný provoz. Seed je 3318493664. Stejné zadání a počáteční stav robotů dostaly všechny čtyři zaznamenané verze vah. V oddělené simulaci se každé váhy během testu používaly bez aktualizací. [Původní scénář](../neural-max-stress/scenario.json)

| Verze vah | Hotové přepravy | Průjezdy přes příčku | Krok zastavení |
| --- | ---: | ---: | ---: |
| 504 aktualizací před původním nahlášeným během | 1/200 | 4 | 353 |
| 510 aktualizací po původním nahlášeném běhu | 5/200 | 15 | 382 |
| 6 946 aktualizací po pokusu 530 | 45/200 | 59 | 1 311 |
| 7 118 aktualizací při pozdějším odběru | 1/200 | 3 | 202 |

V prvních 350 krocích dokončila verze 6 946 celkem 24 přeprav, verze 510 celkem 5. Počet průjezdů přes příčku stoupl z 15 na 28 a součet čekání u průjezdů klesl z 1 751 na 943 kroků čekajících robotů. To je o 46 % méně za stejné časové okno. Za čekání se zde počítá vybraná akce čekat při jízdě v průjezdu či u jeho ústí. Překročení příčky nastane, až se robot dostane bezpečně na druhou stranu. Po celé jízdě měla dřívější verze nejdelší čekání 316 kroků. Verze 6 946 udržela provoz déle, ale jeden robot čekal v okolí průjezdu bez přerušení 1 125 kroků. Všechny verze se nakonec zastavily po 30 krocích bez pokroku a měly nula vykonaných kolizí.

V živém opakování pokusů 530 až 539 dokončilo osm jízd po jedné přepravě, zbývající dvě 12 a 14. Všechny skončily po 30 krocích bez pokroku a každá uložila alespoň čtyři aktualizace vah. V oddělené databázi byly přesně zopakovány pokusy 531 až 533 z uloženého checkpointu 6 946. První z nich se stejným startem dokončil při průběžných aktualizacích 12 přeprav, zatímco pevná verze ze stejného startu dokončila 45. Po další aktualizaci závisí výsledek na nových vahách a úspěšnější chování nemusí vydržet.

Na třech dalších mapách 64 × 64 se stejným počtem robotů, úkolů a průjezdů dopadla změna z 510 na 6 946 aktualizací postupně 3 → 126, 42 → 18 a 6 → 19 hotových přeprav. I všech šest těchto běhů se zastavilo. Tři mapy poskytují doplňkovou kontrolu stability na jiných rozloženích.

[Časové řady a pozorované pokusy](measurements.json) · [Váhy 6 946](checkpoint-6946.json) · [Váhy 7 118](checkpoint-7118.json)
