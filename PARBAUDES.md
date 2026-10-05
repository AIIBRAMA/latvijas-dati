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
