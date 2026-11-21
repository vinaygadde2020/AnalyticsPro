# License decision (needs the project owner)

**No `LICENSE` file has been added.** Choosing a license decides what other people may do with this code, and only the owner can make that choice. Until one is added, the default legal position is "all rights reserved": others can look at the code but have no permission to reuse it.

| Option | What it allows | Pick it if |
|---|---|---|
| **MIT** | Anyone may use, modify and redistribute, including in closed-source products, if they keep your copyright notice | You want maximum reuse and recognition with minimum friction (common for portfolio projects) |
| **Apache-2.0** | Like MIT, plus an explicit patent grant and a requirement to state changes | You want MIT-like freedom with patent protection |
| **GPL-3.0** | Anyone may use and modify it, but anything built on it must also be released under GPL | You want improvements to stay open source |
| **All rights reserved** (no license) | Nobody may reuse it without asking you | You want to show the work but not share it |

All of the dependencies in `requirements.txt` are permissively licensed or compatible with any option above, but this was not legally reviewed.

**To decide:** tell the maintainer which option you want, add the matching `LICENSE` file at the repository root with your name and the year, and replace the "License" section of the README. Do not invent a copyright holder.
