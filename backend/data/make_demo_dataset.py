"""Regenerates synthetic_demo_data.csv. Everything in it is fictional.

Run from anywhere: python3 backend/data/make_demo_dataset.py
Planted patterns are documented in README.md next to this file.
"""

import csv
from pathlib import Path

OUTPUT = Path(__file__).with_name("synthetic_demo_data.csv")
FIELDS = ["post_id", "platform", "account_id", "timestamp", "text", "url", "media_hash", "media_reference"]

CAPTION = "Riverton residents warned: the tap water tested unsafe after the reservoir leak. Officials are hiding the report."

# Group A: repeated media, near-identical captions, posted within 8 minutes.
COORDINATED = [
    ("platform_a", "relay_news_01", "09:00", CAPTION),
    ("platform_a", "relay_news_02", "09:01", CAPTION),
    ("platform_b", "relay_news_03", "09:01", CAPTION),
    ("platform_b", "relay_news_04", "09:02", f"{CAPTION} Share now."),
    ("platform_a", "relay_news_05", "09:03", f"{CAPTION} Share now."),
    ("platform_b", "relay_news_06", "09:04", CAPTION),
    ("platform_a", "relay_news_07", "09:05", f"URGENT: {CAPTION}"),
    ("platform_b", "relay_news_08", "09:06", f"URGENT: {CAPTION}"),
    ("platform_a", "relay_news_01", "09:07", f"{CAPTION} Spread the word."),
    ("platform_b", "relay_news_03", "09:08", f"{CAPTION} Spread the word."),
]

# Group B: same subject, independent wording and timing, no shared media.
INDEPENDENT = [
    ("platform_a", "resident_maya", "07:12", "Our kitchen tap ran cloudy this morning. Has anyone else near the Riverton reservoir noticed?"),
    ("platform_b", "plumber_tom", "08:40", "Three callouts today about discoloured water. Flush your pipes for a few minutes, folks."),
    ("platform_a", "riverton_parent", "10:25", "The school sent a note saying drinking fountains are closed until testing finishes."),
    ("platform_b", "council_watcher", "11:50", "Tonight's council agenda has a reservoir repair item. Worth attending if you care about water bills."),
    ("platform_a", "hydro_student", "13:05", "Reservoir leaks don't automatically mean contamination. Sampling results take a couple of days."),
    ("platform_b", "cafe_owner_lin", "14:30", "We're using bottled water for coffee today, just to be careful, until the utility gives an update."),
    ("platform_a", "local_reporter_d", "15:45", "Spoke with the utility: repairs started and lab samples went out this afternoon. More tomorrow."),
    ("platform_b", "riverside_runner", "17:20", "Path beside the reservoir is fenced off, crews everywhere. Took the long way round on my run."),
    ("platform_a", "retired_chemist", "19:10", "Chlorine smell is normal after a mains repair. Boil notices are what you should watch for."),
    ("platform_b", "new_neighbour_sam", "21:35", "Just moved to Riverton. Is the water situation always this confusing, or is this unusual?"),
]

# Group C: one link shared by two unrelated accounts, hours apart. A single
# weak signal: it should appear as an edge but not form a cluster.
SHARED_LINK = "https://example.invalid/article/riverton-budget"
WEAK_LINK = [
    ("platform_a", "budget_reader", "08:15", f"Interesting numbers in this piece {SHARED_LINK}"),
    ("platform_b", "town_historian", "16:55", f"Compare this with the 1990s figures {SHARED_LINK}"),
]

# Group D: unrelated posts. Several land inside Group A's time window, so timing
# alone must not connect them.
UNRELATED = [
    ("platform_a", "baker_june", "09:01", "Sourdough came out beautifully today, crust finally crackling the way it should."),
    ("platform_b", "cyclist_omar", "09:02", "Forty kilometres before breakfast along the coast road. Legs are complaining loudly."),
    ("platform_a", "birdwatch_ana", "09:03", "Spotted a kingfisher by the old mill bridge. Sat still for nearly ten minutes."),
    ("platform_b", "gamer_kit", "09:04", "Finished the final boss after nineteen attempts. Absolutely no regrets about this weekend."),
    ("platform_a", "gardener_rosa", "09:06", "Tomato seedlings are ready for the greenhouse once these cold nights pass."),
    ("platform_b", "chess_club_ben", "09:07", "Club tournament starts Saturday. Beginners welcome, boards and clocks provided."),
    ("platform_a", "film_fan_nia", "11:30", "Rewatched that old heist film last night, and the soundtrack still holds up perfectly."),
    ("platform_b", "hiker_pavel", "12:15", "Trail map says two hours, my knees say four. Lovely views from the ridge though."),
    ("platform_a", "teacher_ivy", "14:05", "Students built tiny bridges from spaghetti, and one held an entire dictionary."),
    ("platform_b", "potter_sol", "16:20", "New glaze experiment turned out speckled blue. Happy accident from the kiln this week."),
    ("platform_a", "astro_kai", "20:40", "Clear skies tonight, so the telescope is finally out. Jupiter's moons looked sharp."),
    ("platform_b", "knitter_bea", "22:05", "Halfway through the second sleeve, and I've already miscounted the cable pattern twice."),
]


def main() -> None:
    rows = []

    def add(records, media_hash=None, media_reference=None):
        for platform, account, time, text in records:
            post_id = f"d{len(rows) + 1:03d}"
            rows.append(
                {
                    "post_id": post_id,
                    "platform": platform,
                    "account_id": account,
                    "timestamp": f"2026-10-20T{time}:00Z",
                    "text": text,
                    "url": f"https://example.invalid/post/{post_id}",
                    "media_hash": media_hash or "",
                    "media_reference": media_reference or "",
                }
            )

    add(COORDINATED, media_hash="synthetic_hash_reservoir_01", media_reference="synthetic_reservoir_image.jpg")
    add(INDEPENDENT)
    add(WEAK_LINK)
    add(UNRELATED)

    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
