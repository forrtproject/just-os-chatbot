import importlib.util
from pathlib import Path

import numpy as np

# Load eval/topic_map/common.py by path: eval/ is not a package
spec = importlib.util.spec_from_file_location(
    "topic_map_common", Path(__file__).resolve().parent.parent / "eval" / "topic_map" / "common.py"
)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)

PROSE = ("Preregistration means writing down the hypotheses, the design and the analysis plan before "
         "the data are collected, so that readers can tell planned tests from exploratory ones and "
         "judge how much the results depend on choices made after seeing the data.")
REFERENCES = ("Nosek, B. A., et al. (2018). The preregistration revolution. PNAS, 115(11), 2600-2606. "
              "Simmons, J. P., et al. (2011). False-positive psychology. Psychol. Sci., 22(11), 1359-1366. "
              "Wagenmakers, E.-J., et al. (2012). An agenda for purely confirmatory research. 7(6), 632-638.")


def test_clean_strips_markup():
    text = 'See <span id="page-3-1"></span>[Nosek](https://doi.org/10.1/x) and doi: 10.1234/abc **here**'
    out = common.clean(text)
    assert "span" not in out and "https" not in out and "10.1234" not in out and "*" not in out
    assert "Nosek" in out and "here" in out


def test_boilerplate():
    assert not common.is_boilerplate(PROSE)
    assert common.is_boilerplate(REFERENCES)  # many citations per 100 words
    assert common.is_boilerplate("Table 3. Means and SDs")  # too short to count


def test_status_limits():
    assert common.status(0.50) == "blind"
    assert common.status(0.56) == "thin"
    assert common.status(0.60) == "covered"
    assert common.status(0.63) == "strong"


def test_topic_kind():
    assert common.topic_kind(0.6, 0.1) == "reference lists"
    assert common.topic_kind(0.1, 0.8) == "one paper"
    assert common.topic_kind(0.1, 0.3) == "topic"


def test_plain_and_unit():
    assert common.plain({"abc123": "Title"}) == "Title"
    assert common.plain("Title") == "Title"
    v = common.unit([[3.0, 4.0]])
    assert np.allclose(np.linalg.norm(v, axis=1), 1)
