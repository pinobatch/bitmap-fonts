#!/usr/bin/env python3
from collections import defaultdict
import textwrap

def get_wordsbyscore(wordlist, lettervalues):
    wordsbyscore = defaultdict(set)
    maxscore = 0
    for word in wordlist:
        word = word.strip()
        wordchars = set(word)
        score = sum(row[1] for row in lettervalues if row[0] in wordchars)
        wordsbyscore[score].add(word)
    return wordsbyscore


# how distinctive each letter's insular form is
# (not counting long r or long s)
insularvalues = [
    ('a', 1), ('d', 2), ('f', 2), ('g', 2),
    ('l', 1), ('r', 1), ('t', 2), ('v', 1),
]
uv_values = [
    ('u', 1), ('v', 1),
]
valueslists = [
    ('Insular', insularvalues),
    ('U and V', uv_values),
]

with open("/usr/share/dict/words") as infp:
    allwords = list(infp)
for lsname, lettervalues in valueslists:
    wbs = get_wordsbyscore(allwords, lettervalues)
    wbs = sorted(wbs.items(), reverse=True)
    for rowid, (score, scorewords) in enumerate(wbs):
        if rowid > 0 and len(scorewords) > 100: continue
        words_pl = "words" if len(scorewords) > 1 else "word"
        scorewords = sorted(scorewords, key=len)
        print("%s score %d: %d %s" % (lsname, score, len(scorewords), words_pl))
        print(textwrap.fill(", ".join(scorewords[:100])))
