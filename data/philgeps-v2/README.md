---
license: cc0-1.0
language:
- en
pretty_name: PhilGEPS procurement notices and awards, 2000–2025 (v2)
tags:
- government
- philippines
- procurement
- public-procurement
- philgeps
- contracts
- open-contracting
size_categories:
- 10M<n<100M
configs:
- config_name: default
  data_files: philgeps-2000-2025.parquet
- config_name: typed
  data_files: philgeps-2000-2025-typed.parquet
- config_name: sources
  data_files: sources.parquet
---

# PhilGEPS procurement notices and awards, 2000–2025 (v2)

This dataset holds every row of the 70 notice and award exports published by the Philippine Government Electronic Procurement System (PhilGEPS), covering 2000-11--2000-12 to 2025-07--2025-09. That is 18,515,260 rows in one schema, one per line item of a bid notice, with its award where one was published. Every row says which export and which row it came from.

> **Independent and unofficial.** This is csiiiv's normalization of the published PhilGEPS exports, published by BetterGov.ph. It is not an official record.
> - Rows are kept as published. Republished quarters overlap, duplicates are kept on purpose, and nothing is corrected.
> - The exports name no currency for their amounts. PHP is assumed but not confirmed.
> - A notice, an award, an amount or a flag does not by itself establish irregularity or wrongdoing by any agency, supplier or official.

## Local storage note

The untyped `philgeps-2000-2025.parquet` and small `sources.parquet` catalog are cold/offline inputs stored in the adjacent `nep/data_sources/odv-source-databases/philgeps-v2/` archive. A local symlink preserves this path for offline use. The typed dataset stays at this ODV path because the live API reads it.

## Which file to use

| File | Config | Contents |
| --- | --- | --- |
| `philgeps-2000-2025.parquet` | `default` | **Start here.** The normalized layer: 58 columns, every value a string exactly as published, with the source of each row |
| `philgeps-2000-2025-typed.parquet` | `typed` | The same rows and order, typed for analysis: dates are timestamps and amounts are `DECIMAL(38,4)`. Adds three name-comparison keys and per-row cleaning flags (64 columns) |
| `sources.parquet` | `sources` | The 70 exports: file name, period, format, size, SHA-256, layout, row count, and Drive link |
| `source-catalog.json` | — | csiiiv's full source catalog, including each export's column headers |
| `manifest.json` | — | Every file, with its bytes, SHA-256, row count, and the SHA-256 of csiiiv's original Parquet files |

The default layer keeps blanks and literals such as `NULL` and `N/A` exactly as published. The typed layer turns them into real nulls, so count values there.

Every row carries `_source_file_id`, `_source_sheet` and `_source_row_number`. Join `_source_file_id` to `sources.source_file_id` to find the export and the row a value came from.

## Left out: names of private individuals

The exports, and csiiiv's files, include two columns that name private individuals. We leave both out:
- `created_by` is the government staff member who posted the notice: 8,392,977 rows, 62,829 distinct names.
- `awardee_contact_person` is the supplier's contact person: 2,716,421 rows, 89,025 distinct names.

Both appear only in the 43-column exports. Every other column, every row and the row order are unchanged. The release check compares an order-sensitive fingerprint of every kept value against csiiiv's files.

Not here either: the raw exports, and the OCDS-shaped tables csiiiv built from the typed layer.

## Before you add anything up

- **One row is a notice line item, not an award.**
  - 18,515,260 rows carry 10,861,545 distinct bid references.
  - 6,970,129 rows carry an award reference, for 4,903,849 distinct awards.
  - An award with several line items repeats its `contract_amount` on every one of them. Of the 456,917 awards spread over more than one row, 456,655 repeat the same amount. Summing `contract_amount` across rows overcounts, so count each award once.
- **Some quarters were exported more than once.** About 2.5 million rows repeat another row's bid reference, line item, award reference, awardee, amount and item name. They are kept, because choosing which copy to keep is a judgment the data can't make for you.
- **The layouts differ, so coverage differs:**
  - Procuring entity location columns exist only in the 46-column CSV exports.
  - `client_agency` exists only in the 43-column exports.
  - A column a layout doesn't have is null for its rows. The column table below shows how many rows have a value.
