# Received material: the 2024 prototype

This folder is the record of the original project, kept so that the audit in
[`docs/audit-2024-prototype.md`](../docs/audit-2024-prototype.md) can be checked against the
material it describes. Nothing here is used by the rebuild.

## Origin

The prototype was built in spring 2024 by the quant team of Mercury Capital Management (MCM), St
Andrews, and presented as "Automated fundamental analysis in quant". The algorithm lived in
Danyil Nepyivoda's QuantConnect account as project 17552945, "Energetic Sky Blue Jackal"
(algorithm class `SmoothLightBrownPenguin`, a name QuantConnect generated), with the valuation
script in a separate library project, "lib" (17554026). The records do not say which team member
wrote which lines.

## Files

| File | What it is | How it arrived | Verified |
|---|---|---|---|
| `main.py` | The QuantConnect algorithm: seven tickers, pasted fair values, daily trading rule, calendar 2023 | Read from project 17552945 through QuantConnect's web API on 22 September 2026 | Byte-identical to the code QuantConnect stored with the final backtest `e472f920` (4 April 2024), compared on 25 September 2026 |
| `dcf_valuation_yfinance.py` | The valuation script that produced the fair values from yfinance, run by hand one ticker at a time | Read from the library project 17554026 through QuantConnect's web API on 22 September 2026 | SHA-256 recorded at retrieval. It is not part of the backtest's code snapshot (the algorithm never imported it), so it could not be compared with a stored run. Its code matches the deck's two screenshots of it |
| `deck.pptx` | The 9-slide presentation, "Automated fundamental analysis in quant" | Danyil Nepyivoda's copy, archived on 22 September 2026 | File metadata: created 4 April 2024 13:20 UTC, last modified 4 April 2024 17:48 UTC, creator and last modified by "Даниїл Непийвода" (Danyil Nepyivoda's name in Ukrainian). Opened and read; package parts holding personal data, the other team members' names on the title slide and the thumbnail image removed on 25 September 2026 (see [the deck](#the-deck)) |
| `backtest-2023.png` | The deck's results slide image: QuantConnect results page of the final 2023 backtest | Extracted from `deck.pptx` (`ppt/media/image8.png`) | Byte-identical to the image inside the deck. Figures match the export of backtest `e472f920` (equity USD 127,232.87, fees USD 363.04, PSR 96.331%) |
| `code-getting-data.png` | Deck screenshot of `fetch_financial_metrics_for_years` in the valuation script | Extracted from `deck.pptx` (`ppt/media/image4.png`) | Byte-identical to the image inside the deck; code matches `dcf_valuation_yfinance.py` |
| `code-calculating.png` | Deck screenshot of `calculate_ebitda_value` | Extracted from `deck.pptx` (`ppt/media/image5.png`) | Byte-identical to the image inside the deck; code matches `dcf_valuation_yfinance.py` |
| `code-trading.png` | Deck screenshot of `OnData` and `trade` in the algorithm | Extracted from `deck.pptx` (`ppt/media/image6.png`) | Byte-identical to the image inside the deck; code matches `main.py` |
| `code-initialize.png` | Deck screenshot of `Initialize` in the algorithm | Extracted from `deck.pptx` (`ppt/media/image7.png`) | Byte-identical to the image inside the deck; code matches `main.py` |

The two code screenshots of the valuation script show it open in a desktop editor, which fits the
deck's description of the pipeline: the script ran outside QuantConnect and its output was carried
into the algorithm by hand.

## The deck

On 25 September 2026 three things were removed from `deck.pptx`: the package parts that held
personal data (the change-tracking record `ppt/changesInfos/` and the revision record
`ppt/revisionInfo.xml`, with their relationships and content-type entries); the names of the
other team members on the title slide, which now names only Danyil Nepyivoda; and the package
thumbnail `docProps/thumbnail.jpeg`, a picture of that title slide, with its relationship. The
other eight slides, the media and the core properties (title, creator, dates) are unchanged, the
file passes the Office package validator, and the text of those eight slides is identical to that
of the copy archived on 22 September 2026. The checksum below is that of the edited file.

## Checksums (SHA-256)

```text
60ac793e7d500d9e01120d3948c90f61f63408d548f1a37da9818d1fd3134c06  main.py
1b9a2888e0a934461310f6e1ecc3bb5050429b255d92389910beb2e9f879e372  dcf_valuation_yfinance.py
fae18cab8124643a402e80aff47a1b606b4b1f780b93123c129ed09a84484b2f  deck.pptx
fba0924ded9dc0ce99f221acd095e43e5fb493baf4b2c90243a9a3b43e2b702e  backtest-2023.png
acb067a2dfab558b41a8b7fb802c9c9478436ec76a4af567034c3fa4229995c9  code-getting-data.png
4782e89bcb0a49f06a3cc01e2f259b3e4269b85f3ea63c24f88b44c30d0b4f4b  code-calculating.png
209dbac75c452942248244f60a10601a5c685a6301cde8c232a16db5e1a00161  code-trading.png
3ea88c2d7cb62cf75333a9e6321dd1048d38f185606ebc5dd08a43fed7f052cf  code-initialize.png
```

## Verbatim

The two Python files are exactly as they were in QuantConnect, including their defects, unused
imports and comments. They have not been reformatted, corrected or run again here. The project
also held QuantConnect's default `research.ipynb` template notebook, which contains nothing from
the project and is not reproduced.

## Licence

This folder is **not** covered by the MIT licence in [`../LICENSE`](../LICENSE). The code, deck
and images are reproduced as a historical record of the MCM quant team's 2024 work. Anyone wanting
to reuse them needs the permission of the team members who made them.

QuantConnect's generated backtest reports are records in the same sense and are not relicensed
either: [`results/base_2016_2024/qc_report.html`](../results/base_2016_2024/qc_report.html) and
[`results/prototype_2023/qc_report.html`](../results/prototype_2023/qc_report.html).
