# Valsts kases gada pārskati

Portālā lasāmi seši 2024. gada un seši 2025. gada [Valsts budžeta un pašvaldību budžetu izpildes pārskata XLSX resursi](https://data.gov.lv/dati/dataset/valsts-budzeta-un-pasvaldibu-budzetu-izpildes-gada-parskata-dati). Šis papildinājums neaizstāj budžeta mēneša tabulas vai Valsts budžeta tāmes.

- Avots ir Valsts kase; licence **CC0 1.0**. Visos 12 pārskatos kopā pārbaudītas 267 214 aizpildītas rindas. Sešas tukšas noformējuma rindas nesatur datus un tabulā netiek rādītas.
- Gada, iestādes, reģistrācijas numura un klasifikācijas datu vērtības saglabātas. Pārskatā “Pašvaldību pamatbudžeta izpilde 2025. gads” oriģinālā kolonna `Ministrija` satur pašvaldības; portālā tā rādīta kā `Novads`, saglabājot atsauci uz sākotnējo kolonnas nosaukumu.
- `Summa` ir avota `Summa_EUR`; tukša vērtība nav nulle. Portāls neveido kopsummas, kas sajauktu pamatdatus, konsolidāciju, korekcijas vai dažādus EKK hierarhijas līmeņus.
- Priekšskatījums atver vienu pilnu pārskatu. Filtri un CSV eksports darbojas visā atlasītajā pārskatā, ne tikai redzamajā tabulas lapā. Oriģinālais XLSX joprojām ir pieejams avota saitē.

## Atjaunošanas kārtība

`npm run sync:annual` patstāvīgi pārbauda gada pārskatus. Esošā vietnes sinhronizācija izpilda šo soli pēc līdzšinējiem trim datu posmiem. `--allow-standby` ļauj kļūmes gadījumā izmantot tikai visu iepriekš publicēto 12 pārskatu grupu, pārbaudot katra datņu kontrolsummu, resursa identitāti, gadu, shēmu un skaitu. Portālā ir norāde, ka rādīta iepriekšējā pilnā kopija. Pirmās publicēšanas laikā, ja pilna grupa nav pieejama un iepriekšējā publiskajā katalogā vēl nav gada kopiju, līdzšinējos apstiprinātos budžeta datus var publicēt bez šīs jaunās grupas. Nepilna vai bojāta iepriekšējā grupa netiek publicēta.

Precīzās oficiālās adreses un apstiprinātās SHA-256 kontrolsummas ir `lv/scripts/sync_annual_xlsx.py`. Ja iestāde labo vēsturisku avotu vai pievieno jaunu gadu, pirms jaunu datu publicēšanas jāpārbauda licence, darblapa, visi lauki, rindu skaits un summas pret oriģinālu un jāatjaunina attiecīgā adrese un kontrolsumma. Nekāds plašāks datņu saturs bez šīs pārbaudes netiek pārpublicēts. Bezsaistes pārbaude: `python3 lv/scripts/sync_annual_xlsx.py --source-dir MAPE`, kur datnēm ir resursa UUID un paplašinājums `.xlsx`.