- **Dates:**
  - Timestamps carry no time zone. Asia/Manila is likely, but the exports don't say.
  - Bid notices run from 2000-12-01 to 2025-09-30.
  - Award dates run from 1920-01-08 to 2034-10-04, so some are clearly wrong as published. The typed layer flags them; it doesn't fix them.
- **`item_budget` uses `-1` for "not provided".** The typed layer turns it into null and flags the row.
- **Names are kept as printed.** The `*_key` columns group names only by case and spacing. No agency or supplier has been merged with another, and no official identifiers are assigned.
- **74,541 rows name a joint venture that isn't split into its partners.**
- **10 cells contain encoding damage** (U+FFFD, for example `LOS BAÃ‘OS`). They are kept as is and listed in `_replacement_character_columns`.

## Export layouts

| `_source_schema_id` | Exports | Rows |
| --- | ---: | ---: |
| `modern_43` | 40 | 8,544,543 |
| `location_46` | 18 | 8,050,724 |
| `legacy_40_uom` | 11 | 1,595,484 |
| `legacy_40_unit_of_measurement` | 1 | 324,509 |

The 2000–2010 workbooks have their header on row 4. Four 2021–2022 CSVs have no header row and are read by verified column position.

## Cleaning flags (typed layer)

The flags are findings for review, not corrections. 806,356 rows have at least one.

| Flag in `_cleaning_issues` | Rows |
| --- | ---: |
| `item_budget_not_provided_sentinel` | 589,612 |
| `award_before_bid_published` | 179,717 |
| `contract_end_before_notice_to_proceed` | 30,968 |
| `contract_amount_exceeds_approved_budget` | 9,561 |
| `item_budget_exceeds_approved_budget` | 5,200 |
| `invalid_contract_end_date` | 11 |
| `replacement_character` | 8 |
| `missing_bid_reference` | 1 |

## Columns

The "PhilGEPS" notes list the export headers each column was read from.

