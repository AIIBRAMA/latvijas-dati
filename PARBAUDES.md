# Papildinājuma pārbaudes — 2026-11-24

## Reālo publisko avotu pārveidošana

- Pilnais Valsts budžeta tāmju JSON avots: **208 027 386 baiti, 236 015 rindas, 25 kolonnas**. Nav lietots gada filtrs.
- Pilnā avota SHA-256: `2b384a78d4c655d48c67401d4234ec6e561ffb7e4a5509c028a68dc49302ca05`.
- Gadi iegūti dinamiski no visām rindām: **2025 — 137 991**, **2026 — 98 024**; summa sakrīt ar pilnā avota rindu skaitu.
- Publicēšanas kopijas: 2025. gada fails **10 122 263 baiti**, 2026. gada fails **7 173 173 baiti**. Kopā **17 295 436 baiti**, katrs zem 24 MiB limita. Katrā kopijā vārdnīcas satur tikai attiecīgajā gadā lietotos tekstus.
- Četras XLSX kopijas: atvasināto iestāžu EKK **100 753 × 33**, funkcijas **2793 × 22**; pašvaldību EKK **151 309 × 28**, funkcijas **54 581 × 18**.
- Bezsaistes pārveidošana ar precīzi lejupielādētajiem pilnajiem avotiem un `npm run build` veiksmīga. Šie skaiti attiecas uz konkrētajiem pārbaudītajiem avotiem, ne nākamām atjaunošanām.

## Automātiskās pārbaudes

- `python3 -m unittest discover -s lv/tests -p 'test_*.py'`: **32/32** pārbaudes veiksmīgas.
- `npm test`: **16/16** JavaScript pārbaudes veiksmīgas.
- JSON publicēšanas robežai ir 16 pārbaudes: visu gadu un rindu saglabāšana, null/0/negatīvu summu un sākuma nulles kodu saglabāšana, vārdnīcu sablīvēšana, precīza avota URL atbilstība, failu izmēri, dublēti kataloga mērķi, bezsaistes CLI un atomiska faila nomaiņa.
- Pārbaudīta neveiksme pēc pirmā gada faila sagatavošanas, otram gadam pārsniedzot limitu: katalogs un vecās kopijas nemainās, jaunais neatsauktais fails tiek noņemts.
- Pārbaudīta kataloga ierakstīšanas kļūda un atkārtota tā paša avota pārveidošana: iepriekšējās publicēšanas kopijas netiek pārrakstītas vai izdzēstas. Neatbilstoša saglabātā kopija tiek noraidīta.
- Īstais `npm run sync` komandas ceļš izpildīts ar aizvietotu Python ārējo robežu: kataloga, XLSX vai JSON kļūda atgriež nenulles statusu, un nākamie soļi netiek sākti. `npm run sync:xlsx` paliek tā pati atsevišķā XLSX komanda.
- Pārbaudīts, ka Pages darbplūsmā sinhronizācija ir pirms būvēšanas/artefakta augšupielādes, nav `continue-on-error`, un izvēršana ir atkarīga no veiksmīgas būvēšanas. CI konfigurāciju šim papildinājumam nebija nepieciešams vājināt vai mainīt.
- JavaScript pārbaudes aptver viena gada izvēli, visjaunākā gada noklusējumu, sajauktu gadu/kopiju identitāšu noraidīšanu, precīzus atlases apjomus un JSON mērvienības neizdomāšanu.

## Robežas

Pilnas GitHub Actions palaišanas un publiski izvērstās vietnes rezultāts ir atsevišķa publicēšanas pārbaude. Iepriekš minētie testi to neaizstāj. Ja avots vēlāk pārsniedz izmēra/rindu limitu, nomaina shēmu vai pārtrauc atbildēt, atjaunošana apstājas, saglabājot iepriekš publicēto vietni.

Tālāk saglabāti agrāko piegāžu vēsturiskie pārbaudes protokoli. Tajos minētie datumi, rindu skaiti un toreiz nepārbaudītās publicēšanas darbības neapraksta šī papildinājuma pašreizējo stāvokli.

---

# Atjauninājuma 1.1 pārbaudes — 2026-10-05

