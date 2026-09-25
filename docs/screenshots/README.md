# QuantConnect screenshots

The repository's README has a commented-out image line for each screenshot below. The images are
not in the repository yet; Danyil Nepyivoda captures them from his QuantConnect account and adds
them here. Until a file exists, its README line stays commented out so nothing renders as a
broken image.

## Checklist

- [ ] `qc-base-overview.png`: the results page of the base backtest.
  - Project 36836412 ("Automated DCF point-in-time"), backtest `54b5e0649da4a9cbf3f7dce6c409c7fe`,
    named `run1`, run 22 September 2026.
  - Capture the header statistics row (equity, fees, holdings, net profit, PSR, return) and the
    Strategy Equity chart with the full 2016 to 2024 range selected.
  - Check before saving: equity USD 197,850.66, fees USD 1,388.79, return 97.85 %, PSR 0.433%.
    The header's Net Profit field reads USD 78,361.84, a dollar figure; the 97.85% is under
    Return.
- [ ] `qc-base-report.png`: the first page of the report for the same backtest.
  - Open the backtest, go to the Report tab, generate the report if needed, and capture the first
    page (key statistics, cumulative return against the benchmark, drawdown).
- [ ] `qc-prototype-2023.png`: the results page of the 2024 prototype's final backtest.
  - Project 17552945 ("Energetic Sky Blue Jackal"), backtest `e472f920b9bb72dbb8024af7d95f1c04`,
    named "Geeky Sky Blue Caterpillar", created 4 April 2024.
  - Capture the header statistics row and the Strategy Equity chart for 2023. Include the Research
    Guide panel if it still shows "Possible Overfitting".
  - Check before saving: equity USD 127,232.87, fees USD 363.04, return 27.23 %, PSR 96.331%.

## How to capture

- PNG, light theme, browser zoom at 100%, about 1,600 pixels wide.
- Crop to the QuantConnect page content: no browser tabs, address bar, bookmarks or taskbar.
- Leave out anything that identifies the account: the user name or avatar in the top bar, e-mail
  addresses, organisation names, API tokens.
- Save each file in this folder (`docs/screenshots/`) under exactly the name above; the README
  links are case-sensitive on GitHub.

## Turning the README lines on

Each screenshot has one commented-out line in the top-level `README.md`, of the form

```markdown
<!-- ![Alt text](docs/screenshots/qc-base-overview.png) -->
```

To find them:

```powershell
git grep -n "docs/screenshots/" README.md
```

After adding a file, delete the leading `<!-- ` and the trailing ` -->` on its line so it reads

```markdown
![Alt text](docs/screenshots/qc-base-overview.png)
```

Then check the rendered README on GitHub (or in a Markdown preview) and commit the image and the
README change together. Leave the line for any screenshot not yet captured commented out.
