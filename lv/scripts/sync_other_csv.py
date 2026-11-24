"""Publish reviewed CSV data from publishers other than the procurement pilot."""
import argparse
from pathlib import Path

from sync_csv_preview import ROOT, ReviewedSource, sync

# Exact source metadata and normalized-table fingerprints for public CC0 resources.
SOURCES = (
    ReviewedSource(
        dataset_id='14969f9a-ee07-46e2-bbf3-ca0a9f960013',
        resource_id='fd0b9cdc-967a-4bd7-a0f3-80fe67a1b78c',
        sha256='be7a54cc701e2cccc46e58399beba4461d64e504382f30d02623969892ae196b',
        delimiter=',',
        encoding='utf-8-sig',
        slug='android_2023.csv',
        headers=('Date', 'Installed audience (All users, Unique users, Per interval, Daily): All countries / regions', 'Installed audience (All users, Unique users, Per interval, Daily): Latvia', 'Installed audience (All users, Unique users, Per interval, Daily): Lithuania', 'Installed audience (All users, Unique users, Per interval, Daily): United Kingdom', 'Installed audience (All users, Unique users, Per interval, Daily): Germany', 'Notes'),
        empty_tail_columns=0,
        row_count=365,
        organization='liepajas-pilsetas-pasvaldibas-administracija',
        publisher='Liepājas Centrālā administrācija',
        preamble=None,
        table_sha256='f149d4b70e87a826f69973d01e087aef93430c1b2e84029890c0851821ae5db3',
    ),
    ReviewedSource(
        dataset_id='4190de1c-4456-4e54-9c67-5a3e2d14cd8f',
        resource_id='480e75c1-e3f8-49a8-bbe8-30842ec93e78',
        sha256='2826d587f8dc1303a38216a8d43110c3360ed7ac3131e2842e50595dfc7bda4d',
        delimiter=';',
        encoding='cp1257',
        slug='radons_publ_ekas_darbavietas_2016_2017.csv',
        headers=('Mērījumu veikšanas administratīvā teritorija (Republikas nozīmes pilsēta vai novads)', 'Ēkā izvietoto detektoru skaits', 'Ēkas VIDĒJAIS (aritmētiskais) mērījumu rezultāts (Bq/m3)', 'Ēkas MAX mērījuma rezultāts (Bq/m3)', 'Ēkas MIN mērījuma rezultāts (Bq/m3)'),
        empty_tail_columns=0,
        row_count=243,
        organization='varam',
        publisher='Vides aizsardzības un reģionālās attīstības ministrija',
        preamble=('Valsts vides dienesta Radiācijas drošības centra organizētā radona gāzes līmeņa novērtējuma - Latvijas darba vietās un publiskajās ēkās 2016./2017.gadā, mērījumu rezultātu apkopojums.', '', '', '', ''),
        table_sha256='7f03144eb4b0592f0c7ba20258efd6e1568b25abc45a47ed9760cf743dadfd62',
    ),
    ReviewedSource(
        dataset_id='63abc917-3b32-4518-94a8-a678a01ae588',
        resource_id='2fff6951-9f73-429a-b595-785535579b6a',
        sha256='712752342bc88da3659ea06d998a7d9fd393e2bd68475cf063dac25478cb39ca',
        delimiter=';',
        encoding='utf-8-sig',
        slug='eraf064-ghg.csv.csv',
        headers=('Object', 'Plot', 'Plot ID', 'Date', 'Measurement ID', 'Chamber', 'Chamber ID', 'CO₂–C, mg m⁻² h⁻¹', 'CH₄-C, mg m⁻² h⁻¹', 'N₂O-N, mg m⁻² h⁻¹'),
        empty_tail_columns=0,
        row_count=1326,
        organization='silava',
        publisher='Latvijas Valsts mežzinātnes institūts “Silava”',
        preamble=None,
        table_sha256='615d1a2191d61054f073920a49ae98b8c9b967628f4b38551281e8125e95fa50',
    ),
    ReviewedSource(
        dataset_id='8c5af8aa-eb45-4832-a502-313108499951',
        resource_id='e5192e4c-f66d-4287-870f-7bb0f3aed7da',
        sha256='050c2c751ab5547d5d4b0dbd1998c2eb5ded1b2e5b6a8421593264b80a13069a',
        delimiter=',',
        encoding='utf-8-sig',
        slug='psngferry_20231016.csv',
        headers=('Port', 'Previous/next port', 'Ferry flag state (Code)', 'Ferry flag state (Name)', 'Passengers'),
        empty_tail_columns=0,
        row_count=5,
        organization='sam',
        publisher='Satiksmes ministrija',
        preamble=None,
        table_sha256='2a60f7964d9a681a60ea4c7543d24dc7dfffd75cb82e568bbe4d0f6fba45b05b',
    ),
    ReviewedSource(
        dataset_id='a786c8c0-1d19-4451-a467-e0d4af2c48fe',
        resource_id='f2d20b89-a0ce-47eb-86e7-aec94ec37e8f',
        sha256='6a679362fdf1ab886f21900f75673372d9847ba89706fa67134a3ed5528a4cc8',
        delimiter=',',
        encoding='utf-8-sig',
        slug='crgturnbytypeyear_20220807.csv',
        headers=('Kravas veids', ' (Svars)'),
        empty_tail_columns=0,
        row_count=556,
        organization='sam',
        publisher='Satiksmes ministrija',
        preamble=None,
        table_sha256='6a58acbfd48689444045704df2b57a0c104548eb0a4cefecba2f5e97a8c7cf6f',
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Reviewed CSV files named RESOURCE_ID.csv')
    parser.add_argument('--allow-standby', action='store_true', help='Use only the fully verified previous cohort')
    args = parser.parse_args()
    for resource_id, rows in sync(ROOT, args.source_dir, sources=SOURCES, allow_standby=args.allow_standby):
        print(f'{resource_id}: {rows} reviewed CSV rows', flush=True)


if __name__ == '__main__':
    main()
