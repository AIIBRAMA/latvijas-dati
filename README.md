# Latvijas dati

Latviska atvērto datu izpētes vietne, pielāgota no [USAspending](https://github.com/fedspendingtransparency/usaspending-website) idejas un atvērtā koda komponentēm. Avots: [Latvijas Atvērto datu portāls](https://data.gov.lv/lv).

## Papildinājums — Valsts budžeta tāmes un pašvaldību mēneša tabulas

Atbalstīti pieci pārbaudīti Valsts kases resursi trijās datu kopās:

- **Valsts budžeta tāmes**, JSON resurss `45368057-dfd7-4c56-9cac-5ca0e22ca086`. Pilnais publiskais avots pārveidots tabulā, saglabājot visus tajā pieejamos gadus. Pārbaudītajā 2026-11-24 kopijā: 236 015 rindas, no tām 2025. gadā 137 991 un 2026. gadā 98 024. Pārlūks ielādē vienu izvēlēto gadu, sākot ar jaunāko. Tas nav tikai jaunākā gada izgriezums no avota.
- **Pašvaldību budžetu ieņēmumi un izdevumi pa mēnešiem**, EKK resurss `9ac53f2c-88dc-4f54-9871-36ddc5e0af84` un funkciju resurss `d7c4897d-33f6-4885-9cd1-c3abe0f47f69`. Pārbaudītajās XLSX kopijās: 151 309 × 28 un 54 581 × 18 datu rindas/kolonnas.
- **No valsts budžeta daļēji finansētu atvasinātu publisku personu un budžeta nefinansētu iestāžu mēneša tabulas**, jau atbalstītie EKK `a8a020c0-cfad-4600-b506-a568f2fa60d4` un funkciju `09a0ba1c-ce3f-4752-b35c-f3779137ae72` resursi. Aktuālajā pārbaudē: 100 753 × 33 un 2793 × 22. EKK avota AG kolonnai nav virsraksta; tās marķieri saglabāti ar skaidru tehnisku nosaukumu, neizdomājot biznesa nozīmi.

Šie skaiti raksturo pārbaudīto kopiju, ne nemainīgu avota izmēru. Datu kopu apraksti un licences saglabājas katalogā. [Tāmju katalogs](https://data.gov.lv/dati/lv/dataset/valsts-budzeta-tames), [pašvaldību katalogs](https://data.gov.lv/dati/dataset/e2b111ec-c2ad-4525-937e-c28f07af62c9).

### Izpēte un datu nozīme

Poga “Skatīt tabulu” atver publicēšanas laikā sagatavoto kopiju. Pieejama darblapas izvēle un attiecīgajā avotā esošie gada, mēneša, pašvaldības/iestādes, plāna/izpildes, ministrijas, tāmes un klasifikāciju filtri. Meklēšana un CSV eksports (“Visa atlase CSV” XLSX tabulām, “Gada atlase CSV” tāmēm) aptver visu izvēlēto darblapu; tāmēm tā ir **izvēlētā gada** darblapa, ne visi gadi vienlaikus. Tabulas lapā un diagrammā attēloti līdz 50 ierakstiem.

Diagramma lieto `Summa`. Kopsummas netiek rēķinātas, jo rindās var pārklāties pārskatu un hierarhijas līmeņi. Tāmju avots nenorāda atsevišķu valūtas kolonnu, tādēļ vietne nepieņem mērvienību pati. Tukša summa tiek saglabāta kā trūkstoša vērtība, ne nulle; īstā nulle un negatīvas summas paliek skaitļi. Avota kodi, sākuma nulles, “#” un teksta vērtības netiek interpretētas kā maksājumi vai klasifikatoru secinājumi.

CSV saglabā kodu rakstību un neitralizē formulas. Atverot CSV Excel, kodu kolonnām importēšanas dialogā izvēlieties teksta tipu, ja nepieciešams saglabāt sākuma nulles.

### Atjaunošana un droša publicēšana

- `npm run sync`: vispirms publiskais katalogs, pēc tam visi četri pārbaudītie XLSX resursi un pilnais tāmju JSON avots.
- `npm run sync:xlsx`: tāpat kā iepriekš palaiž tikai XLSX importētāju no pašreizējā kataloga; tā tvērums tagad ir četri resursi.
- `npm run sync:budget`: tikai tāmju JSON pārveidošana no pašreizējā kataloga.
- Atkārtojamai bezsaistes pārbaudei: `python3 lv/scripts/sync_xlsx.py --source-dir MAPES_CELS` un `python3 lv/scripts/publish_budget_estimates.py --source-dir MAPES_CELS`. Failu nosaukumi ir precīzs resursa UUID ar `.xlsx` vai `.json` paplašinājumu. JSON failam jābūt pilnam, ne pēc gada filtrētam avotam.

Importam vajadzīga tikai Python standarta bibliotēka. Tāmju avots tiek pieprasīts tikai no pārbaudītā pilnā `https://opendata.kase.gov.lv/api/v1/valsts_budzeta_tames` galapunkta. Avota gada saraksts tiek noteikts no visām saņemtajām rindām, ne ievadīts kodā. Katram gadam publicē atsevišķu `data/json/<UUID>-v1-<SHA16>-<GADS>.json` failu. Visiem gadiem kopīga pilnā avota SHA-256; vārdnīcas katrā gadā sablīvē, nezaudējot rindas. Katalogā `local_preview.sourceFormat` ir `JSON`, bet `partitions` norāda gadu failus un precīzus rindu skaitus. Darblapas saglabā vienoto `schemaVersion: 1` formātu.

Avota JSON izmēra limits ir 384 MiB, rindu limits 400 000, viena gada pārlūka kopijas limits 24 MiB. Pārsniegums, mainīta shēma vai nepilns avots aptur atjaunošanu, nevis klusi izlaiž rindas. Pašreizējie divi gadu faili aizņem aptuveni 10,12 MB un 7,17 MB.

JSON importētājs nomaina kataloga atsauces tikai pēc visu gadu veiksmīgas konvertēšanas. Ja shēma vai integritāte neatbilst pārbaudītajām prasībām, tas saglabā iepriekšējo katalogu un failus; jaunus, vēl neatsauktus failus noņem. Atkārtoti izmanto tikai pārbaudītas tā paša satura kopijas. Vienā lokālajā projekta mapē palaidiet tikai vienu sinhronizāciju vienlaikus.

Ja tieši tāmju avots īslaicīgi neatbild, būvējums var izmantot jau publicēto jaunāko pārbaudīto kopiju no šīs vietnes vai sākotnējo 2026. gada 24. novembra kopiju no `lv/fixtures/budget-estimates`. Pilnos gadu failus pārbauda pirms publicēšanas. Vietnē ir atzīme “rezerves kopija”, tās pārbaudes datums un brīdinājums, ka dati var nebūt aktuāli. Katrā nākamajā sinhronizācijā vispirms mēģina saņemt pilnus svaigus datus no oficiālā avota. Nepareiza shēma, neatļauts URL, TLS vai integritātes kļūda rezerves kopijas režīmu neieslēdz.

GitHub Pages jau izpilda abus testu komplektus un `npm run sync` pirms būvēšanas un augšupielādes. Ja kāds avots vai konvertētājs neizdodas, jaunā vietne netiek publicēta; iepriekš publicētā vietne paliek pieejama. Lokāli `npm run sync` sastāv no secīgiem soļiem: pēc vēlākas kļūdas agrākais kataloga/XLSX solis var jau būt atjaunots. Pirms lokālas publicēšanas jāsagaida veiksmīgs **visas** sinhronizācijas rezultāts, ne jāturpina pēc kļūdas.

Pārējie XLSX/JSON un citi ārējie resursi bez DataStore izmanto avota saiti. Šis nav universāls visu Excel izkārtojumu vai JSON API lasītājs.

## Kas ir gatavs

- Pārskats ar faktiskajiem kataloga rādītājiem un interaktīvu nozaru laukumu diagrammu.
- Visu publisko data.gov.lv kataloga kopu meklēšana; sākotnējā kopijā 1570 kopas (2026-10-05).
- Nozaru, iestāžu, failu formātu un tabulas pieejamības filtri.
- Datu kopas lapa, aktuālo metadatu pārbaude avotā, resursu saites un licences norāde.
- CKAN DataStore resursu tabula ar lapošanu, ierakstu meklēšanu un skaitlisko kolonnu diagrammu.
- Metadatu atlases un tabulas atvērtās lapas CSV eksports.
- Saglabātās kopas šī pārlūka atmiņā; kopīgojami meklējumu un datu kopu URL.
- Pielāgots izkārtojums telefonam un datoram, tastatūras vadība.
- GitHub Pages publicēšanas un ikdienas kataloga atjaunošanas darbplūsma.

## Publicēšana savā GitHub — bez atsevišķa servera

1. Atarhivējiet ZIP. Mapē `latvijas-dati` ir gatavā projekta faili.
2. Savā GitHub izveidojiet jaunu **publisku** repozitāriju, piemēram, `latvijas-dati`.
3. Augšupielādējiet **mapes saturu** repozitārija saknē. `package.json`, `lv` un `.github` jābūt vienā līmenī — neveidojiet lieku ārējo mapi. Pārliecinieties, ka ir augšupielādēta arī slēptā `.github` mape. GitHub Desktop var palīdzēt, ja pārlūkā tā neparādās.
4. Atveriet **Settings → Pages → Build and deployment → Source → GitHub Actions**.
5. Atveriet **Actions → Publicēt Latvijas datus → Run workflow**. Sagaidiet zaļus `build` un `deploy` rezultātus. Ja Actions nav ieslēgts, GitHub piedāvās to iespējot.
6. Vietnes adresi atrodiet **Settings → Pages**. Parasti tā ir `https://LIETOTAJVARDS.github.io/latvijas-dati/`.

Kods darbojas gan projekta apakšmapē, gan domēna saknē. Nav nepieciešama API atslēga, datubāze, Mapbox konts vai maksas ikonu licence. GitHub konta/plāna piemērotību Pages pārbaudiet GitHub iestatījumos.

**Automātiskā atjaunošana:** katru dienu ap 04:23 UTC (07:23 Latvijas vasaras laikā / 06:23 ziemas laikā). GitHub var aizkavēt plānotu palaišanu un neaktīvos repozitārijos to apturēt; vietnē redzams faktiskais datu iegūšanas datums. Plānotās darbplūsmas darbojas noklusējuma zarā. Ja sinhronizācija neizdodas, jaunā versija netiek publicēta un iepriekšējā vietne paliek pieejama. Manuālu atjaunošanu veic ar `Run workflow`.

Ja izvēršat projektu citā repozitārija zarā nekā `main` vai `master`, pielāgojiet `.github/workflows/pages.yml` lauku `branches`.

## Palaišana savā datorā

Nepieciešams Node.js 22.14 vai jaunāks. Kataloga atjaunošanai arī Python 3.12+ (bez papildu bibliotēkām).

Atveriet termināli projekta mapē:

```sh
npm ci --ignore-scripts
npm start
```

Atveriet terminālī norādīto `http://127.0.0.1:5173`. Pirmreizējai palaišanai jau ir iekļauta reāla kataloga kopija.

```sh
npm test          # atlases, eksporta un datu interpretācijas pārbaudes
npm run sync      # katalogs, četri XLSX resursi un pilnas Valsts budžeta tāmes
npm run build     # sagatavo statisko vietni dist/ mapē
npm run preview   # pārbauda sagatavoto vietni
```

Windows datorā, ja komanda `python3` nav pieejama, izmantojiet `py` attiecīgā skripta priekšā. Pilnai atjaunošanai secīgi palaidiet `sync_catalog.py`, `sync_xlsx.py` un `publish_budget_estimates.py` no `lv/scripts/`; turpiniet tikai tad, ja iepriekšējais solis beidzies bez kļūdas.

Ar dubultklikšķi atvērts HTML (`file://`) nav paredzēts izmantošanai: izmantojiet vietējo serveri vai GitHub Pages.

## Kas pārņemts no USAspending

Oriģināls izpētīts pie commit `86af01ba9ab403f2ed75f1d62a0dbcd35dbc4076` (`master`).

| ASV pamats | Latvijas pielāgojums |
|---|---|
| `TreemapCell.jsx` | Pārņemts komponents, latviski piekļūstamības apraksti, tastatūras vadība, Latvijas palete |
| `colorHelper.js` | Pārņemta kontrastējoša teksta krāsas aprēķināšana |
| `ExplorerTreemap.jsx` | Pielāgota D3 binary treemap / hierarchy / TreemapCell uzbūve; finansējuma summu vietā datu kopu skaits |
| Izpēte, filtrēšana un profili | Latvijas datu katalogs, iestāžu atlase un datu kopu lapas |
| ASV finansējuma API | Latvijas CKAN publiskais API un kataloga kopija |

Šī ir mērķēta Latvijas adaptācija, nevis visas ASV sistēmas tulkojums. ASV budžeta, līgumu, finansējuma saņēmēju un ģeogrāfisko izdevumu modeļi Latvijas vispārīgajam katalogam neatbilst, tāpēc nav pārnesti. Sākotnējā projekta lielās atkarības un maksas Font Awesome Pro pakotnes nav nepieciešamas Latvijas versijai.

Piegādes ZIP ietver darbībai nepieciešamo Latvijas kodu, pārņemto kodu un izcelsmes dokumentāciju. Neizmantotie ASV avoti un to vietnes attēli tajā nav iekļauti. Pilnais oriģināls pieejams norādītajā repozitārijā. Pārņemto failu oriģināli salīdzināšanai: `upstream-reference/components/`.

## Dati un ierobežojumi

- Sinhronizācija saņem visu pieejamo **publisko datu kopu katalogu**, nevis lejupielādē visu avota failu saturu. Portāla privāti vai nepublicēti dati nav ietverti.
- Katalogs ir pilna kopija iegūšanas brīdī, nevis nepārtraukti sinhronizēta datubāze. Ja tiek pievienotas kopas, tās parādās pēc nākamās veiksmīgās atjaunošanas.
- Kataloga datu kopu meklēšana notiek nosaukumos, aprakstos, publicētāju nosaukumos un atslēgvārdos. Tā nemeklē visos avota failos.
- Datu kopas aktuālais apraksts un DataStore tabulas tiek pieprasītas tieši no `data.gov.lv`. Četri pārbaudītie XLSX resursi un Valsts budžeta tāmes nolasa vietnes publicēšanas laikā sagatavotās kopijas.
- Tabulas skats darbojas resursiem ar `datastore_active=true` un iepriekš norādītajiem četriem importētajiem Valsts kases XLSX resursiem un tāmju JSON gadu kopijām. Pārējiem CSV/XLSX/PDF/ZIP/WMS un citiem ārējiem resursiem bez DataStore pieejama avota saite. Šis rīks universāli neinterpretē visus failu tipus.
- Vienā tabulas lapā tiek pieprasīti līdz 50 ierakstiem. Diagramma rāda tikai šo lapu un izvēlētās kolonnas, nevis visas datu kopas statistiku. Skaitliska kolonna var būt arī identifikators — tās nozīmi un mērvienību izvērtē lietotājs.
- Nozaru laukumu diagramma rāda 8 lielākās klasificētās nozares. Vienai kopai var būt vairākas nozares; visu kopu kopskaits ir unikāls. Kopas bez norādītas nozares pieejamas katalogā ar atsevišķu filtru.
- “Metadati atjaunoti” nav garantija, ka atjaunoti arī faila novērojumi.
- Vietne nav oficiāls Latvijas valsts portāls un neapgalvo institucionālu apstiprinājumu.

## Tehniskais risinājums

- React un Vite; D3 tikai laukumu diagrammas izkārtojumam.
- `lv/scripts/sync_catalog.py`: lapota `package_search` iegūšana, publisko ierakstu normalizācija, kopskaita pārbaude un atomiska faila nomaiņa. Kļūdas gadījumā nepilns katalogs netiek publicēts.
- `lv/scripts/sync_xlsx.py`: četru pārbaudīto XLSX resursu pārveidošana vienotā tabulu formātā.
- `lv/scripts/sync_budget_estimates.py`: pilna tāmju JSON avota ierobežota lejupielāde un pārbaudītās shēmas lasīšana.
- `lv/scripts/publish_budget_estimates.py`: tāmju sadalīšana pa gadiem, izmēru kontrole un atomiska kataloga atsauču nomaiņa.
- `lv/public/data/catalog.json`: publiskie metadati, pēdējās iegūšanas laiks un pārbaudīto vietējo kopiju atsauces.
- `lv/src/api.js`: CKAN dokumentētais JSONP publiskām GET darbībām. Pārbaudīts, jo avots neatgrieza CORS atļauju parastajam pārlūka `fetch`. Tas ļauj izmantot GitHub Pages bez starpniekservera.
- JSONP izpilda atbildi kā skriptu: uzticamā izcelsme ir fiksēta `https://data.gov.lv`; atļautas tikai `package_show` un `datastore_search`. Lietotājs nevar nomainīt izcelsmi vai ielādēt patvaļīgu skripta adresi. Ja nevēlaties uzticēties JSONP, nākamais arhitektūras solis ir sava servera tikai lasāms API starpnieks.
- Nav API atslēgu, analītikas, servera lietotāju kontu vai lietotāju datu glabāšanas. Saglabātās kopas ir `localStorage`.
- Avota teksts tiek attēlots kā teksts, nevis nefiltrēts HTML. Avota saites atļauj tikai HTTP(S); CSV eksports neitralizē formulu sākuma simbolus.

## Licence un avoti

Koda licence: `LICENSE.md` (CC0, pārņemta no USAspending). Datu kopām saglabājas katra publicētāja noteiktie nosacījumi; koda licence tos neaizstāj.

- https://github.com/fedspendingtransparency/usaspending-website
- https://data.gov.lv/lv
- https://data.gov.lv/dati/api/3/action/package_search
- https://docs.ckan.org/en/2.11/api/index.html
- https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

Skatiet `PARBAUDES.md` ar konkrētās piegādes pārbaudes rezultātiem.
