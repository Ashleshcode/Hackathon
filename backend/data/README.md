# Synthetic demo dataset

`synthetic_demo_data.csv` has 34 fictional posts across `platform_a` and `platform_b`. Riverton, the accounts and the links are all invented. **It must always be presented as `synthetic_demo_data`, never as a real observed campaign.** Import it with the data source set to "Synthetic demo data".

To regenerate it, run `make_demo_dataset.py`.

## Planted patterns

| Group | Posts | What was planted | Expected result |
|---|---|---|---|
| A: coordinated-looking | `d001`–`d010`, 8 `relay_news_*` accounts | Same media hash, near-identical captions, all posted within 8 minutes across both platforms | One cluster of 8 accounts, with hash, caption and timing signals on its edges |
| B: same subject, independent | `d011`–`d020`, 10 accounts | Same fictional reservoir story, with different wording and no shared media, hours apart | No edges, which shows that sharing a subject isn't treated as coordination |
| C: weak link | `d021`–`d022`, 2 accounts | Both link to one article, about 9 hours apart | One edge with a single `shared_url` signal, and no cluster |
| D: unrelated | `d023`–`d034`, 12 accounts | Everyday topics. Six posts fall inside Group A's time window | No edges, which shows that timing alone doesn't link accounts |