| Column | In `default` | Type in `typed` | Rows with a value (typed) | Notes |
| --- | :---: | --- | ---: | --- |
| `_source_file_id` | ✓ | `string` | 18,515,260 | The export the row came from; joins `sources.source_file_id` (SHA-256 of the file). |
| `_source_sheet` | ✓ | `string` | 10,464,536 | Worksheet in that export (null for CSV). |
| `_source_row_number` | ✓ | `int64` | 18,515,260 | Row in that export, as a spreadsheet shows it. |
| `_source_schema_id` | ✓ | `string` | 18,515,260 | Which of the four export layouts the row was read with. |
| `procuring_entity_name` | ✓ | `string` | 18,515,259 | PhilGEPS: “Organization Name”, “Procuring Entity”, “Procuring Entity (PE)” |
| `bid_reference_no` | ✓ | `string` | 18,515,259 | PhilGEPS: “Bid Reference No.”, “Reference ID” |
| `solicitation_no` | ✓ | `string` | 10,450,720 | PhilGEPS: “Solicitation No.” |
| `notice_title` | ✓ | `string` | 18,513,764 | PhilGEPS: “Notice Title” |
| `bid_published_date` | ✓ | `timestamp[us]` | 18,352,964 | PhilGEPS: “Publish Date”, “Published Date” |
| `classification` | ✓ | `string` | 18,515,259 | PhilGEPS: “Classification” |
| `notice_type` | ✓ | `string` | 10,464,535 | PhilGEPS: “Notice Type” |
| `business_category` | ✓ | `string` | 18,515,259 | PhilGEPS: “Business Category” |
| `funding_source` | ✓ | `string` | 18,515,186 | PhilGEPS: “Funding Source” |
| `funding_instrument` | ✓ | `string` | 18,515,130 | PhilGEPS: “Funding Instrument” |
| `procurement_mode` | ✓ | `string` | 18,515,259 | PhilGEPS: “Procurement Mode” |
| `trade_agreement` | ✓ | `string` | 18,515,259 | PhilGEPS: “Trade Agreement” |
| `approved_budget` | ✓ | `decimal128(38, 4)` | 18,515,259 | PhilGEPS: “Approved Budget of the Contract” |
| `area_of_delivery` | ✓ | `string` | 17,138,754 | PhilGEPS: “Area of Delivery” |
| `contract_duration` | ✓ | `int64` | 18,170,001 | PhilGEPS: “Contract Duration” |
| `calendar_type` | ✓ | `string` | 17,889,397 | PhilGEPS: “Calendar Type” |
| `line_item_no` | ✓ | `int64` | 11,818,682 | PhilGEPS: “Line Item No” |
| `item_name` | ✓ | `string` | 11,818,143 | PhilGEPS: “Item Name” |
| `item_description` | ✓ | `string` | 11,810,237 | PhilGEPS: “Item Desc”, “Item Description” |
| `quantity` | ✓ | `decimal128(38, 6)` | 11,818,682 | PhilGEPS: “Quantity” |
| `unit_of_measurement` | ✓ | `string` | 11,818,624 | PhilGEPS: “UOM”, “Unit of Measurement” |
| `item_budget` | ✓ | `decimal128(38, 4)` | 11,229,070 | PhilGEPS: “Item Budget” |
| `prebid_date` | ✓ | `timestamp[us]` | 2,581,455 | PhilGEPS: “PreBid Date” |
| `closing_date` | ✓ | `timestamp[us]` | 18,174,604 | PhilGEPS: “Closing Date” |
| `bid_notice_status` | ✓ | `string` | 18,515,259 | PhilGEPS: “Bid Notice Status”, “Notice Status” |
| `award_reference_no` | ✓ | `string` | 6,970,129 | PhilGEPS: “Award No.”, “Award Reference No.” |
| `award_title` | ✓ | `string` | 6,970,100 | PhilGEPS: “Award Title” |
| `award_type` | ✓ | `string` | 3,061,264 | PhilGEPS: “Award Type” |
| `unspsc_code` | ✓ | `string` | 6,301,316 | PhilGEPS: “UNSPSC Code” |
| `unspsc_description` | ✓ | `string` | 6,301,316 | PhilGEPS: “UNSPSC Description” |
| `awardee_organization_name` | ✓ | `string` | 6,919,984 | PhilGEPS: “Awardee Corporate Title”, “Awardee Organization Name” |
| `contract_amount` | ✓ | `decimal128(38, 4)` | 6,962,376 | PhilGEPS: “Contract Amount” |
| `contract_no` | ✓ | `string` | 2,061,617 | PhilGEPS: “Contract No” |
| `award_published_date` | ✓ | `timestamp[us]` | 6,970,125 | PhilGEPS: “Publish Date(Award)”, “Published Date(Award)” |
| `award_date` | ✓ | `timestamp[us]` | 6,970,070 | PhilGEPS: “Award Date” |
| `notice_to_proceed_date` | ✓ | `timestamp[us]` | 5,043,024 | PhilGEPS: “Notice to Proceed Date” |
| `contract_effectivity_date` | ✓ | `timestamp[us]` | 5,043,024 | PhilGEPS: “Contract Efectivity Date”, “Contract Effectivity Date” |
| `contract_end_date` | ✓ | `timestamp[us]` | 5,068,751 | PhilGEPS: “Contract End Date” |
| `reason_for_award` | ✓ | `string` | 3,060,634 | PhilGEPS: “Reason for Award” |
| `award_notice_status` | ✓ | `string` | 6,970,128 | PhilGEPS: “Award Notice Status”, “Award Status” |
| `client_agency` | ✓ | `string` | 282,983 | PhilGEPS: “Client Agency” |
| `procuring_entity_region` | ✓ | `string` | 8,050,724 | PhilGEPS: “Region” |
| `procuring_entity_province` | ✓ | `string` | 8,050,724 | PhilGEPS: “Province” |
| `procuring_entity_city_municipality` | ✓ | `string` | 8,050,724 | PhilGEPS: “City/Municipality” |
| `government_branch` | ✓ | `string` | 8,050,724 | PhilGEPS: “Government Branch” |
| `procuring_entity_organization_type` | ✓ | `string` | 8,050,724 | PhilGEPS: “PE Organization Type” |
| `procuring_entity_organization_type_grouped` | ✓ | `string` | 8,050,724 | PhilGEPS: “PE Organization Type (Grouped)” |
| `awardee_country` | ✓ | `string` | 3,902,161 | PhilGEPS: “Country of Awardee” |
| `awardee_region` | ✓ | `string` | 3,896,195 | PhilGEPS: “Region of Awardee” |
| `awardee_province` | ✓ | `string` | 3,897,502 | PhilGEPS: “Province of Awardee” |
| `awardee_city_municipality` | ✓ | `string` | 3,899,781 | PhilGEPS: “City/Municipality of Awardee” |
| `awardee_size` | ✓ | `string` | 3,716,039 | PhilGEPS: “Awardee Size” |
| `awardee_joint_venture` | ✓ | `string` | 74,541 | PhilGEPS: “Awardee Joint Venture” |
| `_extra_values` | ✓ | `list<element: string>` | 0 | Unexpected trailing values on the row (none in this release). |
| `procuring_entity_name_key` | — | `string` | 18,515,259 | Upper-case comparison key for grouping names; entities are not merged. |
| `client_agency_key` | — | `string` | 282,983 | Upper-case comparison key for `client_agency`. |
| `awardee_organization_name_key` | — | `string` | 6,919,984 | Upper-case comparison key for `awardee_organization_name`. |
| `_replacement_character_columns` | — | `list<element: string>` | 18,515,260 | Columns on the row that contain U+FFFD (encoding damage, kept as is). |
| `_cleaning_issues` | — | `list<element: string>` | 18,515,260 | Findings for review on this row, not corrections: see the flags table. |
| `_cleaning_issue_count` | — | `int32` | 18,515,260 | Number of findings on the row. |

