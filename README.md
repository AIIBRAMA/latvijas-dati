# Latvijas dati

Latviska atvērto datu izpētes vietne, pielāgota no [USAspending](https://github.com/fedspendingtransparency/usaspending-website) idejas un atvērtā koda komponentēm. Avots: [Latvijas Atvērto datu portāls](https://data.gov.lv/lv).

## Atjauninājums 1.1 — Valsts kases XLSX tabulas

Diviem datu kopas “No valsts budžeta daļēji finansētu atvasinātu publisku personu un budžeta nefinansētu iestāžu budžetu ieņēmumi un izdevumi pa mēnešiem” resursiem pievienots automātisks XLSX imports:

- EKK resurss `a8a020c0-cfad-4600-b506-a568f2fa60d4` — pārbaudītajā failā 91 728 datu rindas, 32 kolonnas.
- FKK resurss `09a0ba1c-ce3f-4752-b35c-f3779137ae72` — pārbaudītajā failā 2533 datu rindas, 22 kolonnas.

Poga “Izpētīt tabulu” atver no XLSX sagatavotu kopiju. Pieejama darblapas izvēle, gada, mēneša, ministrijas, iestādes, plāna/izpildes un citu avota klasifikāciju atlase. Meklēšana un “Visa atlase CSV” aptver visu izvēlēto darblapu. Tabulas lapā un diagrammā attēloti līdz 50 ierakstiem. Diagrammai izmanto `Summa`; kopsummas netiek rēķinātas, jo datu rindās var būt dažādi pārskatu un hierarhijas līmeņi. “#” ir saglabāts kā avota apzīmējums.

XLSX kopijas tiek iegūtas katras veiksmīgas GitHub publicēšanas laikā, arī plānotajā ikdienas atjaunošanā. Laiks un oriģinālā resursa saite paliek redzami. Pārējie XLSX faili joprojām izmanto sākotnējo avota saiti; šis nav universāls visu Excel izkārtojumu lasītājs.

Pilnai vietējai atjaunošanai: `npm run sync`. Tikai abu XLSX resursu atjaunošanai no pašreizējā kataloga: `npm run sync:xlsx`. Importam nepieciešams tikai Python standarta bibliotēku komplekts.

Importētājs pārbauda nepieciešamās kolonnas, šūnu tipus, faila apjomu, saglabātās formulu vērtības un neskaidrus izkārtojumus. Ja kāds no abiem resursiem neizdodas, GitHub nepublicē nepilnu atjauninājumu; iepriekš publicētā vietne paliek pieejama. Tā ir apzināta izvēle pret klusu datu zaudēšanu.

CSV saglabā kodu rakstību. Atverot CSV Excel, kodu kolonnām importēšanas dialogā jāizvēlas teksta tips, ja nepieciešams saglabāt sākuma nulles. Datu failu licences nemainās.

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
npm run sync      # iegūst aktuālo publisko katalogu
npm run build     # sagatavo statisko vietni dist/ mapē
npm run preview   # pārbauda sagatavoto vietni
```

Windows datorā, ja komanda `python3` nav pieejama, palaidiet `py lv/scripts/sync_catalog.py`.

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
- Datu kopas aktuālais apraksts un DataStore tabulas tiek pieprasītas tieši no `data.gov.lv`. Divas XLSX tabulas nolasa vietnes publicēšanas laikā sagatavotās kopijas.
- Tabulas skats darbojas resursiem ar `datastore_active=true` un iepriekš norādītajām divām importētajām Valsts kases XLSX kopijām. Pārējiem CSV/XLSX/PDF/ZIP/WMS un citiem ārējiem resursiem bez DataStore pieejama avota saite. Šis rīks universāli neinterpretē visus failu tipus.
- Vienā tabulas lapā tiek pieprasīti līdz 50 ierakstiem. Diagramma rāda tikai šo lapu un izvēlētās kolonnas, nevis visas datu kopas statistiku. Skaitliska kolonna var būt arī identifikators — tās nozīmi un mērvienību izvērtē lietotājs.
- Nozaru laukumu diagramma rāda 8 lielākās klasificētās nozares. Vienai kopai var būt vairākas nozares; visu kopu kopskaits ir unikāls. Kopas bez norādītas nozares pieejamas katalogā ar atsevišķu filtru.
- “Metadati atjaunoti” nav garantija, ka atjaunoti arī faila novērojumi.
- Vietne nav oficiāls Latvijas valsts portāls un neapgalvo institucionālu apstiprinājumu.

## Tehniskais risinājums

- React un Vite; D3 tikai laukumu diagrammas izkārtojumam.
- `lv/scripts/sync_catalog.py`: lapota `package_search` iegūšana, publisko ierakstu normalizācija, kopskaita pārbaude un atomiska faila nomaiņa. Kļūdas gadījumā nepilns katalogs netiek publicēts.
- `lv/public/data/catalog.json`: publiskie metadati un pēdējās iegūšanas laiks.
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
