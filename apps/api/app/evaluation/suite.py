"""The fixed test suite.

Twelve questions, each chosen because it isolates one thing a retrieval system
can be good or bad at. Every one carries:

  * a preamble saying why it is in the suite at all,
  * a pinned plan - the FTS5 expression, the embedding string and the Cypher
    that each mode will run,
  * hand-authored relevance judgments over the corpus,
  * the traps that were planted for it, and why each is tempting.

Why the plan is pinned
----------------------
In the live app a Claude call turns the question into those four queries. That
call is non-deterministic, costs money, and would make this report measure the
planner rather than the retrievers. Here the plan is fixed at a good-faith,
hand-written translation of the question, identical for every mode, so the only
variable left is the retrieval strategy itself. `runner.py --live-planner` will
use the real planner instead if you want to measure that too.

Judgments are made against the *question*, not against any mode. A player id is
a correct answer to "which players ...?" even though only the graph modes can
return one; that asymmetry is the finding, not a scoring bug.
"""

from __future__ import annotations

from typing import Any

from .scoring import ANSWERS, EVIDENCE, TOPICAL

# --- reusable judgment fragments -----------------------------------------

# Every player carrying at least one CONFLICT_WITH edge, derived at build time
# from the 16 conflict articles. Verified against the graph, not typed by hand.
CONFLICT_PLAYERS = [
    "draymond-green", "rudy-gobert", "kevin-durant", "lebron-james",
    "jordan-poole", "jimmy-butler", "karl-anthony-towns", "joel-embiid",
    "kyrie-irving", "jaylen-brown", "jayson-tatum",
]

FOOD_TRAPS = {
    "article:n15": "Contains 'beef' three times. It is about brisket.",
    "article:n16": "Contains 'beef' in the title. It is about a caterer.",
    "article:n20": "'Beefing up' is weight training. It also mentions a center, so it "
                   "looks doubly relevant to a question about big men.",
}


def _players(ids: list[str], grade: int = ANSWERS) -> dict[str, int]:
    return {f"player:{p}": grade for p in ids}


def _articles(ids: list[str], grade: int) -> dict[str, int]:
    return {f"article:{a}": grade for a in ids}


# --- the suite ------------------------------------------------------------