## Use it

```python
from datasets import load_dataset

philgeps = load_dataset("bettergovph/philgeps-v2", split="train", streaming=True)
```

```sql
-- DuckDB: awards by year, counting each award once
WITH awards AS (
  SELECT DISTINCT award_reference_no, year(award_date) AS year, contract_amount
  FROM 'hf://datasets/bettergovph/philgeps-v2/philgeps-2000-2025-typed.parquet'
  WHERE award_reference_no IS NOT NULL
)
SELECT year, count(*) AS awards, sum(contract_amount) AS amount
FROM awards GROUP BY year ORDER BY year;
```

## Sources and method

- **Source:** the PhilGEPS exports, quarterly and annual XLSX and CSV files, collected in the [PHILGEPS-V2 Drive folder](https://drive.google.com/drive/folders/1Km2gqIfaY_9ZotjvePFZVSMEuxud6WWA).
- **Pipeline:** [csiiiv/philgeps_data_v2](https://github.com/csiiiv/philgeps_data_v2), at the commit in `manifest.json`.
  - Stage 0 downloads the exports and registers each one by its SHA-256.
  - Stage 1 maps every layout onto one schema by column name. Nothing is dropped, deduplicated or coerced, so the result is the normalized layer.
  - The typed layer then applies `config/cleaning_rules.json`: null literals, date and decimal typing, Unicode NFC and trimming, and the comparison keys.
- **This release:**
  - leaves out the two name columns;
  - renames the files;
  - rewrites them with Zstandard compression in 100,000-row groups;
  - checks the row count, column types and an order-sensitive fingerprint of every kept value against csiiiv's files.

## How this relates to bettergovph/philgeps-data

[bettergovph/philgeps-data](https://huggingface.co/datasets/bettergovph/philgeps-data) is the earlier release: 5,481,161 awards in 12 columns. This one has the full line-item exports, with every published column except the two above, and the source of every row.

## License

[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). PhilGEPS notices are works of the Government of the Philippines, and no copyright subsists in them (Republic Act 8293, section 176). Credit is welcome: "PhilGEPS exports normalized by csiiiv (philgeps_data_v2), published by BetterGov.ph".

## Report a problem

Open a discussion on this dataset's Community tab. Include the `_source_file_id` and `_source_row_number`.

## Citation

```bibtex
@misc{bettergov_philgeps_v2,
  title        = {PhilGEPS procurement notices and awards, 2000--2025 (v2)},
  author       = {{BetterGov.ph} and csiiiv},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/bettergovph/philgeps-v2}}
}
```