- Abi XLSX faili saņemti no norādītajiem data.gov.lv resursiem.
- EKK: 91 728 rindas × 32 kolonnas. FKK: 2533 rindas × 22 kolonnas.
- Importētājs saglabā visas rindas; tekstu kolonnas glabā kompaktā vārdnīcu formā. Lielākā JSON kopija ir aptuveni 7,4 MB un tiek ielādēta tikai, atverot resursa tabulu.
- Neatkarīga pārbaude ar openpyxl salīdzina katru pārveidoto šūnu ar sākotnējo XLSX, arī identifikatorus, avota “#”, tukšumus un summas. **2 991 022 šūnas salīdzinātas, 0 atšķirību.**
- `npm test`: 12 JavaScript pārbaudes. Papildus `python3 -m unittest discover -s lv/tests -p 'test_*.py'`: 4 importētāja pārbaudes.
- Reālu datu atlase: 2025. gads + 1. mēnesis + “Izpilde” atgriež 2057 EKK rindas un 62 FKK rindas. Visas šīs rindas ir pieejamas atlases CSV, neatkarīgi no tabulas lapas.
- Vēl nav pārbaudīta atjauninājuma darbība pilnā pārlūka sesijā vai tā publicēšana lietotāja GitHub kontā. Iepriekšējā vietnes versija ir publicēta; šis ZIP to automātiski nemaina.

---

# Piegādes pārbaudes — 2026-10-05

## Pārbaudīts

- Oriģinālais repozitārijs noklonēts un izpētīts pie commit `86af01ba9ab403f2ed75f1d62a0dbcd35dbc4076`.
- Licence un sākotnējās atkarības pārskatītas; Latvijas versija nelieto ASV API vai maksas ikonu pakotnes.
- Pilna `package_search` izgūšana: **1570 unikālas publiskas datu kopas**, **12 821 resurss**; izgūto kopu skaits sakrīt ar API norādīto kopskaitu.
- Katalogā **4762 resursiem** ir avota pazīme `datastore_active=true`. Šī pazīme nav atsevišķas pieejamības pārbaudes garantija katram resursam.
- `package_search` JSONP atbilde saņemta reālā tīkla pieprasījumā.
- `datastore_search` JSONP atbilde saņemta reālā tīkla pieprasījumā resursam `fc0a704c-90bc-40d8-b104-d45ac9f7edd3`: kopā 61 ieraksts, kolonnas `Menesis`, `Metode`, `Skaits`.
- `npm test`: **6/6 sekmīgas pārbaudes** — kombinēti filtri un latviešu diakritika, saglabātās kopas un kārtošana, kategoriju skaitīšana, drošas ārējās saites, CSV formulu neitralizēšana, skaitļu/negatīvu/tukšu vērtību interpretācija. Skaitļiem pārbaudīta arī Latvijas avotā izmantotā tūkstošu atdalīšana ar atstarpēm.
- `npm run build`: sekmīgi izveidota produkcijas vietne `dist/`.

## Vēl nav pārbaudīts

- Pilna lietotāja darbību ķēde reālā pārlūkā un vizuālais izkārtojums datorā/telefonā: izpildes vides pārlūka drošības pārbaude noraidīja vietējās lapas atvēršanu. Dizainā ir pielāgojumi dažādiem ekrāniem, bet šajā vidē tos nevarēja vizuāli apstiprināt.
- Publicēšana jūsu GitHub kontā un GitHub Actions reāla izpilde: repozitārijs jūsu kontā nav izveidots, un vietne nav publiskota. Iekļauta gatava darbplūsma un iestatīšanas instrukcija.
- Visi ārējie avota faili un visas tabulas nav atsevišķi pārbaudītas. To pieejamība, struktūra un aktualitāte ir publicētāju atbildība.

## Pirmā pārbaude pēc publicēšanas

Atveriet sākumlapu, meklējiet “autentifikācijas”, atveriet datu kopu un vienam CSV resursam nospiediet “Izpētīt tabulu”. Pārslēdziet tabulu uz diagrammu un izvēlieties `Skaits`. Pārbaudiet arī filtru maiņu, saglabāšanu, CSV eksportu un vietnes izskatu telefonā.