TEST_CASES: list[dict[str, Any]] = [
    {
        "id": "exact-name",
        "family": "Lexical precision",
        "query": "Draymond Green suspension",
        "headline": "The case keyword search should win",
        "preamble": (
            "A suite that only contains questions the ontology wins is not an "
            "evaluation, it is an advertisement. This one is the control: a proper noun "
            "and a common noun, both spelled exactly as the corpus spells them. There is "
            "no paraphrase to bridge, no threshold to express and no relationship to "
            "traverse. If the cheapest and oldest technique in the box does not win "
            "here, the harness is broken."
        ),
        "what_good_looks_like": (
            "The four articles about a Draymond Green suspension, at the top, in under a "
            "millisecond, with no model call. The trap is the Ja Morant 25-game "
            "suspension: the strongest 'suspension' document in the corpus and the wrong "
            "player entirely."
        ),
        "plan": {
            "interpretation": "Find documents about Draymond Green being suspended.",
            "keyword_query": '"draymond green" OR (draymond AND (suspension OR suspended))',
            "semantic_query": "Draymond Green was suspended by the league after an on-court incident.",
            "cypher": (
                "MATCH (p:Player {id: 'draymond-green'})-[:MENTIONED_IN]->(a:Article)\n"
                "WHERE a.conflict_kind IS NOT NULL\n"
                "RETURN a.id AS id, a.title AS name, a.conflict_kind AS relation_detail,\n"
                "       a.published_at AS published\n"
                "ORDER BY a.published_at DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": [],
        },
        "judgments": {
            **_articles(["n01", "n07", "n03", "n36"], ANSWERS),
            **_articles(["n02", "n13", "n35"], EVIDENCE),
            "player:draymond-green": EVIDENCE,
        },
        "traps": {
            "article:n12": "A 25-game suspension, described in detail, for Ja Morant. The "
                           "best 'suspension' document in the corpus and the wrong player.",
        },
        "commentary": {
            "hybrid": "Ties the keyword score without improving on it, and takes roughly two "
                      "hundred times as long to do it. Worth sitting with: on the question shape "
                      "that most closely resembles ordinary search, the sophisticated pipeline's "
                      "entire contribution is latency. Fusion has nothing to add when one leg was "
                      "already right.",
            "keyword": "The name is rare, so BM25's IDF weighting does most of the work "
                       "unaided. This is the shape of question that made inverted indexes "
                       "the default for thirty years, and no amount of modelling improves "
                       "on it.",
            "semantic": "Ties keyword here, which is worth stating plainly because the "
                        "received wisdom says it should not: the name is distinctive enough "
                        "that its embedding is distinctive too. Two things the score does "
                        "not show. The vector page carries the Ja Morant suspension at rank "
                        "7 and the keyword page does not, so the mode that blurs names did "
                        "eventually blur one. And it costs two orders of magnitude more "
                        "latency for the same answer, because the question has to be "
                        "embedded before anything can be compared.",
            "graph": "MENTIONED_IN plus a conflict_kind filter is exact, but it can only "
                     "return conflict articles, so the aftermath piece, which describes a "
                     "suspension and no conflict, is structurally invisible to it.",
            "hybrid_ontology": "Nothing in this question is a modelled concept, so the "
                               "expansion contributes nothing and this mode is plain hybrid "
                               "with a longer trace. Worth seeing at least once.",
        },
    },
    {
        "id": "beef-word-trap",
        "family": "Vocabulary mismatch",
        "query": "which players have beef with each other?",
        "headline": "One word, three meanings",
        "preamble": (
            "The classic lexical failure, planted deliberately. 'Beef' is a conflict "
            "term, a foodstuff and a verb about weight training, and this corpus contains "
            "all three senses. An inverted index cannot tell them apart because it does "
            "not know they are different: it is matching a string. This test measures how "
            "much damage a single overloaded token does to each strategy, and whether "
            "anything downstream can repair it."
        ),
        "what_good_looks_like": (
            "The eleven players who actually carry a conflict edge. Failing that, the one "
            "explainer that uses the word in its conflict sense. Any page whose top three "
            "results are brisket, Beef Wellington and a weight programme has answered a "
            "different question."
        ),
        "plan": {
            "interpretation": "Find the players who are in an interpersonal dispute with another player.",
            "keyword_query": "beef OR beefing",
            "semantic_query": "NBA players who are feuding with one another; interpersonal disputes and bad blood between players.",
            "cypher": (
                "MATCH (a:Player)-[r:CONFLICT_WITH]->(b:Player)\n"
                "RETURN DISTINCT a.id AS id, a.name AS name, b.name AS counterpart,\n"
                "       r.kind AS relation_detail\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": ["beef"],
        },
        "judgments": {
            **_players(CONFLICT_PLAYERS),
            "article:n13": ANSWERS,
            **_articles(["n01", "n02", "n03", "n04", "n05", "n06", "n07", "n43", "n35"], EVIDENCE),
            **_articles(["n08", "n09", "n10", "n11", "n14"], TOPICAL),
        },
        "traps": dict(FOOD_TRAPS),
        "commentary": {
            "hybrid": "The clearest case in the suite for fusion. The keyword leg contributes "
                      "three food articles, the vector leg contributes conflict articles, and the "
                      "graph leg contributes the actual players - and because the graph leg is "
                      "weighted 2.5x and the food articles appear in only one list, RRF sorts "
                      "them below everything the other legs agreed on. The traps are still on the "
                      "page; they are just no longer at the top of it.",
            "keyword": "Three of the four documents containing 'beef' are about food or the "
                       "gym. BM25 ranks the short lifestyle pieces above the long explainer "
                       "because shorter documents win ties: the length normalisation that "
                       "usually helps is actively hurting here.",
            "semantic": "The vector leg drops all three food articles without being told "
                        "to, which is the clearest demonstration in this suite of what "
                        "embeddings buy you. It still returns articles rather than players.",
            "graph": "CONFLICT_WITH is derived from the conflict blocks on the articles, so "
                     "this returns the answer as entities rather than as reading material. "
                     "Note that it never sees the word 'beef' at any point.",
            "hybrid_ontology": "'Beef' resolves to a class with seven subclasses, which "
                               "becomes a value filter over edge kinds. The food articles "
                               "are not members of any of them, so they cannot come back: "
                               "precision recovered by construction rather than by ranking.",
        },
    },
    {
        "id": "paraphrase",
        "family": "Vocabulary mismatch",
        "query": "who has bad blood with their old teammates?",
        "headline": "The corpus does not use your words",
        "preamble": (
            "The mirror image of the previous test. Here the query vocabulary is fine and "
            "the corpus vocabulary is different: the articles say 'rift', 'altercation', "
            "'confrontation' and 'split into camps'. The exact phrase 'bad blood' appears "
            "in the corpus once, in a documentary review about the 1980s involving none "
            "of these players. This is the question that separates term matching from "
            "meaning matching, and it carries the meanest trap in the suite."
        ),
        "what_good_looks_like": (
            "Conflicts between players who used to share a roster: Green and Durant, "
            "Green and Poole, Butler and Towns, Butler and Embiid. Not a film review."
        ),
        "plan": {
            "interpretation": "Find players in conflict with someone they used to play alongside.",
            "keyword_query": '"bad blood" OR feud OR rivalry OR animosity',
            "semantic_query": "Lingering animosity between a player and a former teammate after they stopped playing together.",
            "cypher": (
                "MATCH (a:Player)-[r0:CONFLICT_WITH]->(b:Player)-[r1:FORMER_TEAMMATE]->(a)\n"
                "RETURN DISTINCT a.id AS id, a.name AS name, b.name AS counterpart,\n"
                "       r0.kind AS relation_detail\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": ["bad blood", "former teammate"],
        },
        "judgments": {
            **_players(["draymond-green", "kevin-durant", "jordan-poole", "jimmy-butler",
                        "karl-anthony-towns", "joel-embiid"]),
            **_articles(["n01", "n02", "n04", "n06"], EVIDENCE),
            **_articles(["n05", "n13", "n43", "n34"], TOPICAL),
        },
        "traps": {
            "article:n19": "The only document in the corpus containing the literal phrase "
                           "'bad blood'. It is a documentary review about the 1980s and "
                           "mentions no player in the database. Keyword search ranks it "
                           "first; the vector leg also finds it plausible.",
        },
        "commentary": {
            "hybrid": "The graph leg supplies the pairs and the vector leg supplies corroborating "
                      "articles, so the page reads as an answer with its sources attached - which "
                      "is the actual argument for hybrid retrieval, rather than the score. The "
                      "documentary survives into the page from the keyword leg and is pushed down "
                      "by the two legs that disagree with it.",
            "hybrid_ontology": "'Bad blood' and 'former teammate' are both modelled, so the "
                               "expansion rebuilds the same two-hop cycle the pinned Cypher "
                               "already had. Identical score, arrived at from the question rather "
                               "than from a hand-written query - which is the difference that "
                               "matters once nobody is hand-writing the query.",
            "keyword": "A single exact-phrase match beats every semantically correct "
                       "document that happens to use different words. The failure is total "
                       "and it looks like a success from the outside: one confident result.",
            "semantic": "Finds the real disputes through paraphrase, which is the whole "
                        "case for dense retrieval. It also still ranks the documentary "
                        "respectably, because a film about rivalries genuinely is about "
                        "animosity. Nothing in the embedding says 'these are not our players'.",
            "graph": "'Old teammate' is a two-hop cycle over an edge that exists in no "
                     "source file. This is the only formulation that encodes the 'their own' "
                     "part of the question at all.",
        },
    },
    {
        "id": "unspoken-conflict",
        "family": "Vocabulary mismatch",
        "query": "which locker rooms have split into factions?",
        "headline": "A dispute described without any dispute vocabulary",
        "preamble": (
            "One article describes a team dividing into camps that stopped speaking, and "
            "does it without using 'beef', 'feud', 'fight', 'altercation' or 'rift'. It "
            "exists to test whether a retriever can find a conflict it has no lexical "
            "hook for. The trap alongside it describes a front office splitting over a "
            "trade decision: same word, same shape, and not a player conflict at all, "
            "which is a distinction only the structured modes hold."
        ),
        "what_good_looks_like": (
            "The Celtics locker-room article first, the three players it involves as the "
            "answer, and the front-office disagreement kept out of the top three."
        ),
        "plan": {
            "interpretation": "Find teams whose players have divided into opposed groups.",
            "keyword_query": '"locker room" AND (split OR factions OR camps OR divided)',
            "semantic_query": "A team locker room that has divided into groups of players who no longer communicate.",
            "cypher": (
                "MATCH (a:Player)-[r:CONFLICT_WITH {kind: 'LockerRoomIncident'}]->(b:Player)\n"
                "RETURN DISTINCT a.id AS id, a.name AS name, b.name AS counterpart,\n"
                "       r.kind AS relation_detail\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": ["locker room incident"],
        },
        "judgments": {
            "article:n43": ANSWERS,
            **_players(["kyrie-irving", "jaylen-brown", "jayson-tatum"]),
            **_players(["draymond-green", "jordan-poole", "jimmy-butler", "karl-anthony-towns"], EVIDENCE),
            **_articles(["n02", "n04", "n05"], EVIDENCE),
            **_articles(["n34", "n13"], TOPICAL),
        },
        "traps": {
            "article:n33": "A front office split over whether to trade a young forward. "
                           "Every surface feature matches - 'split', 'camps', a team, a "
                           "disagreement - and it is not a player conflict.",
        },
        "commentary": {
            "hybrid": "Every leg is partly right and none is decisive, which is what a genuinely "
                      "hard question looks like rather than a broken one. The front-office trap "
                      "still places, because two of the three legs match it on surface features "
                      "and the third has no opinion about articles at all.",
            "hybrid_ontology": "'Locker room incident' resolves to a conflict subclass, which "
                               "types the graph leg correctly, but the expansion also widens the "
                               "text legs with conflict synonyms - and the front-office article "
                               "matches several of them. The domain model draws the line between "
                               "an organisational split and a player split; the synonym bag then "
                               "walks straight back over it.",
            "keyword": "The target article does contain 'locker room' and 'divided', so "
                       "term matching is not hopeless here. It just cannot rank the front "
                       "office piece below it, because on the evidence it can see they are "
                       "the same document.",
            "semantic": "Handles the paraphrase and still cannot separate an organisational "
                        "disagreement from an interpersonal one. Both are 'a split within a "
                        "team', and embeddings encode topic, not participants.",
            "graph": "The conflict block on the article types this as a LockerRoomIncident "
                     "between three named players, so the distinction the text modes cannot "
                     "make was made once, at ingest, by a human.",
        },
    },
    {
        "id": "showcase-two-hop",
        "family": "Composition",
        "query": "which big men have beef with a former teammate?",
        "headline": "Three translations in one question",
        "preamble": (
            "The showcase, included here so that it is scored under the same rubric as "
            "everything else rather than asserted. It needs three independent "
            "translations at once: 'big men' to a position filter, 'beef' to a class "
            "hierarchy, and 'former teammate' to an edge computed from overlapping season "
            "ranges. No document contains the phrase 'big man' anywhere near a conflict, "
            "so there is nothing for a text index to match even in principle. It is also "
            "the hardest test to score generously: a mode can get two of the three "
            "translations right and still be wrong."
        ),
        "what_good_looks_like": (
            "Draymond Green, Joel Embiid and Karl-Anthony Towns. Four pairs, three "
            "distinct players, and nothing else."
        ),
        "plan": {
            "interpretation": "Find power forwards and centers in conflict with a player they used to play alongside.",
            "keyword_query": '("big man" OR "big men") AND (beef OR feud OR altercation)',
            "semantic_query": "A power forward or center feuding with a player he used to be teammates with.",
            "cypher": (
                "MATCH (a:Player)-[r0:CONFLICT_WITH]->(b:Player)-[r1:FORMER_TEAMMATE]->(a)\n"
                "WHERE a.position IN ['PF', 'C']\n"
                "RETURN DISTINCT a.id AS id, a.name AS name, a.position AS position,\n"
                "       b.name AS counterpart, r0.kind AS relation_detail\n"
                "LIMIT 25"
            ),
            "sql_filter": "position IN ('PF','C')",
            "ontology_terms": ["big man", "beef", "former teammate"],
        },
        "judgments": {
            **_players(["draymond-green", "joel-embiid", "karl-anthony-towns"]),
            **_articles(["n06", "n04", "n01", "n02"], EVIDENCE),
            **_articles(["n13", "n26", "n21"], TOPICAL),
        },
        "traps": {
            **FOOD_TRAPS,
            "article:n19": "'Bad blood' and 'rivalries', none of it about anyone in the database.",
        },
        "commentary": {
            "hybrid": "Scores full marks entirely on the strength of the graph leg. The keyword "
                      "leg returns nothing and the vector leg returns a weight-training article, "
                      "so this is not fusion succeeding - it is fusion failing to obstruct the "
                      "one leg that worked. Change the graph weight from 2.5 to 1.0 and this row "
                      "collapses.",
            "keyword": "The conjunction is unsatisfiable: no document contains a big-man "
                       "phrase and a conflict term. An empty result is the honest outcome "
                       "and it still scores zero, because the user wanted an answer.",
            "semantic": "Returns the closest thing it has to a big man feuding, which is a "
                        "weight-training piece about a center and a documentary about "
                        "rivalries. Confidently, in rank order, with a similarity score "
                        "attached.",
            "graph": "Given the right Cypher this is exact. The catch is that 'the right "
                     "Cypher' already contains the three translations: someone or something "
                     "had to know that 'big men' means position IN ['PF','C'] before the "
                     "query could be written at all.",
            "hybrid_ontology": "The only mode that derives all three translations from the "
                               "question itself, deterministically, with no model call. This "
                               "is the row the whole app exists to produce.",
        },
    },
    {
        "id": "threshold",
        "family": "Structured predicate",
        "query": "which snipers are on max contracts?",
        "headline": "Two thresholds wearing nicknames",
        "preamble": (
            "Neither 'sniper' nor 'max contract' is a category anyone stored. Both are "
            "numeric thresholds - fg3_pct >= 0.38 and salary_usd >= 35,000,000 - that the "
            "domain happens to have nicknames for. The word 'sniper' appears nowhere in "
            "the corpus, so there is no term to match and no paraphrase to embed. This is "
            "the test that shows text retrieval failing at something that is not hard: it "
            "is a two-predicate WHERE clause, and the only difficulty is knowing that is "
            "what was asked."
        ),
        "what_good_looks_like": (
            "The ten players who clear both thresholds. An article about the '40 percent "
            "club' is evidence, not an answer: it names five players and the correct list "
            "has ten."
        ),
        "plan": {
            "interpretation": "Find high-percentage three-point shooters earning a maximum salary.",
            "keyword_query": 'sniper OR sharpshooter OR "max contract" OR "three-point"',
            "semantic_query": "Elite three-point shooters who are paid a maximum salary.",
            "cypher": (
                "MATCH (p:Player)\n"
                "WHERE p.fg3_pct >= 0.38 AND p.salary_usd >= 35000000\n"
                "RETURN p.id AS id, p.name AS name, p.position AS position,\n"
                "       p.fg3_pct AS fg3_pct, p.salary_usd AS salary\n"
                "ORDER BY p.fg3_pct DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "fg3_pct >= 0.38 AND salary_usd >= 35000000",
            "ontology_terms": ["sniper", "max contract"],
        },
        "judgments": {
            **_players(["bradley-beal", "kyrie-irving", "karl-anthony-towns", "kevin-durant",
                        "paul-george", "jimmy-butler", "lebron-james", "stephen-curry",
                        "joel-embiid", "luka-doncic"]),
            "article:n38": EVIDENCE,
            **_articles(["n27", "n21", "n29"], TOPICAL),
        },
        "traps": {
            "article:n18": "A feature about what a shooting coach changes in a jumper. "
                           "Dense with shooting vocabulary, contains no player list and no "
                           "salary, and outranks the actual answer in both text modes.",
        },
        "commentary": {
            "hybrid": "The graph leg carries it, exactly as in the showcase. Note what the text "
                      "legs add to a page that is already correct: shooting-technique features "
                      "ranked beneath the answer, which is noise the user still has to read past.",
            "keyword": "'Sniper' has zero postings. The expression degrades to whatever the "
                       "remaining OR branches match, which is articles about shooting "
                       "technique.",
            "semantic": "Retrieves the '40 percent club' article, which is genuinely the "
                        "closest text in the corpus, and stops there. It has no way to "
                        "combine that with a salary condition, so the second half of the "
                        "question is silently dropped.",
            "graph": "A pure property filter with no traversal at all: the graph engine "
                     "acting as a slower SQL. Correct, and a fair reminder that most "
                     "'graph questions' are really just WHERE clauses.",
            "hybrid_ontology": "Both nicknames are defined classes carrying an sql_predicate, "
                               "so the expansion emits the conjunction directly. The ontology "
                               "is doing schema translation here, not reasoning.",
        },
    },
    {
        "id": "counting",
        "family": "Aggregation",
        "query": "which players have been traded more than once?",
        "headline": "Counting is not searching",
        "preamble": (
            "No document states this, because it is not a fact anyone wrote down: it is a "
            "GROUP BY over trade legs. Retrieval systems answer 'which documents are "
            "about X'; this asks 'what is true across all the records', and the two are "
            "not the same operation. The corpus contains one article about a player who "
            "was traded twice, which is exactly the sort of near-miss that makes a text "
            "result look like an answer."
        ),
        "what_good_looks_like": (
            "Five players with a count attached: Durant, Irving, Porzingis and Butler at "
            "three, George at two. A ranked list of articles is the wrong shape of output "
            "no matter what is in it."
        ),
        "plan": {
            "interpretation": "Count trades per player and keep those with more than one.",
            "keyword_query": "traded OR trade OR dealt",
            "semantic_query": "Players who have been traded multiple times during their career.",
            "cypher": (
                "MATCH (p:Player)-[:INVOLVED_IN]->(t:Trade)\n"
                "WITH p, count(t) AS moves\n"
                "WHERE moves > 1\n"
                "RETURN p.id AS id, p.name AS name, moves AS trade_count\n"
                "ORDER BY moves DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": [],
        },
        "judgments": {
            **_players(["kevin-durant", "kyrie-irving", "kristaps-porzingis",
                        "jimmy-butler", "paul-george"]),
            **_articles(["n24", "n23"], TOPICAL),
        },
        "traps": {
            "article:n30": "Titled 'He was traded twice before he turned twenty-six'. It is "
                           "the most relevant-looking document in the corpus for this "
                           "question, it is about Daniel Gafford, and the trade ledger "
                           "records exactly one trade for him. The headline is the trap.",
            "article:n18": "'Trade secrets' is an idiom. The term index cannot tell.",
        },
        "commentary": {
            "hybrid": "The counts come from the graph leg and reach the top of the page. The "
                      "twice-traded feature survives from the text legs, which means the page "
                      "shows you a player the ledger says was traded once, immediately below a "
                      "list that excludes him. That juxtaposition is more informative than either "
                      "leg alone.",
            "hybrid_ontology": "No phrase in this question resolves to a class, so the expansion "
                               "step runs, matches nothing and contributes nothing. This is the "
                               "honest majority case for an ontology: the trace is empty and the "
                               "mode degrades to plain hybrid.",
            "keyword": "'Trade' is one of the most common terms in the corpus, so IDF is low "
                       "and the ranking is close to arbitrary. The idiom article and the "
                       "twice-traded headline both outrank the transaction records.",
            "semantic": "Ranks the 'traded twice' feature highly, which is the correct topic "
                        "and the wrong player. A retriever cannot detect this class of "
                        "error; only a check against the ledger can.",
            "graph": "count() plus a HAVING-style filter. This is the answer, with the counts "
                     "shown, and it disagrees with the article - see the findings at the end.",
        },
    },
    {
        "id": "negation",
        "family": "Negation",
        "query": "players with no conflict history",
        "headline": "Embeddings cannot represent 'not'",
        "preamble": (
            "A vector is a point in a space of topics, and 'conflict' and 'no conflict' "
            "land on the same point. Asking for the absence of something is the sharpest "
            "known failure of dense retrieval, and it is not a tuning problem - the "
            "representation has no slot for negation. This corpus makes it worse on "
            "purpose: one article's entire subject is a breakup in which nobody argued, "
            "and it embeds closer to 'conflict' than most of the real fights do."
        ),
        "what_good_looks_like": (
            "Twenty-seven players who carry no conflict edge. Any article at all in the "
            "top three is a failed answer, because the question is about players and every "
            "article in that neighbourhood is about conflict."
        ),
        "plan": {
            "interpretation": "Find players who have no recorded conflict with any other player.",
            "keyword_query": "conflict OR feud OR altercation OR dispute",
            "semantic_query": "Players with a clean record and no history of disputes or altercations with other players.",
            "cypher": (
                "MATCH (p:Player)\n"
                "WHERE NOT EXISTS { MATCH (p)-[:CONFLICT_WITH]->(:Player) }\n"
                "RETURN p.id AS id, p.name AS name, p.position AS position, p.ppg AS ppg\n"
                "ORDER BY p.ppg DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": ["conflict"],
        },
        "judgments": {
            **_players([
                "luka-doncic", "giannis-antetokounmpo", "jalen-brunson", "devin-booker",
                "stephen-curry", "nikola-jokic", "anthony-edwards", "tyrese-maxey",
                "ja-morant", "anthony-davis", "desmond-bane", "damian-lillard",
                "julius-randle", "paul-george", "jaren-jackson-jr", "jamal-murray",
                "tyler-herro", "kristaps-porzingis", "bam-adebayo", "bradley-beal",
                "jonathan-kuminga", "austin-reaves", "og-anunoby", "aaron-gordon",
                "brook-lopez", "daniel-gafford", "kyle-anderson",
            ]),
        },
        "traps": {
            "article:n34": "'The quiet part of a superteam breakup' - an article whose whole "
                           "subject is the absence of open conflict. It is the closest "
                           "document in the corpus to this query and it is about two players "
                           "who both carry conflict edges.",
            "article:n13": "The explainer for the most documented feud in the corpus, "
                           "returned by a query asking for its opposite.",
        },
        "commentary": {
            "keyword": "The plan strips the negation before the index ever sees it, so this "
                       "runs as a search for conflict. Every result is the exact inverse of "
                       "what was asked, ranked confidently.",
            "semantic": "The same failure with better prose. The 'no history of disputes' "
                        "phrasing moves the query vector towards conflict documents, not away "
                        "from them. This row is the most useful thing in the report for "
                        "anyone who believes embeddings understand the question.",
            "graph": "NOT EXISTS is a first-class operator. Negation is trivial the moment "
                     "you have a closed world to negate over, and impossible before that.",
            "hybrid": "The graph leg carries the correct answer and RRF weights it 2.5x, "
                      "which is enough to hold the top of the page against two text legs "
                      "that are both wrong in the same direction. Worth noticing that this "
                      "works because one leg was right, not because fusion detected "
                      "anything: agreement between the two text legs is agreement on the "
                      "inverse of the question.",
            "hybrid_ontology": "The sharpest regression in the whole report, and the most "
                               "instructive. 'Conflict' resolves to a modelled class, so the "
                               "expansion helpfully rewrites the graph leg into a "
                               "CONFLICT_WITH traversal - which returns precisely the "
                               "players the question excludes. The ontology has no more "
                               "notion of negation than the embedding does; it just fails "
                               "with a citation attached. An expansion step that cannot see "
                               "the word 'no' will confidently invert your query.",
        },
    },
    {
        "id": "structured-group",
        "family": "Structured predicate",
        "query": "which players went to Kentucky?",
        "headline": "A structured question wearing a text costume",
        "preamble": (
            "This reads like a text question and is a SELECT with a WHERE clause. It "
            "earns its place because text search appears to succeed: there is one feature "
            "article about the Kentucky pipeline, it ranks first, and it names six "
            "players. The database holds eight. A page that looks right and is a quarter "
            "incomplete is more dangerous than one that obviously failed, and nothing in "
            "the result page distinguishes the two."
        ),
        "what_good_looks_like": (
            "Eight players. The article is worth returning as evidence, but on its own it "
            "silently drops two of them."
        ),
        "plan": {
            "interpretation": "List the players whose college is Kentucky.",
            "keyword_query": "Kentucky",
            "semantic_query": "Players who played college basketball at Kentucky.",
            "cypher": (
                "MATCH (p:Player)\n"
                "WHERE p.college = 'Kentucky'\n"
                "RETURN p.id AS id, p.name AS name, p.college AS college,\n"
                "       p.draft_year AS draft_year\n"
                "ORDER BY p.draft_year\n"
                "LIMIT 25"
            ),
            "sql_filter": "college = 'Kentucky'",
            "ontology_terms": [],
        },
        "judgments": {
            **_players(["anthony-davis", "devin-booker", "jamal-murray", "karl-anthony-towns",
                        "julius-randle", "tyrese-maxey", "bam-adebayo", "tyler-herro"]),
            "article:n31": EVIDENCE,
            "article:n42": TOPICAL,
        },
        "traps": {},
        "commentary": {
            "hybrid": "The graph leg returns all eight players and the text legs add the pipeline "
                      "article as context. This is the best possible outcome for the question - "
                      "the complete list, plus the one document that explains why the list looks "
                      "like that.",
            "hybrid_ontology": "Nothing here is a modelled concept - 'Kentucky' is a value, not a "
                               "class - so the expansion matches nothing and this is plain "
                               "hybrid. An ontology models vocabulary, not data.",
            "keyword": "'Kentucky' is a rare term, so this is a clean retrieval - of one "
                       "document. The document is not the answer; it is a summary of part of "
                       "the answer, and nothing marks the difference.",
            "semantic": "Finds the same article plus adjacent college and draft features. "
                        "Broader, no more complete.",
            "graph": "Eight rows, ordered by draft year. The article's six names are a "
                     "subset of them. This is the clearest coverage gap in the suite.",
        },
    },
    {
        "id": "pick-ledger",
        "family": "Aggregation",
        "query": "who owes the most unprotected first round picks?",
        "headline": "The ledger lives in the edges, and the article rounds it",
        "preamble": (
            "Draft picks are the one part of this corpus that is genuinely an asset "
            "ledger: 29 picks, each with an origin team, a destination and a protection "
            "string. There is a summary article on the same subject, so semantic search "
            "looks like it has succeeded. It has not - the article frames two deals as "
            "four picks each, and counting the rows gives four and three. This test is "
            "here for the case where the text is not a trap, not wrong exactly, and still "
            "not the answer."
        ),
        "what_good_looks_like": (
            "Phoenix at four, the Clippers and Minnesota at three. Teams, with counts."
        ),
        "plan": {
            "interpretation": "Count unprotected first-round picks by the team that gave them up.",
            "keyword_query": '"unprotected" AND ("first round" OR "first-round" OR picks)',
            "semantic_query": "Which teams have traded away the most unprotected first round draft picks.",
            "cypher": (
                "MATCH (p:Player)-[:INVOLVED_IN]->(t:Trade)-[:TRADE_FROM]->(team:Team)\n"
                "RETURN team.id AS id, team.name AS name, count(t) AS trades_out\n"
                "ORDER BY trades_out DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": [],
            "plan_note": (
                "Picks are rows on trade_picks, not nodes in the graph. The best available "
                "Cypher can therefore reach the trades and the teams but not the pick "
                "counts, and this test scores it on that rather than inventing a query the "
                "schema does not support."
            ),
        },
        "judgments": {
            "team:PHX": ANSWERS,
            "team:LAC": ANSWERS,
            "team:MIN": ANSWERS,
            "article:n23": EVIDENCE,
            **_articles(["n24", "n40"], TOPICAL),
        },
        "traps": {},
        "commentary": {
            "hybrid": "Fusion cannot manufacture a leg that works. The graph leg counts trades "
                      "rather than picks, both text legs return the summary article, and the "
                      "fused page is the summary article with transaction pieces beneath it. "
                      "Three retrievers, one schema gap, no answer.",
            "hybrid_ontology": "No class matches, so this is plain hybrid at higher cost. The "
                               "pattern to notice across the suite: where the ontology "
                               "contributes nothing it is not neutral, it is neutral plus "
                               "latency.",
            "keyword": "'Unprotected' is rare enough that the summary article comes back "
                       "first and almost alone. One document, no counts, and a framing the "
                       "ledger does not support.",
            "semantic": "The same article, surrounded by other transaction pieces. The "
                        "apparent success is the finding: a plausible top result with no way "
                        "to check it.",
            "graph": "This is the honest failure in the suite. Picks were modelled as rows "
                     "on a relational table rather than as edges, so the graph cannot count "
                     "them, and the mode is limited by the schema rather than by the "
                     "technique. Worth leaving in the report rather than quietly modelling "
                     "around.",
        },
    },
    {
        "id": "two-defined-classes",
        "family": "Composition",
        "query": "rim protectors who shoot threes",
        "headline": "An intersection of two nicknames, answer size one",
        "preamble": (
            "Both halves are defined classes: rim protector is bpg >= 1.5, and the "
            "shooting threshold is fg3_pct >= 0.38. Seven players clear the first, eleven "
            "clear the second, and exactly one clears both. A correct answer here is a "
            "single name, which makes it the sharpest precision test in the suite: there "
            "is no partial credit to hide in. The corpus also contains an article titled "
            "'Rim protection is still the cheapest defense you can buy', which is on "
            "topic, well written and completely useless for this."
        ),
        "what_good_looks_like": (
            "Joel Embiid. One row. Anything longer is wrong in a way that is hard to see."
        ),
        "plan": {
            "interpretation": "Find players who both block shots at a high rate and shoot threes well.",
            "keyword_query": '"rim protector" OR "shot blocker" OR "rim protection"',
            "semantic_query": "A shot-blocking big man who also shoots three-pointers at a high percentage.",
            "cypher": (
                "MATCH (p:Player)\n"
                "WHERE p.bpg >= 1.5 AND p.fg3_pct >= 0.38\n"
                "RETURN p.id AS id, p.name AS name, p.position AS position,\n"
                "       p.bpg AS bpg, p.fg3_pct AS fg3_pct\n"
                "ORDER BY p.bpg DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "bpg >= 1.5 AND fg3_pct >= 0.38",
            "ontology_terms": ["rim protector", "sniper"],
        },
        "judgments": {
            "player:joel-embiid": ANSWERS,
            **_players(["kristaps-porzingis", "brook-lopez"], EVIDENCE),
            **_players(["rudy-gobert", "anthony-davis", "jaren-jackson-jr", "daniel-gafford"], TOPICAL),
            "article:n21": TOPICAL,
            "article:n29": TOPICAL,
        },
        "traps": {
            "article:n22": "'Rim protection is still the cheapest defense you can buy'. It "
                           "names three rim protectors, two of whom shoot no threes at all. "
                           "Top result in both text modes, and it will mislead you.",
        },
        "commentary": {
            "hybrid": "Loses half a point to pure graph search, and the reason is instructive: "
                      "the graph leg returns exactly one correct row, and the text legs then fill "
                      "the remaining seven slots of the page with articles about the archetype. A "
                      "correct answer of size one is very hard for a ranked-list interface to "
                      "present honestly.",
            "keyword": "Matches the phrase in the one article that uses it, and stops. The "
                       "second half of the question contributes nothing, because it was never "
                       "expressible as a term.",
            "semantic": "Retrieves the stretch-five and seven-footer features, which are "
                        "about exactly this archetype and name the wrong players. Archetype "
                        "similarity is not threshold satisfaction.",
            "graph": "Two comparisons and an AND. The answer is one row because the data says "
                     "one row.",
            "hybrid_ontology": "Both classes carry an sql_predicate, so the intersection is "
                               "assembled from the ontology rather than guessed. Watch the "
                               "asymmetry this exposes: the expansion widens the text legs "
                               "with synonyms at the same time, which pulls the rim-protection "
                               "article back in through the fusion.",
        },
    },
    {
        "id": "headline-lie",
        "family": "Provenance",
        "query": "which players are former teammates?",
        "headline": "When the document asserts what the data denies",
        "preamble": (
            "One article is titled 'Two former teammates meet in the conference finals'. "
            "The two players named in it never shared a roster in this dataset. Every "
            "text mode believes the headline, because believing the document is the only "
            "thing a text mode does. The graph derives the relationship from overlapping "
            "season ranges and disagrees. This test is in the suite because it is the "
            "cheapest illustration of what grounding actually means: not better ranking, "
            "but a second source that can contradict the first."
        ),
        "what_good_looks_like": (
            "Real pairs - Irving and James at Cleveland, Durant and Curry at Golden "
            "State, Poole and Green - and the conference-finals article kept out."
        ),
        "plan": {
            "interpretation": "Find pairs of players who used to play for the same team and no longer do.",
            "keyword_query": '"former teammate" OR "former teammates" OR "used to play with"',
            "semantic_query": "Two players who used to be teammates and now play for different franchises.",
            "cypher": (
                "MATCH (a:Player)-[r:FORMER_TEAMMATE]->(b:Player)\n"
                "RETURN DISTINCT a.id AS id, a.name AS name, b.name AS counterpart,\n"
                "       r.team_id AS via_team, r.to_season AS last_season\n"
                "ORDER BY last_season DESC\n"
                "LIMIT 25"
            ),
            "sql_filter": "",
            "ontology_terms": ["former teammate"],
        },
        "judgments": {
            # All 23 players carrying at least one FORMER_TEAMMATE edge. The edge is
            # derived from overlapping stint ranges, so this list exists in no file.
            **_players([
                "anthony-davis", "anthony-edwards", "bradley-beal", "brook-lopez",
                "daniel-gafford", "draymond-green", "jalen-brunson", "jaylen-brown",
                "jayson-tatum", "jimmy-butler", "joel-embiid", "jonathan-kuminga",
                "jordan-poole", "julius-randle", "karl-anthony-towns", "kevin-durant",
                "kristaps-porzingis", "kyle-anderson", "kyrie-irving", "lebron-james",
                "luka-doncic", "rudy-gobert", "stephen-curry",
            ]),
            **_articles(["n34", "n02"], EVIDENCE),
            **_articles(["n01", "n42"], TOPICAL),
        },
        "traps": {
            "article:n44": "'Two former teammates meet in the conference finals'. Lillard "
                           "and Durant. They have never appeared on the same roster in this "
                           "dataset - Lillard carries no FORMER_TEAMMATE edge at all. The "
                           "phrase is in the title, so every text mode ranks it first.",
        },
        "commentary": {
            "hybrid": "The graph leg's real pairs outrank the false headline, so fusion produces "
                      "the right page - but look at why. It is not that anything detected the "
                      "contradiction; it is that twenty-three correct pairs from a 2.5-weighted "
                      "leg outnumber one article. Grounding here is a voting outcome, not a "
                      "check.",
            "hybrid_ontology": "'Former teammate' resolves to a derived property, so the "
                               "expansion reconstructs the traversal from the question. Same "
                               "result as plain hybrid, because the pinned plan already contained "
                               "the correct Cypher - which is precisely the comparison this suite "
                               "cannot make fairly.",
            "keyword": "Exact phrase, in the title, with title weighting at 2.0. This is "
                       "keyword search working perfectly and returning a false statement.",
            "semantic": "Ranks the same article highly for the same reason plus paraphrase. "
                        "Neither text mode has anything to check the claim against.",
            "graph": "FORMER_TEAMMATE is computed from overlapping season ranges in the "
                     "stints table. The pair in the headline produces no edge, so the graph "
                     "cannot return them even if asked to.",
        },
    },
]

FAMILIES: list[dict[str, str]] = [
    {
        "id": "Lexical precision",
        "blurb": "Exact terms, spelled the way the corpus spells them. The control group.",
    },
    {
        "id": "Vocabulary mismatch",
        "blurb": "The question and the corpus use different words for the same thing, or "
                 "the same word for different things.",
    },
    {
        "id": "Structured predicate",
        "blurb": "A threshold or a field comparison wearing a nickname.",
    },
    {
        "id": "Aggregation",
        "blurb": "The answer is a count across records, which no single document states.",
    },
    {
        "id": "Negation",
        "blurb": "The absence of something. The known hard failure of dense retrieval.",
    },
    {
        "id": "Composition",
        "blurb": "Two or three translations that all have to land for the answer to be right.",
    },
    {
        "id": "Provenance",
        "blurb": "A document asserts something the structured data contradicts.",
    },
]
